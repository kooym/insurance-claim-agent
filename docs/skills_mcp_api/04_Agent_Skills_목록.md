# Agent Skills 목록

> 이 프로젝트에 필요한 Skills 정의 (Document Parser, Rule Engine, Fraud Detector, Result Writer)

---

## 1. Document Parser

| 항목 | 내용 |
|------|------|
| **역할** | 청구 서류(보험금청구서, 진단서, 입원확인서, 수술확인서) → ParsedDocument |
| **구현** | `src/ocr/doc_parser.py` |
| **모드** | regex (기본), llm, hybrid |
| **Phase 2** | OCR 연동 (클로바, GPT-4o Vision) |

### 입력/출력

- **입력**: `data/sample_docs/{claim_id}/` 디렉터리
- **출력**: `list[ParsedDocument]` (doc_type, confidence, fields)

---

## 2. Rule Engine

| 항목 | 내용 |
|------|------|
| **역할** | ClaimContext → 룰 순차 실행 → ClaimDecision |
| **구현** | `src/rules/rule_engine.py` |
| **룰** | COM-001~004, DOC-CHECK, IND-001, SIL-001, SUR-001, FRD-007, FIN |

### 룰 순서

1. COM (공통 선행) — FAIL 시 즉시 종료
2. DOC (서류 완비)
3. 담보별 (IND, SIL, SUR)
4. FRD-007 (비급여 비중)
5. FIN (최종 집계)

---

## 3. Fraud Detector

| 항목 | 내용 |
|------|------|
| **역할** | 보험사기 징후 탐지 → reviewer_flag, fraud_investigation_flag |
| **구현** | `rule_engine.py` 내 FRD 룰 (FRD-003, FRD-005, FRD-007, FRD-008 등) |
| **Phase 2** | COM-004 중복청구, FRD 확장 |

### FRD 룰

- **FRD-003**: COM-003 FAIL 시 반복청구 탐지
- **FRD-005**: 비급여 약제 허가범위 (식약처 DUR 연동)
- **FRD-007**: 비급여 비중 60% 초과 → 담당자 플래그
- **FRD-008**: 낮병동 입원, 2cm 미만 결절 등

---

## 4. Result Writer

| 항목 | 내용 |
|------|------|
| **역할** | ClaimDecision → 지급결의서, 고객안내문, decision.json, 처리로그 |
| **구현** | `src/agents/result_writer.py` |
| **출력** | `outputs/{claim_id}/` |

### 생성 파일

| 파일 | 용도 |
|------|------|
| decision.json | 판정 결과 (기계 판독) |
| 지급결의서.txt | 내부 결의 |
| 고객안내문.txt | 고객 발송용 |
| 부지급결의서.txt | 부지급 시 |
| 고객안내문_부지급.txt | 부지급 고객 안내 |
| 처리로그.json | 감사 추적 |

---

## 5. Skills 간 인터페이스

```
Document Parser  →  ParsedDocument[]
Orchestrator     →  ClaimContext
Rule Engine      →  ClaimDecision
Result Writer    ←  ClaimDecision, ClaimContext
```
