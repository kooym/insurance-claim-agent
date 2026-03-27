"""
프로젝트 전역 설정.

설계 원칙:
  - 모든 외부 연동 값(API 키, 모델명, 임계값)은 환경 변수로 주입받는다.
  - 파일 경로는 이 파일에서 중앙 관리한다.
  - 판단 데이터(KCD 면책, 수술 분류, 실손 세대)는 data/reference/*.json 이 유일한 원본이다.
  - settings.py 에 판단 로직이나 하드코딩된 보험 상수를 두지 않는다.

사용 방법:
  1. .env.example 을 복사해 .env 파일 생성
  2. 필요한 API 키와 파라미터 입력
  3. 코드에서 from config.settings import ... 으로 사용
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 기준으로 .env 파일 자동 탐지
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


# ══════════════════════════════════════════════════════════════════
# 프로젝트 루트 (다른 경로들의 기준점)
# ══════════════════════════════════════════════════════════════════
PROJECT_ROOT = _PROJECT_ROOT


# ══════════════════════════════════════════════════════════════════
# LLM 설정
# ══════════════════════════════════════════════════════════════════
# 공급자: openai | azure | anthropic | hyperclova
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL    = os.getenv("LLM_MODEL",    "gpt-4o")

# API 키 (각자 사용하는 공급자의 키만 .env 에 입력)
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY",     "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY",  "")
CLOVA_API_KEY      = os.getenv("CLOVA_API_KEY",      "")
CLOVA_API_GATEWAY_KEY = os.getenv("CLOVA_API_GATEWAY_KEY", "")

# Azure OpenAI (LLM_PROVIDER=azure 일 때 사용)
AZURE_OPENAI_ENDPOINT    = os.getenv("AZURE_OPENAI_ENDPOINT",    "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
AZURE_OPENAI_DEPLOYMENT  = os.getenv("AZURE_OPENAI_DEPLOYMENT",  "")

LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
LLM_MAX_RETRIES     = int(os.getenv("LLM_MAX_RETRIES",     "3"))
# 최대 출력 토큰 수 (GPT-5 계열 = max_completion_tokens, GPT-4 계열 = max_tokens)
LLM_MAX_TOKENS      = int(os.getenv("LLM_MAX_TOKENS",      "32768"))


# ══════════════════════════════════════════════════════════════════
# 문서 파싱 방식
# ══════════════════════════════════════════════════════════════════
# regex | llm | hybrid
# - regex  : 정규식만 사용. API 키 불필요. PoC 기본값.
# - llm    : LLM 으로 서류 전체 파싱. 높은 정확도, API 비용 발생.
# - hybrid : regex 실패 시 LLM fallback. 권장.
DOC_PARSE_MODE      = os.getenv("DOC_PARSE_MODE", "regex")
DOC_PARSE_LLM_MODEL = os.getenv("DOC_PARSE_LLM_MODEL", "gpt-4o-mini")

# OCR 백엔드: vision | tesseract | hybrid
# - vision   : GPT 멀티모달로 이미지 직접 분석 (권장, 영수증 정확도 높음)
# - tesseract: 로컬 Tesseract OCR (무료, 한국어 의료문서 정확도 낮음)
# - hybrid   : vision 우선, 실패 시 tesseract 폴백
OCR_BACKEND = os.getenv("OCR_BACKEND", "vision")

# Vision OCR 에 사용할 모델 (멀티모달 지원 모델이어야 함)
# gpt-4o가 Visual Grounding(표 구조 인식) 최강 — 복잡한 영수증 표 추출에 최적
# gpt-5.3-chat 등 reasoning 모델은 OCR보다 심사 추론(AGENT_LLM_MODEL)에 적합
VISION_OCR_MODEL = os.getenv("VISION_OCR_MODEL", "gpt-4o")

# OCR (실제 PDF / 이미지 처리 시 — 레거시)
CLOVA_OCR_API_URL    = os.getenv("CLOVA_OCR_API_URL",    "")
CLOVA_OCR_SECRET_KEY = os.getenv("CLOVA_OCR_SECRET_KEY", "")


# ══════════════════════════════════════════════════════════════════
# RAG / 벡터 DB 설정
# ══════════════════════════════════════════════════════════════════
# openai | local
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "local")
EMBEDDING_MODEL    = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)

# chroma | pinecone
VECTOR_DB_TYPE = os.getenv("VECTOR_DB_TYPE", "chroma")

# Pinecone (VECTOR_DB_TYPE=pinecone 일 때만 사용)
PINECONE_API_KEY     = os.getenv("PINECONE_API_KEY",     "")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT", "")
PINECONE_INDEX_NAME  = os.getenv("PINECONE_INDEX_NAME",  "insurance-policy-rag")

RAG_CHUNK_SIZE    = int(os.getenv("RAG_CHUNK_SIZE",    "500"))
RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "50"))
RAG_TOP_K         = int(os.getenv("RAG_TOP_K",         "5"))


# ══════════════════════════════════════════════════════════════════
# 파일 경로 (모두 PROJECT_ROOT 기준 절대경로)
# ══════════════════════════════════════════════════════════════════
# 참조 데이터 (판단의 단일 원본 — 이 경로 외에서 보험 상수를 읽으면 안 됨)
DATA_REF_DIR        = PROJECT_ROOT / "data" / "reference"
CONTRACTS_DB_PATH   = DATA_REF_DIR / "contracts_db.json"
CLAIMS_HISTORY_PATH = DATA_REF_DIR / "claims_history_db.json"
KCD_EXCLUSION_PATH  = DATA_REF_DIR / "kcd_exclusion_map.json"
SURGERY_CLASS_PATH  = DATA_REF_DIR / "surgery_classification.json"
SILSON_GEN_PATH     = DATA_REF_DIR / "silson_generation_map.json"
BILLING_CODES_PATH  = DATA_REF_DIR / "billing_codes.json"
INJURY_GRADE_PATH   = DATA_REF_DIR / "injury_grade_table.json"
RULE_CLAUSE_MAP_PATH = DATA_REF_DIR / "rule_clause_map.json"

# 신규 등록 계약 (원본 contracts_db.json 보존, 별도 파일)
CUSTOM_CONTRACTS_PATH = DATA_REF_DIR / "custom_contracts.json"

# 사용자 DB (인증)
USERS_DB_PATH = PROJECT_ROOT / "data" / "users.json"

# 약관 문서 (RAG 소스)
POLICY_DOCS_PATH = PROJECT_ROOT / "data" / "policies"
VECTOR_DB_PATH   = PROJECT_ROOT / "data" / "vectorstore"

# 테스트 입력 서류
SAMPLE_DOCS_PATH   = PROJECT_ROOT / "data" / "sample_docs"
TEST_INPUTS_PATH   = PROJECT_ROOT / "data" / "test_cases" / "test_inputs.json"
EXPECTED_PATH      = PROJECT_ROOT / "data" / "test_cases" / "expected" / "expected_results.json"

# 출력
OUTPUT_DIR = PROJECT_ROOT / "outputs"
LOG_FILE   = OUTPUT_DIR / "audit.log"


# ══════════════════════════════════════════════════════════════════
# 처리 흐름 제어
# ══════════════════════════════════════════════════════════════════
# 비급여 비중이 이 값을 초과하면 담당자 플래그 부여
NON_COVERED_RATIO_THRESHOLD = float(
    os.getenv("NON_COVERED_RATIO_THRESHOLD", "0.60")
)

# 사기 위험도가 이 레벨 이상이면 human-in-the-loop 강제 진입
HUMAN_REVIEW_TRIGGER_RISK_LEVEL = os.getenv(
    "HUMAN_REVIEW_TRIGGER_RISK_LEVEL", "HIGH"
)

# 서류 파싱 신뢰도 최솟값. 이 값 미만이면 담당자 검토 플래그 부여
# 0.0 = 항상 통과, 1.0 = 완전 추출시에만 통과
PARSE_CONFIDENCE_THRESHOLD = float(
    os.getenv("PARSE_CONFIDENCE_THRESHOLD", "0.5")
)

VERBOSE_LOGGING = os.getenv("VERBOSE_LOGGING", "true").lower() == "true"


# ══════════════════════════════════════════════════════════════════
# API 서버 / UI (선택 사항)
# ══════════════════════════════════════════════════════════════════
API_HOST     = os.getenv("API_HOST",     "0.0.0.0")
API_PORT     = int(os.getenv("API_PORT", "8000"))
API_RELOAD   = os.getenv("API_RELOAD",   "true").lower() == "true"
STREAMLIT_PORT = int(os.getenv("STREAMLIT_PORT", "8501"))


# ══════════════════════════════════════════════════════════════════
# Agent 모드 (LangGraph 기반 Hybrid Agent)
# ══════════════════════════════════════════════════════════════════
# rule  : 기존 룰 기반 파이프라인 (LLM 미사용, 기본값)
# agent : LangGraph Agent + 룰엔진 교차검증 (OpenAI API 필요)
AGENT_MODE = os.getenv("AGENT_MODE", "rule")

# Agent 모드 일일 호출 한도 (건). 초과 시 자동으로 룰 모드 폴백.
AGENT_DAILY_LIMIT = int(os.getenv("AGENT_DAILY_LIMIT", "50"))

# 개발 환경 무제한 모드 — true 설정 시 AGENT_DAILY_LIMIT 무시
AGENT_UNLIMITED_MODE = os.getenv("AGENT_UNLIMITED_MODE", "false").lower() == "true"

# Agent 심사 추론 모델 (파싱은 DOC_PARSE_LLM_MODEL, 심사는 이 모델)
AGENT_LLM_MODEL = os.getenv("AGENT_LLM_MODEL", "gpt-4o")

# 테스트 시 실제 API 호출 여부 (pytest --live 플래그로도 오버라이드 가능)
TEST_USE_LIVE_API = os.getenv("TEST_USE_LIVE_API", "false").lower() == "true"


# ══════════════════════════════════════════════════════════════════
# 로깅
# ══════════════════════════════════════════════════════════════════
LOG_LEVEL = "DEBUG" if VERBOSE_LOGGING else "INFO"
