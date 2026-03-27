"""
ChromaDB 기반 벡터스토어 관리.

책임:
  - Chroma persistent client 초기화 (VECTOR_DB_PATH)
  - 컬렉션 생성·조회 (get_or_create_collection)
  - 문서 청크 추가 (add_documents)
  - 유사도 검색 (query)
  - 컬렉션 삭제·초기화 (delete_collection, clear)

설계 결정:
  - 임베딩은 EmbedderBase 인터페이스를 통해 주입받는다
    (LocalEmbedder 기본, OpenAIEmbedder 교체 가능)
  - ChromaDB EmbeddingFunction 어댑터로 래핑해 Chroma 내부 임베딩 API 충족
  - 컬렉션당 단일 임베딩 모델 고정 (재초기화 시 차원 불일치 방지)

사용 방법:
  vsm = VectorStoreManager()          # settings 기반 자동 초기화

  # 문서 추가
  vsm.add_documents(
      texts     = ["약관 본문 청크1", "청크2"],
      metadatas = [{"source": "standard_policy.md", "page": 1}, ...],
      ids       = ["doc-001-chunk-0", "doc-001-chunk-1"],
  )

  # 유사 청크 검색
  results = vsm.query("입원일당 면책기간", n_results=5)
  for r in results:
      print(r["text"], r["score"], r["metadata"])
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from config.settings import (
    VECTOR_DB_PATH,
    VECTOR_DB_TYPE,
    RAG_TOP_K,
)
from src.rag.embedder import EmbedderBase, get_embedder

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 결과 타입
# ══════════════════════════════════════════════════════════════════

@dataclass
class RetrievedChunk:
    """query() 반환값의 개별 결과 항목."""
    id: str
    text: str
    score: float                           # 0 ~ 1 (높을수록 유사)
    metadata: dict = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════
# ChromaDB EmbeddingFunction 어댑터
# ══════════════════════════════════════════════════════════════════

class _EmbedderAdapter:
    """
    EmbedderBase → chromadb.EmbeddingFunction 어댑터.

    ChromaDB 1.5+ EmbeddingFunction 인터페이스 충족:
      __call__(input) → Embeddings  — add/upsert 시 호출
      embed_query(input) → Embeddings — query 시 호출
      name() → str
    """

    def __init__(self, embedder: EmbedderBase) -> None:
        self._embedder = embedder

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self._embedder.embed(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        """ChromaDB 1.5+ query path 에서 호출되는 임베딩 메서드."""
        return self._embedder.embed(input)

    def name(self) -> str:
        return f"custom-{self._embedder.model_name}"


# ══════════════════════════════════════════════════════════════════
# VectorStoreManager
# ══════════════════════════════════════════════════════════════════

class VectorStoreManager:
    """
    ChromaDB 영속 클라이언트 래퍼.

    생성자 인수:
        db_path    : Chroma 데이터 저장 경로 (기본: settings.VECTOR_DB_PATH)
        embedder   : EmbedderBase 구현체 (기본: get_embedder() — settings 기반)
        collection : 기본 컬렉션 이름 (기본: "insurance_rag")
    """

    DEFAULT_COLLECTION = "insurance_rag"

    def __init__(
        self,
        db_path: Optional[Path] = None,
        embedder: Optional[EmbedderBase] = None,
        collection: str = DEFAULT_COLLECTION,
    ) -> None:
        self._db_path = Path(db_path or VECTOR_DB_PATH)
        self._db_path.mkdir(parents=True, exist_ok=True)

        self._embedder = embedder or get_embedder()
        self._adapter = _EmbedderAdapter(self._embedder)
        self._default_collection_name = collection

        self._client: Any = None           # 지연 초기화
        self._collections: dict[str, Any] = {}

    # ── 내부 초기화 ────────────────────────────────────────────────

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import chromadb
            except ImportError as e:
                raise ImportError(
                    "chromadb 가 설치되어 있지 않습니다. "
                    "`pip install chromadb` 또는 `pip install -r requirements.txt`"
                ) from e
            self._client = chromadb.PersistentClient(path=str(self._db_path))
            logger.debug("ChromaDB 클라이언트 초기화: %s", self._db_path)
        return self._client

    def _get_collection(self, name: str) -> Any:
        if name not in self._collections:
            client = self._get_client()
            col = client.get_or_create_collection(
                name=name,
                embedding_function=self._adapter,
                metadata={"hnsw:space": "cosine"},  # 코사인 유사도 사용
            )
            self._collections[name] = col
            logger.debug(
                "컬렉션 '%s' 로드 (문서 수: %d)", name, col.count()
            )
        return self._collections[name]

    # ── 공개 API ───────────────────────────────────────────────────

    def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict],
        ids: list[str],
        collection: Optional[str] = None,
    ) -> None:
        """
        청크를 벡터스토어에 추가한다.

        Args:
            texts:     청크 텍스트 목록
            metadatas: 각 청크의 메타데이터 (source, page, doc_type 등)
            ids:       각 청크의 고유 ID (중복 시 upsert)
            collection: 대상 컬렉션명. None 이면 기본 컬렉션 사용.

        주의: ids 가 이미 존재하면 upsert (덮어쓰기) 처리된다.
        """
        if not texts:
            return
        if len(texts) != len(metadatas) or len(texts) != len(ids):
            raise ValueError(
                "texts / metadatas / ids 의 길이가 일치해야 합니다. "
                f"texts={len(texts)}, metadatas={len(metadatas)}, ids={len(ids)}"
            )

        col_name = collection or self._default_collection_name
        col = self._get_collection(col_name)

        # ChromaDB 1.5+ 는 빈 dict 메타데이터를 허용하지 않음 — 플레이스홀더 삽입
        safe_metas = [m if m else {"_src": "unknown"} for m in metadatas]

        col.upsert(documents=texts, metadatas=safe_metas, ids=ids)
        logger.info(
            "벡터스토어 추가: 컬렉션='%s', 청크 수=%d", col_name, len(texts)
        )

    def query(
        self,
        query_text: str,
        n_results: int = RAG_TOP_K,
        collection: Optional[str] = None,
        where: Optional[dict] = None,
    ) -> list[RetrievedChunk]:
        """
        쿼리 텍스트와 가장 유사한 청크를 검색한다.

        Args:
            query_text: 검색 쿼리
            n_results:  반환할 최대 결과 수 (기본: settings.RAG_TOP_K)
            collection: 검색 대상 컬렉션명. None 이면 기본 컬렉션.
            where:      메타데이터 필터 (예: {"doc_type": "policy"})

        Returns:
            RetrievedChunk 리스트 (score 내림차순)
        """
        col_name = collection or self._default_collection_name
        col = self._get_collection(col_name)

        total = col.count()
        if total == 0:
            logger.warning(
                "컬렉션 '%s' 가 비어 있습니다. 먼저 indexer 를 실행하세요.", col_name
            )
            return []

        # 요청 수가 저장된 문서 수를 초과하지 않도록 제한
        actual_n = min(n_results, total)

        query_kwargs: dict[str, Any] = {
            "query_embeddings": [self._embedder.embed_one(query_text)],
            "n_results": actual_n,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        raw = col.query(**query_kwargs)

        chunks: list[RetrievedChunk] = []
        docs      = raw.get("documents", [[]])[0]
        metas     = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]
        ids_list  = raw.get("ids", [[]])[0]

        for doc_id, text, meta, dist in zip(ids_list, docs, metas, distances):
            # Chroma cosine: distance = 1 - cosine_similarity → score = 1 - dist
            score = round(max(0.0, 1.0 - float(dist)), 4)
            chunks.append(
                RetrievedChunk(id=doc_id, text=text, score=score, metadata=meta or {})
            )

        # score 내림차순 정렬 (Chroma 가 이미 정렬하지만 명시적으로 보장)
        chunks.sort(key=lambda c: c.score, reverse=True)
        logger.debug(
            "쿼리 '%s': %d건 검색 (컬렉션='%s')", query_text[:30], len(chunks), col_name
        )
        return chunks

    def count(self, collection: Optional[str] = None) -> int:
        """컬렉션에 저장된 청크 수를 반환한다."""
        col_name = collection or self._default_collection_name
        return self._get_collection(col_name).count()

    def delete_collection(self, collection: Optional[str] = None) -> None:
        """컬렉션 전체를 삭제한다 (테스트·재인덱싱 시 사용)."""
        col_name = collection or self._default_collection_name
        client = self._get_client()
        try:
            client.delete_collection(col_name)
            self._collections.pop(col_name, None)
            logger.info("컬렉션 '%s' 삭제 완료.", col_name)
        except Exception:
            logger.debug("컬렉션 '%s' 삭제 실패 (존재하지 않을 수 있음).", col_name)

    def clear(self, collection: Optional[str] = None) -> None:
        """
        컬렉션의 모든 문서를 삭제한 뒤 빈 컬렉션으로 재생성한다.
        (인덱스 재구성 시 사용)
        """
        self.delete_collection(collection)
        col_name = collection or self._default_collection_name
        self._get_collection(col_name)  # 빈 컬렉션 재생성
        logger.info("컬렉션 '%s' 초기화(clear) 완료.", col_name)

    def list_collections(self) -> list[str]:
        """존재하는 컬렉션 이름 목록을 반환한다."""
        client = self._get_client()
        return [col.name for col in client.list_collections()]

    # ── 편의 메서드 ────────────────────────────────────────────────

    @property
    def embedder(self) -> EmbedderBase:
        """현재 사용 중인 임베더 인스턴스."""
        return self._embedder

    @property
    def db_path(self) -> Path:
        """ChromaDB 데이터 저장 경로."""
        return self._db_path

    def __repr__(self) -> str:
        return (
            f"VectorStoreManager("
            f"db_path={self._db_path}, "
            f"embedder={self._embedder.model_name}, "
            f"default_collection={self._default_collection_name!r})"
        )
