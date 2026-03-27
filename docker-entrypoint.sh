#!/bin/bash
# ══════════════════════════════════════════════════════════════════
#  보험금 심사 Agent — Docker 엔트리포인트
#  1) RAG 인덱스 확인/빌드
#  2) Streamlit 앱 실행
# ══════════════════════════════════════════════════════════════════
set -e

echo "[entrypoint] Checking RAG index..."
python -c "from src.rag.indexer import ensure_index; ensure_index()" \
    || echo "[entrypoint] RAG index build skipped"

echo "[entrypoint] Users DB: $(ls -la data/users.json 2>/dev/null || echo 'will be created on first access')"

echo "[entrypoint] Starting Streamlit..."
exec python -m streamlit run app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true
