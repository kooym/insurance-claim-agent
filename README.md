# 지급보험금산정 AI Agent — PoC

보험 청구 서류를 읽어 규칙 기반으로 지급 보험금을 자동 산정하는 AI Agent 실증(PoC) 시스템입니다.

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [전체 아키텍처](#2-전체-아키텍처)
3. [폴더 구조](#3-폴더-구조)
4. [빠른 시작 (Quick Start)](#4-빠른-시작)
5. [환경 변수 설정 (.env)](#5-환경-변수-설정)
6. [6가지 시나리오 요약](#6-6가지-시나리오-요약)
7. [데이터 구조 설명](#7-데이터-구조-설명)
8. [설계 원칙](#8-설계-원칙)
9. [향후 개발 로드맵](#9-향후-개발-로드맵)
10. [사전작업 문서](#10-사전작업-문서)

---

## 1. 프로젝트 개요

### 목적

보험사 담당자가 수행하는 **보험금 지급 심사** 업무를 AI Agent로 자동화하는 PoC입니다.

- 고객이 제출한 청구 서류(진단서, 영수증 등)를 읽어 핵심 정보를 추출
- 약관 규칙(룰 엔진)을 적용해 지급 여부와 금액을 산정
- 결과를 담당자가 검토할 수 있는 형식으로 출력

### PoC 범위 (18개 시나리오)

#### 기본 시나리오 (CLM-2024-001 ~ 013)

| 시나리오 | 결과 | 핵심 검증 포인트 |
|---------|------|----------------|
| CLM-2024-001 | **지급** | 입원일당(질병 면책 4일 반영) + 실손 3세대 |
| CLM-2024-002 | **검토필요** | 비급여 비중 72% 초과 → 담당자 플래그 |
| CLM-2024-003 | **부지급** | KCD K70.3 면책사유 자동 탐지 |
| CLM-2024-004 | **보류** | 서류 미비 자동 감지 + 보완 요청 생성 |
| CLM-2024-005 | **부지급** | 면책기간(90일) 이내 청구 자동 거절 |
| CLM-2024-006 | **일부지급** | 4세대 SIL만 (입원 3일→IND 면책일수 초과→IND 부지급) |
| CLM-2024-007 | **검토필요** | 조건부면책(정신질환 F32) — 특약 미가입 FLAGGED |
| CLM-2024-008 | **지급** | 재해 입원(W10 낙상) — 재해담보 면책1일 적용 |
| CLM-2024-009 | **일부지급** | SUR max_class=3인데 4종 수술 → SUR FAIL + IND/SIL 지급 |
| CLM-2024-010 | **부지급** | 계약 실효(미납) → COM-001 FAIL 즉시 부지급 |
| CLM-2024-011 | **지급** | 4세대 실손 비급여 도수치료 한도캡 적용 |
| CLM-2024-012 | **검토필요** | 수술코드 미제공 → KCD로 수술분류 추론 → FLAGGED |
| CLM-2024-013 | **검토필요** | 반복청구(COM-004) + 만성질환 발병일 불명 이중 플래그 |

#### Agent 전용 시나리오 (CLM-2024-101 ~ 105)

| 시나리오 | 결과 | 핵심 검증 포인트 |
|---------|------|----------------|
| CLM-2024-101 | **일부지급** | 고신뢰도 자동승인 — 깨끗한 서류 + auto_approve 라우팅 |
| CLM-2024-102 | **검토필요** | 서류간 정보 불일치 — 교차검증 anomaly → senior_review |
| CLM-2024-103 | **검토필요** | 사기의심 복합플래그 — 과잉입원+고액비급여+반복청구 → mandatory_hold |
| CLM-2024-104 | **일부지급** | 담보해석 경계선 — 미용 vs 기능 모호 → enhanced_review |
| CLM-2024-105 | **일부지급** | 복합담보 혼합판정 — 재해골절+합병증+수술+실손+입원일당 |

---

## 2. 전체 아키텍처

```
[ 입력 ]  data/sample_docs/{claim_id}/*.txt
              │
              ▼
┌─────────────────────────────────────────────────┐
│  Orchestrator  (src/agents/orchestrator.py)      │
│                                                   │
│  ┌──────────────────┐   ┌─────────────────────┐  │
│  │  Doc Parser      │   │  Data Loader        │  │
│  │  (src/ocr/)      │   │  (src/utils/)       │  │
│  │                  │   │                     │  │
│  │  [regex 모드]     │   │  contracts_db.json  │  │
│  │  텍스트에서 추출  │   │  claims_history.json│  │
│  │                  │   │  kcd_exclusion.json  │  │
│  │  [llm 모드]      │   │  surgery_class.json  │  │
│  │  LLM API 호출    │   │  silson_gen.json     │  │
│  └──────────────────┘   └─────────────────────┘  │
│              │                    │               │
│              └──────────┬─────────┘               │
│                         ▼                         │
│              ┌──────────────────┐                 │
│              │  ClaimContext    │                 │
│              │  (src/schemas.py)│                 │
│              └──────────────────┘                 │
│                         │                         │
│                         ▼                         │
│  ┌──────────────────────────────────────────────┐ │
│  │  Rule Engine  (src/rules/rule_engine.py)     │ │
│  │                                              │ │
│  │  COM-001 계약 유효성 ──→ FAIL: 부지급 즉시   │ │
│  │  COM-002 면책기간   ──→ FAIL: 부지급 즉시   │ │
│  │  COM-003 KCD 면책   ──→ FAIL: 부지급 즉시   │ │
│  │  DOC-CHECK 서류완비 ──→ FAIL: 보류 즉시     │ │
│  │                                              │ │
│  │  IND-001 입원일당  ┐                         │ │
│  │  SIL-001 실손의료비 ├→ 각 담보 독립 계산     │ │
│  │  SUR-001 수술비    ┘                         │ │
│  │                                              │ │
│  │  FRD-007 비급여비중 ──→ FLAGGED: 플래그만    │ │
│  └──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
              │
              ▼
[ 출력 ]  outputs/{claim_id}/
          • 보상직원_산정요약.txt  ← 절차·규정·산식·지급예정일 (보상 직원용)
          • decision.json (expected_payment_date 포함)
          • 지급/부지급/보류 문서, 처리로그.json
```

> **상세 아키텍처**: [docs/architecture/01_전체_시스템_아키텍처.md](docs/architecture/01_전체_시스템_아키텍처.md) | [의사결정 논리구조](docs/architecture/02_의사결정_논리구조.md)

### 문서 파싱 방식 (DOC_PARSE_MODE)

| 모드 | 동작 | API 키 필요 | 정확도 |
|-----|------|------------|--------|
| `regex` | 정규식으로 필드 추출 | 불필요 | 중 (PoC 기본) |
| `llm` | LLM API로 서류 전체 파싱 | 필요 | 높음 |
| `hybrid` | regex 실패 시 LLM fallback | 필요 | 가장 높음 (권장) |

---

## 3. 폴더 구조

```
지급보험금산정_agent/
│
├── .env.example          ← 환경 변수 템플릿 (이걸 .env 로 복사해서 사용)
├── .env                  ← 실제 API 키 (git 커밋 금지)
├── .gitignore
├── requirements.txt
├── README.md
│
├── config/
│   ├── __init__.py
│   └── settings.py       ← 모든 설정 중앙 관리. 판단 데이터는 여기 두지 않음.
│
├── src/
│   ├── schemas.py         ← Agent 간 인터페이스 계약 (dataclass 정의)
│   ├── agents/
│   │   └── orchestrator.py ← 처리 흐름 총괄 (LangGraph 8-node 파이프라인)
│   ├── api/
│   │   └── main.py         ← FastAPI REST API (포트 8000)
│   ├── llm/
│   │   └── client.py       ← Azure OpenAI LLM 클라이언트
│   ├── ocr/
│   │   └── doc_parser.py   ← 서류 파일 → 구조화 데이터 추출 (regex/llm/hybrid)
│   ├── rag/
│   │   ├── indexer.py      ← 약관 벡터 인덱싱 (ChromaDB)
│   │   └── retriever.py    ← 약관 검색 (RAG)
│   ├── rules/
│   │   └── rule_engine.py  ← 보험금 산정 룰 실행 (COM/DOC/IND/SIL/SUR/FRD)
│   ├── ui/
│   │   ├── __init__.py     ← CSS 디자인 시스템
│   │   ├── components.py   ← Streamlit UI 컴포넌트 (20+ 렌더 함수)
│   │   └── labels.py       ← 한글 라벨·프로필·시나리오 카드 데이터
│   └── utils/
│       ├── data_loader.py  ← JSON 참조 데이터 로드 및 조회 (O(1))
│       └── comparison_loader.py ← 비교 뷰 데이터 로더
│
├── data/
│   ├── reference/          ← 판단 데이터의 단일 원본 (코드에서 수정 금지)
│   │   ├── contracts_db.json         ← 계약 DB (policy_no 키 기반)
│   │   ├── claims_history_db.json    ← 청구 이력 DB (policy_no 키 기반)
│   │   ├── kcd_exclusion_map.json    ← KCD 면책사유 매핑
│   │   ├── surgery_classification.json ← 수술 분류표 (1~5종)
│   │   └── silson_generation_map.json  ← 실손 세대별 계산 공식
│   │
│   ├── policies/           ← 약관 원문 (RAG 소스)
│   │   └── standard_policy.md
│   │
│   ├── sample_docs/        ← 시나리오별 청구 서류 (Agent 입력)
│   │   ├── CLM-2024-001/ ~ CLM-2024-013/   ← 기본 13개 시나리오
│   │   └── CLM-2024-101/ ~ CLM-2024-105/   ← Agent 전용 5개 시나리오
│   │
│   ├── test_cases/
│   │   ├── scenarios.json            ← 18개 시나리오 정의 (입력·기대결과·Agent메타)
│   │   ├── test_inputs.json          ← 테스트 입력 (계약번호 + 서류 목록)
│   │   └── expected/
│   │       ├── expected_results.json  ← 기본 13개 기대 결과
│   │       └── CLM-2024-{101~105}.json ← Agent 시나리오 golden files
│   │
│   └── vectorstore/        ← ChromaDB 벡터 인덱스 (자동 생성)
│
├── docs/
│   ├── 01_데모가이드.md
│   ├── 02_시나리오정의.md
│   ├── 03_룰정의서.md
│   ├── PRE_WORK_MASTER_TASKS.md    ← 사전작업 마스터 태스크
│   ├── insurance_standards/         ← 보험 기준 문서 (실손·입원일당·수술비·KCD·지급기한)
│   ├── architecture/                ← 아키텍처 명세 (시스템·의사결정·데이터플로우·Phase2)
│   ├── skills_mcp_api/              ← MCP·공공API·OCR·Skills 가이드
│   └── rulebook/
│       ├── 현대해상_보험금산정_룰북.md
│       ├── 변호사선임비용_특약_분석.md
│       └── 00_룰북현황및준비체크리스트.md
│
├── outputs/                ← Agent 실행 결과 (자동 생성)
│   └── {claim_id}/
│       └── decision.json
│
├── app.py                  ← Streamlit UI 메인 (포트 8501)
│
└── tests/                  ← 자동화 테스트 (1,239 passed, 3 skipped)
│   ├── test_agent.py       ← Agent 파이프라인·신뢰도·라우팅·시나리오 (302)
│   ├── test_e2e.py         ← E2E 파이프라인 18개 시나리오 (35)
│   ├── test_ui_integration.py ← UI 통합 18개 시나리오 (132)
│   ├── test_rule_engine.py ← 룰 엔진 단위 테스트 (66)
│   ├── test_comparison_view.py ← 비교 뷰 로더·렌더 (36)
    └── ... (13개 테스트 파일 총 1,242 테스트)
```

---

## 4. 빠른 시작

### 사전 요구사항

- Python 3.11 이상, 3.14 미만 (3.12 권장)
- API 키 (OpenAI 또는 Anthropic — `regex` 모드에서는 불필요)

### 설치

```bash
# 1. 저장소 클론 또는 폴더 이동
cd 지급보험금산정_agent

# 2. 가상환경 생성 및 활성화
python3 -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\activate        # Windows

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 환경 변수 설정
cp .env.example .env
# .env 파일을 열어 필요한 값 입력 (아래 섹션 참고)
```

### 실행

```bash
# API 키 없이 regex 모드로 전체 시나리오 실행
DOC_PARSE_MODE=regex python3 -m src.agents.orchestrator

# 결과 확인
cat outputs/CLM-2024-001/decision.json
cat outputs/CLM-2024-003/decision.json
```

---

## 5. 환경 변수 설정

`.env.example` 을 복사해서 `.env` 파일을 만들고 값을 채웁니다.

### 최소 설정 (API 키 없이 PoC 실행)

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
DOC_PARSE_MODE=regex      ← 이 모드에서는 API 키 불필요
VERBOSE_LOGGING=true
```

### OpenAI 사용 시 (LLM 파싱 활성화)

```env
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=sk-...     ← 여기에 실제 키 입력
DOC_PARSE_MODE=hybrid     ← regex 실패 시 LLM fallback
DOC_PARSE_LLM_MODEL=gpt-4o-mini
```

### Anthropic 사용 시

```env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=sk-ant-...
DOC_PARSE_MODE=hybrid
DOC_PARSE_LLM_MODEL=claude-3-haiku-20240307
```

> **주의**: `.env` 파일은 절대 git에 커밋하지 마세요. `.gitignore`에 이미 포함되어 있습니다.

---

## 6. 주요 시나리오 요약

> 전체 18개 시나리오의 상세 정의: [docs/02_시나리오정의.md](docs/02_시나리오정의.md)

### CLM-2024-001 — 정상 지급

- **피보험자**: 홍길동 | **계약**: POL-20200315-001 (3세대 실손)
- **진단**: K35.8 급성 충수염 | **수술**: 복강경 충수절제술 (3종)
- **입원**: 5일 | **급여 본인부담**: 350,000원 | **비급여**: 180,000원
- **결과**: 입원일당 30,000 (5일 − 면책4일 = 1일 × 30,000) + 실손 = **지급**

### CLM-2024-002 — 검토 필요 (비급여 과다)

- **피보험자**: 김영희 | **계약**: POL-20180601-002 (3세대 실손, 수술비 3종)
- **진단**: D24 유방 양성 신생물 | **수술**: 유방 종양 절제술 (3종)
- **입원**: 2일 | **급여 본인부담**: 420,000원 | **비급여**: 1,100,000원 (72.4%)
- **결과**: 수술비 500,000 + 실손 1,216,000 = **1,716,000원 지급 + 담당자 플래그**

### CLM-2024-003 — 자동 부지급 (면책사유)

- **피보험자**: 이철수 | **계약**: POL-20220901-003
- **진단**: K70.3 알코올성 간경변증 → 약관 제2조 제1항 제3호 면책
- **결과**: **0원, 부지급** — 동일 면책사유 반복 청구 이력으로 사기 조사 검토

### CLM-2024-004 — 자동 보류 (서류 미비)

- **피보험자**: 박지수 | **계약**: POL-20190220-004
- **청구**: 수술비 + 실손 | **제출 서류**: 청구서, 진단서만 제출
- **결과**: **0원, 보류** — 수술확인서·진료비영수증 보완 요청 발송

### CLM-2024-005 — 자동 부지급 (면책기간)

- **피보험자**: 최민준 | **계약**: POL-20240901-005 (2024-09-01 신규 가입)
- **사고일**: 2024-11-03 (계약 후 63일 — 면책기간 90일 이내)
- **결과**: **0원, 부지급** — 면책기간 종료일(2024-11-30) 이전 사고

### CLM-2024-006 — 4세대 실손 일부지급

- **피보험자**: 최민준 | **계약**: POL-20240901-005 (4세대 실손, 2024-09-01 가입)
- **사고일**: 2025-01-15 (면책기간 90일 경과 후)
- **청구**: 입원일당(질병) + 실손의료비(4세대 입원)
- **결과**: **일부지급** — SIL 4세대 입원 계산 적용 (IND 면책일수 초과로 IND 부지급)

---

## 7. 데이터 구조 설명

### 참조 데이터 조회 방식

모든 참조 데이터는 `data/reference/` 폴더의 JSON 파일이 유일한 원본입니다.
코드에서는 `src/utils/data_loader.py` 를 통해서만 접근합니다.

```python
from src.utils.data_loader import get_contract, check_kcd_exclusion, get_surgery_class

# O(1) 계약 조회
contract = get_contract("POL-20200315-001")

# KCD 면책 판정
exclusion = check_kcd_exclusion("K70.3")  # → {"denial_message": "...", "policy_clause": "..."}

# 수술 분류 조회 (코드 또는 이름)
surgery = get_surgery_class(surgery_code="4701")
surgery = get_surgery_class(surgery_name="복강경 충수절제술")
```

### 스키마 계층

```
ParsedDocument      (서류 1건 파싱 결과)
      ↓ 여러 건 조합
ClaimContext        (청구 전체 컨텍스트 — rule_engine 입력)
      ↓ 룰 실행
RuleResult[]        (룰 하나하나의 실행 결과)
      ↓ 집계
ClaimDecision       (최종 판정 — output_writer 입력)
```

---

## 8. 설계 원칙

1. **단일 원본 (Single Source of Truth)**: 보험 판단 데이터는 `data/reference/*.json` 에만 존재합니다. `settings.py`나 코드 안에 보험 상수를 두지 않습니다.

2. **Agent 가 계산해야 할 것은 입력 서류에 쓰지 않는다**: 서류 파일은 실제 OCR 결과처럼 원본 텍스트만 포함합니다. 비율 계산, 면책 판정 등은 Agent 코드가 수행합니다.

3. **테스트 정답 데이터는 격리**: `expected_results.json` 은 `tests/` 에서만 참조합니다. `src/` 코드에서 접근 금지.

4. **None 안전 처리**: 파싱 실패로 정보가 없으면 예외 발생 대신 명시적 FAIL/SKIP 처리합니다.

5. **환경 변수로 모든 외부 연동 제어**: API 키, 모델명, 임계값은 `.env` 로만 주입합니다.

---

## 9. 개발 로드맵

### Phase 1 (완료 ✅ — PoC 준비)
- [x] 13개 시나리오 서류 파일 구성
- [x] 참조 데이터 JSON 완성 (계약 DB, 이력 DB, KCD 맵, 수술 분류, 실손 세대)
- [x] 룰 엔진 구조 설계 및 인터페이스 정의
- [x] env 기반 설정 구조 완성

### Phase 2 (완료 kr✅ — 구현)
- [x] doc_parser 정규식 추출 완성 (날짜, 계약번호 등)
- [x] rule_engine 18개 시나리오 전체 통과 (COM/DOC/IND/SIL/SUR/FRD)
- [x] LLM 기반 파싱 (hybrid 모드) + Vision OCR 파이프라인
- [x] 결과 출력 문서 생성 (지급결의서, 부지급안내문, 보상직원요약)
- [x] Streamlit UI 구현 (시나리오 갤러리 → 4단계 실시간 처리)
- [x] FastAPI REST API (포트 8000)
- [x] RAG 연동 (ChromaDB 벡터 검색 + 약관 조항 인용)
- [x] LangGraph 8-node 오케스트레이션 파이프라인
- [x] Confidence 점수 + 5-tier 리스크 + ReviewRouting
- [x] 비교 뷰 UI (다건 비교 분석 대시보드)

### Block C (완료 ✅ — OCR/Vision)
- [x] C-1~C-7: doc_type 확장, Vision LLM, 신뢰도 점수, 교차검증, 에러 핸들링

### Block A (완료 ✅ — Confidence 시스템)
- [x] A-1~A-8: ConfidenceScore, 5-tier 리스크, 대시보드, ReviewRouting, 교차검증

### Block B (완료 ✅ — Agent 시나리오)
- [x] B-1: Agent 전용 시나리오 데이터 (CLM-2024-101~105)
- [x] B-2: 비교 뷰 UI (comparison_loader + render_comparison_view)
- [x] B-3: Agent 시나리오 E2E 실행 테스트
- [x] B-4: Agent 시나리오 UI 통합 테스트
- [x] B-5: 종합 검증·문서 업데이트

### Block S (완료 ✅ — 안정성 강화)
- [x] S-1: Python 3.12 다운그레이드 + venv 재생성
- [x] S-2: requirements 통합 + NumPy 의존성 명시화
- [x] S-3: st.image() bytes 전달 + fallback
- [x] S-4: LLM 클라이언트 lazy import 전환
- [x] S-5: reset_client() API + retry 리셋
- [x] S-6: run.sh 시작 환경 사전 검증
- [x] S-7: 문서 버전 정합성 + 전환 로드맵

### 프론트엔드 전환 로드맵 (향후)

현재 Streamlit UI + FastAPI 백엔드 구조입니다. Streamlit 자체는 빠른 PoC에 적합하나,
운영 환경에서는 React/Next.js SPA로 전환을 검토할 수 있습니다.
FastAPI 백엔드(`src/api/`)가 이미 구축되어 있어, SPA 전환 시 그대로 활용 가능합니다.

- **현재**: Streamlit (PoC, 불필요한 API 키 없이 regex 모드 데모 가능)
- **향후**: React/Next.js + FastAPI REST API (운영 환경)

### 향후 과제
- [ ] 실제 OCR (Naver Clova / GPT-4o Vision) 운영 연동
- [ ] 연간 누적 한도 (타 청구와 합산) 스키마 확장
- [ ] 5세대 실손 수치 반영 (2026 시행 예정)

---

## 10. 사전작업 문서

전체 시나리오 실행 전 필요한 보험 기준·아키텍처·MCP/API 문서입니다.

| 문서 | 설명 |
|------|------|
| [00_문서목록_및_Agent_가이드](docs/00_문서목록_및_Agent_가이드.md) | 문서 인덱스·Agent 읽기 순서·용어집 (Agent 진입점) |
| [AGENT_문서_포맷_가이드](docs/AGENT_문서_포맷_가이드.md) | Agent가 문서 해석 시 준수할 포맷 규칙 |
| [PRE_WORK_MASTER_TASKS.md](docs/PRE_WORK_MASTER_TASKS.md) | 사전작업 마스터 태스크 (우선순위·상태) |
| [REVIEW_AND_SCORE.md](docs/REVIEW_AND_SCORE.md) | 사전작업 검토·스코어, Phase0/1 MECE 체크 |
| [보험 기준](docs/insurance_standards/) | 실손 세대별, 입원일당, 수술비, KCD 면책, 지급기한 |
| [아키텍처](docs/architecture/) | 시스템 구조, 의사결정 논리, 데이터 플로우, Phase2 로드맵 |
| [MCP/API/Skills](docs/skills_mcp_api/) | MCP 설정, 공공API, OCR 연동, Agent Skills |
