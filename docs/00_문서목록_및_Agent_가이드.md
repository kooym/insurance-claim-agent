# 문서 목록 및 Agent 가이드

> **대상**: 이 프로젝트에서 작업하는 AI Agent.  
> **목적**: 어떤 문서를 어떤 순서로 참조할지, 용어 정의, MECE 문서 분류를 한 곳에서 제공.

---

## 1. Agent 작업 시 권장 읽기 순서

| 단계 | 읽을 문서 | 용도 |
|------|----------|------|
| 1 | **본 문서** (00_문서목록_및_Agent_가이드.md) | 진입점, 용어집, 문서 인덱스 |
| 2 | [PRE_WORK_MASTER_TASKS.md](PRE_WORK_MASTER_TASKS.md) | 사전작업 태스크·상태·코드 연결점 |
| 3 | [architecture/01_전체_시스템_아키텍처.md](architecture/01_전체_시스템_아키텍처.md) | 전체 흐름, Phase1/2 구분 |
| 4 | [architecture/03_데이터_플로우_명세.md](architecture/03_데이터_플로우_명세.md) | ParsedDocument → ClaimContext → ClaimDecision 스키마 |
| 5 | [architecture/02_의사결정_논리구조.md](architecture/02_의사결정_논리구조.md) | COM → DOC → IND/SIL/SUR → FRD 플로우 |
| 6 | **보험 기준** (insurance_standards/*.md) | 룰 구현·검증 시 해당 담보/기준 참조 |
| 7 | **룰북** (rulebook/현대해상_보험금산정_룰북.md) | 룰 상세 정의 |
| 8 | [02_시나리오정의.md](02_시나리오정의.md) | 시나리오별 입력·예상 결과 |

---

## 2. 문서 인덱스 (MECE 분류)

### 2.1 기준 (Phase 0 — 보험 기준 문서)

| 문서 | 경로 | 코드 연결점 |
|------|------|-------------|
| 실손 세대별 기준 | insurance_standards/01_실손의료보험_세대별_기준.md | rule_engine.py::rule_sil() |
| 입원일당 지급기준 | insurance_standards/02_입원일당_지급기준.md | rule_engine.py::rule_ind() |
| 수술비 분류기준 | insurance_standards/03_수술비_분류기준.md | surgery_classification.json |
| KCD 면책코드 완전목록 | insurance_standards/04_KCD_면책코드_완전목록.md | kcd_exclusion_map.json |
| 보험금 지급기한·법적근거 | insurance_standards/05_보험금지급기한_및_법적근거.md | result_writer.py |

### 2.2 구조 (Phase 1 — 아키텍처)

| 문서 | 경로 | 용도 |
|------|------|------|
| 전체 시스템 아키텍처 | architecture/01_전체_시스템_아키텍처.md | 흐름, MCP/API 위치 |
| 의사결정 논리구조 | architecture/02_의사결정_논리구조.md | 룰 순서, 법적 근거 |
| 데이터 플로우 명세 | architecture/03_데이터_플로우_명세.md | 스키마, 필드 정의 |
| Phase2 구현로드맵 | architecture/04_Phase2_구현로드맵.md | RAG, OCR, COM-004, 4세대 한도 |
| **Phase2 마스터 태스크** | **PHASE2_MASTER_TASKS.md** | Phase2 작업 목록, 태스크별 리소스 준비 현황 |
| 보상 직원 워크플로우 (Phase2) | **WORKFLOW_보상직원_Phase2.md** | 입력·출력, 산정 규칙 요약, 실행 방법 |

### 2.3 연동 (Phase 1 — MCP/API/Skills)

| 문서 | 경로 | 용도 |
|------|------|------|
| MCP 설정가이드 | skills_mcp_api/01_MCP_설정가이드.md | .cursor/mcp.json |
| 공공API 카탈로그 | skills_mcp_api/02_공공API_카탈로그.md | HIRA, 식약처, data.go.kr |
| OCR 연동가이드 | skills_mcp_api/03_OCR_연동가이드.md | 클로바, GPT-4o Vision |
| Agent Skills 목록 | skills_mcp_api/04_Agent_Skills_목록.md | Parser, Rule Engine, FRD, Writer |

### 2.4 룰·시나리오·계획

| 문서 | 경로 | 용도 |
|------|------|------|
| 사전작업 마스터 태스크 | PRE_WORK_MASTER_TASKS.md | 태스크 목록, 문서·코드 연결점 |
| 검토·스코어 | REVIEW_AND_SCORE.md | 완성도, 갭, 보강 내역 |
| 시나리오 정의 | 02_시나리오정의.md | CLM-2024-001~006 입력·예상 결과 |
| 데모 가이드 | 01_데모가이드.md | 데모 흐름 |
| 룰 정의서 | 03_룰정의서.md | 룰 상세 |
| 현대해상 룰북 | rulebook/현대해상_보험금산정_룰북.md | COM/SIL/IND/SUR/FRD 룰 |
| 룰북 현황·체크리스트 | rulebook/00_룰북현황및준비체크리스트.md | 담보별 완성도 |

---

## 3. 용어집 (Glossary)

Agent가 코드·문서를 읽을 때 동일 의미로 해석하기 위한 용어 정의.

| 용어 | 의미 |
|------|------|
| **COM** | 공통 선행 룰 (COM-001 계약유효성, COM-002 면책기간, COM-003 KCD면책, COM-004 중복·단기가입) |
| **DOC-CHECK** | 서류 완비 확인 룰 |
| **IND** | 입원일당 담보 (IND-001) |
| **SIL** | 실손의료비 담보 (SIL-001) |
| **SUR** | 수술비 담보 (SUR-001) |
| **FRD** | 보험사기 조사 선정 룰 (FRD-003 반복청구, FRD-007 비급여비중 등) |
| **KCD** | 한국표준질병·사인분류 (진단코드, 예: K35.8, K70.3) |
| **ClaimContext** | 단일 청구의 입력 요약 (policy_no, kcd_code, hospital_days, claimed_coverage_types 등) |
| **ClaimDecision** | 룰 엔진 최종 출력 (decision, total_payment, breakdown, applied_rules 등) |
| **RuleResult** | 단일 룰 실행 결과 (rule_id, status, reason, evidence) |
| **status** | PASS \| FAIL \| SKIP \| FLAGGED |
| **decision** | 지급 \| 부지급 \| 보류 \| 검토필요 |
| **담보** | 보험 계약의 보장 단위 (입원일당, 실손의료비, 수술비 등) |
| **면책** | 보험금을 지급하지 않는 사유 (약관 제2조 등) |
| **면책기간** | 가입 후 일정 기간 청구 불인정 (질병 90일, 재해 0일) |
| **4세대 실손** | 2021-07-01~ 가입, 급여 80%·비급여 70% 분리 적용 |

---

## 4. 참조 데이터 파일 (코드에서만 사용)

| 파일 | 경로 | 조회 함수 (data_loader) |
|------|------|------------------------|
| 계약 DB | data/reference/contracts_db.json | get_contract(), get_coverages_by_type() |
| 청구 이력 | data/reference/claims_history_db.json | get_claims_history() |
| KCD 면책 | data/reference/kcd_exclusion_map.json | check_kcd_exclusion(), check_kcd_conditional_exclusion() |
| 수술 분류 | data/reference/surgery_classification.json | get_surgery_class(), get_surgery_code_by_name() |
| 실손 세대 | data/reference/silson_generation_map.json | get_silson_generation_rule() |
| 비급여 항목 한도 | data/reference/billing_codes.json | get_billing_codes(), get_4gen_noncover_category() |
| 부상등급 | data/reference/injury_grade_table.json | get_injury_grade_by_weeks() |

---

## 5. Agent 문서 포맷 원칙

- **제목**: `# 문서명 (Agent 구현용)` 또는 `# 문서명` 후 상단에 목적·출처 블록.
- **표**: 필드·룰·연결점은 표로 정리해 파싱·참조하기 쉽게 함.
- **코드 연결점**: 각 기준/룰 문서 하단에 `코드 연결점` 또는 `Agent 구현 시 참조` 섹션 포함.
- **입력/출력**: 모듈·함수 설명 시 입력(경로·타입)·출력(타입·예시) 명시.

상세: [AGENT_문서_포맷_가이드.md](AGENT_문서_포맷_가이드.md)

---

## 6. 시나리오 ↔ 룰 매핑 (검증 시 참조)

| 시나리오 | 예상 판정 | 적용 룰 (PASS/FAIL/FLAGGED) |
|----------|----------|-----------------------------|
| CLM-2024-001 | 지급 | COM-001~004 PASS, DOC PASS, IND-001 PASS, SIL-001 PASS, FRD-007 PASS |
| CLM-2024-002 | 검토필요 | COM~DOC PASS, SIL-001·SUR-001 PASS, FRD-007 FLAGGED (비급여 72%) |
| CLM-2024-003 | 부지급 | COM-003 FAIL (K70.3), FRD-003 반복청구 |
| CLM-2024-004 | 보류 | COM PASS, DOC-CHECK FAIL (서류 미비) |
| CLM-2024-005 | 부지급 | COM-002 FAIL (면책기간 90일 이내) |
| CLM-2024-006 | 지급 | COM-001~004 PASS, DOC PASS, IND-001·SIL-001 PASS (4세대) |

---

## 7. 검증 방법 (Agent 작업 후)

- **전체 시나리오 실행**: `DOC_PARSE_MODE=regex python3 -m src.agents.orchestrator`
- **기대 결과**: `data/test_cases/expected/expected_results.json` — 청구별 decision, total_payment 등
- **출력**: `outputs/{claim_id}/decision.json`, 지급결의서.txt, 고객안내문.txt
