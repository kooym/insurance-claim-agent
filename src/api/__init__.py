"""
REST API 레이어 (TASK-13~19).

FastAPI 앱 진입점:
  src/api/app.py      — FastAPI 인스턴스 + 라우터 등록
  src/api/routers/    — 도메인별 라우터
    claims.py         — TASK-14, 15: 청구 처리 + 결과 조회
    documents.py      — TASK-14: 서류 파일 업로드 + 파싱
    rules.py          — TASK-17: 룰 엔진 직접 실행
    rag.py            — TASK-18: RAG 검색 + 인덱스 관리
    health.py         — TASK-19: 헬스체크 + 관리
  src/api/models.py   — Pydantic 요청/응답 모델
  src/api/deps.py     — 공통 의존성 (설정, 인스턴스 주입)

실행 방법:
  uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
"""
