"""
TASK-13: FastAPI 앱 진입점.

라우터 구성:
  /health     — TASK-19: 헬스체크 + settings 조회
  /claims     — TASK-14, 15: 청구 처리 + 결과 조회
  /rules      — TASK-17: 룰 엔진 직접 실행
  /rag        — TASK-18, 19: RAG 검색 + 인덱스 관리

OpenAPI 문서:
  http://localhost:8000/docs   — Swagger UI
  http://localhost:8000/redoc  — ReDoc

실행 방법:
  uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import claims, rules, rag, health

# ──────────────────────────────────────────────────────────────────
# FastAPI 인스턴스 (TASK-13)
# ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="지급보험금 산정 Agent REST API",
    description=(
        "보험금 청구 서류를 파싱하고 룰 엔진을 실행하여 지급 여부와 보험금을 산정하는 API.\n\n"
        "## 주요 기능\n"
        "- **청구 처리**: 서류 디렉터리 기반 또는 파일 직접 업로드 처리\n"
        "- **룰 엔진**: ClaimContext JSON으로 룰 직접 실행\n"
        "- **RAG 검색**: 약관·기준 문서 유사도 검색\n"
        "- **인덱스 관리**: 문서 청크 분할·벡터 저장·재구성\n"
    ),
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ──────────────────────────────────────────────────────────────────
# CORS (개발 환경용 — 운영 시 origins 제한 필요)
# ──────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────
# 라우터 등록
# ──────────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(claims.router)
app.include_router(rules.router)
app.include_router(rag.router)


# ──────────────────────────────────────────────────────────────────
# 루트
# ──────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return {
        "message": "지급보험금 산정 Agent REST API",
        "version": "3.0.0",
        "docs": "/docs",
        "health": "/health",
    }
