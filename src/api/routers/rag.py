"""
TASK-18, 19: RAG 검색 + 인덱스 관리 엔드포인트.

POST /rag/search       — 자유 텍스트 벡터 검색
POST /rag/search/claim — ClaimContext 기반 멀티 쿼리 검색
GET  /rag/stats        — 벡터스토어 통계 (청크 수, 컬렉션 목록)
POST /rag/index/build  — TASK-19: 전체 인덱싱 (force 파라미터 지원)
DELETE /rag/index      — TASK-19: 인덱스 전체 초기화
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status

from src.api.deps import VsmDep
from src.api.models import (
    RagQueryRequest,
    RagQueryResponse,
    RagChunkOut,
    IndexRebuildResponse,
)
from src.rag.indexer import build_index, IndexStats
from src.rag.retriever import ClaimRetriever, build_queries_from_context
from src.schemas import ClaimContext

router = APIRouter(prefix="/rag", tags=["rag"])


# ──────────────────────────────────────────────────────────────────
# TASK-18: POST /rag/search — 자유 텍스트 검색
# ──────────────────────────────────────────────────────────────────

@router.post(
    "/search",
    response_model=RagQueryResponse,
    summary="자유 텍스트 RAG 검색",
    description="자유 텍스트 쿼리로 약관·기준 문서 청크를 유사도 검색한다.",
)
def rag_search(req: RagQueryRequest, vsm: VsmDep):
    if vsm.count() == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="벡터스토어가 비어 있습니다. POST /rag/index/build 를 먼저 실행하세요.",
        )

    retriever = ClaimRetriever(vsm=vsm)
    chunks = retriever.retrieve_raw(
        query_text=req.query,
        top_k=req.top_k,
        min_score=req.min_score,
        doc_types=req.doc_types,
    )
    return RagQueryResponse(
        query=req.query,
        chunks=[
            RagChunkOut(id=c.id, text=c.text, score=c.score, metadata=c.metadata)
            for c in chunks
        ],
        total=len(chunks),
    )


# ──────────────────────────────────────────────────────────────────
# TASK-18: POST /rag/search/claim — ClaimContext 기반 검색
# ──────────────────────────────────────────────────────────────────

class _ClaimContextQuery(ClaimContext):
    """ClaimContext 필드를 POST 바디로 받기 위한 임시 Pydantic 래퍼."""
    pass


@router.post(
    "/search/claim",
    response_model=RagQueryResponse,
    summary="ClaimContext 기반 RAG 검색",
    description=(
        "ClaimContext 필드를 전달하면 KCD·진단·수술·담보 정보를 바탕으로\n"
        "복수 쿼리를 자동 생성해 검색한다."
    ),
)
def rag_search_by_claim(
    claim_id: str = Query(...),
    policy_no: str = Query(...),
    claim_date: str = Query(...),
    accident_date: str = Query(...),
    kcd_code: str = Query("UNKNOWN"),
    diagnosis: str = Query(""),
    surgery_name: Optional[str] = Query(None),
    surgery_code: Optional[str] = Query(None),
    claimed_coverage_types: Optional[str] = Query(None, description="콤마 구분, 예: IND,SIL"),
    top_k: int = Query(5, ge=1, le=20),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    vsm: VsmDep = None,
):
    if vsm.count() == 0:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="벡터스토어가 비어 있습니다. POST /rag/index/build 를 먼저 실행하세요.",
        )

    cov_types = [c.strip() for c in claimed_coverage_types.split(",")] if claimed_coverage_types else []

    ctx = ClaimContext(
        claim_id=claim_id,
        policy_no=policy_no,
        claim_date=claim_date,
        accident_date=accident_date,
        admission_date=None,
        discharge_date=None,
        hospital_days=None,
        kcd_code=kcd_code,
        diagnosis=diagnosis,
        surgery_name=surgery_name,
        surgery_code=surgery_code,
        covered_self_pay=None,
        non_covered_amount=None,
        submitted_doc_types=[],
        claimed_coverage_types=cov_types,
    )

    retriever = ClaimRetriever(vsm=vsm)
    result = retriever.retrieve(ctx, top_k=top_k, min_score=min_score)

    queries_summary = "; ".join(result.query_texts[:3])
    if len(result.query_texts) > 3:
        queries_summary += f" … 외 {len(result.query_texts)-3}개"

    return RagQueryResponse(
        query=queries_summary,
        chunks=[
            RagChunkOut(id=c.id, text=c.text, score=c.score, metadata=c.metadata)
            for c in result.chunks
        ],
        total=len(result.chunks),
    )


# ──────────────────────────────────────────────────────────────────
# TASK-18: GET /rag/stats
# ──────────────────────────────────────────────────────────────────

@router.get("/stats", summary="벡터스토어 통계")
def rag_stats(vsm: VsmDep):
    """벡터스토어 청크 수, 컬렉션 목록을 반환한다."""
    try:
        chunk_count = vsm.count()
        collections = vsm.list_collections()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"벡터스토어 조회 실패: {e}",
        )
    return {
        "chunk_count": chunk_count,
        "collections": collections,
        "db_path": str(vsm.db_path),
    }


# ──────────────────────────────────────────────────────────────────
# TASK-19: POST /rag/index/build — 인덱스 재구성
# ──────────────────────────────────────────────────────────────────

@router.post(
    "/index/build",
    response_model=IndexRebuildResponse,
    summary="RAG 인덱스 구성·재구성",
    description=(
        "data/policies/ 및 docs/insurance_standards/ 의 문서를 청크 분할하여\n"
        "벡터스토어에 적재한다.\n\n"
        "- `force=true`: 기존 인덱스를 삭제하고 전체 재구성\n"
        "- `force=false` (기본): 변경된 파일만 재인덱싱"
    ),
)
def build_rag_index(
    vsm: VsmDep,
    force: bool = Query(False, description="기존 인덱스 삭제 후 재구성 여부"),
    chunk_size: int = Query(500, ge=100, le=2000),
    overlap: int = Query(50, ge=0, le=200),
):
    try:
        stats: IndexStats = build_index(vsm=vsm, force=force, chunk_size=chunk_size, overlap=overlap)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"인덱싱 실패: {e}",
        )

    msg = (
        f"{'전체 재구성' if force else '증분 인덱싱'} 완료 — "
        f"파일 {stats.total_files}개, 청크 {stats.total_chunks}개 "
        f"(스킵 {stats.skipped_files}개, 실패 {len(stats.failed_files)}개)"
    )
    return IndexRebuildResponse(
        total_files=stats.total_files,
        total_chunks=stats.total_chunks,
        skipped_files=stats.skipped_files,
        failed_files=stats.failed_files,
        message=msg,
    )


# ──────────────────────────────────────────────────────────────────
# TASK-19: DELETE /rag/index — 인덱스 초기화
# ──────────────────────────────────────────────────────────────────

@router.delete(
    "/index",
    summary="RAG 인덱스 초기화",
    description="벡터스토어의 기본 컬렉션을 전부 삭제한다 (복구 불가).",
)
def clear_rag_index(vsm: VsmDep):
    try:
        vsm.clear()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"인덱스 초기화 실패: {e}",
        )
    return {"message": "인덱스가 초기화되었습니다. POST /rag/index/build 로 재구성하세요."}
