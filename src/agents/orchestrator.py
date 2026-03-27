"""
오케스트레이터 — 청구 처리 전체 흐름 조율.

흐름:
  load_claim_files()
    → doc_parser.parse_claim_documents()   # STEP 1: 문서 처리
    → build_claim_context()                # STEP 2: 컨텍스트 조립
    → rule_engine.run_rules()              # STEP 3: 룰 엔진 실행
    → result_writer.write_results()        # STEP 4: 결과 문서 생성
"""
from __future__ import annotations
import json
from pathlib import Path

from src.ocr.doc_parser import parse_claim_documents
from src.rules.rule_engine import run_rules
from src.schemas import ClaimContext, ClaimDecision, ParsedDocument
from config.settings import SAMPLE_DOCS_PATH, OUTPUT_DIR, DOC_PARSE_MODE, VERBOSE_LOGGING, AGENT_MODE


# ══════════════════════════════════════════════════════════════════
# 서류 유형별 파싱 신뢰도 가중치 (A-2)
# ══════════════════════════════════════════════════════════════════
# 보험금 산정에 직접적 영향이 큰 서류일수록 높은 가중치.
# 가중치가 높은 서류의 파싱 품질이 낮으면 전체 신뢰도에 더 큰 영향.
DOC_TYPE_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "진료비영수증": 3.0,      # 실손 금액 산정의 핵심 (급여/비급여 구분)
    "진단서": 2.5,            # KCD 코드 + 진단명 → 면책 판단 근거
    "입원확인서": 2.0,        # 입원일수 → 입원일당 산정 근거
    "수술확인서": 2.0,        # 수술명/코드 → 수술비 분류 근거
    "진료비세부내역서": 2.0,  # 4세대 비급여 항목별 한도 산정
    "보험금청구서": 1.0,      # 행정적 서류 (보험금 산정 직접 영향 적음)
    "미분류": 0.5,            # 파싱 품질 불확실
}
_DEFAULT_DOC_WEIGHT = 1.0  # 위 맵에 없는 유형의 기본 가중치


# ══════════════════════════════════════════════════════════════════
# STEP 2: ClaimContext 조립
# ══════════════════════════════════════════════════════════════════

def build_claim_context(
    claim_id: str,
    policy_no: str,
    claim_date: str,
    documents: list[ParsedDocument],
) -> ClaimContext:
    """
    파싱된 서류 목록에서 ClaimContext 조립.

    필드 병합 전략:
      - "선점 우선(first-wins)": 먼저 추출된 non-None 값을 유지
      - claimed_coverage_types: 보험금청구서 doc_type에서만 추출
      - surgery_name / surgery_code: 수술확인서 doc_type에서 우선 적용
    """
    fields: dict = {}
    doc_types: list[str] = []
    claimed_coverage_types: list[str] = []
    min_confidence: float = 1.0
    weighted_conf_sum: float = 0.0  # A-2: 가중 confidence 합
    weight_sum: float = 0.0         # A-2: 가중치 합

    for doc in documents:
        doc_types.append(doc.doc_type)
        min_confidence = min(min_confidence, doc.confidence)
        # A-2: 서류 유형별 가중치 적용
        w = DOC_TYPE_CONFIDENCE_WEIGHTS.get(doc.doc_type, _DEFAULT_DOC_WEIGHT)
        weighted_conf_sum += doc.confidence * w
        weight_sum += w

        # claimed_coverage_types: 보험금청구서에서만 추출
        if doc.doc_type == "보험금청구서" and "claimed_coverage_types" in doc.fields:
            claimed_coverage_types = doc.fields["claimed_coverage_types"]

        # 수술 정보: 수술확인서 doc에서 우선 덮어쓰기 (가장 정확한 소스)
        if doc.doc_type == "수술확인서":
            for k in ("surgery_name", "surgery_code"):
                if k in doc.fields and doc.fields[k] is not None:
                    fields[k] = doc.fields[k]
            continue  # 수술확인서의 다른 필드는 이미 처리한 것 유지

        # billing_items: 진료비세부내역서에서 수집 (여러 건이면 합침)
        if doc.doc_type == "진료비세부내역서" and "billing_items" in doc.fields and doc.fields["billing_items"]:
            fields.setdefault("billing_items", []).extend(doc.fields["billing_items"])

        # 나머지 필드: first-wins (이미 있는 non-None 값은 덮어쓰지 않음)
        for k, v in doc.fields.items():
            if k in ("claimed_coverage_types", "billing_items"):
                continue  # 별도 처리
            if v is not None and k not in fields:
                fields[k] = v

    # accident_date 처리: CHRONIC_UNKNOWN 감지 + 폴백 순서 (입원일 → 청구일)
    raw_accident = fields.get("accident_date")
    chronic_onset_flag = False
    if raw_accident == "CHRONIC_UNKNOWN":
        # 보험업계 표준: 만성질환 발병일 불명 시 입원일(최초 치료일) 기준
        accident_date = fields.get("admission_date") or claim_date
        chronic_onset_flag = True
    elif raw_accident:
        accident_date = raw_accident
    else:
        # 발병일 미추출 시도 입원일 우선 폴백
        accident_date = fields.get("admission_date") or claim_date

    return ClaimContext(
        claim_id=claim_id,
        policy_no=policy_no,
        claim_date=claim_date,
        accident_date=accident_date,
        admission_date=fields.get("admission_date"),
        discharge_date=fields.get("discharge_date"),
        hospital_days=fields.get("hospital_days"),
        kcd_code=fields.get("kcd_code", "UNKNOWN"),
        diagnosis=fields.get("diagnosis", ""),
        surgery_name=fields.get("surgery_name"),
        surgery_code=fields.get("surgery_code"),
        covered_self_pay=fields.get("covered_self_pay"),
        non_covered_amount=fields.get("non_covered"),
        submitted_doc_types=list(dict.fromkeys(doc_types)),  # 순서 유지 중복 제거
        claimed_coverage_types=claimed_coverage_types,
        raw_documents=documents,
        parse_confidence_min=round(min_confidence, 2),
        parse_confidence_avg=round(weighted_conf_sum / max(weight_sum, 1e-9), 3),  # A-2: 서류유형별 가중평균
        billing_items=fields.get("billing_items") or [],
        chronic_onset_flag=chronic_onset_flag,
    )


# ══════════════════════════════════════════════════════════════════
# 단일 청구 처리
# ══════════════════════════════════════════════════════════════════

def process_claim(
    claim_id: str,
    policy_no: str,
    claim_date: str,
    on_progress=None,
    use_agent: bool = False,
) -> ClaimDecision:
    """
    단일 청구 처리 진입점.
    서류 경로: data/sample_docs/{claim_id}/
    on_progress: 선택적 콜백 함수 — 단계별 진행률을 외부(UI)에 전달
    use_agent: True면 LangGraph Agent 모드, False면 기존 룰 기반
    """
    doc_dir = SAMPLE_DOCS_PATH / claim_id
    if not doc_dir.exists():
        raise FileNotFoundError(f"서류 디렉토리 없음: {doc_dir}")

    # Agent 모드 분기
    effective_agent = use_agent or AGENT_MODE == "agent"
    if effective_agent:
        try:
            from src.agents.claim_graph import run_agent_claim
            return run_agent_claim(
                claim_id=claim_id,
                policy_no=policy_no,
                claim_date=claim_date,
                doc_dir=str(doc_dir),
                on_progress=on_progress,
            )
        except Exception as exc:
            if VERBOSE_LOGGING:
                print(f"  [Agent 폴백] {exc} — 룰 기반으로 전환")
            # Agent 실패 시 아래 룰 기반으로 계속 진행

    if VERBOSE_LOGGING:
        print(f"\n[STEP 1] 문서 처리: {claim_id} ({doc_dir})")

    # STEP 1: 서류 파싱
    if on_progress:
        on_progress({"step": 1, "status": "started", "name": "문서 파싱"})
    documents = parse_claim_documents(doc_dir, mode=DOC_PARSE_MODE)

    if VERBOSE_LOGGING:
        for doc in documents:
            print(f"  파일: {doc.doc_type:12s} | 신뢰도: {doc.confidence:.1f} "
                  f"| 추출 필드: {list(doc.fields.keys())}")
    if on_progress:
        for doc in documents:
            on_progress({"step": 1, "doc_type": doc.doc_type, "confidence": doc.confidence})
        on_progress({"step": 1, "status": "complete", "doc_count": len(documents)})

    # STEP 2: 컨텍스트 조립
    if VERBOSE_LOGGING:
        print(f"\n[STEP 2] 컨텍스트 조립")
    if on_progress:
        on_progress({"step": 2, "status": "started", "name": "컨텍스트 조립"})
    ctx = build_claim_context(claim_id, policy_no, claim_date, documents)
    if on_progress:
        on_progress({"step": 2, "status": "complete", "kcd": ctx.kcd_code,
                     "hospital_days": ctx.hospital_days,
                     "chronic_onset_flag": ctx.chronic_onset_flag})

    if VERBOSE_LOGGING:
        print(f"  KCD: {ctx.kcd_code} | 입원: {ctx.hospital_days}일 "
              f"| 청구담보: {ctx.claimed_coverage_types}")
        print(f"  급여본인부담: {ctx.covered_self_pay:,}원 | "
              f"비급여: {ctx.non_covered_amount or 0:,}원"
              if ctx.covered_self_pay else "  진료비 정보 없음")

    # STEP 3: 룰 실행
    if VERBOSE_LOGGING:
        print(f"\n[STEP 3] 룰 엔진 실행")
    if on_progress:
        on_progress({"step": 3, "status": "started", "name": "룰 엔진"})
    decision = run_rules(ctx)

    # 룰 모드에서도 기본 신뢰도 산출 (A-1)
    from src.agents.validator import compute_rule_only_confidence
    decision.confidence = compute_rule_only_confidence(ctx, decision)

    if on_progress:
        for r in decision.applied_rules:
            on_progress({"step": 3, "rule_id": r.rule_id, "rule_status": r.status,
                         "reason": r.reason, "value": r.value})
        on_progress({"step": 3, "status": "complete", "decision": decision.decision,
                     "total_payment": decision.total_payment})

    if VERBOSE_LOGGING:
        print(f"  → 판정: {decision.decision} | 지급액: {decision.total_payment:,}원")

    # STEP 4: 결과 저장
    if VERBOSE_LOGGING:
        print(f"\n[STEP 4] 결과 문서 생성")
    if on_progress:
        on_progress({"step": 4, "status": "started", "name": "결과 문서 생성"})
    _write_all_results(decision, ctx)
    if on_progress:
        on_progress({"step": 4, "status": "complete"})

    return decision


# ══════════════════════════════════════════════════════════════════
# STEP 4: 결과 저장 (result_writer 위임)
# ══════════════════════════════════════════════════════════════════

def _write_all_results(decision: ClaimDecision, ctx: ClaimContext) -> None:
    """decision.json 저장 + 결과 문서 생성 (result_writer 위임)."""
    from src.agents.result_writer import write_results
    write_results(decision, ctx)


# ══════════════════════════════════════════════════════════════════
# 전체 테스트 케이스 실행
# ══════════════════════════════════════════════════════════════════

def run_all_test_cases() -> None:
    """data/test_cases/test_inputs.json 의 모든 케이스를 순서대로 실행."""
    from config.settings import PROJECT_ROOT
    inputs_path = PROJECT_ROOT / "data" / "test_cases" / "test_inputs.json"
    test_inputs = json.loads(inputs_path.read_text(encoding="utf-8"))

    results_summary: list[dict] = []

    for case in test_inputs["test_inputs"]:
        sep = "=" * 60
        print(f"\n{sep}")
        print(f"  청구번호: {case['claim_id']}  |  계약번호: {case['policy_no']}")
        print(sep)

        try:
            decision = process_claim(
                case["claim_id"],
                case["policy_no"],
                case["claim_date"],
            )
            _print_decision_summary(decision)
            results_summary.append({
                "claim_id": case["claim_id"],
                "decision": decision.decision,
                "total_payment": decision.total_payment,
                "reviewer_flag": decision.reviewer_flag,
                "fraud_flag": decision.fraud_investigation_flag,
                "status": "success",
            })
        except Exception as e:
            print(f"  [오류] {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            results_summary.append({
                "claim_id": case["claim_id"],
                "status": "error",
                "error": str(e),
            })

    # 최종 요약 출력
    _print_final_summary(results_summary)


def _print_decision_summary(decision: ClaimDecision) -> None:
    """판정 결과를 콘솔에 출력."""
    icon = {"지급": "✅", "부지급": "✗ ", "보류": "⏳", "검토필요": "⚠️ "}.get(decision.decision, "?")
    print(f"\n  {icon} 판정: {decision.decision}  |  지급액: {decision.total_payment:,}원")

    if decision.breakdown:
        for rule_id, ev in decision.breakdown.items():
            amt = ev.get("benefit_amount", 0)
            formula = ev.get("formula", "")
            print(f"     {rule_id}: {amt:,}원  ({formula})")

    if decision.denial_reason:
        print(f"  사유: {decision.denial_reason}")
    if decision.policy_clause:
        print(f"  약관: {decision.policy_clause}")
    if decision.missing_docs:
        print(f"  미제출 서류: {', '.join(decision.missing_docs)}")
    if decision.reviewer_flag:
        print(f"  ⚠️  담당자 검토: {decision.reviewer_reason}")
    if decision.fraud_investigation_flag:
        print(f"  🚨 사기조사 플래그: {decision.fraud_investigation_reason}")

    print(f"\n  적용 룰:")
    for r in decision.applied_rules:
        status_icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "-", "FLAGGED": "⚑"}.get(r.status, "?")
        print(f"     {status_icon} {r.rule_id}: {r.status}  — {r.reason[:60]}")


def _print_final_summary(results: list[dict]) -> None:
    """전체 시나리오 실행 결과 요약 표 출력."""
    print(f"\n{'=' * 60}")
    print("  전체 실행 결과 요약")
    print(f"{'=' * 60}")
    print(f"  {'청구번호':<18} {'판정':<8} {'지급액':>12}  {'플래그'}")
    print(f"  {'-'*56}")
    for r in results:
        if r["status"] == "error":
            print(f"  {r['claim_id']:<18} {'ERROR':<8} {'':>12}  {r['error'][:20]}")
        else:
            flags = []
            if r.get("reviewer_flag"):
                flags.append("담당자검토")
            if r.get("fraud_flag"):
                flags.append("🚨사기조사")
            flag_str = ", ".join(flags) if flags else ""
            print(f"  {r['claim_id']:<18} {r['decision']:<8} "
                  f"{r['total_payment']:>12,}원  {flag_str}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run_all_test_cases()
