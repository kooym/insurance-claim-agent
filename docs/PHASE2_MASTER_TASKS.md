# Phase 2 마스터 태스크 및 리소스 준비 현황

> **목적**: Phase 2에서 수행할 작업 목록 정리 및 각 태스크 수행에 필요한 리소스 준비 여부 점검.  
> **진입점**: [architecture/04_Phase2_구현로드맵.md](architecture/04_Phase2_구현로드맵.md)

---

## 1. Phase 2 태스크 요약

| ID | 태스크 | 우선순위 | 예상 공수 | 전제 조건 |
|----|--------|----------|----------|----------|
| **P2-01** | 입원일당 면책일수(질병 4일/재해 1일) rule_ind() 반영 | 높음 | 중 | 없음 |
| **P2-02** | 진료비세부내역서 항목 파싱 → billing_items, ClaimContext 확장 | 높음 | 중 | 없음 |
| **P2-03** | 4세대 비급여 항목별 한도 rule_sil() 적용 | 높음 | 중 | P2-02 완료 |
| **P2-04** | 지급 예정일(3영업일) 계산 및 고객안내문 반영 | 중간 | 소 | 없음 |
| **P2-05** | 수술비 미등록 시 LLM/kcd_to_surgery_codes 추론 | 중간 | 소 | LLM 설정 |
| **P2-06** | OCR 연동 (클로바 또는 GPT-4o Vision) | 중간 | 중 | API 키·가이드 |
| **P2-07** | RAG Agent 파이프라인 (청크·벡터·검색) | 낮음 | 중 | 약관 원문·설정 |

**참고**: COM-004(중복·단기가입·반복 청구)는 이미 구현 완료. Phase 2 로드맵에서 제외.

---

## 2. 태스크별 상세 및 리소스 준비 현황

### P2-01: 입원일당 면책일수 (질병 4일/재해 1일)

| 구분 | 내용 |
|------|------|
| **목표** | rule_ind()에서 입원일수를 그대로 쓰지 않고, 질병 시 4일·재해 시 1일 차감 후 지급일수 산정 |
| **코드** | `src/rules/rule_engine.py::rule_ind()` |
| **계산식** | `payable_days = MAX(0, hospital_days - 4)` (질병), `- 1` (재해) |

**필요 리소스**

| 리소스 | 준비 여부 | 비고 |
|--------|----------|------|
| 기준 문서 | ✅ | docs/insurance_standards/02_입원일당_지급기준.md — 계산식·재입원 14일 사이클 명시 |
| 질병/재해 구분 로직 | ✅ | rule_engine 내 _classify_claim_nature(kcd) 이미 존재 (V/W/X/Y → 재해) |
| contracts_db 담보·daily_benefit | ✅ | get_coverages_by_type("IND"), daily_benefit 사용 중 |
| 연간 누적 입원일수 | ⚠️ | claims_history에 ytd_inpatient_days 있음. 연도·갱신 로직은 보강 가능 |

**결론**: **리소스 준비됨.** 문서·코드·데이터 모두 존재. 구현만 진행하면 됨.

---

### P2-02: 진료비세부내역서 항목 파싱 → billing_items

| 구분 | 내용 |
|------|------|
| **목표** | 진료비세부내역서에서 항목코드(예: MX121, GH901)·금액·횟수 추출 → ParsedDocument.fields, ClaimContext에 반영 |
| **코드** | `src/ocr/doc_parser.py`, `src/schemas.py`, `src/agents/orchestrator.py::build_claim_context()` |

**필요 리소스**

| 리소스 | 준비 여부 | 비고 |
|--------|----------|------|
| 서류 유형 감지 | ✅ | "진료비세부내역서" detect_doc_type 키워드 "항목코드" 존재 |
| 항목코드·한도 매핑 | ✅ | data/reference/billing_codes.json (item_codes, annual_limit_4gen, max_sessions_4gen) |
| data_loader | ✅ | get_billing_codes(), get_4gen_noncover_category() 구현됨 |
| ParsedDocument.fields 표준 키 | ⚠️ | `billing_items` 키 미정의 — 스키마·문서에 추가 필요 |
| ClaimContext 필드 | ⚠️ | `billing_items: list[dict]` 필드 없음 — schemas.py 확장 필요 |
| 세부내역서 샘플 형식 | ✅ | data/sample_docs/CLM-2024-006/05_진료비세부내역서.txt — "항목코드 / 항목명 / 급여여부 / 금액" 행 단위 (예: GH910 비급여 85,000) |

**결론**: **대부분 준비.** billing_codes·로더·샘플 형식(항목코드/항목명/급여여부/금액 행) 존재. 스키마 확장(ParsedDocument.fields, ClaimContext.billing_items) 및 doc_parser에서 행 단위 정규식 추출 로직 추가만 하면 됨.

---

### P2-03: 4세대 비급여 항목별 한도 rule_sil() 적용

| 구분 | 내용 |
|------|------|
| **목표** | ClaimContext.billing_items 기준으로 도수치료 350만/50회, 주사 250만/50회, MRI 300만 한도·횟수 적용 |
| **코드** | `src/rules/rule_engine.py::rule_sil()` |

**필요 리소스**

| 리소스 | 준비 여부 | 비고 |
|--------|----------|------|
| billing_codes.json | ✅ | noncover_categories, code_prefix_mapping 존재 |
| get_4gen_noncover_category() | ✅ | data_loader 구현됨 |
| ClaimContext.billing_items | ❌ | P2-02 완료 후 사용 가능 |
| 연간 누적 (항목별)·보험연도 | ⚠️ | claims_history 또는 별도 누적 저장 필요. 현재 스키마에 없음 |

**결론**: **P2-02 의존.** P2-02에서 billing_items·(선택) 연간 누적 구조 마련 후 rule_sil()에서 한도·횟수 체크 로직 추가.

---

### P2-04: 지급 예정일(3영업일) 계산

| 구분 | 내용 |
|------|------|
| **목표** | 접수일(claim_date) 기준 3영업일 후 날짜 계산 → 고객안내문에 "지급 예정일: YYYY-MM-DD" 명시 |
| **코드** | `src/agents/result_writer.py`, (선택) `src/utils/date_utils.py` |

**필요 리소스**

| 리소스 | 준비 여부 | 비고 |
|--------|----------|------|
| 기준 문서 | ✅ | docs/insurance_standards/05_보험금지급기한_및_법적근거.md |
| claim_date | ✅ | ClaimContext.claim_date 사용 가능 |
| 공휴일 목록 | ⚠️ | 3영업일 계산 시 토·일·공휴일 제외 필요. 한국 공휴일 데이터 또는 휴일 API/파일 필요 |
| result_writer | ✅ | 고객안내문 생성 로직 존재. 여기에 예정일 문자열 주입 가능 |

**결론**: **대부분 준비.** 공휴일 처리만 정하면 됨(간이: 주말만 제외 또는 공휴일 JSON/모듈 추가).

---

### P2-05: 수술비 미등록 시 LLM / kcd_to_surgery_codes 추론

| 구분 | 내용 |
|------|------|
| **목표** | surgery_classification.json에 없는 수술명·코드일 때, KCD 또는 수술명으로 1~5종 추론 후 담당자 플래그 |
| **코드** | `src/utils/data_loader.py::get_surgery_class()`, (확장) rule_engine::rule_sur() |

**필요 리소스**

| 리소스 | 준비 여부 | 비고 |
|--------|----------|------|
| surgery_classification.json | ✅ | 100+ 수술, kcd_to_surgery_codes 역인덱스 있음 |
| get_surgery_class(code, name) | ✅ | 코드·이름 조회 구현됨 |
| KCD→후보 수술 매핑 | ✅ | kcd_to_surgery_codes로 후보 추론 가능 |
| LLM 호출 (미매핑 시) | ⚠️ | settings LLM 설정·API 키 필요. 선택 사항 |
| 수술비 분류 기준 문서 | ✅ | docs/insurance_standards/03_수술비_분류기준.md |

**결론**: **리소스 준비됨.** kcd_to_surgery_codes만으로도 후보 추론 가능. LLM은 "미등록 수술 → 1~5종 추론" 시 선택 적용.

---

### P2-06: OCR 연동 (클로바 / GPT-4o Vision)

| 구분 | 내용 |
|------|------|
| **목표** | PDF·이미지 입력 시 OCR로 텍스트 추출 후 기존 parse_claim_documents()에 넘김 |
| **코드** | `src/ocr/doc_parser.py` — _extract_text_from_pdf(), _extract_text_from_image() 등 추가 |

**필요 리소스**

| 리소스 | 준비 여부 | 비고 |
|--------|----------|------|
| 가이드 문서 | ✅ | docs/skills_mcp_api/03_OCR_연동가이드.md — 클로바·GPT-4o 예시 코드 |
| 설정 | ✅ | CLOVA_OCR_API_URL, CLOVA_OCR_SECRET_KEY, OPENAI_API_KEY (settings) |
| doc_parser 진입점 | ✅ | parse_claim_documents()에서 파일 확장자별 분기 가능 |
| 클로바/GPT-4o API 스펙 | ⚠️ | 실제 엔드포인트·요청 형식은 외부 문서 참조 필요 |
| PDF 페이지별 이미지 변환 | ⚠️ | pdf2image 등 라이브러리 추가 필요 |

**결론**: **가이드·설정 준비됨.** 실제 API 연동·PDF 처리 라이브러리는 구현 시 추가.

---

### P2-07: RAG Agent 파이프라인

| 구분 | 내용 |
|------|------|
| **목표** | 약관·룰북 문서 청크 분할 → 벡터 저장 → ClaimContext 기반 검색 → 판정 근거 보강 또는 담당자 참조용 |
| **코드** | `src/rag/` (신규) 또는 data_loader 확장, rule_engine 선택적 RAG 호출 |

**필요 리소스**

| 리소스 | 준비 여부 | 비고 |
|--------|----------|------|
| 설정 | ✅ | EMBEDDING_PROVIDER, VECTOR_DB_TYPE, RAG_CHUNK_SIZE, RAG_TOP_K, POLICY_DOCS_PATH, VECTOR_DB_PATH |
| 약관 원문 | ⚠️ | data/policies/ 에 standard_policy.md 1건 확인. 룰북·기준 문서 ingestion 확장 가능 |
| 벡터 DB (Chroma/Pinecone) | ⚠️ | 경로만 정의. 초기화·인덱싱 코드 없음 |
| 임베딩 모델 | ⚠️ | local 시 sentence-transformers 등 설치·호출 필요 |

**결론**: **설정·경로 준비됨.** 청크 생성·임베딩·저장·검색 파이프라인 신규 구현 필요. 약관 소스 확장 권장.

---

## 3. 리소스 준비 종합

| 리소스 유형 | 준비됨 | 부족/조건부 |
|-------------|--------|-------------|
| **문서** | 02_입원일당, 03_수술비, 05_지급기한, billing_codes, Phase2 로드맵, OCR 가이드 | 공휴일 정의, RAG 소스 확장 |
| **데이터** | billing_codes.json, surgery (100+), kcd_exclusion, claims_history, contracts_db | billing_items 스키마, 연간 항목별 누적(선택) |
| **코드** | rule_ind/sil/sur, data_loader(billing, injury_grade), doc_parser 기본, result_writer | doc_parser billing_items 추출, RAG 모듈, OCR 호출 |
| **설정** | settings (RAG, OCR, BILLING_CODES_PATH 등) | API 키(.env), 공휴일 데이터 |

---

## 4. 권장 수행 순서

1. **P2-01** 입원일당 면책일수 — 리소스 모두 준비, 독립 구현 가능.  
2. **P2-02** 진료비세부내역서 항목 파싱 — 스키마 확장 + 파서 로직. (샘플 서류 형식 확인 후 진행)  
3. **P2-03** 4세대 항목별 한도 — P2-02 완료 후 rule_sil()에 한도·횟수 로직 추가.  
4. **P2-04** 지급 예정일 — 공휴일 처리 정한 뒤 result_writer 수정.  
5. **P2-05** 수술비 미등록 추론 — kcd_to_surgery_codes 활용 먼저, 필요 시 LLM.  
6. **P2-06** OCR — 가이드 따라 doc_parser에 PDF/이미지 분기·API 호출 추가.  
7. **P2-07** RAG — 청크·임베딩·벡터저장·검색 모듈 구현 후 rule_engine과 연동.

---

## 5. 빠른 체크리스트 (구현 착수 전)

- [ ] 입원일당: 02_입원일당_지급기준.md 계산식 확인
- [ ] 4세대 한도: billing_codes.json 항목코드와 실제 세부내역서 항목코드 형식 매칭
- [ ] 스키마: ParsedDocument.fields `billing_items`, ClaimContext `billing_items` 추가
- [ ] 지급 예정일: 공휴일 목록(또는 주말만 제외) 결정
- [ ] OCR: .env에 CLOVA 또는 OPENAI API 키 설정
- [ ] RAG: data/policies 에 넣을 문서 목록 확정
