"""
룰 엔진 — 모든 보험금 판정 룰을 순서대로 실행.

실행 순서:
  1. COM (공통 선행) — FAIL 시 즉시 종료 → 부지급
     1-1. COM-003 FAIL 시 FRD-003 반복청구 탐지 추가 실행
  2. DOC (서류 완비) — FAIL 시 즉시 종료 → 보류
     ※ claimed_coverage_types 기준으로 필요 서류 판단
  3. 담보별 룰 (IND / SIL / SUR)
     ※ claimed_coverage_types 에 포함된 담보만 실행
  4. FRD-007 (비급여 비중) — FLAGGED 시 플래그만 부여, 처리 계속
  5. FIN — 최종 집계 → ClaimDecision 반환

설계 원칙:
  - 각 룰 함수는 순수 함수. 외부 상태를 변경하지 않는다.
  - 판단 데이터는 data_loader 를 통해서만 접근한다.
  - None 값 처리: 필수 정보 부재 → FAIL 또는 SKIP 으로 명시적 처리.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Optional

from src.schemas import ClaimContext, ClaimDecision, RuleResult
from src.utils.data_loader import (
    get_contract,
    get_claims_history,
    get_coverages_by_type,
    check_kcd_exclusion,
    check_kcd_conditional_exclusion,
    get_surgery_class,
    get_4gen_noncover_category,
    get_billing_codes,
    get_surgery_code_by_name,
    get_surgery_codes_by_kcd,
    get_rule_clause,
)
from config.settings import NON_COVERED_RATIO_THRESHOLD, PARSE_CONFIDENCE_THRESHOLD


# ══════════════════════════════════════════════════════════════════
# 약관 근거 자동 삽입 — 모든 RuleResult.evidence에 조항 정보 부여
# ══════════════════════════════════════════════════════════════════

def _enrich_evidence(result: RuleResult) -> RuleResult:
    """RuleResult.evidence에 약관 조항 근거(policy_clause, clause_title,
    clause_text, legal_basis)를 자동 삽입한다.
    이미 존재하는 키는 덮어쓰지 않는다(setdefault)."""
    clause = get_rule_clause(result.rule_id)
    if clause:
        result.evidence.setdefault("policy_clause", clause["policy_clause"])
        result.evidence.setdefault("clause_title", clause["clause_title"])
        result.evidence.setdefault("clause_text", clause["clause_text"])
        result.evidence.setdefault("legal_basis", clause["legal_basis"])
    return result


def _enrich_applied(applied: list[RuleResult]) -> list[RuleResult]:
    """applied 리스트의 모든 RuleResult에 약관 근거를 일괄 삽입."""
    for r in applied:
        _enrich_evidence(r)
    return applied


def _parse_date(s: Optional[str]) -> Optional[date]:
    """날짜 문자열 파싱. 실패 시 None 반환 (예외 발생 안 함)."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


# ══════════════════════════════════════════════════════════════════
# COM 룰 — 공통 선행 검사
# ══════════════════════════════════════════════════════════════════

def rule_com_001(ctx: ClaimContext, contract: dict) -> RuleResult:
    """COM-001: 계약 유효성 확인 (계약 상태 + 보험료 납입 상태)."""
    status  = contract.get("status", "")
    premium = contract.get("premium_status", "")

    if status != "유효":
        return RuleResult(
            "COM-001", "FAIL",
            f"계약 상태 이상: '{status}' — 유효 계약이 아닙니다.",
            evidence={"contract_status": status, "premium_status": premium},
        )
    if premium not in ("정상", "납입유예"):
        return RuleResult(
            "COM-001", "FAIL",
            f"납입 상태 이상: '{premium}' — 보험료 납입이 정상적이지 않습니다.",
            evidence={"contract_status": status, "premium_status": premium},
        )
    return RuleResult(
        "COM-001", "PASS", "계약 유효, 납입 정상",
        evidence={"contract_status": status, "premium_status": premium},
    )


def rule_com_002(ctx: ClaimContext, contract: dict) -> RuleResult:
    """
    COM-002: 면책기간 확인.
    판단 기준일: 사고 발생일(accident_date). 파싱 실패 시 claim_date 로 대체.
    계약의 각 담보별 waiting_period_days 중 하나라도 면책기간 이내이면 FAIL.
    """
    accident = _parse_date(ctx.accident_date)
    if accident is None:
        accident = _parse_date(ctx.claim_date)
    if accident is None:
        return RuleResult(
            "COM-002", "FAIL",
            "사고일 정보를 확인할 수 없습니다. 수동 검토가 필요합니다.",
            evidence={"accident_date_raw": ctx.accident_date},
        )

    contract_dt = _parse_date(contract.get("contract_date"))
    if contract_dt is None:
        return RuleResult("COM-002", "FAIL", "계약일 정보 오류.")

    claimed = set(ctx.claimed_coverage_types) if ctx.claimed_coverage_types else None

    for cov_code, cov in contract.get("coverages", {}).items():
        if claimed and cov.get("type") not in claimed:
            continue

        wp_days = cov.get("waiting_period_days", 0)
        if wp_days == 0:
            continue

        wp_end = contract_dt + timedelta(days=wp_days)
        if accident <= wp_end:
            return RuleResult(
                "COM-002", "FAIL",
                (
                    f"면책기간 이내 청구 — 담보: {cov.get('coverage_name', cov_code)} | "
                    f"계약일: {contract_dt.isoformat()} | "
                    f"면책 종료일: {wp_end.isoformat()} | "
                    f"사고일: {accident.isoformat()}"
                ),
                evidence={
                    "coverage_code": cov_code,
                    "contract_date": contract_dt.isoformat(),
                    "waiting_period_days": wp_days,
                    "waiting_period_end": wp_end.isoformat(),
                    "accident_date": accident.isoformat(),
                },
            )

    return RuleResult(
        "COM-002", "PASS",
        f"면책기간 경과 확인 — 사고일: {accident.isoformat()}",
        evidence={"accident_date": accident.isoformat()},
    )


def rule_com_003(ctx: ClaimContext) -> RuleResult:
    """COM-003: KCD 코드 기반 면책사유 확인 (kcd_exclusion_map.json 절대 면책 매칭)."""
    if ctx.kcd_code == "UNKNOWN":
        return RuleResult(
            "COM-003", "FAIL",
            "주 상병코드(KCD)를 확인할 수 없습니다. 서류 재확인이 필요합니다.",
            evidence={"kcd_code": ctx.kcd_code},
        )

    exclusion = check_kcd_exclusion(ctx.kcd_code)
    if exclusion:
        return RuleResult(
            "COM-003", "FAIL",
            f"{exclusion['denial_message']} (KCD: {ctx.kcd_code})",
            evidence={
                "kcd_code": ctx.kcd_code,
                "exclusion_category": exclusion["category"],
                "policy_clause": exclusion["policy_clause"],
            },
        )

    return RuleResult(
        "COM-003", "PASS",
        f"면책사유 해당 없음 — KCD: {ctx.kcd_code} ({ctx.diagnosis})",
        evidence={"kcd_code": ctx.kcd_code},
    )


def rule_com_004(ctx: ClaimContext, contract: dict) -> RuleResult:
    """
    COM-004: 중복·단기가입·반복 청구 징후 확인.
    - 동일 청구건 중복: past_claims에 동일 claim_id 있으면 FLAGGED
    - 단기 가입 후 청구: (청구일 - 계약일) <= 30일 이고 IND/SUR 청구 시 FLAGGED
    - 반복 청구: 최근 1년 동일·유사 청구 >= 3회 FLAGGED
    """
    history = get_claims_history(ctx.policy_no)
    contract_dt = _parse_date(contract.get("contract_date"))
    claim_dt = _parse_date(ctx.claim_date)
    claimed = set(ctx.claimed_coverage_types) if ctx.claimed_coverage_types else set()
    reasons = []

    if history and claim_dt and contract_dt:
        past = history.get("past_claims", [])

        claim_ids = [c.get("claim_id") for c in past if c.get("claim_id")]
        if ctx.claim_id in claim_ids:
            reasons.append("동일 청구건이 이력에 이미 존재 — 중복 청구 의심")

        days_since_contract = (claim_dt - contract_dt).days
        if days_since_contract <= 30 and (claimed & {"IND", "SUR"}):
            reasons.append(
                f"가입 후 {days_since_contract}일 만에 입원/수술 청구 — 단기 가입 후 청구 (담당자 확인 권장)"
            )

        one_year_ago = claim_dt - timedelta(days=365) if claim_dt else None
        if one_year_ago:
            recent_count = sum(
                1 for c in past
                if _parse_date(c.get("claim_date")) and _parse_date(c.get("claim_date")) >= one_year_ago
            )
            if recent_count >= 3:
                reasons.append(f"최근 1년 청구 {recent_count}회 — 반복 청구 검토 권장")

    if reasons:
        return RuleResult(
            "COM-004", "FLAGGED",
            "; ".join(reasons),
            evidence={"reasons": reasons},
        )
    return RuleResult(
        "COM-004", "PASS",
        "중복·단기가입·반복 청구 징후 없음",
        evidence={},
    )


def rule_frd_003(ctx: ClaimContext, denial_kcd: str) -> Optional[RuleResult]:
    """
    FRD-003: 동일 면책사유 반복 청구 탐지.
    COM-003 FAIL 후 보조적으로 실행. 청구 이력에서 동일 KCD 계열 부지급 이력 확인.
    """
    history = get_claims_history(ctx.policy_no)
    if not history:
        return None

    kcd_prefix = denial_kcd[:3]
    repeat_denials = [
        c for c in history.get("past_claims", [])
        if c.get("decision") == "부지급"
        and c.get("kcd_code", "").startswith(kcd_prefix)
    ]
    existing_flags = [
        f for f in history.get("fraud_flags", [])
        if f.get("rule_id") == "FRD-003"
    ]
    frd_risk = history.get("frd_risk_level", "LOW")

    if repeat_denials or existing_flags or frd_risk == "HIGH":
        count = len(repeat_denials)
        return RuleResult(
            "FRD-003", "FLAGGED",
            (
                f"동일 면책사유({denial_kcd}) 반복 청구 이력 {count}건 — "
                f"사기 조사팀 통보 검토 필요. (FRD 위험도: {frd_risk})"
            ),
            evidence={
                "denial_kcd": denial_kcd,
                "kcd_prefix_checked": kcd_prefix,
                "repeat_denial_count": count,
                "existing_fraud_flags": len(existing_flags),
                "frd_risk_level": frd_risk,
            },
        )
    return None


# ══════════════════════════════════════════════════════════════════
# DOC 룰 — 서류 완비 확인
# ══════════════════════════════════════════════════════════════════

# 담보 유형별 필수 서류 정의
_REQUIRED_DOCS: dict[str, list[str]] = {
    "IND": ["진단서", "입원확인서"],
    "SIL": ["진단서", "진료비영수증", "진료비세부내역서"],
    "SUR": ["진단서", "수술확인서", "진료비영수증"],
}


def rule_doc_check(ctx: ClaimContext, contract: dict) -> RuleResult:
    """
    DOC-CHECK: 청구 담보에 필요한 서류 완비 여부 확인.

    판단 기준:
      - 보험금청구서는 모든 청구에 필수 (기본 요건)
      - claimed_coverage_types 가 있으면 청구한 담보 기준으로 필수 서류 결정
        단, 계약에 가입되지 않은 담보는 제외 (오청구 방어)
      - 비어 있으면 계약에 가입된 모든 담보 기준 (보수적 처리)
    """
    submitted = set(ctx.submitted_doc_types)

    # 보험금청구서는 모든 청구의 기본 필수 서류
    if "보험금청구서" not in submitted:
        return RuleResult(
            "DOC-CHECK", "FAIL",
            "보험금청구서 미제출 — 청구 접수의 필수 서류입니다.",
            evidence={
                "required_base": ["보험금청구서"],
                "submitted": sorted(submitted),
                "missing": ["보험금청구서"],
            },
        )

    # 계약에 실제 가입된 담보 유형 목록
    subscribed_types = {ct for ct in ("IND", "SIL", "SUR")
                        if get_coverages_by_type(ctx.policy_no, ct)}

    # 어떤 담보 유형을 기준으로 서류를 확인할지 결정
    if ctx.claimed_coverage_types:
        # 청구 담보 ∩ 가입 담보 — 미가입 담보 청구는 서류 요구 대상에서 제외
        check_types = [ct for ct in ctx.claimed_coverage_types if ct in subscribed_types]
        if not check_types:
            check_types = list(subscribed_types)
    else:
        check_types = list(subscribed_types)

    needed: set[str] = set()
    for cov_type in check_types:
        if cov_type in _REQUIRED_DOCS:
            needed.update(_REQUIRED_DOCS[cov_type])

    missing = sorted(needed - submitted)

    if missing:
        return RuleResult(
            "DOC-CHECK", "FAIL",
            f"필수 서류 미제출: {', '.join(missing)}",
            evidence={
                "check_basis": check_types,
                "required": sorted(needed),
                "submitted": sorted(submitted),
                "missing": missing,
            },
        )
    return RuleResult(
        "DOC-CHECK", "PASS",
        f"서류 완비 ({len(submitted)}건 제출)",
        evidence={"check_basis": check_types, "submitted": sorted(submitted)},
    )


# ══════════════════════════════════════════════════════════════════
# 담보별 룰 — 보험금 계산
# ══════════════════════════════════════════════════════════════════

def _classify_claim_nature(kcd_code: str) -> str:
    """
    KCD 코드로 질병/재해 분류.
    V~Y 계열(외인 손상 및 중독) → 재해, 그 외 → 질병.
    """
    if kcd_code and kcd_code[0].upper() in ('V', 'W', 'X', 'Y'):
        return "재해"
    return "질병"


def _payable_inpatient_days(hospital_days: int, claim_nature: str) -> int:
    """
    입원일당 지급 대상 일수 산정 (면책일수 차감).
    질병: 4일 면책 → MAX(0, hospital_days - 4)
    재해: 1일 면책 → MAX(0, hospital_days - 1)
    """
    if claim_nature == "재해":
        return max(0, hospital_days - 1)
    return max(0, hospital_days - 4)


def rule_ind(ctx: ClaimContext) -> RuleResult:
    """
    IND-001: 입원일당 계산.

    Phase 2: 면책일수 적용 — 질병 4일/재해 1일 차감 후 지급일수 산정.
    복수 담보: 질병 vs 재해 담보를 KCD로 판별, coverage_name에 '질병'/'재해' 포함 여부로 구분.
    """
    coverages = get_coverages_by_type(ctx.policy_no, "IND")
    if not coverages:
        return RuleResult("IND-001", "SKIP", "입원일당 미가입")
    if ctx.hospital_days is None:
        return RuleResult("IND-001", "FAIL", "입원일수 정보를 확인할 수 없습니다.")
    if ctx.hospital_days == 0:
        return RuleResult("IND-001", "FAIL", "입원일수 0일 — 입원일당 지급 대상이 아닙니다.")

    claim_nature = _classify_claim_nature(ctx.kcd_code)
    payable_days = _payable_inpatient_days(ctx.hospital_days, claim_nature)

    if payable_days == 0:
        wait_days = 4 if claim_nature == "질병" else 1
        return RuleResult(
            "IND-001", "FAIL",
            f"입원 {ctx.hospital_days}일 — 면책일수({claim_nature} {wait_days}일) 차감 후 지급 대상 0일.",
            evidence={
                "claim_nature": claim_nature,
                "hospital_days_claimed": ctx.hospital_days,
                "waiting_days": wait_days,
                "payable_days": 0,
            },
        )

    matched = [c for c in coverages if claim_nature in c.get("coverage_name", "")]
    applicable = matched if matched else coverages

    total_amount = 0
    cov_breakdown = []
    for cov in applicable:
        max_days = cov.get("max_days_per_claim", 180)
        days = min(payable_days, max_days)
        daily = cov["daily_benefit"]
        amt = days * daily
        total_amount += amt
        wait_days = 4 if claim_nature == "질병" else 1
        cov_breakdown.append({
            "coverage_code": cov["coverage_code"],
            "coverage_name": cov["coverage_name"],
            "hospital_days_claimed": ctx.hospital_days,
            "waiting_days": wait_days,
            "payable_days": days,
            "daily_benefit": daily,
            "benefit_amount": amt,
            "formula": f"({ctx.hospital_days}일 - 면책{wait_days}일) × {daily:,}원 = {days}일 × {daily:,}원",
        })

    summary_formula = " + ".join(
        f"{b['payable_days']}일×{b['daily_benefit']:,}" for b in cov_breakdown
    )
    return RuleResult(
        "IND-001", "PASS",
        f"입원일당({claim_nature}) — 입원 {ctx.hospital_days}일, 면책 차감 후 {payable_days}일 지급 = {total_amount:,}원",
        value=float(total_amount),
        evidence={
            "claim_nature": claim_nature,
            "kcd_code": ctx.kcd_code,
            "hospital_days_claimed": ctx.hospital_days,
            "payable_days": payable_days,
            "coverages_applied": cov_breakdown,
            "benefit_amount": total_amount,
            "formula": summary_formula,
        },
    )


def rule_sil(ctx: ClaimContext) -> RuleResult:
    """
    SIL-001: 실손의료비 계산 (세대별 자기부담금 적용).

    세대별 공식:
      1세대: (급여 + 비급여) × 100%
      2세대: 급여 × 90% + 비급여 × 80%
      3세대: (급여 + 비급여) × 80%, 최소 공제 10,000원
      4세대: 급여 × 80% + 비급여 × 70%, 최소 공제 10,000원
              ※ 비급여 특약 3대 항목(도수치료·주사료·MRI) 연간 한도 별도 적용

    복수 담보 처리:
      - 입원(hospital_days > 0) → coverage_name에 '입원' 포함 담보 우선 선택
      - 통원(hospital_days == 0 또는 None) → '통원' 포함 담보 우선 선택
      - 매칭 없으면 첫 번째 담보 사용 (폴백)
    """
    coverages = get_coverages_by_type(ctx.policy_no, "SIL")
    if not coverages:
        return RuleResult("SIL-001", "SKIP", "실손의료비 미가입")
    if ctx.covered_self_pay is None:
        return RuleResult("SIL-001", "FAIL", "급여 본인부담금 정보를 확인할 수 없습니다.")

    # 입원 vs 통원 담보 선택
    is_inpatient = ctx.hospital_days is not None and ctx.hospital_days > 0
    care_type = "입원" if is_inpatient else "통원"
    matched = [c for c in coverages if care_type in c.get("coverage_name", "")]
    cov = matched[0] if matched else coverages[0]

    gen           = cov.get("silson_generation", 3)
    copay_covered = cov.get("copay_rate_covered",    0.20)
    copay_non     = cov.get("copay_rate_non_covered", 0.20)
    min_copay     = cov.get("min_copay", 10000)
    non_covered_amt = ctx.non_covered_amount or 0

    non_covered_capped = non_covered_amt
    non_covered_cap_note = ""
    sil_4gen_cap_details: list[str] = []

    if gen == 4 and non_covered_amt > 0 and ctx.billing_items:
        db = get_billing_codes()
        noncov = [
            b for b in ctx.billing_items
            if b.get("is_noncovered") and (b.get("amount") or 0) >= 0
        ]
        regulated_raw_by_key: dict[str, int] = {}
        for b in noncov:
            cat = get_4gen_noncover_category(b.get("item_code", ""))
            if not cat:
                continue
            ck = cat.get("_category_key") or "?"
            regulated_raw_by_key[ck] = regulated_raw_by_key.get(ck, 0) + int(b["amount"])

        regulated_capped_sum = 0
        for ck, raw in regulated_raw_by_key.items():
            cat = db.get("noncover_categories", {}).get(ck)
            if not cat:
                regulated_capped_sum += raw
                continue
            lim = int(cat.get("annual_limit_4gen") or 9_999_999_999)
            cap = min(raw, lim)
            regulated_capped_sum += cap
            if raw > lim:
                sil_4gen_cap_details.append(
                    f"{ck}: 청구 {raw:,}원 → 4세대 연간한도 {lim:,}원 반영 {cap:,}원"
                )
        regulated_raw_total = sum(regulated_raw_by_key.values())
        other_nc = max(0, non_covered_amt - regulated_raw_total)
        non_covered_capped = regulated_capped_sum + other_nc
        if sil_4gen_cap_details:
            non_covered_cap_note = " | " + "; ".join(sil_4gen_cap_details)
        elif regulated_raw_total > 0:
            non_covered_cap_note = " (세부내역서 기준 4세대 비급여 항목별 한도 반영)"
    elif gen == 4 and non_covered_amt > 0:
        non_covered_cap_note = " (진료비세부내역서 미파싱 — 비급여 총액 기준, 항목별 한도 미적용)"

    # 자기부담금 계산
    copay_applied = max(
        int(ctx.covered_self_pay * copay_covered + non_covered_capped * copay_non),
        min_copay,
    )
    amount = ctx.covered_self_pay + non_covered_capped - copay_applied

    if gen <= 2:
        formula = (
            f"급여 {ctx.covered_self_pay:,}×{(1-copay_covered)*100:.0f}% + "
            f"비급여 {non_covered_capped:,}×{(1-copay_non)*100:.0f}% = {amount:,}원"
        )
    else:
        formula = (
            f"(급여 {ctx.covered_self_pay:,} × {(1-copay_covered)*100:.0f}%) + "
            f"(비급여 {non_covered_capped:,} × {(1-copay_non)*100:.0f}%) = {amount:,}원"
            + non_covered_cap_note
        )

    return RuleResult(
        "SIL-001", "PASS",
        f"실손 {gen}세대 ({care_type}) — {formula}",
        value=float(amount),
        evidence={
            "coverage_code": cov["coverage_code"],
            "coverage_name": cov["coverage_name"],
            "silson_generation": gen,
            "care_type": care_type,
            "covered_self_pay": ctx.covered_self_pay,
            "non_covered_amount": non_covered_amt,
            "non_covered_capped": non_covered_capped,
            "sil_4gen_cap_details": sil_4gen_cap_details,
            "copay_rate_covered": copay_covered,
            "copay_rate_non_covered": copay_non,
            "copay_applied": copay_applied,
            "benefit_amount": amount,
            "formula": formula,
        },
    )


def rule_sur(ctx: ClaimContext) -> RuleResult:
    """
    SUR-001: 수술비 정액 지급.
    수술코드 우선 → 수술명 → KCD 기반 후보(분류표) 순으로 매핑.
    KCD 후보만으로 매칭 시 담당자 검토 플래그(증거에 inferred 표시).
    """
    coverages = get_coverages_by_type(ctx.policy_no, "SUR")
    if not coverages:
        return RuleResult("SUR-001", "SKIP", "수술비 미가입")

    if not ctx.surgery_code and not ctx.surgery_name:
        return RuleResult("SUR-001", "SKIP", "수술 없음 (수술코드/수술명 미확인)")

    surgery_info = None
    inferred_from_kcd = False
    kcd_candidates: list[str] = []

    if ctx.surgery_code:
        surgery_info = get_surgery_class(surgery_code=ctx.surgery_code)
    if not surgery_info and ctx.surgery_name:
        mapped = get_surgery_code_by_name(ctx.surgery_name)
        if mapped:
            surgery_info = get_surgery_class(surgery_code=mapped)
        if not surgery_info:
            surgery_info = get_surgery_class(surgery_name=ctx.surgery_name)

    if not surgery_info and ctx.kcd_code and ctx.kcd_code != "UNKNOWN":
        kcd_candidates = get_surgery_codes_by_kcd(ctx.kcd_code)
        for scode in kcd_candidates:
            surgery_info = get_surgery_class(surgery_code=scode)
            if surgery_info:
                inferred_from_kcd = True
                break

    if not surgery_info:
        return RuleResult(
            "SUR-001", "FAIL",
            f"수술 분류표에서 해당 수술을 찾을 수 없습니다. "
            f"(코드: {ctx.surgery_code}, 수술명: {ctx.surgery_name}, KCD후보: {kcd_candidates}) — 수동 분류 필요.",
            evidence={
                "surgery_code": ctx.surgery_code,
                "surgery_name": ctx.surgery_name,
                "kcd_candidates": kcd_candidates,
            },
        )

    cov = coverages[0]
    surgery_class = surgery_info["class"]
    max_class     = cov.get("max_class_covered", 5)
    benefit_map   = cov.get("surgery_benefit_by_class", {})

    if surgery_class > max_class:
        return RuleResult(
            "SUR-001", "FAIL",
            f"수술 {surgery_class}종 — 가입 담보 최대 {max_class}종 초과. 지급 불가.",
            evidence={"surgery_class": surgery_class, "max_class_covered": max_class},
        )

    amount = benefit_map.get(str(surgery_class), 0)
    status = "FLAGGED" if inferred_from_kcd else "PASS"
    reason = (
        f"수술비 {surgery_class}종 — {surgery_info['name']} → {amount:,}원 "
        f"(KCD {ctx.kcd_code} 기준 분류표 후보 매칭 — 담당자 확인 권장)"
        if inferred_from_kcd
        else f"수술비 {surgery_class}종 — {surgery_info['name']} → {amount:,}원"
    )
    return RuleResult(
        "SUR-001", status, reason,
        value=float(amount),
        evidence={
            "coverage_code": cov["coverage_code"],
            "surgery_code": surgery_info.get("code"),
            "surgery_name": surgery_info["name"],
            "surgery_class": surgery_class,
            "benefit_amount": amount,
            "formula": f"{surgery_class}종 수술비 정액 {amount:,}원",
            "inferred_from_kcd": inferred_from_kcd,
            "kcd_candidates_used": kcd_candidates if inferred_from_kcd else [],
        },
    )


# ══════════════════════════════════════════════════════════════════
# FRD 룰 — 사기/이상 탐지 (처리 중단 없이 플래그만 부여)
# ══════════════════════════════════════════════════════════════════

def rule_frd_007(ctx: ClaimContext) -> RuleResult:
    """FRD-007: 비급여 비중 과다 감지."""
    covered = ctx.covered_self_pay   or 0
    non_cov = ctx.non_covered_amount or 0
    total   = covered + non_cov

    if total == 0:
        return RuleResult("FRD-007", "SKIP", "진료비 정보 없음")

    ratio = non_cov / total
    if ratio > NON_COVERED_RATIO_THRESHOLD:
        return RuleResult(
            "FRD-007", "FLAGGED",
            (
                f"비급여 비중 {ratio*100:.1f}% — "
                f"임계값({NON_COVERED_RATIO_THRESHOLD*100:.0f}%) 초과. "
                f"비급여 항목 적정성 검토 필요."
            ),
            value=ratio,
            evidence={
                "covered_self_pay": covered,
                "non_covered_amount": non_cov,
                "non_covered_ratio": round(ratio, 4),
                "threshold": NON_COVERED_RATIO_THRESHOLD,
            },
        )
    return RuleResult(
        "FRD-007", "PASS",
        f"비급여 비중 {ratio*100:.1f}% — 정상 범위",
        evidence={"non_covered_ratio": round(ratio, 4)},
    )


# ══════════════════════════════════════════════════════════════════
# 전체 실행 진입점
# ══════════════════════════════════════════════════════════════════

def run_rules(ctx: ClaimContext) -> ClaimDecision:
    """
    ClaimContext 를 받아 모든 룰을 순서대로 실행하고 ClaimDecision 을 반환한다.
    실행 순서와 조기 종료 조건이 명시적으로 드러나도록 작성.
    """
    applied: list[RuleResult] = []

    # ── 계약 조회 ──────────────────────────────────────────────────
    contract = get_contract(ctx.policy_no)
    if not contract:
        return ClaimDecision(
            claim_id=ctx.claim_id,
            decision="부지급",
            total_payment=0,
            breakdown={},
            applied_rules=[],
            denial_reason=f"계약번호 {ctx.policy_no} 를 조회할 수 없습니다. 계약번호를 확인해 주세요.",
        )

    # ── COM 룰 (FAIL 시 즉시 부지급) ──────────────────────────────
    com004_flag = False
    conditional_exclusion_flag = False

    for rule_fn, args in [
        (rule_com_001, (ctx, contract)),
        (rule_com_002, (ctx, contract)),
        (rule_com_003, (ctx,)),
    ]:
        result = rule_fn(*args)
        applied.append(result)

        if result.status == "FAIL":
            fraud_flag = False
            fraud_reason = None

            # COM-003 면책사유 FAIL 시 FRD-003 반복청구 탐지 추가 실행
            if result.rule_id == "COM-003":
                frd3 = rule_frd_003(ctx, ctx.kcd_code)
                if frd3:
                    applied.append(frd3)
                    fraud_flag = True
                    fraud_reason = frd3.reason

            _enrich_applied(applied)
            return ClaimDecision(
                claim_id=ctx.claim_id,
                decision="부지급",
                total_payment=0,
                breakdown={},
                applied_rules=applied,
                denial_reason=result.reason,
                policy_clause=result.evidence.get("policy_clause"),
                fraud_investigation_flag=fraud_flag,
                fraud_investigation_reason=fraud_reason,
            )

    # COM-004: 중복·단기가입·반복 청구 징후 (FLAGGED 시 담당자 검토)
    com004_result = rule_com_004(ctx, contract)
    applied.append(com004_result)
    if com004_result.status == "FLAGGED":
        com004_flag = True

    # 조건부면책(정신질환 F계열, 선천기형 Q계열) — 특약 확인 필요 시 담당자 플래그
    cond = check_kcd_conditional_exclusion(ctx.kcd_code)
    if cond:
        applied.append(RuleResult(
            "CONDITIONAL-EXCLUSION", "FLAGGED",
            f"조건부면책 해당 — {cond.get('desc', cond['category'])}. 특약 가입 여부 확인 필요.",
            evidence=cond,
        ))
        conditional_exclusion_flag = True

    # ── 서류 완비 확인 (FAIL 시 즉시 보류) ────────────────────────
    doc_result = rule_doc_check(ctx, contract)
    applied.append(doc_result)
    if doc_result.status == "FAIL":
        _enrich_applied(applied)
        return ClaimDecision(
            claim_id=ctx.claim_id,
            decision="보류",
            total_payment=0,
            breakdown={},
            applied_rules=applied,
            missing_docs=doc_result.evidence.get("missing", []),
        )

    # ── 담보별 룰 (claimed_coverage_types 기준으로 실행 대상 결정) ─
    breakdown: dict = {}
    total_payment: int = 0
    sur_kcd_inference_flag = False
    denial_coverages: list[dict] = []   # 일부지급 시 지급 불가 담보
    passed_coverages: list[str] = []    # 지급 가능 담보

    # claimed 가 지정된 경우 해당 담보만, 없으면 전체 실행
    claimed = set(ctx.claimed_coverage_types) if ctx.claimed_coverage_types else None

    for rule_fn, cov_type, rule_id in [
        (rule_ind, "IND", "IND-001"),
        (rule_sil, "SIL", "SIL-001"),
        (rule_sur, "SUR", "SUR-001"),
    ]:
        if claimed is not None and cov_type not in claimed:
            applied.append(RuleResult(
                rule_id, "SKIP",
                f"{cov_type} 담보 미청구 (청구서 미체크)",
            ))
            continue

        res = rule_fn(ctx)
        applied.append(res)
        pays = res.status == "PASS" or (
            res.rule_id == "SUR-001" and res.status == "FLAGGED" and res.value is not None
        )
        if pays and res.value is not None:
            breakdown[res.rule_id] = res.evidence
            total_payment += int(res.value)
            passed_coverages.append(rule_id)
        elif res.status == "FAIL":
            denial_coverages.append({
                "rule_id": res.rule_id,
                "coverage_type": cov_type,
                "reason": res.reason,
                "evidence": res.evidence,
            })
        if res.rule_id == "SUR-001" and res.status == "FLAGGED":
            sur_kcd_inference_flag = True

    # ── FRD-007 (비급여 비중, 플래그만 부여) ──────────────────────
    frd_result = rule_frd_007(ctx)
    applied.append(frd_result)

    reviewer_flag   = (
        frd_result.status == "FLAGGED" or com004_flag or conditional_exclusion_flag
        or sur_kcd_inference_flag
    )
    reviewer_reason = None
    if reviewer_flag:
        parts = []
        if frd_result.status == "FLAGGED":
            parts.append(frd_result.reason)
        if com004_flag:
            parts.append(com004_result.reason)
        if conditional_exclusion_flag:
            parts.append("조건부면책(정신질환/선천기형) 해당 — 특약 확인 필요.")
        if sur_kcd_inference_flag:
            parts.append("수술비: KCD 기준 분류표 후보 매칭 — 실제 수술명·코드와 일치 여부 확인 필요.")
        reviewer_reason = " | ".join(parts)

    # ── CONF-001 (파싱 신뢰도, 낮으면 담당자 검토 전환) ───────────
    if ctx.parse_confidence_min < PARSE_CONFIDENCE_THRESHOLD:
        conf_result = RuleResult(
            "CONF-001", "FLAGGED",
            (
                f"서류 파싱 신뢰도 낮음 — 최솟값 {ctx.parse_confidence_min:.0%} "
                f"(임계값 {PARSE_CONFIDENCE_THRESHOLD:.0%}) — 서류 원본 육안 확인 필요."
            ),
            evidence={
                "parse_confidence_min": ctx.parse_confidence_min,
                "threshold": PARSE_CONFIDENCE_THRESHOLD,
                "submitted_docs": ctx.submitted_doc_types,
            },
        )
        applied.append(conf_result)
        reviewer_flag = True
        reviewer_reason = (reviewer_reason + " | " + conf_result.reason) if reviewer_reason else conf_result.reason

    # ── CHRONIC-ONSET (만성질환 발병일 불명 — 기왕증 확인 필요) ────
    if ctx.chronic_onset_flag:
        chronic_result = RuleResult(
            "CHRONIC-ONSET", "FLAGGED",
            "발병일 불명(만성 경과) — 기왕증 여부 및 고지의무 확인 필요. 입원일 기준으로 면책기간 산정.",
            evidence={
                "fallback_used": "admission_date",
                "accident_date_used": ctx.accident_date,
                "note": "상법 제651조(고지의무), 금감원 분쟁조정 판례 기준",
            },
        )
        applied.append(chronic_result)
        reviewer_flag = True
        reviewer_reason = (reviewer_reason + " | " + chronic_result.reason) if reviewer_reason else chronic_result.reason

    # ── 최종 판정 결정 ─────────────────────────────────────────────
    # 일부지급: 청구한 담보 중 일부는 PASS, 일부는 FAIL (SKIP 제외)
    #   - passed_coverages 와 denial_coverages 가 모두 비어있지 않으면 일부지급
    #   - reviewer_flag 와 독립적으로 판정 (두 축 분리)
    if denial_coverages and passed_coverages and total_payment > 0:
        decision = "일부지급"
    elif reviewer_flag:
        decision = "검토필요"
    else:
        decision = "지급"

    _enrich_applied(applied)
    return ClaimDecision(
        claim_id=ctx.claim_id,
        decision=decision,
        total_payment=total_payment,
        breakdown=breakdown,
        applied_rules=applied,
        reviewer_flag=reviewer_flag,
        reviewer_reason=reviewer_reason,
        denial_coverages=denial_coverages,
    )
