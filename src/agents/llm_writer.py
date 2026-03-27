"""
LLM 기반 결과 문서 생성 — Agent 모드 전용.

기존 result_writer.py 의 템플릿 기반 문서를 LLM이 자연어로 재작성한다.
LLM 실패 시 기존 result_writer.py 로 자동 폴백.

공개 API:
  write_results_with_llm(decision, ctx, confidence) → Path

설계 원칙:
  - 기존 result_writer.py 를 먼저 호출하여 기본 문서 생성.
  - LLM으로 고객안내문만 자연어 개선 (결의서·처리로그는 정형 유지).
  - 부지급/일부지급: 거절 사유를 약관 인용으로 상세 설명.
  - 신뢰도 정보를 보상직원_산정요약.txt 에 포함.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.schemas import ClaimDecision, ClaimContext
from config.settings import OUTPUT_DIR

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 시스템 프롬프트
# ══════════════════════════════════════════════════════════════════

_CUSTOMER_LETTER_PROMPT = """당신은 한국 보험사의 고객 커뮤니케이션 전문가입니다.

보험금 심사 결과를 고객에게 안내하는 편지를 작성하세요.

## 작성 원칙
1. 정중하고 따뜻한 어조
2. 결정 사유를 명확하고 이해하기 쉽게 설명
3. 부지급/일부지급 시 약관 조항을 인용하되 알기 쉬운 말로 풀어서 설명
4. 이의신청 방법을 반드시 안내 (부지급/일부지급)
5. 금액은 천원 단위 구분 표시 (예: 1,200,000원)
6. 문의처 (고객센터 1588-XXXX) 안내

## 형식
- 제목: 보험금 [지급/부지급/일부지급/보류] 결정 안내
- 인사말로 시작
- 결정 내용 → 사유 → 문의처 순서
- 마무리 인사
- 회사명: (주)한국생명보험 보험금지급팀"""

_STAFF_BRIEFING_PROMPT = """당신은 보험 심사 결과를 직원에게 브리핑하는 전문가입니다.

심사 결과의 핵심 포인트를 간결하게 요약하세요.

## 작성 원칙
1. 핵심 판정 사유를 첫 줄에 (한 문장)
2. 주의 사항이나 리스크 요소
3. 담보별 산정 내역 (금액, 산식)
4. AI 신뢰도 + 교차검증 결과
5. 직원이 추가 확인해야 할 사항

한국어로 작성하고, 불필요한 장식 없이 간결하게."""


# ══════════════════════════════════════════════════════════════════
# 메인 함수
# ══════════════════════════════════════════════════════════════════

def write_results_with_llm(
    decision: ClaimDecision,
    ctx: ClaimContext,
    confidence=None,
) -> Path:
    """
    LLM으로 결과 문서를 생성.

    1. 기존 result_writer 로 기본 문서 생성 (결의서, 처리로그 등)
    2. LLM으로 고객안내문 자연어 개선
    3. 보상직원_산정요약.txt 에 신뢰도 정보 추가

    Args:
        decision:   최종 판정 결과
        ctx:        청구 컨텍스트
        confidence: ConfidenceScore (Agent 모드에서만 존재)

    Returns:
        출력 디렉토리 경로
    """
    # 1. 기존 템플릿 문서 먼저 생성
    from src.agents.result_writer import write_results
    out_dir = write_results(decision, ctx)

    # 2. LLM 으로 고객안내문 개선
    try:
        _enhance_customer_letter(decision, ctx, out_dir)
    except Exception as exc:
        logger.warning("고객안내문 LLM 개선 실패 (기존 유지): %s", exc)

    # 3. 보상직원_산정요약.txt 에 신뢰도 추가
    try:
        _enhance_staff_briefing(decision, ctx, confidence, out_dir)
    except Exception as exc:
        logger.warning("직원 브리핑 LLM 개선 실패 (기존 유지): %s", exc)

    return out_dir


# ══════════════════════════════════════════════════════════════════
# 고객안내문 LLM 개선
# ══════════════════════════════════════════════════════════════════

def _enhance_customer_letter(
    decision: ClaimDecision,
    ctx: ClaimContext,
    out_dir: Path,
) -> None:
    """고객안내문을 LLM으로 자연어 개선."""
    from src.llm.client import chat, is_available
    from config.settings import AGENT_LLM_MODEL

    if not is_available():
        return

    # 기존 안내문 파일 찾기
    letter_files = [
        "고객안내문.txt",
        "고객안내문_일부지급.txt",
        "고객안내문_부지급.txt",
    ]
    existing_letter = None
    existing_path = None
    for fname in letter_files:
        fpath = out_dir / fname
        if fpath.exists():
            existing_letter = fpath.read_text(encoding="utf-8")
            existing_path = fpath
            break

    if not existing_letter:
        return

    # 약관 근거 수집
    clause_info = []
    for rule in decision.applied_rules:
        if rule.evidence.get("policy_clause"):
            clause_info.append({
                "rule_id": rule.rule_id,
                "status": rule.status,
                "policy_clause": rule.evidence.get("policy_clause", ""),
                "clause_title": rule.evidence.get("clause_title", ""),
                "clause_text": rule.evidence.get("clause_text", ""),
            })

    denial_info = []
    if decision.denial_reason:
        denial_info.append(decision.denial_reason)
    for dc in decision.denial_coverages:
        denial_info.append(dc.get("reason", ""))

    user_msg = (
        f"## 심사 결과\n"
        f"- 판정: {decision.decision}\n"
        f"- 금액: {decision.total_payment:,}원\n"
        f"- 청구번호: {decision.claim_id}\n"
        f"- 피보험자: {ctx.policy_no}\n"
        f"- 진단명: {ctx.diagnosis}\n\n"
    )
    if denial_info:
        user_msg += f"## 거절/불가 사유\n" + "\n".join(f"- {r}" for r in denial_info) + "\n\n"
    if clause_info:
        user_msg += f"## 약관 근거\n```json\n{json.dumps(clause_info, ensure_ascii=False, indent=2)}\n```\n\n"
    user_msg += (
        f"## 기존 안내문 (참고)\n{existing_letter[:2000]}\n\n"
        f"위 내용을 바탕으로 고객안내문을 개선하세요. "
        f"기존 형식은 참고하되, 더 자연스럽고 이해하기 쉽게 재작성하세요."
    )

    response = chat(
        messages=[
            {"role": "system", "content": _CUSTOMER_LETTER_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        model=AGENT_LLM_MODEL,
        temperature=0.3,
        max_tokens=4096,
    )

    improved = response.choices[0].message.content
    if improved and len(improved) > 100:
        # LLM 개선 버전으로 덮어쓰기
        existing_path.write_text(improved, encoding="utf-8")
        logger.info("고객안내문 LLM 개선 완료: %s", existing_path.name)


# ══════════════════════════════════════════════════════════════════
# 보상직원 브리핑 LLM 개선 + 신뢰도 추가
# ══════════════════════════════════════════════════════════════════

def _enhance_staff_briefing(
    decision: ClaimDecision,
    ctx: ClaimContext,
    confidence,
    out_dir: Path,
) -> None:
    """보상직원_산정요약.txt 에 AI 신뢰도 + LLM 브리핑 추가."""
    briefing_path = out_dir / "보상직원_산정요약.txt"

    existing_content = ""
    if briefing_path.exists():
        existing_content = briefing_path.read_text(encoding="utf-8")

    # 신뢰도 섹션 추가
    confidence_section = ""
    if confidence:
        confidence_section = f"""
■ AI 신뢰도 분석
─────────────────────────────────────────────────────────────
  서류 파싱 신뢰도  : {confidence.parse_confidence:.0%}
  룰엔진 판정 신뢰도: {confidence.rule_confidence:.0%}
  LLM 판단 신뢰도   : {confidence.llm_confidence:.0%}
  교차검증 일치도   : {confidence.cross_validation:.0%}
  ─────────────────────────────
  종합 신뢰도       : {confidence.overall:.0%}
  리스크 등급       : {confidence.risk_level}
"""

    # A-7: 심사 라우팅 정보
    routing_section = ""
    routing = getattr(decision, "review_routing", None)
    if routing:
        checklist_text = ""
        for i, item in enumerate(routing.checklist, 1):
            checklist_text += f"  {i}. {item}\n"
        routing_section = f"""
■ 심사 라우팅 (A-7)
─────────────────────────────────────────────────────────────
  라우팅 액션       : {routing.action}
  우선순위          : {routing.priority}
  심사 담당         : {routing.reviewer_level}
  예상 소요시간     : {routing.estimated_minutes}분
  라우팅 사유       : {routing.routing_reason}

  [체크리스트]
{checklist_text}
"""

    # LLM 브리핑 생성 시도
    llm_briefing = ""
    try:
        from src.llm.client import chat, is_available
        from config.settings import AGENT_LLM_MODEL

        if is_available():
            summary_data = {
                "decision": decision.decision,
                "total_payment": decision.total_payment,
                "breakdown": decision.breakdown,
                "denial_reason": decision.denial_reason,
                "denial_coverages": decision.denial_coverages,
                "reviewer_flag": decision.reviewer_flag,
                "reviewer_reason": decision.reviewer_reason,
                "kcd_code": ctx.kcd_code,
                "diagnosis": ctx.diagnosis,
                "hospital_days": ctx.hospital_days,
            }
            if confidence:
                summary_data["confidence"] = confidence.to_dict()

            response = chat(
                messages=[
                    {"role": "system", "content": _STAFF_BRIEFING_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"아래 심사 결과를 직원 브리핑으로 요약하세요:\n\n"
                            f"```json\n{json.dumps(summary_data, ensure_ascii=False, indent=2)}\n```"
                        ),
                    },
                ],
                model=AGENT_LLM_MODEL,
                temperature=0.2,
                max_tokens=2048,
            )
            llm_briefing = f"""
■ AI 분석 요약
─────────────────────────────────────────────────────────────
{response.choices[0].message.content}
"""
    except Exception as exc:
        logger.debug("LLM 브리핑 생성 실패 (무시): %s", exc)

    # 기존 내용 + 신뢰도 + 라우팅 + LLM 브리핑 합치기
    enhanced = existing_content.rstrip()
    if confidence_section:
        enhanced += "\n" + confidence_section
    if routing_section:
        enhanced += "\n" + routing_section
    if llm_briefing:
        enhanced += "\n" + llm_briefing

    enhanced += f"""
─────────────────────────────────────────────────────────────
생성 모드: AI Agent (LangGraph)  |  생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
─────────────────────────────────────────────────────────────
"""

    briefing_path.write_text(enhanced, encoding="utf-8")
    logger.info("보상직원 브리핑 개선 완료")
