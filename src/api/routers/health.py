"""
TASK-19: 헬스체크 + 관리 엔드포인트.

GET  /health           — 서비스 상태 + vectorstore 문서 수
GET  /health/settings  — 현재 적용 중인 주요 settings 목록
"""
from __future__ import annotations

from fastapi import APIRouter

from src.api.deps import VsmDep
from src.api.models import HealthResponse
from config.settings import (
    EMBEDDING_PROVIDER, EMBEDDING_MODEL,
    VECTOR_DB_TYPE, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP, RAG_TOP_K,
    DOC_PARSE_MODE, LLM_PROVIDER, LLM_MODEL,
    POLICY_DOCS_PATH, VECTOR_DB_PATH,
)

router = APIRouter(prefix="/health", tags=["health"])

_VERSION = "2.0.0"


@router.get("", response_model=HealthResponse, summary="서비스 헬스체크")
def health_check(vsm: VsmDep):
    """서비스 가동 상태 및 vectorstore 적재 청크 수를 반환한다."""
    try:
        chunk_count = vsm.count()
    except Exception:
        chunk_count = -1

    return HealthResponse(
        status="ok",
        version=_VERSION,
        vectorstore_chunks=chunk_count,
        settings={
            "embedding_provider": EMBEDDING_PROVIDER,
            "embedding_model":    EMBEDDING_MODEL,
            "vector_db_type":     VECTOR_DB_TYPE,
            "rag_chunk_size":     RAG_CHUNK_SIZE,
            "rag_chunk_overlap":  RAG_CHUNK_OVERLAP,
            "rag_top_k":          RAG_TOP_K,
            "doc_parse_mode":     DOC_PARSE_MODE,
            "llm_provider":       LLM_PROVIDER,
            "llm_model":          LLM_MODEL,
            "policy_docs_path":   str(POLICY_DOCS_PATH),
            "vector_db_path":     str(VECTOR_DB_PATH),
        },
    )


@router.get("/settings", summary="현재 적용 settings")
def get_settings():
    """현재 적용 중인 주요 설정값을 반환한다 (API 키 제외)."""
    return {
        "embedding_provider": EMBEDDING_PROVIDER,
        "embedding_model":    EMBEDDING_MODEL,
        "vector_db_type":     VECTOR_DB_TYPE,
        "rag_chunk_size":     RAG_CHUNK_SIZE,
        "rag_chunk_overlap":  RAG_CHUNK_OVERLAP,
        "rag_top_k":          RAG_TOP_K,
        "doc_parse_mode":     DOC_PARSE_MODE,
        "llm_provider":       LLM_PROVIDER,
        "llm_model":          LLM_MODEL,
        "policy_docs_path":   str(POLICY_DOCS_PATH),
        "vector_db_path":     str(VECTOR_DB_PATH),
    }
