"""
텍스트 임베딩 추상화 레이어.

지원 공급자:
  - local  : sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2)
             → API 키 불필요, 한국어 지원 양호, CPU 실행 가능
  - openai : text-embedding-3-small
             → API 키 필요, 고품질, 유료

설정 (config/settings.py):
  EMBEDDING_PROVIDER  "local" | "openai"
  EMBEDDING_MODEL     모델 이름 (공급자별 기본값 있음)
  OPENAI_API_KEY      OpenAI 사용 시 필요

사용 방법:
  from src.rag.embedder import get_embedder
  embedder = get_embedder()               # settings 기반 자동 선택
  vectors  = embedder.embed(["텍스트1", "텍스트2"])   # list[list[float]]
"""
from __future__ import annotations

import abc
from typing import Any

from config.settings import (
    EMBEDDING_PROVIDER,
    EMBEDDING_MODEL,
    OPENAI_API_KEY,
)


# ══════════════════════════════════════════════════════════════════
# 추상 기반 클래스
# ══════════════════════════════════════════════════════════════════

class EmbedderBase(abc.ABC):
    """임베딩 공급자 공통 인터페이스."""

    @abc.abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 목록 → 벡터 목록 (각 벡터는 동일 차원의 float 리스트)."""

    @abc.abstractmethod
    def embed_one(self, text: str) -> list[float]:
        """단일 텍스트 → 벡터."""

    @property
    @abc.abstractmethod
    def dimension(self) -> int:
        """벡터 차원 수 (ChromaDB 컬렉션 생성 시 사용)."""

    @property
    @abc.abstractmethod
    def model_name(self) -> str:
        """현재 사용 중인 모델 이름."""

    def is_model_available(self) -> bool:
        """모델이 즉시 사용 가능한지 (네트워크 다운로드 불필요) 반환. 기본값 True."""
        return True


# ══════════════════════════════════════════════════════════════════
# local: sentence-transformers
# ══════════════════════════════════════════════════════════════════

_LOCAL_DEFAULT_MODEL = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)


class LocalEmbedder(EmbedderBase):
    """
    sentence-transformers 기반 로컬 임베더.

    최초 호출 시 모델을 다운로드(캐시)하며, 이후 재사용한다.
    다국어 MiniLM-L12-v2 는 한국어 포함 50+ 언어 지원.
    """

    def __init__(self, model_name: str = _LOCAL_DEFAULT_MODEL) -> None:
        self._model_name = model_name
        self._model: Any = None  # 지연 로딩

    # ── 모델 캐시 확인 ────────────────────────────────────────
    def is_model_available(self) -> bool:
        """로컬 캐시에 모델이 준비되어 있는지 확인한다 (네트워크 불필요)."""
        try:
            from pathlib import Path
            cache_dir = (
                Path.home() / ".cache" / "huggingface" / "hub"
                / f"models--{self._model_name.replace('/', '--')}"
            )
            if not cache_dir.exists():
                return False
            blobs = list((cache_dir / "blobs").glob("*")) if (cache_dir / "blobs").exists() else []
            # 모델 weight 파일(>10MB)이 하나 이상 있으면 캐시 완료로 판단
            return any(f.stat().st_size > 10_000_000 for f in blobs if f.is_file())
        except Exception:
            return False

    def _load(self) -> None:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers 가 설치되어 있지 않습니다. "
                    "`pip install sentence-transformers` 또는 "
                    "`pip install -r requirements.txt`"
                ) from e
            self._model = SentenceTransformer(self._model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._load()
        vectors = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vectors]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        self._load()
        return int(self._model.get_sentence_embedding_dimension())

    @property
    def model_name(self) -> str:
        return self._model_name


# ══════════════════════════════════════════════════════════════════
# openai: text-embedding-3-small
# ══════════════════════════════════════════════════════════════════

_OPENAI_DEFAULT_MODEL = "text-embedding-3-small"
_OPENAI_DIM = 1536  # text-embedding-3-small 기본 차원


class OpenAIEmbedder(EmbedderBase):
    """
    OpenAI Embeddings API 기반 임베더.
    OPENAI_API_KEY 환경변수가 설정돼 있어야 한다.
    """

    def __init__(
        self,
        model_name: str = _OPENAI_DEFAULT_MODEL,
        api_key: str = OPENAI_API_KEY,
    ) -> None:
        self._model_name = model_name
        self._api_key = api_key
        self._client: Any = None

    def _load(self) -> None:
        if self._client is None:
            if not self._api_key:
                raise ValueError(
                    "OPENAI_API_KEY 가 설정되지 않았습니다. "
                    ".env 에 OPENAI_API_KEY=sk-... 를 추가하세요."
                )
            try:
                from openai import OpenAI
            except ImportError as e:
                raise ImportError(
                    "openai 패키지가 설치되어 있지 않습니다. "
                    "`pip install openai`"
                ) from e
            self._client = OpenAI(api_key=self._api_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._load()
        # OpenAI API 는 배치 최대 2048 토큰 × 입력 수 제한 있음
        # 여기서는 단순 전체 배치 전송 (대량 ingestion 은 indexer 에서 배치 분할)
        response = self._client.embeddings.create(
            model=self._model_name,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        return _OPENAI_DIM

    @property
    def model_name(self) -> str:
        return self._model_name


# ══════════════════════════════════════════════════════════════════
# 팩토리
# ══════════════════════════════════════════════════════════════════

def get_embedder(
    provider: str | None = None,
    model: str | None = None,
) -> EmbedderBase:
    """
    설정 기반으로 적절한 임베더 인스턴스를 반환한다.

    Args:
        provider: "local" | "openai". None 이면 settings.EMBEDDING_PROVIDER 사용.
        model:    모델 이름. None 이면 settings.EMBEDDING_MODEL 사용.

    Returns:
        EmbedderBase 구현 인스턴스 (지연 로딩 — 실제 모델은 첫 embed() 호출 시 로드)
    """
    _provider = (provider or EMBEDDING_PROVIDER).lower()
    _model = model or EMBEDDING_MODEL

    if _provider == "openai":
        return OpenAIEmbedder(model_name=_model)
    elif _provider == "local":
        return LocalEmbedder(model_name=_model)
    else:
        raise ValueError(
            f"알 수 없는 EMBEDDING_PROVIDER: '{_provider}'. "
            "'local' 또는 'openai' 를 사용하세요."
        )
