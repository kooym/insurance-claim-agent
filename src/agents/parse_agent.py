"""
서류 파싱 Agent — GPT-4o Structured Output 기반 비정형 서류 구조화.

기존 regex 파싱(doc_parser.py)과 **교차검증**하여 신뢰도를 산출한다.
regex 결과가 있으면 LLM 결과와 필드별 비교하여 불일치 시 confidence 감점.

공개 API:
  parse_with_agent(doc_dir, mode="regex") → list[ParsedDocument]
  parse_single_with_llm(raw_text, doc_type) → dict[str, Any]

설계 원칙:
  - 기존 ParsedDocument 스키마를 반환 (호환성 유지).
  - LLM 파싱 실패 시 regex 결과로 폴백.
  - 교차검증 결과를 evidence 에 기록 (감사 추적).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from src.schemas import ParsedDocument

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# JSON Schema — GPT-4o structured output 용
# ══════════════════════════════════════════════════════════════════

_EXTRACTION_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "document_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "doc_type": {
                    "type": "string",
                    "description": "서류 유형: 진단서|입원확인서|수술확인서|진료비영수증|진료비세부내역서|보험금청구서|미분류",
                },
                "kcd_code": {"type": ["string", "null"], "description": "KCD 상병코드 (예: K35.8)"},
                "diagnosis": {"type": ["string", "null"], "description": "진단명"},
                "hospital_days": {"type": ["integer", "null"], "description": "총 입원일수"},
                "admission_date": {"type": ["string", "null"], "description": "입원일 (YYYY-MM-DD)"},
                "discharge_date": {"type": ["string", "null"], "description": "퇴원일 (YYYY-MM-DD)"},
                "covered_self_pay": {"type": ["integer", "null"], "description": "급여 본인부담금 (원)"},
                "non_covered": {"type": ["integer", "null"], "description": "비급여 본인부담금 (원)"},
                "total_self_pay": {"type": ["integer", "null"], "description": "최종 본인 납부액 (원)"},
                "surgery_name": {"type": ["string", "null"], "description": "수술명"},
                "surgery_code": {"type": ["string", "null"], "description": "수술코드"},
                "surgery_date": {"type": ["string", "null"], "description": "수술일 (YYYY-MM-DD)"},
                "accident_date": {"type": ["string", "null"], "description": "발병/사고일 (YYYY-MM-DD 또는 CHRONIC_UNKNOWN)"},
                "policy_no": {"type": ["string", "null"], "description": "보험계약번호"},
                "confidence": {"type": "number", "description": "추출 확신도 0.0~1.0"},
                "reasoning": {"type": "string", "description": "추출 과정 설명 (한국어, 2-3문장)"},
            },
            "required": [
                "doc_type", "kcd_code", "diagnosis", "hospital_days",
                "admission_date", "discharge_date", "covered_self_pay",
                "non_covered", "total_self_pay", "surgery_name", "surgery_code",
                "surgery_date", "accident_date", "policy_no", "confidence", "reasoning",
            ],
            "additionalProperties": False,
        },
    },
}

_SYSTEM_PROMPT = """당신은 보험 청구 서류에서 정보를 추출하는 전문가입니다.

주어진 서류 텍스트에서 아래 필드를 정확히 추출하세요:
- 서류 유형 (진단서, 입원확인서, 수술확인서, 진료비영수증, 진료비세부내역서, 보험금청구서 중 하나)
- KCD 상병코드, 진단명
- 입원일수, 입원일, 퇴원일
- 급여 본인부담금, 비급여, 최종 본인 납부액
- 수술명, 수술코드, 수술일
- 발병/사고일 (만성질환으로 발병일 불명이면 "CHRONIC_UNKNOWN")
- 보험계약번호

추출 규칙:
1. 금액은 콤마를 제거하고 정수로 반환 (예: 1,200,000 → 1200000)
2. 날짜는 YYYY-MM-DD 형식으로 통일 (예: 2024.12.03 → 2024-12-03)
3. 서류에 해당 정보가 없으면 null 반환
4. reasoning에 추출 과정을 한국어 2-3문장으로 설명

confidence 산출 기준 (A-4):
  - 핵심 필드(서류 유형별 필수 필드) 추출 성공 비율
  - 금액 필드: 원문에 명확한 숫자가 있으면 1.0, 추정이면 0.5
  - 날짜 필드: 원문에 명확한 날짜가 있으면 1.0, 모호하면 0.5
  - KCD 코드: 정확한 코드 형식이면 1.0, 코드 없이 진단명만 있으면 0.4
  - 전체: 추출 성공 필드수 / 전체 필수 필드수 기반으로 0.0~1.0 산출"""


# ══════════════════════════════════════════════════════════════════
# 단일 서류 LLM 파싱
# ══════════════════════════════════════════════════════════════════

def parse_single_with_llm(
    raw_text: str,
    doc_type_hint: str = "미분류",
    model: Optional[str] = None,
) -> dict[str, Any]:
    """
    단일 서류 텍스트를 GPT-4o structured output으로 파싱.

    Args:
        raw_text:      서류 원문 텍스트
        doc_type_hint: regex가 판별한 서류 유형 힌트
        model:         사용할 모델 (기본: settings.DOC_PARSE_LLM_MODEL)

    Returns:
        추출된 필드 dict. 실패 시 {"_llm_error": "..."} 반환.
    """
    try:
        from src.llm.client import chat
        from config.settings import DOC_PARSE_LLM_MODEL

        use_model = model or DOC_PARSE_LLM_MODEL

        # 텍스트가 너무 길면 앞뒤 잘라서 전송
        max_chars = 8000
        if len(raw_text) > max_chars:
            raw_text = raw_text[:max_chars] + "\n\n... (이하 생략)"

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"[서류 유형 힌트: {doc_type_hint}]\n\n"
                    f"아래 서류에서 정보를 추출하세요:\n\n{raw_text}"
                ),
            },
        ]

        response = chat(
            messages=messages,
            model=use_model,
            temperature=0.0,
            max_tokens=2048,
            response_format=_EXTRACTION_SCHEMA,
        )

        content = response.choices[0].message.content
        result = json.loads(content)

        # null → None 정리 + 불필요 키 제거
        fields = {}
        for key, val in result.items():
            if key in ("confidence", "reasoning"):
                continue
            if val is not None:
                fields[key] = val

        fields["_llm_confidence"] = result.get("confidence", 0.5)
        fields["_llm_reasoning"] = result.get("reasoning", "")
        return fields

    except Exception as exc:
        logger.warning("LLM 파싱 실패: %s", exc)
        return {"_llm_error": str(exc)}


# ══════════════════════════════════════════════════════════════════
# 교차검증 — regex vs LLM 결과 비교
# ══════════════════════════════════════════════════════════════════

_COMPARE_FIELDS = [
    "kcd_code", "diagnosis", "hospital_days",
    "admission_date", "discharge_date",
    "covered_self_pay", "non_covered", "total_self_pay",
    "surgery_name", "accident_date",
]


def _cross_validate(
    regex_fields: dict,
    llm_fields: dict,
) -> tuple[dict, float, list[str]]:
    """
    regex 결과와 LLM 결과를 교차검증.

    Returns:
        (merged_fields, confidence_adjustment, discrepancies)
        - merged_fields: regex 우선, LLM으로 보완된 필드
        - confidence_adjustment: -0.1 per mismatch
        - discrepancies: 불일치 필드 설명 목록
    """
    merged = dict(regex_fields)
    discrepancies: list[str] = []
    mismatch_count = 0

    for field_name in _COMPARE_FIELDS:
        regex_val = regex_fields.get(field_name)
        llm_val = llm_fields.get(field_name)

        # LLM에만 있으면 보완
        if regex_val is None and llm_val is not None:
            merged[field_name] = llm_val
            continue

        # 둘 다 있으면 비교
        if regex_val is not None and llm_val is not None:
            if _values_match(regex_val, llm_val):
                continue  # 일치
            else:
                mismatch_count += 1
                discrepancies.append(
                    f"{field_name}: regex={regex_val} vs llm={llm_val}"
                )
                # regex 우선 유지 (숫자 필드는 regex가 더 정확한 경우가 많음)

    confidence_adj = -0.05 * mismatch_count
    return merged, confidence_adj, discrepancies


def _values_match(a: Any, b: Any) -> bool:
    """두 값이 실질적으로 동일한지 비교 (타입 무관)."""
    if a == b:
        return True
    # 숫자 비교 (int vs str)
    try:
        if int(a) == int(b):
            return True
    except (ValueError, TypeError):
        pass
    # 문자열 비교 (공백/대소문자 무시)
    try:
        if str(a).strip().lower() == str(b).strip().lower():
            return True
    except Exception:
        pass
    return False


# ══════════════════════════════════════════════════════════════════
# 메인: Agent 기반 서류 파싱
# ══════════════════════════════════════════════════════════════════

def parse_with_agent(
    doc_dir: str | Path,
    regex_mode: str = "regex",
) -> list[ParsedDocument]:
    """
    Agent 모드 서류 파싱: regex → LLM → 교차검증.

    1. 기존 regex 파싱으로 1차 추출
    2. 각 서류에 대해 LLM structured output 파싱
    3. 교차검증으로 신뢰도 산출 + 필드 보완

    Args:
        doc_dir:     서류 폴더 경로
        regex_mode:  regex 파싱 모드 (기본: "regex")

    Returns:
        list[ParsedDocument] — 교차검증 완료된 파싱 결과
    """
    from src.ocr.doc_parser import parse_claim_documents
    from src.llm.client import is_available

    doc_path = Path(doc_dir)

    # 1. regex 파싱
    regex_docs = parse_claim_documents(doc_path, mode=regex_mode)

    # LLM 미사용 가능하면 regex 결과 그대로 반환
    if not is_available():
        logger.info("LLM 미사용 — regex 결과 반환")
        return regex_docs

    # 2+3. 각 서류에 대해 LLM 파싱 + 교차검증
    enriched_docs: list[ParsedDocument] = []

    for doc in regex_docs:
        try:
            llm_result = parse_single_with_llm(
                raw_text=doc.raw_text,
                doc_type_hint=doc.doc_type,
            )

            if "_llm_error" in llm_result:
                # LLM 실패 → regex 결과 그대로 사용
                doc.parse_errors.append(f"LLM 파싱 실패: {llm_result['_llm_error']}")
                enriched_docs.append(doc)
                continue

            # 교차검증
            merged_fields, conf_adj, mismatches = _cross_validate(
                doc.fields, llm_result,
            )

            # 신뢰도 계산
            llm_conf = llm_result.get("_llm_confidence", 0.5)
            base_conf = doc.confidence
            final_conf = max(0.0, min(1.0, (base_conf + llm_conf) / 2 + conf_adj))

            enriched_doc = ParsedDocument(
                doc_type=doc.doc_type,
                raw_text=doc.raw_text,
                fields=merged_fields,
                parse_mode="agent",
                confidence=round(final_conf, 2),
                parse_errors=doc.parse_errors + (
                    [f"교차검증 불일치: {m}" for m in mismatches]
                ),
            )
            enriched_docs.append(enriched_doc)

            if mismatches:
                logger.info(
                    "교차검증 불일치 (%s): %s",
                    doc.doc_type, "; ".join(mismatches),
                )

        except Exception as exc:
            logger.warning("Agent 파싱 실패 (%s): %s", doc.doc_type, exc)
            enriched_docs.append(doc)

    return enriched_docs
