# 지급보험금산정 Agent — 사전작업 마스터 태스크

> **단일 진입점**: 모든 사전작업을 우선순위·카테고리별로 정리한 문서.
> 계획: `pre-work_사전작업_전체_167b3daf.plan.md`

---

## 1. 우선순위별 태스크 요약

| 우선순위 | 태스크 수 | 상태 | 비고 |
|----------|----------|------|------|
| **P0** | 6 | 완료 | 보험 기준 문서 5종 + 마스터 태스크 |
| **P1** | 11 | 완료 | 아키텍처, MCP/API, 데이터 보강 |
| **P2** | 3 | 완료 | injury_grade, mcp.json, README |

---

## 2. P0 — 보험 기준 문서 (완료)

| ID | 태스크 | 산출물 | 상태 |
|----|--------|--------|------|
| T01 | 실손의료보험 세대별 기준 | `docs/insurance_standards/01_실손의료보험_세대별_기준.md` | ✅ |
| T02 | 입원일당 지급기준 | `docs/insurance_standards/02_입원일당_지급기준.md` | ✅ |
| T03 | 수술비 분류기준 | `docs/insurance_standards/03_수술비_분류기준.md` | ✅ |
| T04 | KCD 면책코드 완전목록 | `docs/insurance_standards/04_KCD_면책코드_완전목록.md` | ✅ |
| T05 | 보험금지급기한 및 법적근거 | `docs/insurance_standards/05_보험금지급기한_및_법적근거.md` | ✅ |
| T06 | 마스터 태스크 목록 | `docs/PRE_WORK_MASTER_TASKS.md` (본 문서) | ✅ |

---

## 3. P1 — 아키텍처·MCP·데이터 보강

### 3.1 아키텍처 문서

| ID | 태스크 | 산출물 | 상태 |
|----|--------|--------|------|
| T07 | 전체 시스템 아키텍처 | `docs/architecture/01_전체_시스템_아키텍처.md` | ✅ |
| T08 | 의사결정 논리구조 | `docs/architecture/02_의사결정_논리구조.md` | ✅ |
| T09 | 데이터 플로우 명세 | `docs/architecture/03_데이터_플로우_명세.md` | ✅ |
| T10 | Phase2 구현로드맵 | `docs/architecture/04_Phase2_구현로드맵.md` | ✅ |

### 3.2 MCP/Skills/API 문서

| ID | 태스크 | 산출물 | 상태 |
|----|--------|--------|------|
| T11 | MCP 설정가이드 | `docs/skills_mcp_api/01_MCP_설정가이드.md` | ✅ |
| T12 | 공공API 카탈로그 | `docs/skills_mcp_api/02_공공API_카탈로그.md` | ✅ |
| T13 | OCR 연동가이드 | `docs/skills_mcp_api/03_OCR_연동가이드.md` | ✅ |
| T14 | Agent Skills 목록 | `docs/skills_mcp_api/04_Agent_Skills_목록.md` | ✅ |

### 3.3 데이터 보강

| ID | 태스크 | 산출물 | 상태 |
|----|--------|--------|------|
| T15 | billing_codes.json | `data/reference/billing_codes.json` | ✅ |
| T16 | kcd_exclusion_map 보강 | `data/reference/kcd_exclusion_map.json` | ✅ |
| T17 | surgery_classification 확장 | `data/reference/surgery_classification.json` | ✅ |

---

## 4. P2 — Phase2 준비

| ID | 태스크 | 산출물 | 상태 |
|----|--------|--------|------|
| T18 | injury_grade_table | `data/reference/injury_grade_table.json` | ✅ |
| T19 | MCP 실제 설정 | `.cursor/mcp.json` | ✅ |
| T20 | README 업데이트 | `README.md` | ✅ |

---

## 5. 문서·코드 연결점

| 문서/데이터 | 코드 연결점 | 활용 |
|-------------|------------|------|
| `01_실손의료보험_세대별_기준.md` | `rule_engine.py::rule_sil()` | 5세대 copay 로직 |
| `02_입원일당_지급기준.md` | `rule_engine.py::rule_ind()` | 면책일수 4일/1일 |
| `03_수술비_분류기준.md` | `surgery_classification.json` | 수술 분류표 확장 |
| `04_KCD_면책코드_완전목록.md` | `kcd_exclusion_map.json` | 조건부면책 추가 |
| `billing_codes.json` | `rule_engine.py::rule_sil()` | 4세대 항목별 한도 |
| `01_MCP_설정가이드.md` | `.cursor/mcp.json` | MCP 설치·설정 |
| `02_공공API_카탈로그.md` | `src/utils/data_loader.py` | 외부 API 연동 |
| `03_OCR_연동가이드.md` | `src/ocr/doc_parser.py` | OCR 개선 |

---

## 6. 갭 분석 (착수 전)

| 영역 | 갭 | 우선순위 |
|------|-----|---------|
| 입원일당 | 질병 4일/재해 1일 면책일수 미반영 | P0 |
| 5세대 실손 | 2026년 자부담 50% 미준비 | P1 |
| 수술분류표 | 40여 개 → 수백 개 필요 | P0 |
| KCD | 조건부면책 체계 미완 | P0 |
| COM-004 | 중복청구 룰 미구현 | P1 |
| RAG Agent | 파이프라인 미구현 | P1 |
| 4세대 비급여 | 진료비세부내역서 항목코드 파싱 미완 | P1 |
| MCP | `.cursor/mcp.json` 미설정 | P1 |
| 공공 API | HIRA/식약처 연동 없음 | P2 |
| OCR | 클로바/GPT-4o Vision 연동 없음 | P2 |
