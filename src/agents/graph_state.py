"""
LangGraph Agent 상태 정의.

LangGraph StateGraph 의 공유 상태(State)를 정의한다.
기존 src/schemas.py 의 ClaimContext / ClaimDecision 을 포함하면서,
Agent 추론 과정에서 필요한 추가 필드(RAG 결과, LLM 추론, 신뢰도)를 확장한다.

설계 원칙:
  - TypedDict 기반 (LangGraph 표준).
  - 기존 dataclass 스키마와의 호환성 유지.
  - 각 그래프 노드는 이 상태의 일부 키를 읽고 쓴다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict

from src.schemas import (
    ClaimContext, ClaimDecision, ParsedDocument, RuleResult,
    ConfidenceScore,  # TASK-G1: schemas.py 로 이동됨
)


# ══════════════════════════════════════════════════════════════════
# LangGraph Agent 상태 (TypedDict)
# ══════════════════════════════════════════════════════════════════

class AgentState(TypedDict, total=False):
    """
    LangGraph StateGraph 의 공유 상태.

    각 그래프 노드는 이 상태의 일부 키를 읽고 업데이트한다.
    total=False 로 선언하여 모든 키가 선택적(Optional).

    ── 입력 (그래프 시작 시 설정) ──
    claim_id         : str    — 청구번호
    policy_no        : str    — 계약번호
    claim_date       : str    — 청구일자
    doc_dir          : str    — 서류 폴더 경로

    ── 서류 파싱 노드 출력 ──
    documents        : list[ParsedDocument]
    parse_errors     : list[str]

    ── 컨텍스트 조립 노드 출력 ──
    context          : ClaimContext

    ── 계약 조회 노드 출력 ──
    contract_info    : dict
    claims_history   : dict

    ── RAG 검색 노드 출력 ──
    rag_results      : list[dict]  — 약관 검색 결과 청크 목록

    ── LLM 심사 추론 노드 출력 ──
    llm_reasoning    : str         — LLM의 판단 추론 과정
    llm_decision     : str         — LLM 판정 (지급/부지급/보류/검토필요/일부지급)
    llm_amount       : int         — LLM 산정 금액
    llm_confidence   : float       — LLM 자체 확신도

    ── 룰엔진 교차검증 노드 출력 ──
    rule_decision    : ClaimDecision   — 룰엔진 판정 결과
    validation_notes : list[str]        — 교차검증 불일치 사항

    ── 최종 판정 노드 출력 ──
    final_decision   : ClaimDecision   — 최종 확정 판정
    confidence       : ConfidenceScore — 신뢰도 점수

    ── 진행 상태 (UI 콜백용) ──
    current_step     : str             — 현재 실행 중인 노드 이름
    progress_messages: list[str]       — 단계별 진행 메시지
    errors           : list[str]       — 에러 목록
    """
    # 입력
    claim_id: str
    policy_no: str
    claim_date: str
    doc_dir: str

    # 서류 파싱
    documents: list[ParsedDocument]
    parse_errors: list[str]

    # 컨텍스트
    context: ClaimContext

    # 계약 정보
    contract_info: dict
    claims_history: dict

    # RAG
    rag_results: list[dict]

    # LLM 추론
    llm_reasoning: str
    llm_decision: str
    llm_amount: int
    llm_confidence: float
    llm_confidence_factors: dict   # A-4: LLM 평가 요인별 신뢰도
    llm_breakdown: dict            # A-3: LLM 담보별 산정 결과

    # 룰엔진 교차검증
    rule_decision: ClaimDecision
    validation_notes: list[str]

    # 최종 결과
    final_decision: ClaimDecision
    confidence: ConfidenceScore

    # 진행 상태
    current_step: str
    progress_messages: list[str]
    errors: list[str]
