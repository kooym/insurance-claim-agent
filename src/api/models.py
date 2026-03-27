"""
Pydantic 요청/응답 모델 (TASK-13).

설계 원칙:
  - 내부 dataclass(ClaimContext, ClaimDecision 등)와 분리
  - API 경계에서만 사용 (Controller Layer)
  - camelCase 별칭 제공 (프론트엔드 친화)
"""
from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# ══════════════════════════════════════════════════════════════════
# 공통
# ══════════════════════════════════════════════════════════════════

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None


# ══════════════════════════════════════════════════════════════════
# TASK-14: 청구 처리 요청 (ClaimProcessRequest)
# ══════════════════════════════════════════════════════════════════

class ClaimProcessRequest(BaseModel):
    """POST /claims/process — 청구 처리 요청 바디."""
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str = Field(..., description="청구 고유 ID (예: CLM-2024-001)")
    policy_no: str = Field(..., description="보험계약번호")
    claim_date: str = Field(..., description="청구 접수일 (YYYY-MM-DD)")
    doc_parse_mode: Optional[Literal["regex", "llm", "hybrid"]] = Field(
        None, description="서류 파싱 모드. None 이면 settings.DOC_PARSE_MODE 사용."
    )


# ══════════════════════════════════════════════════════════════════
# TASK-15: 청구 결과 응답 (ClaimResultResponse)
# ══════════════════════════════════════════════════════════════════

class RuleResultOut(BaseModel):
    rule_id: str
    status: str
    reason: str
    value: Optional[float] = None


# A-8: 신뢰도 + 라우팅 응답 모델
class ConfidenceOut(BaseModel):
    """A-8: 신뢰도 점수 응답."""
    parse_confidence: float = 0.0
    rule_confidence: float = 0.0
    llm_confidence: float = 0.0
    cross_validation: float = 0.0
    overall: float = 0.0
    risk_level: str = "UNKNOWN"
    confidence_factors: Optional[dict] = None


class ReviewRoutingOut(BaseModel):
    """A-8: 심사 라우팅 응답."""
    action: str = "standard_review"
    priority: str = "normal"
    reviewer_level: str = "일반심사역"
    checklist: list[str] = Field(default_factory=list)
    estimated_minutes: int = 0
    routing_reason: str = ""


class ClaimResultResponse(BaseModel):
    """GET /claims/{claim_id} 및 POST /claims/process 공통 응답."""
    claim_id: str
    decision: str
    total_payment: int
    expected_payment_date: Optional[str] = None
    breakdown: dict = Field(default_factory=dict)
    applied_rules: list[RuleResultOut] = Field(default_factory=list)
    reviewer_flag: bool = False
    reviewer_reason: Optional[str] = None
    missing_docs: list[str] = Field(default_factory=list)
    denial_reason: Optional[str] = None
    policy_clause: Optional[str] = None
    fraud_investigation_flag: bool = False
    output_dir: Optional[str] = None
    # A-8: 신뢰도 + 라우팅
    confidence: Optional[ConfidenceOut] = None
    review_routing: Optional[ReviewRoutingOut] = None


# ══════════════════════════════════════════════════════════════════
# TASK-17: 룰 엔진 직접 실행 (RuleRunRequest)
# ══════════════════════════════════════════════════════════════════

class RuleRunRequest(BaseModel):
    """POST /rules/run — ClaimContext JSON을 직접 전달해 룰 실행."""
    model_config = ConfigDict(populate_by_name=True)

    claim_id: str
    policy_no: str
    claim_date: str
    accident_date: str
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    hospital_days: Optional[int] = None
    kcd_code: str = "UNKNOWN"
    diagnosis: str = ""
    surgery_name: Optional[str] = None
    surgery_code: Optional[str] = None
    covered_self_pay: Optional[int] = None
    non_covered_amount: Optional[int] = None
    submitted_doc_types: list[str] = Field(default_factory=list)
    claimed_coverage_types: list[str] = Field(default_factory=list)
    billing_items: list[dict] = Field(default_factory=list)
    parse_confidence_min: float = 1.0
    chronic_onset_flag: bool = False


# ══════════════════════════════════════════════════════════════════
# TASK-18: RAG 검색 (RagQueryRequest / RagQueryResponse)
# ══════════════════════════════════════════════════════════════════

class RagQueryRequest(BaseModel):
    """POST /rag/search — 자유 텍스트 또는 ClaimContext 기반 검색."""
    query: str = Field(..., description="검색 쿼리 텍스트")
    top_k: int = Field(5, ge=1, le=20, description="반환 청크 수 (1~20)")
    min_score: float = Field(0.0, ge=0.0, le=1.0, description="최소 유사도 (0.0~1.0)")
    doc_types: Optional[list[str]] = Field(
        None, description="필터링할 doc_type 목록 (policy/standard/rulebook)"
    )


class RagChunkOut(BaseModel):
    id: str
    text: str
    score: float
    metadata: dict = Field(default_factory=dict)


class RagQueryResponse(BaseModel):
    query: str
    chunks: list[RagChunkOut]
    total: int


# ══════════════════════════════════════════════════════════════════
# TASK-19: 인덱스 관리 / 헬스체크
# ══════════════════════════════════════════════════════════════════

class IndexRebuildResponse(BaseModel):
    total_files: int
    total_chunks: int
    skipped_files: int
    failed_files: list[str]
    message: str


class HealthResponse(BaseModel):
    status: str
    version: str
    vectorstore_chunks: int
    settings: dict
