"""
RAG Retriever — ClaimContext 기반 약관·기준 문서 검색.

책임:
  1. ClaimContext → 검색 쿼리 생성
       KCD 코드, 진단명, 수술명, 청구 담보 유형 → 복수 쿼리 세트
  2. 벡터스토어 유사도 검색
       VectorStoreManager.query() 위임, doc_type 필터 지원
  3. 결과 집계·중복 제거
       동일 청크 ID 가 여러 쿼리에서 반환되면 최고 점수만 유지
  4. 근거 텍스트 반환
       rule_engine / result_writer 에서 판정 근거로 활용할 수 있도록
       RetrievalResult 구조화

공개 API:
  retrieve(ctx, top_k, min_score, doc_types) → RetrievalResult
  retrieve_raw(query_text, top_k, min_score, doc_types) → list[RetrievedChunk]
  ClaimRetriever (클래스, DI 용)

사용 방법:
  # 모듈 수준 싱글턴 (settings 기반 VectorStoreManager 자동 생성)
  from src.rag.retriever import retrieve
  result = retrieve(ctx)
  for chunk in result.chunks:
      print(chunk.score, chunk.text[:80])

  # VectorStoreManager 직접 주입 (테스트·재사용 시)
  from src.rag.retriever import ClaimRetriever
  retriever = ClaimRetriever(vsm=my_vsm)
  result = retriever.retrieve(ctx, top_k=3)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from config.settings import RAG_TOP_K
from src.schemas import ClaimContext
from src.rag.vectorstore import VectorStoreManager, RetrievedChunk

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 결과 타입
# ══════════════════════════════════════════════════════════════════

@dataclass
class RetrievalResult:
    """
    retrieve() 의 최종 반환값.

    Attributes:
        chunks:        중복 제거·점수 내림차순 정렬된 청크 목록
        query_texts:   실제로 벡터스토어에 전달한 쿼리 문자열 목록 (디버깅용)
        total_queried: 쿼리 횟수 합계 (raw 검색 횟수, 중복 포함)
        context_summary: ClaimContext 의 핵심 필드 요약 (로그·감사용)
    """
    chunks: list[RetrievedChunk] = field(default_factory=list)
    query_texts: list[str] = field(default_factory=list)
    total_queried: int = 0
    context_summary: dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════
# 쿼리 빌더
# ══════════════════════════════════════════════════════════════════

# 청구 담보 유형 → 검색 키워드 매핑
_COVERAGE_KEYWORDS: dict[str, list[str]] = {
    "IND": ["입원일당", "면책기간", "입원일수", "질병 4일", "재해 1일"],
    "SIL": ["실손의료비", "비급여", "급여 본인부담금", "실손 보상", "자기부담금"],
    "SUR": ["수술비", "수술 종류", "수술 분류", "수술확인서"],
    "AMD": ["응급의료비", "응급실", "외래"],
    "CAN": ["암진단비", "암 진단", "암 보험금"],
    "FRA": ["골절", "골절진단비"],
    "DIS": ["진단비", "특정질환"],
}

# doc_type 필터 — 담보별 우선 검색 대상
_COVERAGE_DOC_TYPES: dict[str, list[str]] = {
    "IND": ["standard", "policy"],
    "SIL": ["policy", "standard"],
    "SUR": ["standard", "policy"],
}


def build_queries_from_context(ctx: ClaimContext) -> list[str]:
    """
    ClaimContext 에서 벡터스토어 검색 쿼리 목록을 생성한다.

    쿼리 생성 전략:
      1. KCD 코드 + 진단명 → 상병 관련 약관 조항 검색
      2. 청구 담보별 키워드 → 담보 지급 기준 검색
      3. 수술명/코드 (있을 경우) → 수술비 관련 조항 검색
      4. 보편 쿼리 (면책, 지급 기한) — 항상 포함

    Returns:
        중복 제거된 쿼리 문자열 목록
    """
    queries: list[str] = []

    # ① KCD + 진단명
    kcd = ctx.kcd_code or "UNKNOWN"
    diagnosis = ctx.diagnosis or ""
    if kcd != "UNKNOWN":
        queries.append(f"{kcd} 상병 보험금 지급 기준")
    if diagnosis:
        queries.append(f"{diagnosis} 면책 여부 및 보험금 지급 기준")
    if kcd != "UNKNOWN" and diagnosis:
        queries.append(f"{kcd} {diagnosis} 약관 조항")

    # ② 청구 담보별 키워드
    for cov_type in ctx.claimed_coverage_types or ["IND", "SIL"]:
        for keyword in _COVERAGE_KEYWORDS.get(cov_type, []):
            queries.append(f"{keyword} 지급 기준 및 면책 조항")

    # ③ 수술 관련
    if ctx.surgery_name:
        queries.append(f"{ctx.surgery_name} 수술비 지급 기준")
    if ctx.surgery_code:
        queries.append(f"수술 분류 {ctx.surgery_code} 종 수술비")

    # ④ 보편 쿼리
    queries.extend([
        "면책기간 및 지급 제한 조건",
        "보험금 지급 기한 및 법적 근거",
    ])

    # 중복 제거 (순서 유지)
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


# ══════════════════════════════════════════════════════════════════
# ClaimRetriever
# ══════════════════════════════════════════════════════════════════

class ClaimRetriever:
    """
    ClaimContext 기반 벡터스토어 검색기.

    Args:
        vsm: VectorStoreManager 인스턴스. None 이면 settings 기반 자동 생성.
    """

    def __init__(self, vsm: Optional[VectorStoreManager] = None) -> None:
        self._vsm: Optional[VectorStoreManager] = vsm   # 지연 초기화 지원

    def _get_vsm(self) -> VectorStoreManager:
        if self._vsm is None:
            self._vsm = VectorStoreManager()
        return self._vsm

    # ── 공개 메서드 ────────────────────────────────────────────────

    def retrieve(
        self,
        ctx: ClaimContext,
        top_k: int = RAG_TOP_K,
        min_score: float = 0.0,
        doc_types: Optional[list[str]] = None,
    ) -> RetrievalResult:
        """
        ClaimContext 를 분석해 관련 약관·기준 문서 청크를 검색한다.

        Args:
            ctx:       청구 컨텍스트
            top_k:     최종 반환 청크 수 (중복 제거 후)
            min_score: 최소 유사도 점수 (0.0 ~ 1.0). 미만 청크는 제외.
            doc_types: 검색 대상 doc_type 필터 목록 (예: ["policy", "standard"]).
                       None 이면 전체 컬렉션에서 검색.

        Returns:
            RetrievalResult — 중복 제거·점수 정렬된 청크 + 쿼리 메타데이터
        """
        queries = build_queries_from_context(ctx)
        chunks  = self._run_multi_query(queries, top_k, min_score, doc_types)

        return RetrievalResult(
            chunks=chunks[:top_k],
            query_texts=queries,
            total_queried=len(queries),
            context_summary=self._summarize_context(ctx),
        )

    def retrieve_raw(
        self,
        query_text: str,
        top_k: int = RAG_TOP_K,
        min_score: float = 0.0,
        doc_types: Optional[list[str]] = None,
    ) -> list[RetrievedChunk]:
        """
        자유 텍스트 쿼리로 직접 검색한다.
        (단일 쿼리, rule_engine 또는 UI 에서 직접 호출 시 사용)
        """
        return self._run_multi_query(
            [query_text], top_k, min_score, doc_types
        )[:top_k]

    # ── 내부 메서드 ────────────────────────────────────────────────

    def _run_multi_query(
        self,
        queries: list[str],
        per_query_k: int,
        min_score: float,
        doc_types: Optional[list[str]],
    ) -> list[RetrievedChunk]:
        """
        복수 쿼리를 실행하고 결과를 병합·중복 제거·점수 정렬한다.

        동일 청크 ID 가 여러 쿼리에서 반환되면 최고 점수를 유지한다.
        """
        vsm = self._get_vsm()

        # doc_type 필터: ChromaDB where 구문으로 변환
        where_filter: Optional[dict] = None
        if doc_types:
            if len(doc_types) == 1:
                where_filter = {"doc_type": doc_types[0]}
            else:
                where_filter = {"$or": [{"doc_type": dt} for dt in doc_types]}

        # 쿼리별 검색 → 최고 점수 dict 에 누적
        best: dict[str, RetrievedChunk] = {}
        for q in queries:
            try:
                results = vsm.query(
                    q,
                    n_results=per_query_k,
                    where=where_filter,
                )
                for chunk in results:
                    if chunk.score < min_score:
                        continue
                    existing = best.get(chunk.id)
                    if existing is None or chunk.score > existing.score:
                        best[chunk.id] = chunk
            except Exception as exc:
                logger.warning("쿼리 실행 실패 ('%s'): %s", q[:40], exc)

        # 점수 내림차순 정렬
        merged = sorted(best.values(), key=lambda c: c.score, reverse=True)
        logger.info(
            "retrieve: %d쿼리 → 후보 %d청크 (min_score=%.2f)",
            len(queries), len(merged), min_score,
        )
        return merged

    @staticmethod
    def _summarize_context(ctx: ClaimContext) -> dict:
        """로그·감사용 ClaimContext 핵심 필드 요약."""
        return {
            "claim_id":               ctx.claim_id,
            "kcd_code":               ctx.kcd_code,
            "diagnosis":              ctx.diagnosis,
            "surgery_name":           ctx.surgery_name,
            "surgery_code":           ctx.surgery_code,
            "claimed_coverage_types": ctx.claimed_coverage_types,
            "hospital_days":          ctx.hospital_days,
        }


# ══════════════════════════════════════════════════════════════════
# 모듈 수준 싱글턴 — 가장 간단한 사용 인터페이스
# ══════════════════════════════════════════════════════════════════

_default_retriever: Optional[ClaimRetriever] = None


def _get_default_retriever() -> ClaimRetriever:
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = ClaimRetriever()
    return _default_retriever


def retrieve(
    ctx: ClaimContext,
    top_k: int = RAG_TOP_K,
    min_score: float = 0.0,
    doc_types: Optional[list[str]] = None,
) -> RetrievalResult:
    """
    모듈 수준 retrieve() 함수.
    내부적으로 싱글턴 ClaimRetriever 를 사용한다.

    Args:
        ctx:       청구 컨텍스트
        top_k:     반환할 최대 청크 수
        min_score: 최소 유사도 점수 (0.0 ~ 1.0)
        doc_types: doc_type 필터 (None = 전체)

    Returns:
        RetrievalResult
    """
    return _get_default_retriever().retrieve(ctx, top_k, min_score, doc_types)


def retrieve_raw(
    query_text: str,
    top_k: int = RAG_TOP_K,
    min_score: float = 0.0,
    doc_types: Optional[list[str]] = None,
) -> list[RetrievedChunk]:
    """
    자유 텍스트로 직접 검색하는 모듈 수준 함수.
    """
    return _get_default_retriever().retrieve_raw(
        query_text, top_k, min_score, doc_types
    )
