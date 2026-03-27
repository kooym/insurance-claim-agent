"""
결과 출력 에이전트 — ClaimDecision 을 받아 결과 문서를 자동 생성.

생성 파일:
  지급/검토필요  → 지급결의서.txt + 고객안내문.txt + 처리로그.json
  일부지급       → 일부지급결의서.txt + 고객안내문_일부지급.txt + 처리로그.json
  부지급         → 부지급결의서.txt + 고객안내문_부지급.txt + 처리로그.json
  보류           → 보류통보서.txt + 처리로그.json
"""
from __future__ import annotations
import json
from datetime import datetime, date
from pathlib import Path
from typing import Any

from src.schemas import ClaimDecision, ClaimContext
from config.settings import OUTPUT_DIR
from src.utils.date_utils import add_business_days_iso, business_days_explanation


# ══════════════════════════════════════════════════════════════════
# 진입점
# ══════════════════════════════════════════════════════════════════

def write_results(decision: ClaimDecision, ctx: ClaimContext) -> Path:
    """
    판정 결과 전체 문서를 outputs/{claim_id}/ 에 생성.
    재실행 시 이전 판정에서 생성된 .txt/.json 파일을 먼저 제거하여 일관성을 보장.
    반환: 출력 디렉토리 경로
    """
    out_dir = OUTPUT_DIR / decision.claim_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # 이전 실행 결과 파일 제거 (SAMPLE 파일 등 수동 배치 파일은 보존)
    _managed_files = {
        "decision.json", "처리로그.json",
        "지급결의서.txt", "고객안내문.txt",
        "부지급결의서.txt", "고객안내문_부지급.txt",
        "일부지급결의서.txt", "고객안내문_일부지급.txt",
        "보류통보서.txt",
        "보상직원_산정요약.txt",
    }
    for f in out_dir.iterdir():
        if f.name in _managed_files:
            f.unlink()

    # 1. decision.json (구조화 데이터, 항상 생성)
    _write_decision_json(decision, ctx, out_dir)

    # 2. 판정 유형별 문서
    if decision.decision in ("지급", "검토필요"):
        _write_payment_documents(decision, ctx, out_dir)
        _write_staff_briefing(decision, ctx, out_dir)
    elif decision.decision == "일부지급":
        _write_partial_payment_documents(decision, ctx, out_dir)
        _write_staff_briefing(decision, ctx, out_dir)
    elif decision.decision == "부지급":
        _write_denial_documents(decision, ctx, out_dir)
        _write_staff_briefing(decision, ctx, out_dir)
    elif decision.decision == "보류":
        _write_pending_documents(decision, ctx, out_dir)
        _write_staff_briefing(decision, ctx, out_dir)

    # 3. 처리 로그 (항상 생성)
    _write_processing_log(decision, ctx, out_dir)

    print(f"  [결과 저장] {out_dir}")
    return out_dir


# ══════════════════════════════════════════════════════════════════
# decision.json
# ══════════════════════════════════════════════════════════════════

def _write_decision_json(decision: ClaimDecision, ctx: ClaimContext, out_dir: Path) -> None:
    expected_pay_date = add_business_days_iso(ctx.claim_date, 3)
    output = {
        "claim_id":            decision.claim_id,
        "decision":            decision.decision,
        "total_payment":       decision.total_payment,
        "expected_payment_date": expected_pay_date,
        "payment_deadline_note": business_days_explanation(ctx.claim_date, 3),
        "breakdown":           decision.breakdown,
        "reviewer_flag":       decision.reviewer_flag,
        "reviewer_reason":     decision.reviewer_reason,
        "missing_docs":        decision.missing_docs,
        "denial_reason":       decision.denial_reason,
        "policy_clause":       decision.policy_clause,
        "fraud_investigation_flag":   decision.fraud_investigation_flag,
        "fraud_investigation_reason": decision.fraud_investigation_reason,
        "denial_coverages":    decision.denial_coverages,
        "applied_rules": [
            {
                "rule_id": r.rule_id,
                "status":  r.status,
                "reason":  r.reason,
                "value":   r.value,
            }
            for r in decision.applied_rules
        ],
        "generated_at": datetime.now().isoformat(),
    }

    # A-8: 신뢰도 + 라우팅 정보 추가
    if decision.confidence:
        output["confidence"] = decision.confidence.to_dict()
    routing = getattr(decision, "review_routing", None)
    if routing:
        output["review_routing"] = routing.to_dict()

    path = out_dir / "decision.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"    → decision.json")


# ══════════════════════════════════════════════════════════════════
# 지급 문서
# ══════════════════════════════════════════════════════════════════

def _write_payment_documents(
    decision: ClaimDecision, ctx: ClaimContext, out_dir: Path
) -> None:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    flag_notice = ""
    if decision.reviewer_flag:
        reason_text = (decision.reviewer_reason or "담당자 검토 요망")[:60]
        flag_notice = f"""
┌─────────────────────────────────────────────────────────────┐
│  ⚠️  담당자 검토 필요                                          │
│  {reason_text:60s}│
│  본 건은 담당자 최종 승인 후 지급 처리됩니다.                  │
└─────────────────────────────────────────────────────────────┘"""

    breakdown_lines = ""
    for rule_id, ev in decision.breakdown.items():
        amt = ev.get("benefit_amount", 0)
        formula = ev.get("formula", "")
        clause = ev.get("policy_clause", "")
        breakdown_lines += f"\n  {rule_id:<10}: {amt:>12,}원   ({formula})"
        if clause:
            breakdown_lines += f"\n              약관 근거: {clause}"

    rules_lines = "\n".join(
        f"  {r.rule_id:<12} [{r.status:<7}]  {r.reason[:55]}"
        + (f"\n                          약관: {r.evidence.get('policy_clause', '')}" if r.evidence.get('policy_clause') else "")
        for r in decision.applied_rules
    )

    content = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                      보 험 금  지 급 결 의 서
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
결의일자  : {today}
청구번호  : {decision.claim_id}
보험계약번호: {ctx.policy_no}
피보험자  : {_get_insured_name(ctx)}
{flag_notice}
■ 지급 결정
─────────────────────────────────────────────────────────────
판정 결과  : {decision.decision}
지급 보험금: {decision.total_payment:,}원

■ 담보별 산정 내역
─────────────────────────────────────────────────────────────{breakdown_lines}
                                         ─────────────────
                              합계        {decision.total_payment:>12,}원

■ 룰 적용 결과 (감사 추적)
─────────────────────────────────────────────────────────────
{rules_lines}

■ 처리 의견
─────────────────────────────────────────────────────────────
AI Agent 자동 산정 완료. {'담당자 검토 후 지급 처리 요망.' if decision.reviewer_flag else '자동 지급 처리 가능.'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
담당자 확인: ________________  (서명)       결재일: {today}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    (out_dir / "지급결의서.txt").write_text(content, encoding="utf-8")
    print(f"    → 지급결의서.txt")

    # 고객 안내문
    customer_content = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                  보험금 지급 결정 안내
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
안녕하세요. 귀하의 보험금 청구에 대하여 아래와 같이 안내드립니다.

■ 청구 내용
─────────────────────────────────────────────────────────────
청구번호   : {decision.claim_id}
피보험자   : {_get_insured_name(ctx)}
진단명     : {ctx.diagnosis or "확인 중"}
청구 담보  : {', '.join(ctx.claimed_coverage_types)}

■ 지급 결정
─────────────────────────────────────────────────────────────
결정 내용  : 보험금 {"지급 예정" if not decision.reviewer_flag else "검토 중 (담당자 확인 후 지급)"}
지급 금액  : {decision.total_payment:,}원
지급 예정일: {_payment_due_text(ctx, decision.reviewer_flag)}

■ 문의처
─────────────────────────────────────────────────────────────
보험금 지급 관련 문의: 고객센터 1588-XXXX (평일 09:00~18:00)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{today}
(주)한국생명보험  보험금지급팀
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    (out_dir / "고객안내문.txt").write_text(customer_content, encoding="utf-8")
    print(f"    → 고객안내문.txt")


# ══════════════════════════════════════════════════════════════════
# 일부지급 문서
# ══════════════════════════════════════════════════════════════════

def _write_partial_payment_documents(
    decision: ClaimDecision, ctx: ClaimContext, out_dir: Path
) -> None:
    """일부지급: 지급되는 담보 + 지급 불가 담보를 모두 명시."""
    today = datetime.now().strftime("%Y년 %m월 %d일")

    flag_notice = ""
    if decision.reviewer_flag:
        reason_text = (decision.reviewer_reason or "담당자 검토 요망")[:60]
        flag_notice = f"""
┌─────────────────────────────────────────────────────────────┐
│  ⚠️  담당자 검토 필요                                          │
│  {reason_text:60s}│
│  본 건은 담당자 최종 승인 후 지급 처리됩니다.                  │
└─────────────────────────────────────────────────────────────┘"""

    # 지급 담보 내역
    paid_lines = ""
    for rule_id, ev in decision.breakdown.items():
        amt = ev.get("benefit_amount", 0)
        formula = ev.get("formula", "")
        clause = ev.get("policy_clause", "")
        paid_lines += f"\n  {rule_id:<10}: {amt:>12,}원   ({formula})"
        if clause:
            paid_lines += f"\n              약관 근거: {clause}"

    # 지급 불가 담보 내역
    denied_lines = ""
    for dc in decision.denial_coverages:
        rid = dc.get("rule_id", "")
        reason = dc.get("reason", "")
        ev = dc.get("evidence", {})
        clause = ev.get("policy_clause", "")
        denied_lines += f"\n  {rid:<10}: 지급 불가 — {reason[:60]}"
        if clause:
            denied_lines += f"\n              약관 근거: {clause}"

    rules_lines = "\n".join(
        f"  {r.rule_id:<12} [{r.status:<7}]  {r.reason[:55]}"
        + (f"\n                          약관: {r.evidence.get('policy_clause', '')}" if r.evidence.get('policy_clause') else "")
        for r in decision.applied_rules
    )

    content = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                  보 험 금  일 부 지 급  결 의 서
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
결의일자  : {today}
청구번호  : {decision.claim_id}
보험계약번호: {ctx.policy_no}
피보험자  : {_get_insured_name(ctx)}
{flag_notice}
■ 일부지급 결정
─────────────────────────────────────────────────────────────
판정 결과  : 일부지급
지급 보험금: {decision.total_payment:,}원 (아래 지급 가능 담보 합계)

■ 지급 담보 산정 내역
─────────────────────────────────────────────────────────────{paid_lines}
                                         ─────────────────
                              합계        {decision.total_payment:>12,}원

■ 지급 불가 담보 (사유)
─────────────────────────────────────────────────────────────{denied_lines}

■ 룰 적용 결과 (감사 추적)
─────────────────────────────────────────────────────────────
{rules_lines}

■ 처리 의견
─────────────────────────────────────────────────────────────
일부 담보 지급 불가 사유 발생. {'담당자 검토 후 지급 처리 요망.' if decision.reviewer_flag else '지급 가능 담보에 대해 자동 지급 처리 가능.'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
담당자 확인: ________________  (서명)       결재일: {today}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    (out_dir / "일부지급결의서.txt").write_text(content, encoding="utf-8")
    print(f"    → 일부지급결의서.txt")

    # 고객 안내문 (일부지급)
    denied_customer_lines = ""
    for dc in decision.denial_coverages:
        denied_customer_lines += f"\n  - {dc.get('coverage_type', '?')} 담보: {dc.get('reason', '')[:60]}"

    customer_content = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              보험금 일부지급 결정 안내
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
안녕하세요, {_get_insured_name(ctx)} 고객님.

귀하의 보험금 청구({decision.claim_id})에 대하여
일부 담보에 대해 지급이 결정되었으며,
일부 담보는 아래 사유로 지급이 불가합니다.

■ 지급 내용
─────────────────────────────────────────────────────────────
지급 금액  : {decision.total_payment:,}원
지급 예정일: {_payment_due_text(ctx, decision.reviewer_flag)}

■ 지급 불가 담보 안내
─────────────────────────────────────────────────────────────{denied_customer_lines}

■ 이의신청 방법
─────────────────────────────────────────────────────────────
지급 불가 결정에 이의가 있으신 경우:
  1. 회사 내부 재심사 요청 (결정일로부터 30일 이내)
  2. 금융감독원 분쟁조정 신청: 1332 (90일 이내)

■ 문의처
─────────────────────────────────────────────────────────────
보험금 관련 문의: 고객센터 1588-XXXX (평일 09:00~18:00)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{today}
(주)한국생명보험  보험금지급팀
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    (out_dir / "고객안내문_일부지급.txt").write_text(customer_content, encoding="utf-8")
    print(f"    → 고객안내문_일부지급.txt")


# ══════════════════════════════════════════════════════════════════
# 부지급 문서
# ══════════════════════════════════════════════════════════════════

def _write_denial_documents(
    decision: ClaimDecision, ctx: ClaimContext, out_dir: Path
) -> None:
    today = datetime.now().strftime("%Y년 %m월 %d일")

    fraud_notice = ""
    if decision.fraud_investigation_flag:
        fraud_notice = f"""
■ 보험사기 조사 안내 (내부 처리)
─────────────────────────────────────────────────────────────
🚨 {decision.fraud_investigation_reason}
   → 사기조사팀 통보 및 추가 조사 진행 예정
"""

    rules_lines = "\n".join(
        f"  {r.rule_id:<12} [{r.status:<7}]  {r.reason[:55]}"
        + (f"\n                          약관: {r.evidence.get('policy_clause', '')}" if r.evidence.get('policy_clause') else "")
        for r in decision.applied_rules
    )

    denial_content = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                      보 험 금  부 지 급  결 의 서
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
결의일자  : {today}
청구번호  : {decision.claim_id}
보험계약번호: {ctx.policy_no}
피보험자  : {_get_insured_name(ctx)}

■ 부지급 결정
─────────────────────────────────────────────────────────────
판정 결과  : 부지급
지급 보험금: 0원

■ 부지급 사유
─────────────────────────────────────────────────────────────
사유    : {decision.denial_reason or "사유 확인 중"}
약관 근거: {decision.policy_clause or "해당 조항 확인 중"}

■ 적용 룰 (감사 추적)
─────────────────────────────────────────────────────────────
{rules_lines}
{fraud_notice}
■ 이의신청 안내
─────────────────────────────────────────────────────────────
본 결정에 이의가 있으신 경우 결정 통보일로부터 90일 이내에
금융감독원 분쟁조정위원회에 조정을 신청하실 수 있습니다.
  - 금융감독원 분쟁조정센터: 1332 (평일 09:00~18:00)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
담당자 확인: ________________  (서명)       결재일: {today}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    (out_dir / "부지급결의서.txt").write_text(denial_content, encoding="utf-8")
    print(f"    → 부지급결의서.txt")

    # 고객 안내문 (쉬운 말로 작성)
    customer_denial = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
              보험금 부지급 결정 안내
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
안녕하세요, {_get_insured_name(ctx)} 고객님.

귀하께서 청구하신 보험금({decision.claim_id})에 대하여
아래와 같은 사유로 부지급 결정을 내렸습니다.

■ 부지급 사유
─────────────────────────────────────────────────────────────
{decision.denial_reason or ""}

적용 약관: {decision.policy_clause or ""}

■ 이의신청 방법
─────────────────────────────────────────────────────────────
이 결정에 동의하지 않으시는 경우, 다음 방법으로 이의를 제기하실 수 있습니다.

  1. 회사 내부 심의 재청구
     - 새로운 의학적 증거자료를 첨부하여 재심사 요청 가능
     - 신청 기한: 결정 통보일로부터 30일 이내

  2. 금융감독원 분쟁조정 신청
     - 금융감독원 분쟁조정센터: 국번없이 1332
     - 신청 기한: 결정 통보일로부터 90일 이내

  3. 소송 제기
     - 관할 법원에 소를 제기하실 수 있습니다.

■ 문의처
─────────────────────────────────────────────────────────────
보험금 관련 문의: 고객센터 1588-XXXX (평일 09:00~18:00)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{today}
(주)한국생명보험  보험금지급팀
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    (out_dir / "고객안내문_부지급.txt").write_text(customer_denial, encoding="utf-8")
    print(f"    → 고객안내문_부지급.txt")


# ══════════════════════════════════════════════════════════════════
# 보류 문서
# ══════════════════════════════════════════════════════════════════

def _write_pending_documents(
    decision: ClaimDecision, ctx: ClaimContext, out_dir: Path
) -> None:
    today = datetime.now().strftime("%Y년 %m월 %d일")
    missing_list = "\n".join(
        f"  {i+1}. {doc}" for i, doc in enumerate(decision.missing_docs)
    ) if decision.missing_docs else "  (목록 확인 중)"

    pending_content = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                보 험 금  서 류  보 완  요 청
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
발송일자  : {today}
청구번호  : {decision.claim_id}
보험계약번호: {ctx.policy_no}
피보험자  : {_get_insured_name(ctx)}

■ 서류 보완 요청
─────────────────────────────────────────────────────────────
안녕하세요, {_get_insured_name(ctx)} 고객님.

귀하의 보험금 청구 건({decision.claim_id})을 심사하는 과정에서
아래 서류가 미제출된 것을 확인하였습니다.

■ 추가 제출 필요 서류
─────────────────────────────────────────────────────────────
{missing_list}

■ 제출 안내
─────────────────────────────────────────────────────────────
  제출 기한 : 본 통보 수령일로부터 30일 이내
              (소멸시효 기준: 청구일로부터 3년 이내)

  제출 방법 :
    1. 온라인: 회사 홈페이지 → 보험금청구 → 서류 추가 제출
    2. 이메일: claims@sample-insurance.co.kr
    3. 팩스: 02-XXXX-XXXX
    4. 방문: 가까운 영업점 또는 고객센터

  ※ 기한 내 서류가 제출되지 않을 경우 청구 취하로 처리될 수 있습니다.

■ 문의처
─────────────────────────────────────────────────────────────
보험금 관련 문의: 고객센터 1588-XXXX (평일 09:00~18:00)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{today}
(주)한국생명보험  보험금지급팀
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    (out_dir / "보류통보서.txt").write_text(pending_content, encoding="utf-8")
    print(f"    → 보류통보서.txt")


# ══════════════════════════════════════════════════════════════════
# 처리 로그 (JSON)
# ══════════════════════════════════════════════════════════════════

def _write_processing_log(
    decision: ClaimDecision, ctx: ClaimContext, out_dir: Path
) -> None:
    def _serialize(obj: Any) -> Any:
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)

    log = {
        "log_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "claim_summary": {
            "claim_id":             ctx.claim_id,
            "policy_no":            ctx.policy_no,
            "claim_date":           ctx.claim_date,
            "accident_date":        ctx.accident_date,
            "kcd_code":             ctx.kcd_code,
            "diagnosis":            ctx.diagnosis,
            "hospital_days":        ctx.hospital_days,
            "surgery_name":         ctx.surgery_name,
            "surgery_code":         ctx.surgery_code,
            "covered_self_pay":     ctx.covered_self_pay,
            "non_covered_amount":   ctx.non_covered_amount,
            "submitted_doc_types":  ctx.submitted_doc_types,
            "claimed_coverage_types": ctx.claimed_coverage_types,
            "parse_confidence_min": ctx.parse_confidence_min,
        },
        "decision_summary": {
            "decision":       decision.decision,
            "total_payment":  decision.total_payment,
            "reviewer_flag":  decision.reviewer_flag,
            "fraud_flag":     decision.fraud_investigation_flag,
            "denial_reason":  decision.denial_reason,
            "policy_clause":  decision.policy_clause,
            "missing_docs":   decision.missing_docs,
        },
        "rule_trace": [
            {
                "rule_id":  r.rule_id,
                "status":   r.status,
                "reason":   r.reason,
                "value":    r.value,
                "evidence": r.evidence,
            }
            for r in decision.applied_rules
        ],
        "parsed_documents": [
            {
                "doc_type":     doc.doc_type,
                "parse_mode":   doc.parse_mode,
                "confidence":   doc.confidence,
                "extracted_fields": list(doc.fields.keys()),
                "parse_errors": doc.parse_errors,
            }
            for doc in ctx.raw_documents
        ],
    }

    # A-8: 신뢰도 + 라우팅 정보 추가
    if decision.confidence:
        log["confidence"] = decision.confidence.to_dict()
    routing = getattr(decision, "review_routing", None)
    if routing:
        log["review_routing"] = routing.to_dict()

    path = out_dir / "처리로그.json"
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2, default=_serialize),
                    encoding="utf-8")
    print(f"    → 처리로그.json")


def _payment_due_text(ctx: ClaimContext, reviewer_flag: bool) -> str:
    exp = add_business_days_iso(ctx.claim_date, 3)
    if reviewer_flag:
        return f"담당자 검토 완료 후 3영업일 이내 (검토 완료일 기준 재산정)"
    if exp:
        return f"{exp} (접수일 {ctx.claim_date} 기준 3영업일 후, 토·일·공휴일 제외)"
    return "접수 후 3영업일 이내 (접수일 확인 필요)"


def _write_staff_briefing(
    decision: ClaimDecision, ctx: ClaimContext, out_dir: Path
) -> None:
    """
    보상 직원용 — 절차·규정·산식·금액·검토사항을 한 문서에 정리.
    """
    expected = add_business_days_iso(ctx.claim_date, 3)
    workflow = """① COM (계약·면책기간·KCD 절대면책·중복·단기가입·반복청구)
② 조건부면책(F/Q계열) 플래그
③ DOC (필수 서류 완비)
④보별 산정: IND(입원일당·면책4일/질병·1일/재해) / SIL(실손 세대·4세대 비급여항목 한도) / SUR(수술종·KCD후보 추론 시 검토)
⑤ FRD-007 비급여 비중, CONF-001 파싱 신뢰도"""

    regulation_refs = """docs/insurance_standards/01_실손의료보험_세대별_기준.md
docs/insurance_standards/02_입원일당_지급기준.md (면책일수)
docs/insurance_standards/03_수술비_분류기준.md
docs/insurance_standards/05_보험금지급기한_및_법적근거.md
data/reference/billing_codes.json (4세대 비급여 3대 항목 한도)"""

    breakdown_txt = ""
    for rid, ev in decision.breakdown.items():
        amt = ev.get("benefit_amount", 0)
        formula = ev.get("formula", "")
        breakdown_txt += f"\n  • {rid}: {amt:,}원\n    산식/근거: {formula}\n"
        if ev.get("sil_4gen_cap_details"):
            breakdown_txt += f"    4세대 한도: {'; '.join(ev['sil_4gen_cap_details'])}\n"
        if rid == "IND-001" and ev.get("coverages_applied"):
            for c in ev["coverages_applied"]:
                breakdown_txt += (
                    f"      - {c.get('coverage_name')}: 입원{c.get('hospital_days_claimed')}일 "
                    f"→ 면책{c.get('waiting_days')}일 차감 → 지급{c.get('payable_days')}일 × "
                    f"{c.get('daily_benefit', 0):,}원\n"
                )
        if rid == "SUR-001" and ev.get("inferred_from_kcd"):
            breakdown_txt += "      ⚠ KCD 기준 분류표 후보로 추정 — 수술확인서와 대조 필수\n"

    rules_trace = "\n".join(
        f"  [{r.status:7}] {r.rule_id}: {r.reason[:70]}"
        + (f"\n            약관: {r.evidence.get('policy_clause', '')}" if r.evidence.get('policy_clause') else "")
        for r in decision.applied_rules
    )

    billing_note = ""
    if ctx.billing_items:
        billing_note = f"\n■ 진료비세부내역서 항목 ({len(ctx.billing_items)}건, 비급여 한도 매핑용)\n"
        for b in ctx.billing_items[:25]:
            nc = "비급여" if b.get("is_noncovered") else "급여"
            billing_note += f"  {b.get('item_code')} {nc} {b.get('amount', 0):,}원\n"
        if len(ctx.billing_items) > 25:
            billing_note += f"  … 외 {len(ctx.billing_items) - 25}건\n"

    content = f"""━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
           보상 직원용 — 산정 절차·규정·금액 요약 (Phase 2)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
청구번호: {decision.claim_id}  |  계약: {ctx.policy_no}  |  접수일: {ctx.claim_date}
KCD: {ctx.kcd_code}  |  진단: {ctx.diagnosis}
청구 담보: {', '.join(ctx.claimed_coverage_types) or '(청구서 미체크 시 계약 담보 기준)'}

■ 1. 본 건 처리 워크플로우 (룰 실행 순서)
─────────────────────────────────────────────────────────────
{workflow}

■ 2. 적용 규정·참고 문서 (저장소 경로)
─────────────────────────────────────────────────────────────
{regulation_refs}

■ 3. 판정·지급 요약
─────────────────────────────────────────────────────────────
  판정     : {decision.decision}
  지급 합계: {decision.total_payment:,}원
  지급 예정일(참고): {expected or '—'} ({business_days_explanation(ctx.claim_date, 3)})

■ 4. 담보별 산정 내역 (금액·산식)
─────────────────────────────────────────────────────────────
{breakdown_txt or '  (해당 담보 지급 없음 또는 보류/부지급)'}
{_format_denial_coverages_staff(decision)}
■ 5. 전 룰 실행 로그
─────────────────────────────────────────────────────────────
{rules_trace}
{billing_note}
■ 6. 담당자 확인 사항
─────────────────────────────────────────────────────────────
  검토 플래그: {'예 — ' + (decision.reviewer_reason or '') if decision.reviewer_flag else '아니오 (자동 지급 가능)'}
  부지급/보류 사유: {decision.denial_reason or decision.missing_docs or '—'}
  사기조사: {decision.fraud_investigation_reason or '—'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
본 문서는 AI Agent 자동 생성물입니다. 최종 지급은 내부 규정 및 승인 절차를 따르십시오.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    (out_dir / "보상직원_산정요약.txt").write_text(content, encoding="utf-8")
    print(f"    → 보상직원_산정요약.txt")


# ══════════════════════════════════════════════════════════════════
# 유틸리티
# ══════════════════════════════════════════════════════════════════

def _format_denial_coverages_staff(decision: ClaimDecision) -> str:
    """일부지급 시 지급 불가 담보 섹션 포맷. 비어있으면 빈 문자열."""
    if not decision.denial_coverages:
        return ""
    lines = "\n■ 4-1. 지급 불가 담보 (일부지급 사유)\n"
    lines += "─────────────────────────────────────────────────────────────\n"
    for dc in decision.denial_coverages:
        rid = dc.get("rule_id", "")
        cov = dc.get("coverage_type", "")
        reason = dc.get("reason", "")
        ev = dc.get("evidence", {})
        clause = ev.get("policy_clause", "")
        lines += f"  • {rid} ({cov}): {reason[:70]}\n"
        if clause:
            lines += f"    약관 근거: {clause}\n"
    return lines + "\n"

def _get_insured_name(ctx: ClaimContext) -> str:
    """계약 DB에서 피보험자명 조회. 없으면 policy_no 반환."""
    try:
        from src.utils.data_loader import get_contract
        contract = get_contract(ctx.policy_no)
        if contract:
            return contract.get("insured", {}).get("name", ctx.policy_no)
    except Exception:
        pass
    return ctx.policy_no
