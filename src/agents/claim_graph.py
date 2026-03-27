"""
LangGraph 기반 보험 심사 Agent 그래프.

기존 룰 기반 파이프라인(orchestrator.py)을 LangGraph StateGraph로 재구성.
각 노드가 하나의 심사 단계를 담당하며, 룰엔진 교차검증으로 안전성을 확보한다.

그래프 구조:
  [parse_docs] → [build_context] → [lookup_contract] → [search_policy]
       → [llm_reason] → [rule_validate] → [finalize] → [write_results]

공개 API:
  run_agent_claim(claim_id, policy_no, claim_date, doc_dir, on_progress)
      → ClaimDecision

설계 원칙:
  - 각 노드는 AgentState 의 일부를 읽고 업데이트.
  - LLM 실패 시 룰엔진 결과로 자동 폴백.
  - on_progress 콜백으로 UI에 진행 상태 전달.
  - 기존 ClaimDecision 스키마를 반환 (호환성 유지).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from src.schemas import ClaimContext, ClaimDecision

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 시스템 프롬프트 — 보험 심사 전문가
# ══════════════════════════════════════════════════════════════════

_CLAIM_REVIEW_SYSTEM_PROMPT = """당신은 한국 보험사의 보험금 심사 전문가입니다.

주어진 청구 정보, 계약 정보, 약관 조항을 분석하여 보험금 지급 여부를 판정하세요.

## 판정 유형
- 지급: 모든 조건 충족, 보험금 지급
- 부지급: 면책 사유 해당 또는 계약 무효
- 보류: 서류 미비로 판단 불가
- 검토필요: 사기 의심, 반복 청구 등 담당자 확인 필요
- 일부지급: 일부 담보만 지급 가능 (나머지는 면책/미가입)

## 심사 기준
1. 계약 유효성: 계약 상태가 "active"인지 확인
2. 면책기간: 질병 4일, 재해 1일 면책 적용 여부
3. KCD 면책: 상병코드가 면책 사유에 해당하는지
4. 담보별 산정: 입원일당(IND), 실손의료비(SIL), 수술비(SUR)
5. 비급여 비중: 60% 초과 시 검토 플래그

## 출력 형식
반드시 아래 JSON 형식으로 답변하세요:
{
  "decision": "지급|부지급|보류|검토필요|일부지급",
  "total_payment": 금액(정수),
  "reasoning": "판정 근거 (약관 조항 인용 포함, 한국어 3-5문장)",
  "confidence": 0.0~1.0,
  "breakdown": {
    "IND-001": {"amount": 금액, "formula": "산식 설명"},
    "SIL-001": {"amount": 금액, "formula": "산식 설명"},
    "SUR-001": {"amount": 금액, "formula": "산식 설명"}
  },
  "denial_reasons": ["거절 사유1", ...],
  "risk_flags": ["위험 플래그1", ...]
}"""


# ══════════════════════════════════════════════════════════════════
# 그래프 노드 함수들
# ══════════════════════════════════════════════════════════════════

def _node_parse_docs(state: dict) -> dict:
    """노드 1: 서류 파싱 (Agent 모드 — regex + LLM 교차검증)."""
    from src.agents.parse_agent import parse_with_agent

    doc_dir = state["doc_dir"]
    documents = parse_with_agent(doc_dir, regex_mode="regex")

    parse_errors = []
    for doc in documents:
        parse_errors.extend(doc.parse_errors)

    return {
        "documents": documents,
        "parse_errors": parse_errors,
        "current_step": "서류 파싱 완료",
        "progress_messages": state.get("progress_messages", []) + [
            f"📄 서류 {len(documents)}건 파싱 완료",
        ],
    }


def _node_build_context(state: dict) -> dict:
    """노드 2: ClaimContext 조립."""
    from src.agents.orchestrator import build_claim_context

    ctx = build_claim_context(
        claim_id=state["claim_id"],
        policy_no=state["policy_no"],
        claim_date=state["claim_date"],
        documents=state["documents"],
    )

    return {
        "context": ctx,
        "current_step": "컨텍스트 조립 완료",
        "progress_messages": state.get("progress_messages", []) + [
            f"📋 청구 정보 조합 완료 (KCD: {ctx.kcd_code})",
        ],
    }


def _node_lookup_contract(state: dict) -> dict:
    """노드 3: 계약·청구이력 조회."""
    from src.agents.tools import lookup_contract

    result = lookup_contract(state["policy_no"])

    return {
        "contract_info": result.get("contract"),
        "claims_history": result.get("claims_history"),
        "current_step": "계약 조회 완료",
        "progress_messages": state.get("progress_messages", []) + [
            f"📋 계약 조회 완료 (발견: {result.get('contract_found', False)})",
        ],
    }


def _node_search_policy(state: dict) -> dict:
    """노드 4: RAG 약관 검색."""
    from src.agents.tools import search_policy

    ctx = state["context"]
    queries = []

    # KCD + 진단명 검색
    if ctx.kcd_code and ctx.kcd_code != "UNKNOWN":
        queries.append(f"{ctx.kcd_code} {ctx.diagnosis} 보험금 지급 기준")

    # 담보별 검색
    for cov_type in ctx.claimed_coverage_types or ["IND", "SIL"]:
        cov_names = {"IND": "입원일당", "SIL": "실손의료비", "SUR": "수술비"}
        queries.append(f"{cov_names.get(cov_type, cov_type)} 면책기간 지급 기준")

    # 수술 검색
    if ctx.surgery_name:
        queries.append(f"{ctx.surgery_name} 수술비 지급 기준")

    # 쿼리 실행 & 결과 합침
    all_chunks = []
    for q in queries[:5]:  # 최대 5개 쿼리
        result = search_policy(q, top_k=3)
        all_chunks.extend(result.get("chunks", []))

    # 중복 제거 (text 기준)
    seen_texts: set[str] = set()
    unique_chunks = []
    for chunk in all_chunks:
        text_key = chunk.get("text", "")[:100]
        if text_key not in seen_texts:
            seen_texts.add(text_key)
            unique_chunks.append(chunk)

    return {
        "rag_results": unique_chunks[:10],  # 최대 10개
        "current_step": "약관 검색 완료",
        "progress_messages": state.get("progress_messages", []) + [
            f"📚 약관 검색 완료 ({len(unique_chunks)}건 발견)",
        ],
    }


def _node_llm_reason(state: dict) -> dict:
    """노드 5: LLM 심사 추론."""
    from src.llm.client import chat, is_available
    from config.settings import AGENT_LLM_MODEL

    if not is_available():
        return {
            "llm_reasoning": "LLM 미사용 — 룰엔진 결과 사용",
            "llm_decision": "",
            "llm_amount": 0,
            "llm_confidence": 0.0,
            "current_step": "LLM 추론 스킵",
            "errors": state.get("errors", []) + ["LLM API 미사용"],
        }

    ctx = state["context"]
    contract = state.get("contract_info", {})
    rag_results = state.get("rag_results", [])

    # 약관 검색 결과를 텍스트로 조합
    policy_text = ""
    if rag_results:
        policy_text = "\n\n".join([
            f"[약관 조항 - {r.get('source', '')} / {r.get('section', '')}]\n{r.get('text', '')}"
            for r in rag_results[:5]
        ])

    # 청구 정보 요약
    claim_info = {
        "claim_id": ctx.claim_id,
        "policy_no": ctx.policy_no,
        "claim_date": ctx.claim_date,
        "kcd_code": ctx.kcd_code,
        "diagnosis": ctx.diagnosis,
        "hospital_days": ctx.hospital_days,
        "admission_date": ctx.admission_date,
        "discharge_date": ctx.discharge_date,
        "surgery_name": ctx.surgery_name,
        "covered_self_pay": ctx.covered_self_pay,
        "non_covered_amount": ctx.non_covered_amount,
        "claimed_coverages": ctx.claimed_coverage_types,
        "submitted_docs": ctx.submitted_doc_types,
        "accident_date": ctx.accident_date,
    }

    # 계약 정보 요약 (민감 정보 제거)
    contract_summary = {}
    if contract:
        contract_summary = {
            "status": contract.get("status"),
            "start_date": contract.get("start_date"),
            "coverages": contract.get("coverages", []),
            "product_name": contract.get("product_name"),
        }

    user_message = (
        f"## 청구 정보\n```json\n{json.dumps(claim_info, ensure_ascii=False, indent=2)}\n```\n\n"
        f"## 계약 정보\n```json\n{json.dumps(contract_summary, ensure_ascii=False, indent=2)}\n```\n\n"
    )
    if policy_text:
        user_message += f"## 관련 약관 조항\n{policy_text}\n\n"

    user_message += "위 정보를 바탕으로 보험금 지급 여부를 판정하세요."

    try:
        response = chat(
            messages=[
                {"role": "system", "content": _CLAIM_REVIEW_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            model=AGENT_LLM_MODEL,
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        result = json.loads(content)

        return {
            "llm_reasoning": result.get("reasoning", ""),
            "llm_decision": result.get("decision", ""),
            "llm_amount": result.get("total_payment", 0),
            "llm_confidence": result.get("confidence", 0.5),
            "llm_confidence_factors": result.get("confidence_factors", {}),  # A-4
            "llm_breakdown": result.get("breakdown", {}),  # A-3
            "current_step": "LLM 추론 완료",
            "progress_messages": state.get("progress_messages", []) + [
                f"🤖 AI 심사 추론 완료 (판정: {result.get('decision', '?')})",
            ],
        }

    except Exception as exc:
        logger.error("LLM 심사 추론 실패: %s", exc)
        return {
            "llm_reasoning": f"LLM 추론 실패: {exc}",
            "llm_decision": "",
            "llm_amount": 0,
            "llm_confidence": 0.0,
            "current_step": "LLM 추론 실패",
            "errors": state.get("errors", []) + [f"LLM 추론 실패: {exc}"],
        }


def _node_rule_validate(state: dict) -> dict:
    """노드 6: 룰엔진 실행 + 간단 교차검증 요약.

    상세 교차검증은 finalize 노드에서 validator.py를 통해 수행.
    여기서는 LLM vs 룰엔진 판정 불일치만 빠르게 감지.
    """
    from src.rules.rule_engine import run_rules

    ctx = state["context"]
    rule_decision = run_rules(ctx)

    # 빠른 판정 불일치 요약 (상세 비교는 finalize에서)
    validation_notes = []
    llm_decision = state.get("llm_decision", "")

    if llm_decision and llm_decision != rule_decision.decision:
        validation_notes.append(
            f"⚠️ 판정 불일치: AI={llm_decision} vs 룰={rule_decision.decision}"
        )

    return {
        "rule_decision": rule_decision,
        "validation_notes": validation_notes,
        "current_step": "교차검증 완료",
        "progress_messages": state.get("progress_messages", []) + [
            f"✅ 룰엔진 교차검증 완료"
            + (f" ({len(validation_notes)}건 불일치)" if validation_notes else " (일치)"),
        ],
    }


def _node_finalize(state: dict) -> dict:
    """노드 7: 최종 판정 확정 + 교차검증 + 신뢰도 산출."""
    from src.agents.validator import validate_decisions

    rule_decision: ClaimDecision = state["rule_decision"]
    llm_decision_str = state.get("llm_decision", "")
    llm_confidence = state.get("llm_confidence", 0.0)
    llm_confidence_factors = state.get("llm_confidence_factors", {})  # A-4
    llm_reasoning = state.get("llm_reasoning", "")
    llm_amount = state.get("llm_amount", 0)
    llm_breakdown = state.get("llm_breakdown", {})  # A-3
    ctx: ClaimContext = state["context"]
    parse_errors = state.get("parse_errors", [])

    # ── 최종 판정: 룰엔진 결과를 기본으로, LLM 보강 ──
    final_decision = rule_decision

    # LLM reasoning 을 applied_rules 의 evidence 에 추가
    if llm_reasoning:
        for rule in final_decision.applied_rules:
            rule.evidence["llm_reasoning"] = llm_reasoning
            if llm_decision_str:
                rule.evidence["llm_decision"] = llm_decision_str

    # ── 교차검증 + 신뢰도 (validator.py 위임) ──
    llm_result = {
        "decision": llm_decision_str,
        "total_payment": llm_amount,
        "confidence": llm_confidence,
        "confidence_factors": llm_confidence_factors,  # A-4
        "reasoning": llm_reasoning,
        "breakdown": llm_breakdown,  # A-3: 담보별 교차검증용
    }

    validation = validate_decisions(
        llm_result=llm_result,
        rule_decision=rule_decision,
        ctx=ctx,
        parse_mismatches=parse_errors,
    )

    confidence = validation.confidence

    # reviewer_flag 전파 (validator 가 review_required 판단)
    if validation.review_required and not final_decision.reviewer_flag:
        final_decision.reviewer_flag = True
        existing_reason = final_decision.reviewer_reason or ""
        new_reasons = " | ".join(validation.review_reasons)
        final_decision.reviewer_reason = (
            existing_reason + " | " + new_reasons
        ).strip(" | ")

    # fraud_risk 전파
    if validation.fraud_risk and not final_decision.fraud_investigation_flag:
        final_decision.fraud_investigation_flag = True
        final_decision.fraud_investigation_reason = " / ".join(
            validation.fraud_reasons
        )

    # confidence 를 ClaimDecision 에 주입
    final_decision.confidence = confidence

    # A-7: 심사 라우팅 결정
    from src.agents.validator import determine_review_routing
    routing = determine_review_routing(confidence, final_decision, validation)
    final_decision.review_routing = routing

    routing_msg = f"🔀 심사라우팅: {routing.action} → {routing.reviewer_level}"
    if routing.priority in ("urgent", "critical"):
        routing_msg += f" (⚡ {routing.priority.upper()})"

    return {
        "final_decision": final_decision,
        "confidence": confidence,
        "validation_result": validation,
        "review_routing": routing,
        "current_step": "판정 확정 완료",
        "progress_messages": state.get("progress_messages", []) + [
            f"📊 최종 판정: {final_decision.decision} "
            f"(신뢰도: {confidence.overall:.0%}, 리스크: {confidence.risk_level})",
            routing_msg,
        ],
    }


def _node_write_results(state: dict) -> dict:
    """노드 8: 결과 문서 생성."""
    from src.agents.result_writer import write_results
    from src.agents.llm_writer import write_results_with_llm

    final_decision: ClaimDecision = state["final_decision"]
    ctx: ClaimContext = state["context"]
    confidence = state.get("confidence")

    # LLM Writer 시도 → 실패 시 기존 템플릿 폴백
    try:
        write_results_with_llm(final_decision, ctx, confidence)
    except Exception as exc:
        logger.warning("LLM Writer 실패, 템플릿 폴백: %s", exc)
        write_results(final_decision, ctx)

    return {
        "current_step": "결과 생성 완료",
        "progress_messages": state.get("progress_messages", []) + [
            "📝 결과 문서 생성 완료",
        ],
    }


# ══════════════════════════════════════════════════════════════════
# 그래프 빌드 & 실행
# ══════════════════════════════════════════════════════════════════

def _build_graph():
    """LangGraph StateGraph 를 빌드하여 반환."""
    try:
        from langgraph.graph import StateGraph, START, END
    except ImportError:
        raise ImportError(
            "langgraph 패키지가 필요합니다. pip install langgraph"
        )

    from src.agents.graph_state import AgentState

    graph = StateGraph(AgentState)

    # 노드 등록
    graph.add_node("parse_docs", _node_parse_docs)
    graph.add_node("build_context", _node_build_context)
    graph.add_node("lookup_contract", _node_lookup_contract)
    graph.add_node("search_policy", _node_search_policy)
    graph.add_node("llm_reason", _node_llm_reason)
    graph.add_node("rule_validate", _node_rule_validate)
    graph.add_node("finalize", _node_finalize)
    graph.add_node("write_results", _node_write_results)

    # 엣지 정의 (순차 실행)
    graph.add_edge(START, "parse_docs")
    graph.add_edge("parse_docs", "build_context")
    graph.add_edge("build_context", "lookup_contract")
    graph.add_edge("lookup_contract", "search_policy")
    graph.add_edge("search_policy", "llm_reason")
    graph.add_edge("llm_reason", "rule_validate")
    graph.add_edge("rule_validate", "finalize")
    graph.add_edge("finalize", "write_results")
    graph.add_edge("write_results", END)

    return graph.compile()


# 싱글턴 (컴파일 비용 절약)
_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()
    return _compiled_graph


def run_agent_claim(
    claim_id: str,
    policy_no: str,
    claim_date: str,
    doc_dir: str,
    on_progress: Optional[Callable] = None,
) -> ClaimDecision:
    """
    Agent 모드로 단일 청구를 처리.

    Args:
        claim_id:    청구번호
        policy_no:   계약번호
        claim_date:  청구일자
        doc_dir:     서류 폴더 경로
        on_progress: 진행 콜백 ({"step": str, "message": str})

    Returns:
        ClaimDecision — 최종 판정 결과

    LLM 전체 실패 시 자동으로 룰 기반 파이프라인으로 폴백.
    """
    from src.llm.usage_tracker import can_use, record_usage

    # 일일 한도 확인
    if not can_use():
        logger.warning("Agent 일일 한도 초과 — 룰 기반 폴백")
        if on_progress:
            on_progress({"step": "fallback", "message": "⚡ 일일 한도 초과 — 룰 기반 모드"})
        return _fallback_rule_based(claim_id, policy_no, claim_date, doc_dir, on_progress)

    try:
        graph = _get_graph()

        # 초기 상태
        initial_state = {
            "claim_id": claim_id,
            "policy_no": policy_no,
            "claim_date": claim_date,
            "doc_dir": doc_dir,
            "progress_messages": [],
            "errors": [],
        }

        # 그래프 실행 (스트리밍으로 각 노드 진행 상태 전달)
        final_state = None
        for step_output in graph.stream(initial_state):
            # step_output: {node_name: {updated_keys}}
            for node_name, updates in step_output.items():
                if on_progress:
                    msg = updates.get("current_step", node_name)
                    messages = updates.get("progress_messages", [])
                    on_progress({
                        "step": node_name,
                        "message": msg,
                        "details": messages[-1] if messages else "",
                    })
                final_state = updates

        # 사용량 기록
        record_usage()

        # 최종 결과 추출
        if final_state and "final_decision" in final_state:
            return final_state["final_decision"]

        # graph.stream 에서 final_state 구조가 다를 수 있으므로
        # invoke 로 재시도
        result = graph.invoke(initial_state)
        record_usage()
        decision = result.get("final_decision")
        if decision:
            return decision

        raise RuntimeError("Agent 그래프 결과에 final_decision 없음")

    except ImportError as exc:
        logger.warning("LangGraph 미설치 — 룰 기반 폴백: %s", exc)
        return _fallback_rule_based(claim_id, policy_no, claim_date, doc_dir, on_progress)

    except Exception as exc:
        logger.error("Agent 그래프 실행 실패 — 룰 기반 폴백: %s", exc)
        if on_progress:
            on_progress({"step": "fallback", "message": f"⚠️ Agent 오류 — 룰 기반 폴백 ({exc})"})
        return _fallback_rule_based(claim_id, policy_no, claim_date, doc_dir, on_progress)


def _fallback_rule_based(
    claim_id: str,
    policy_no: str,
    claim_date: str,
    doc_dir: str,
    on_progress: Optional[Callable] = None,
) -> ClaimDecision:
    """Agent 실패 시 기존 룰 기반 파이프라인으로 폴백."""
    from src.ocr.doc_parser import parse_claim_documents
    from src.agents.orchestrator import build_claim_context
    from src.rules.rule_engine import run_rules
    from src.agents.result_writer import write_results

    doc_path = Path(doc_dir)
    documents = parse_claim_documents(doc_path)
    ctx = build_claim_context(claim_id, policy_no, claim_date, documents)
    decision = run_rules(ctx)
    write_results(decision, ctx)
    return decision
