# ══════════════════════════════════════════════════════════════════
#  보험금 심사 Agent — Docker 이미지 (Multi-stage)
#
#  빌드: docker build -t insurance-agent .
#  실행: docker run --rm -p 8501:8501 --env-file .env insurance-agent
# ══════════════════════════════════════════════════════════════════

# ── Stage 1: 의존성 빌드 ────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# sentence-transformers(PyTorch 2GB+)와 pytest 제외 → 이미지 경량화
RUN grep -v -iE "sentence-transformers|pytest" requirements.txt > requirements-prod.txt \
    && pip install --no-cache-dir --prefix=/install -r requirements-prod.txt


# ── Stage 2: 런타임 ────────────────────────────────────────────
FROM python:3.12-slim

# Tesseract OCR (한국어 지원)
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-kor \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 빌드 스테이지에서 설치된 패키지 복사
COPY --from=builder /install /usr/local

WORKDIR /app

# 소스 코드 복사
COPY app.py pyproject.toml ./
COPY config/ ./config/
COPY src/ ./src/
COPY data/reference/ ./data/reference/
COPY data/policies/ ./data/policies/
COPY data/sample_docs/ ./data/sample_docs/
COPY data/test_cases/ ./data/test_cases/
COPY docs/ ./docs/
COPY docker-entrypoint.sh .

# 런타임 디렉토리 생성 + Streamlit 설정
RUN mkdir -p outputs data/vectorstore data/uploads .streamlit \
    && chmod +x docker-entrypoint.sh

# .streamlit/config.toml — address를 0.0.0.0으로 (컨테이너 외부 접근 허용)
RUN printf '[theme]\n\
primaryColor="#1B64DA"\n\
backgroundColor="#FFFFFF"\n\
secondaryBackgroundColor="#F9FAFB"\n\
textColor="#191F28"\n\
font="sans serif"\n\
\n\
[server]\n\
headless=true\n\
port=8501\n\
address="0.0.0.0"\n\
enableCORS=false\n\
enableXsrfProtection=false\n\
\n\
[browser]\n\
gatherUsageStats=false\n' > .streamlit/config.toml

# 보안: non-root 사용자
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
