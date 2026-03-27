"""
교차검증 + 이상 탐지 — Agent 판정의 안전성 확보.

LLM 판정과 룰엔진 판정을 비교하여 불일치를 탐지하고,
ConfidenceScore 를 산출하는 전담 모듈.

공개 API:
  validate_decisions(llm_result, rule_decision, ctx) → ValidationResult
  compute_confidence(ctx, rule_decision, llm_result, parse_mismatches) → ConfidenceScore

설계 원칙:
  - 룰엔진 결과를 "정답 기준(ground truth)"으로 간주.
  - LLM 결과가 룰엔진과 다르면 리스크 플래그 부여.
  - 비급여 비중 + 고액 청구 → fraud_risk 자동 감지.
  - 모든 불일치를 로그에 기록 (감사 추적).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.schemas import (
    ClaimContext, ClaimDecision, ConfidenceScore, ReviewRouting,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 결과 타입
# ══════════════════════════════════════════════════════════════════

@dataclass
class ValidationResult:
    """교차검증 결과."""

    # 판정 일치 여부
    decision_match: bool = True       # LLM vs 룰 판정 유형 일치
    amount_match: bool = True         # 금액 차이 10% 이내

    # 불일치 상세
    decision_diff: str = ""           # "AI=지급 vs 룰=부지급"
    amount_diff_pct: float = 0.0      # 금액 차이 비율 (%)

    # 이상 탐지 플래그
    fraud_risk: bool = False          # 사기 의심
    fraud_reasons: list[str] = field(default_factory=list)

    # 권장 조치
    review_required: bool = False     # 담당자 검토 필요
    review_reasons: list[str] = field(default_factory=list)

    # 산출된 신뢰도
    confidence: Optional[ConfidenceScore] = None

    # 담보별 불일치 상세 (A-3)
    coverage_diffs: list[dict] = field(default_factory=list)
    # [{"rule_id": "SIL-001", "llm_amount": 300000, "rule_amount": 244000,
    #   "diff_pct": 23.0, "note": "..."}]

    # 전체 불일치 노트
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "decision_match": self.decision_match,
            "amount_match": self.amount_match,
            "decision_diff": self.decision_diff,
            "amount_diff_pct": round(self.amount_diff_pct, 1),
            "fraud_risk": self.fraud_risk,
            "fraud_reasons": self.fraud_reasons,
            "review_required": self.review_required,
            "review_reasons": self.review_reasons,
            "coverage_diffs": self.coverage_diffs,
            "notes": self.notes,
            "confidence": self.confidence.to_dict() if self.confidence else None,
        }


# ══════════════════════════════════════════════════════════════════
# 교차검증 메인
# ══════════════════════════════════════════════════════════════════

def validate_decisions(
    llm_result: dict,
    rule_decision: ClaimDecision,
    ctx: ClaimContext,
    parse_mismatches: Optional[list[str]] = None,
) -> ValidationResult:
    """
    LLM 판정과 룰엔진 판정을 교차검증.

    Args:
        llm_result:       LLM 판정 결과 dict
            - decision: str ("지급", "부지급", ...)
            - total_payment: int
            - confidence: float (0-1)
            - reasoning: str
        rule_decision:    룰엔진 판정 (ClaimDecision)
        ctx:             청구 컨텍스트
        parse_mismatches: 서류 파싱 교차검증 불일치 목록

    Returns:
        ValidationResult
    """
    result = ValidationResult()

    llm_decision = llm_result.get("decision", "")
    llm_amount = llm_result.get("total_payment", 0)
    llm_confidence = llm_result.get("confidence", 0.5)

    # ── 1. 판정 유형 비교 ────────────────────────────────────────
    if llm_decision and llm_decision != rule_decision.decision:
        result.decision_match = False
        result.decision_diff = f"AI={llm_decision} vs 룰={rule_decision.decision}"
        result.notes.append(f"⚠️ 판정 불일치: {result.decision_diff}")
        result.review_required = True
        result.review_reasons.append("AI-룰 판정 유형 불일치")
        logger.warning("판정 불일치: %s", result.decision_diff)

    # ── 2. 금액 비교 ─────────────────────────────────────────────
    if llm_amount and rule_decision.total_payment:
        diff = abs(llm_amount - rule_decision.total_payment)
        base = max(rule_decision.total_payment, 1)
        result.amount_diff_pct = (diff / base) * 100

        if result.amount_diff_pct > 10:
            result.amount_match = False
            result.notes.append(
                f"⚠️ 금액 불일치 ({result.amount_diff_pct:.0f}%): "
                f"AI={llm_amount:,}원 vs 룰={rule_decision.total_payment:,}원"
            )
            if result.amount_diff_pct > 30:
                result.review_required = True
                result.review_reasons.append(
                    f"금액 차이 {result.amount_diff_pct:.0f}% (임계값 30% 초과)"
                )

    # ── 3. 담보별 금액 비교 (A-3) ────────────────────────
    llm_breakdown = llm_result.get("breakdown", {})
    if llm_breakdown and rule_decision.breakdown:
        result.coverage_diffs = _compare_breakdowns(
            llm_breakdown, rule_decision.breakdown,
        )
        if result.coverage_diffs:
            for cd in result.coverage_diffs:
                result.notes.append(
                    f"⚠️ 담보 {cd['rule_id']} 금액 불일치 ({cd['diff_pct']:.0f}%): "
                    f"AI={cd['llm_amount']:,}원 vs 룰={cd['rule_amount']:,}원"
                )

    # ── 4. 이상 탐지 (fraud risk) ────────────────────────────
    _detect_anomalies(result, rule_decision, ctx)

    # ── 5. 신뢰도 산출 ───────────────────────────────────────
    result.confidence = compute_confidence(
        ctx=ctx,
        rule_decision=rule_decision,
        llm_result=llm_result,
        parse_mismatches=parse_mismatches or [],
    )

    # 리스크 HIGH/CRITICAL → 자동 review_required
    if result.confidence.risk_level in ("HIGH", "CRITICAL") and not result.review_required:
        result.review_required = True
        result.review_reasons.append(f"신뢰도 {result.confidence.risk_level} RISK")

    return result


# ══════════════════════════════════════════════════════════════════
# A-4: LLM confidence_factors 가중평균 산출
# ══════════════════════════════════════════════════════════════════

# confidence_factors 가중치 (프롬프트 루브릭과 동일)
_CONFIDENCE_FACTOR_WEIGHTS: dict[str, float] = {
    "data_completeness": 0.25,
    "policy_match": 0.25,
    "calculation_certainty": 0.25,
    "ambiguity_level": 0.15,
    "edge_case_risk": 0.10,
}


def _compute_llm_confidence(llm_result: dict) -> float:
    """
    LLM 결과에서 llm_confidence 산출 (A-4).

    confidence_factors가 있으면 가중평균으로 재계산하여
    LLM이 반환한 단일 confidence 값보다 정교한 신뢰도를 산출.
    factors가 없으면 기존 단일 confidence 사용 (하위 호환).

    Args:
        llm_result: LLM 판정 dict (confidence, confidence_factors 포함)

    Returns:
        0.0~1.0 범위의 llm_confidence
    """
    factors = llm_result.get("confidence_factors", {})

    if factors and isinstance(factors, dict):
        weighted_sum = 0.0
        weight_sum = 0.0
        for factor_name, weight in _CONFIDENCE_FACTOR_WEIGHTS.items():
            val = factors.get(factor_name)
            if val is not None:
                try:
                    val = float(val)
                    val = max(0.0, min(1.0, val))  # 범위 보정
                    weighted_sum += val * weight
                    weight_sum += weight
                except (TypeError, ValueError):
                    pass

        if weight_sum > 0:
            computed = weighted_sum / weight_sum
            # LLM 원본 confidence와 factors 가중평균의 평균 (양쪽 정보 모두 활용)
            raw_conf = llm_result.get("confidence", 0.5)
            raw_conf = max(0.0, min(1.0, float(raw_conf)))
            # factors 가 3개 이상이면 factors 가중평균 70%, 원본 30%
            # factors 가 적으면 원본 비중 높임
            factor_count = sum(
                1 for f in _CONFIDENCE_FACTOR_WEIGHTS
                if factors.get(f) is not None
            )
            if factor_count >= 3:
                llm_conf = computed * 0.7 + raw_conf * 0.3
            else:
                llm_conf = computed * 0.4 + raw_conf * 0.6
            return max(0.0, min(1.0, round(llm_conf, 3)))

    # 폴백: factors 없으면 기존 단일 confidence 사용
    raw_conf = llm_result.get("confidence", 0.5)
    try:
        return max(0.0, min(1.0, float(raw_conf)))
    except (TypeError, ValueError):
        return 0.5


# ══════════════════════════════════════════════════════════════════
# A-3: 교차검증 헬퍼 함수
# ══════════════════════════════════════════════════════════════════

# 판정 유사도 그룹 — 같은 그룹 내 불일치는 덜 심각
_DECISION_GROUPS: dict[str, int] = {
    "지급": 0,
    "일부지급": 0,    # 지급 계열
    "부지급": 1,
    "보류": 2,
    "검토필요": 2,    # 보류 계열
}


def _decision_similarity(llm_decision: str, rule_decision: str) -> float:
    """
    두 판정의 유사도를 0.0~1.0 으로 산출 (A-3).

    - 완전 일치: 1.0
    - 같은 그룹 (예: 지급↔일부지급): 0.6
    - 다른 그룹 (예: 지급↔부지급): 0.2
    - 미지 판정: 0.0
    """
    if llm_decision == rule_decision:
        return 1.0

    g1 = _DECISION_GROUPS.get(llm_decision)
    g2 = _DECISION_GROUPS.get(rule_decision)

    if g1 is None or g2 is None:
        return 0.0  # 미지 판정 유형
    if g1 == g2:
        return 0.6  # 같은 계열
    return 0.2       # 완전히 다른 계열


def _amount_diff_to_score(diff_pct: float) -> float:
    """
    금액 차이 비율(%)을 0.0~1.0 점수로 변환 (A-3).

    구간:
      0~2%  : 1.0  (거의 일치)
      2~5%  : 0.9
      5~10% : 0.75
      10~20%: 0.5
      20~30%: 0.3
      30%+  : 0.1
    """
    if diff_pct <= 2:
        return 1.0
    if diff_pct <= 5:
        return 0.9
    if diff_pct <= 10:
        return 0.75
    if diff_pct <= 20:
        return 0.5
    if diff_pct <= 30:
        return 0.3
    return 0.1


def _compare_breakdowns(
    llm_breakdown: dict,
    rule_breakdown: dict,
) -> list[dict]:
    """
    담보별(breakdown) 금액 비교 (A-3).

    Args:
        llm_breakdown:  LLM이 산출한 담보별 breakdown
            {"IND-001": {"amount": 210000, ...}, ...}
        rule_breakdown: 룰엔진 담보별 breakdown
            {"IND-001": {"benefit_amount": 210000, ...}, ...}

    Returns:
        불일치 담보 목록. 빈 리스트면 전체 일치.
    """
    diffs: list[dict] = []

    # 룰 breakdown의 모든 담보를 기준으로 비교
    all_rule_ids = set(rule_breakdown.keys()) | set(llm_breakdown.keys())

    for rule_id in all_rule_ids:
        rule_ev = rule_breakdown.get(rule_id, {})
        llm_ev = llm_breakdown.get(rule_id, {})

        # 금액 추출 (LLM은 "amount" 또는 "benefit_amount" 키 사용 가능)
        rule_amt = rule_ev.get("benefit_amount") or rule_ev.get("amount", 0)
        llm_amt = llm_ev.get("amount") or llm_ev.get("benefit_amount", 0)

        try:
            rule_amt = int(rule_amt)
            llm_amt = int(llm_amt)
        except (TypeError, ValueError):
            rule_amt = 0
            llm_amt = 0

        if rule_amt == 0 and llm_amt == 0:
            continue  # 둘 다 0이면 비교 의미 없음

        base = max(rule_amt, 1)
        diff_pct = abs(llm_amt - rule_amt) / base * 100

        if diff_pct > 5:  # 5% 초과 시 불일치로 기록
            diffs.append({
                "rule_id": rule_id,
                "llm_amount": llm_amt,
                "rule_amount": rule_amt,
                "diff_pct": round(diff_pct, 1),
                "note": (
                    f"{rule_id}: AI={llm_amt:,}원 vs 룰={rule_amt:,}원 "
                    f"({diff_pct:.0f}% 차이)"
                ),
            })

    return diffs


def _coverage_match_score(
    llm_breakdown: dict,
    rule_breakdown: dict,
) -> float:
    """
    담보별 일치도를 0.0~1.0 으로 산출 (A-3).

    각 담보의 금액 차이를 _amount_diff_to_score로 변환 후 평균.
    """
    all_rule_ids = set(rule_breakdown.keys()) | set(llm_breakdown.keys())
    if not all_rule_ids:
        return 1.0

    scores: list[float] = []
    for rule_id in all_rule_ids:
        rule_ev = rule_breakdown.get(rule_id, {})
        llm_ev = llm_breakdown.get(rule_id, {})

        rule_amt = rule_ev.get("benefit_amount") or rule_ev.get("amount", 0)
        llm_amt = llm_ev.get("amount") or llm_ev.get("benefit_amount", 0)

        try:
            rule_amt = int(rule_amt)
            llm_amt = int(llm_amt)
        except (TypeError, ValueError):
            scores.append(0.5)
            continue

        if rule_amt == 0 and llm_amt == 0:
            scores.append(1.0)
            continue

        # 한쪽만 존재하면 불일치
        if rule_amt == 0 or llm_amt == 0:
            scores.append(0.2)
            continue

        base = max(rule_amt, 1)
        diff_pct = abs(llm_amt - rule_amt) / base * 100
        scores.append(_amount_diff_to_score(diff_pct))

    return sum(scores) / len(scores) if scores else 1.0


# ══════════════════════════════════════════════════════════════════
# 이상 탐지
# ══════════════════════════════════════════════════════════════════

def _detect_anomalies(
    result: ValidationResult,
    decision: ClaimDecision,
    ctx: ClaimContext,
) -> None:
    """비급여 비중, 고액 청구, 반복 패턴 등 이상 감지."""

    # ① 비급여 비중 > 50% + 고액 청구
    covered = ctx.covered_self_pay or 0
    non_cov = ctx.non_covered_amount or 0
    total = covered + non_cov
    if total > 0:
        non_cov_ratio = non_cov / total
        if non_cov_ratio > 0.5 and total > 3_000_000:
            result.fraud_risk = True
            result.fraud_reasons.append(
                f"비급여 비중 {non_cov_ratio:.0%} + 고액 청구 ({total:,}원)"
            )

    # ② 부지급인데 금액이 큰 청구 (사기 시도 의심)
    if decision.decision == "부지급" and total > 5_000_000:
        result.fraud_reasons.append(
            f"부지급 판정이나 청구 금액이 고액 ({total:,}원)"
        )

    # ③ 사기조사 플래그가 이미 있으면 전파
    if decision.fraud_investigation_flag:
        result.fraud_risk = True
        result.fraud_reasons.append(
            decision.fraud_investigation_reason or "기존 사기조사 플래그"
        )


# ══════════════════════════════════════════════════════════════════
# A-7: 심사 라우팅 결정
# ══════════════════════════════════════════════════════════════════

def determine_review_routing(
    confidence: ConfidenceScore,
    decision: ClaimDecision,
    validation: ValidationResult,
) -> ReviewRouting:
    """
    A-7: 신뢰도 + 판정 결과를 기반으로 심사 라우팅을 결정.

    매핑:
      VERY_LOW  → auto_approve   (자동처리, ~0분)
      LOW       → standard_review (일반심사역, ~5분)
      MEDIUM    → enhanced_review (일반심사역, ~15분, 추가 체크리스트)
      HIGH      → senior_review   (선임심사역, ~30분)
      CRITICAL  → mandatory_hold  (팀장/부서장, ~60분, 필수 보류)

    Args:
        confidence: 산출된 ConfidenceScore
        decision:   룰엔진 ClaimDecision
        validation: 교차검증 결과 (fraud, 불일치 등)

    Returns:
        ReviewRouting 객체
    """
    risk = confidence.risk_level
    checklist: list[str] = []

    # ── 기본 체크리스트 (공통) ──
    base_checks = []

    # fraud_risk → 항상 체크리스트에 추가
    if validation.fraud_risk:
        base_checks.append("🚨 사기 의심 플래그 확인 — 사기조사팀 통보 여부 판단")

    # 판정 불일치 → 체크리스트
    if not validation.decision_match:
        base_checks.append(f"⚠️ AI-룰 판정 불일치 확인: {validation.decision_diff}")

    # 금액 불일치 → 체크리스트
    if not validation.amount_match:
        base_checks.append(
            f"⚠️ 금액 차이 확인: {validation.amount_diff_pct:.0f}%"
        )

    # 담보별 불일치 → 체크리스트
    if validation.coverage_diffs:
        for cd in validation.coverage_diffs[:3]:  # 최대 3개
            base_checks.append(
                f"📊 담보 {cd['rule_id']} 금액 차이 {cd['diff_pct']:.0f}% 확인"
            )

    # 서류 미비 → 체크리스트
    if decision.missing_docs:
        base_checks.append(
            f"📋 미비 서류 확인: {', '.join(decision.missing_docs)}"
        )

    # ── risk_level별 라우팅 ──
    if risk == "VERY_LOW":
        # 자동 승인 가능 — 단, fraud/불일치 있으면 standard로 상향
        if validation.fraud_risk or not validation.decision_match:
            checklist = base_checks + ["✅ 자동승인 조건 미충족 → 일반심사 전환"]
            return ReviewRouting(
                action="standard_review",
                priority="normal",
                reviewer_level="일반심사역",
                checklist=checklist,
                estimated_minutes=10,
                routing_reason="VERY_LOW 리스크이나 불일치/사기 플래그 존재",
            )
        checklist = ["✅ 자동 처리 — 추가 검토 불필요"]
        return ReviewRouting(
            action="auto_approve",
            priority="low",
            reviewer_level="자동처리",
            checklist=checklist,
            estimated_minutes=0,
            routing_reason="VERY_LOW 리스크, 모든 검증 통과",
        )

    if risk == "LOW":
        checklist = base_checks + [
            "📋 서류 완비 여부 최종 확인",
            "💰 산정 금액 적정성 확인",
        ]
        return ReviewRouting(
            action="standard_review",
            priority="normal",
            reviewer_level="일반심사역",
            checklist=checklist,
            estimated_minutes=5,
            routing_reason="LOW 리스크 — 표준 심사 절차",
        )

    if risk == "MEDIUM":
        checklist = base_checks + [
            "📋 서류 파싱 결과 원본 대조",
            "💰 담보별 산정 금액 재검증",
            "📑 약관 적용 조항 확인",
            "🔍 불확실 항목 표시 확인",
        ]
        return ReviewRouting(
            action="enhanced_review",
            priority="high",
            reviewer_level="일반심사역",
            checklist=checklist,
            estimated_minutes=15,
            routing_reason="MEDIUM 리스크 — 불확실 항목 존재, 강화 심사 필요",
        )

    if risk == "HIGH":
        checklist = base_checks + [
            "🔴 전문 심사역 지정 검토",
            "📋 서류 원본 대조 필수",
            "💰 담보별 산정 금액 수동 재계산",
            "📑 약관 조항 해석 확인",
            "🏥 진단서/수술확인서 의료자문 필요 여부",
            "📊 유사 청구 이력 비교",
        ]
        return ReviewRouting(
            action="senior_review",
            priority="urgent",
            reviewer_level="선임심사역",
            checklist=checklist,
            estimated_minutes=30,
            routing_reason="HIGH 리스크 — 선임심사역 검토 필요",
        )

    # CRITICAL
    checklist = base_checks + [
        "🚨 즉시 팀장/부서장 보고",
        "📋 전 서류 원본 대조 필수",
        "💰 전체 산정 금액 수동 재계산",
        "📑 약관 조항 법무팀 해석 확인",
        "🏥 의료자문위원회 자문 의뢰",
        "📊 사기조사팀 통보 여부 결정",
        "📝 특이사항 보고서 작성",
    ]
    return ReviewRouting(
        action="mandatory_hold",
        priority="critical",
        reviewer_level="팀장",
        checklist=checklist,
        estimated_minutes=60,
        routing_reason="CRITICAL 리스크 — 필수 보류, 팀장 승인 필요",
    )


# ══════════════════════════════════════════════════════════════════
# 신뢰도 산출
# ══════════════════════════════════════════════════════════════════

def compute_confidence(
    ctx: ClaimContext,
    rule_decision: ClaimDecision,
    llm_result: Optional[dict] = None,
    parse_mismatches: Optional[list[str]] = None,
) -> ConfidenceScore:
    """
    ConfidenceScore 를 산출.

    Args:
        ctx:              청구 컨텍스트
        rule_decision:    룰엔진 판정 결과
        llm_result:       LLM 판정 dict (없으면 룰 모드)
        parse_mismatches: 파싱 교차검증 불일치 목록

    Returns:
        ConfidenceScore (overall + risk_level 자동 산출)
    """

    # ── parse_confidence (가중평균 기반, min은 보조 지표) ───────────
    parse_conf = getattr(ctx, "parse_confidence_avg", ctx.parse_confidence_min)
    # 파싱 교차검증 불일치가 있으면 감점
    mismatch_count = len(parse_mismatches or [])
    if mismatch_count > 0:
        parse_conf = max(0.1, parse_conf - mismatch_count * 0.05)

    # ── rule_confidence ───────────────────────────────────────────
    # FLAGGED 룰 개수에 반비례
    flagged_count = sum(
        1 for r in rule_decision.applied_rules if r.status == "FLAGGED"
    )
    rule_conf = max(0.3, 1.0 - flagged_count * 0.2)

    # FAIL 이 있으면 (정상적 부지급/보류) → 확실한 판정이므로 높은 신뢰도
    fail_count = sum(
        1 for r in rule_decision.applied_rules if r.status == "FAIL"
    )
    if fail_count > 0 and flagged_count == 0:
        rule_conf = min(1.0, rule_conf + 0.1)  # 명확한 부지급은 확실

    # ── llm_confidence (A-4: confidence_factors 활용) ─────────────
    if llm_result:
        llm_conf = _compute_llm_confidence(llm_result)
    else:
        # 룰 모드: LLM 미사용 → 중립값
        llm_conf = 0.5

    # ── cross_validation (A-3: 세분화) ─────────────────────────────
    if llm_result and llm_result.get("decision"):
        llm_decision = llm_result["decision"]
        llm_amount = llm_result.get("total_payment", 0)

        # ① 판정 유사도
        decision_sim = _decision_similarity(llm_decision, rule_decision.decision)

        # ② 금액 일치도
        if llm_amount and rule_decision.total_payment:
            diff_pct = (
                abs(llm_amount - rule_decision.total_payment)
                / max(rule_decision.total_payment, 1) * 100
            )
            amount_sc = _amount_diff_to_score(diff_pct)
        elif llm_amount == 0 and rule_decision.total_payment == 0:
            amount_sc = 1.0
        else:
            amount_sc = 0.5

        # ③ 담보별 일치도
        llm_bk = llm_result.get("breakdown", {})
        if llm_bk and rule_decision.breakdown:
            cov_sc = _coverage_match_score(llm_bk, rule_decision.breakdown)
            cross_val = decision_sim * 0.40 + amount_sc * 0.30 + cov_sc * 0.30
        else:
            cross_val = decision_sim * 0.50 + amount_sc * 0.50
    else:
        # LLM 미사용
        cross_val = 0.5

    # ── 종합 산출 ─────────────────────────────────────────────────
    is_agent = bool(llm_result and llm_result.get("decision"))

    # A-6: confidence_factors 를 ConfidenceScore 에 저장 (UI 대시보드 표시용)
    factors = {}
    if llm_result:
        raw_factors = llm_result.get("confidence_factors", {})
        if raw_factors and isinstance(raw_factors, dict):
            for k in _CONFIDENCE_FACTOR_WEIGHTS:
                v = raw_factors.get(k)
                if v is not None:
                    try:
                        factors[k] = max(0.0, min(1.0, float(v)))
                    except (TypeError, ValueError):
                        pass

    score = ConfidenceScore(
        parse_confidence=round(parse_conf, 3),
        rule_confidence=round(rule_conf, 3),
        llm_confidence=round(llm_conf, 3),
        cross_validation=round(cross_val, 3),
        confidence_factors=factors,
    )
    score.compute_overall(agent_mode=is_agent)

    logger.info(
        "ConfidenceScore: parse=%.2f rule=%.2f llm=%.2f xval=%.2f → overall=%.2f (%s)",
        score.parse_confidence, score.rule_confidence,
        score.llm_confidence, score.cross_validation,
        score.overall, score.risk_level,
    )

    return score


# ══════════════════════════════════════════════════════════════════
# 편의 함수: 룰 모드용 신뢰도 산출
# ══════════════════════════════════════════════════════════════════

def compute_rule_only_confidence(
    ctx: ClaimContext,
    rule_decision: ClaimDecision,
) -> ConfidenceScore:
    """
    룰 모드 전용 신뢰도 산출 (LLM 미사용).

    Agent 모드가 아니어도 기본 신뢰도를 산출할 때 사용.
    파싱 40% + 룰 60% 가중치로 overall 산출 (LLM/교차검증 제외).
    """
    return compute_confidence(
        ctx=ctx,
        rule_decision=rule_decision,
        llm_result=None,
        parse_mismatches=None,
    )
