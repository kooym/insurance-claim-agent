"""
공통 의존성 (Dependency Injection) — TASK-13.

FastAPI Depends() 로 주입되는 싱글턴·설정 객체들.
테스트 시 override_dependency 로 교체 가능.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from src.rag.vectorstore import VectorStoreManager


# ══════════════════════════════════════════════════════════════════
# VectorStoreManager 싱글턴
# ══════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _create_vsm() -> VectorStoreManager:
    """settings 기반 VectorStoreManager 싱글턴 (프로세스당 1개)."""
    return VectorStoreManager()


def get_vsm() -> VectorStoreManager:
    return _create_vsm()


VsmDep = Annotated[VectorStoreManager, Depends(get_vsm)]
