"""
RAG (Retrieval-Augmented Generation) 모듈.

구성:
  embedder.py     — 텍스트 임베딩 (local sentence-transformers / OpenAI)
  vectorstore.py  — ChromaDB 기반 벡터스토어 CRUD
  indexer.py      — 약관·룰북 문서 → 청크 → 벡터스토어 적재
  retriever.py    — ClaimContext 기반 유사 청크 검색

빠른 시작:
  # 1. 최초 1회 인덱싱
  from src.rag.indexer import build_index
  build_index()                  # 변경된 파일만 인덱싱
  build_index(force=True)        # 전체 재인덱싱

  # 2. 벡터스토어 직접 조작
  from src.rag.vectorstore import VectorStoreManager
  vsm = VectorStoreManager()
  results = vsm.query("입원일당 면책기간", n_results=5)

  # 3. ClaimContext 기반 검색
  from src.rag.retriever import retrieve
  result = retrieve(ctx)
  for chunk in result.chunks:
      print(chunk.score, chunk.text[:80])
"""
# ── Lazy imports ─────────────────────────────────────────────────────────────
# chromadb / sentence-transformers 등 무거운 의존성이 설치되지 않은 환경에서도
# `import src.rag` 자체는 실패하지 않도록 지연 로딩한다.
# 실제 사용 시점에 서브모듈을 직접 임포트하면 된다:
#   from src.rag.retriever import retrieve_raw
#   from src.rag.vectorstore import VectorStoreManager

def __getattr__(name: str):
    """모듈 수준 lazy import — 사용 시점에만 서브모듈 로드."""
    _EMBEDDER   = {"get_embedder", "EmbedderBase"}
    _VECTORSTORE = {"VectorStoreManager"}
    _INDEXER    = {"build_index", "index_file", "split_document", "DocumentChunk", "IndexStats"}
    _RETRIEVER  = {"ClaimRetriever", "RetrievalResult", "retrieve", "retrieve_raw", "build_queries_from_context"}

    if name in _EMBEDDER:
        from src.rag import embedder as _m
        return getattr(_m, name)
    if name in _VECTORSTORE:
        from src.rag import vectorstore as _m
        return getattr(_m, name)
    if name in _INDEXER:
        from src.rag import indexer as _m
        return getattr(_m, name)
    if name in _RETRIEVER:
        from src.rag import retriever as _m
        return getattr(_m, name)
    raise AttributeError(f"module 'src.rag' has no attribute {name!r}")


__all__ = [
    # embedder
    "get_embedder", "EmbedderBase",
    # vectorstore
    "VectorStoreManager",
    # indexer
    "build_index", "index_file", "split_document", "DocumentChunk", "IndexStats",
    # retriever
    "ClaimRetriever", "RetrievalResult", "retrieve", "retrieve_raw",
    "build_queries_from_context",
]
