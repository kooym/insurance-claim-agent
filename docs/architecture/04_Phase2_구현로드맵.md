# Phase 2 구현로드맵

> **목적**: Agent가 Phase2에서 구현할 항목과 우선순위를 참조하기 위함.  
> **범위**: RAG Agent, OCR 연동, COM-004(✅ 구현됨), 4세대 비급여 항목별 한도, 입원 면책일수.  
> **코드 연결점**: `docs/architecture/04_Phase2_구현로드맵.md` — 구현 시 본 문서 우선순위 참조.

---

## 1. RAG Agent

### 1.1 현황

- `config/settings.py`에 EMBEDDING_PROVIDER, VECTOR_DB_TYPE, RAG_CHUNK_SIZE 등 설정 존재
- `data/policies/`, `data/vectorstore/` 경로 정의됨
- **파이프라인 미구현**

### 1.2 구현 목표

| 항목 | 내용 |
|------|------|
| 청크 생성 | 약관·룰북 문서 → 청크 분할 (RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP) |
| 벡터 저장 | Chroma 또는 Pinecone에 임베딩 저장 |
| 검색 | ClaimContext 기반 쿼리 → Top-K 유사 청크 조회 |
| 활용 | rule_engine 판정 시 근거 보강, 또는 담당자 검토 시 참조 문서 제공 |

### 1.3 연결점

- `src/utils/data_loader.py` 또는 `src/rag/` 신규 모듈
- `rule_engine.run_rules()` 내부에서 선택적 RAG 호출

---

## 2. OCR 연동

### 2.1 현황

- `config/settings.py`에 CLOVA_OCR_API_URL, CLOVA_OCR_SECRET_KEY 존재
- `src/ocr/doc_parser.py`에 `_parse_with_llm()` 존재
- **실제 PDF/이미지 처리 연동 코드 없음**

### 2.2 구현 목표

| 항목 | 내용 |
|------|------|
| 클로바 OCR | Template/General API 호출 → 텍스트 추출 |
| GPT-4o Vision | 이미지 입력 → 구조화된 JSON 추출 |
| doc_parser | PDF/이미지 입력 시 OCR → parse_claim_documents()에 전달 |

### 2.3 연결점

- `src/ocr/doc_parser.py`에 `_extract_text_from_pdf()`, `_extract_text_from_image()` 추가
- `docs/skills_mcp_api/03_OCR_연동가이드.md` 참조

---

## 3. COM-004 중복청구 — ✅ 구현 완료

### 3.1 현황

- 룰북에 COM-004 설계 존재
- **rule_engine.py에 rule_com_004() 구현 완료**, run_rules() COM 단계 연동됨

### 3.2 구현 내용 (완료)

| 항목 | 내용 |
|------|------|
| 중복 청구 체크 | 동일 청구건(claim_id, policy_no, accident_date) 존재 여부 |
| 단기 가입 후 청구 | (청구일 - 가입일) ≤ 30일 AND 수술비/입원일당 → 담당자 플래그 |
| 반복 청구 | 최근 1년 동일·유사 사고 청구 ≥ 3회 → 담당자 플래그 |

### 3.3 연결점

- `get_claims_history()` 사용, `claims_history_db.json` 스키마 활용
- `rule_com_004()` → `run_rules()` COM 단계에서 실행, FLAGGED 시 reviewer_reason에 반영

---

## 4. 4세대 비급여 항목별 한도 실제 적용

### 4.1 현황

- `silson_generation_map.json`에 4세대 비급여 3대 항목 한도 정의
- **진료비세부내역서 항목코드 파싱 미완** → 항목별 한도 적용 불가

### 4.2 구현 목표

| 항목 | 연간 한도 | 연간 횟수 | 적용 조건 |
|------|----------|----------|----------|
| 도수치료/체외충격파 | 350만 원 | 50회 | 항목코드 MX121, MX122 등 |
| 비급여 주사료 | 250만 원 | 50회 | 항목코드 GH9XX 등 |
| MRI/MRA | 300만 원 | - | 항목코드 HB5XX, HB6XX 등 |

### 4.3 연결점

- `data/reference/billing_codes.json` 생성 (T15)
- `ParsedDocument.fields`에 `billing_items: list[dict]` 추가 (항목코드, 금액, 횟수)
- `rule_sil()` 내부에서 `billing_codes.json` 기반 항목별 한도 체크

---

## 5. 수술비 미등록 처리 (LLM 추론)

### 5.1 현황

- `surgery_classification.json`에 40여 개 수술 등록
- 미등록 수술 시 FAIL

### 5.2 구현 목표

| 항목 | 내용 |
|------|------|
| LLM 유사 분류 | 수술명 + KCD → 1~5종 유사 분류 추론 |
| 담당자 확인 | 추론 결과에 `reviewer_flag` 부여 |
| `kcd_to_surgery_codes` 역인덱스 | KCD만 있을 때 후보 수술 추론 |

### 5.3 연결점

- `get_surgery_class()` 수정: 미매핑 시 LLM 호출 또는 `kcd_to_surgery_codes` 조회
- `docs/insurance_standards/03_수술비_분류기준.md` 참조

---

## 6. 우선순위

| 순위 | 항목 | 예상 공수 | 비고 |
|------|------|----------|------|
| 1 | 4세대 비급여 billing_codes + rule_sil 연동 | 중 | 진료비세부내역서 항목 파싱(P2-02) 선행 |
| 2 | ~~COM-004 중복청구~~ | — | ✅ 구현 완료 |
| 3 | 입원일당 면책일수(4일/1일) rule_ind 반영 | 중 | 문서·로직 준비됨 |
| 4 | OCR 연동 (클로바 또는 GPT-4o Vision) | 중 | 가이드·설정 준비됨 |
| 5 | RAG Agent 파이프라인 | 중 | 설정·경로 준비됨 |
| 6 | 수술비 LLM 추론 | 소 | kcd_to_surgery_codes 활용 가능 |

**상세 태스크·리소스 점검**: [../PHASE2_MASTER_TASKS.md](../PHASE2_MASTER_TASKS.md)
