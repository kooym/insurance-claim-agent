"""
LangGraph Agent 용 Tool 정의.

기존 룰 기반 파이프라인의 함수들을 LangChain Tool 로 래핑한다.
Agent(GPT-4o)가 이 Tool 들을 호출하면서 심사 과정을 수행한다.

Tool 목록:
  1. parse_documents    — 서류 파싱 (doc_parser 래핑)
  2. lookup_contract    — 계약·청구이력 조회 (data_loader 래핑)
  3. search_policy      — 약관 검색 (RAG retriever 래핑)
  4. validate_with_rules— 룰엔진 교차검증 (rule_engine 래핑)
  5. calculate_amount   — 담보별 보험금 산정 (rule_engine 개별 함수 래핑)

설계 원칙:
  - 각 Tool 은 순수 함수. 부작용 없음 (파일 I/O 제외).
  - 반환값은 JSON-serializable dict.
  - 기존 함수를 래핑할 뿐, 로직을 복제하지 않음.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# Tool 1: 서류 파싱
# ══════════════════════════════════════════════════════════════════

def parse_documents(doc_dir: str, mode: str = "regex") -> dict:
    """
    서류 폴더의 모든 문서를 파싱하여 구조화된 데이터를 반환.

    Args:
        doc_dir: 서류 폴더 경로 (예: data/sample_docs/CLM-2024-001)
        mode:    파싱 모드 (regex | llm | hybrid)

    Returns:
        {
            "documents": [
                {
                    "doc_type": "진단서",
                    "fields": {"kcd_code": "K35.8", ...},
                    "confidence": 0.95,
                    "parse_mode": "regex",
                    "parse_errors": [],
                },
                ...
            ],
            "doc_count": 5,
            "min_confidence": 0.85,
        }
    """
    from src.ocr.doc_parser import parse_claim_documents

    doc_path = Path(doc_dir)
    if not doc_path.exists():
        return {"error": f"서류 폴더 없음: {doc_dir}", "documents": [], "doc_count": 0}

    documents = parse_claim_documents(doc_path, mode=mode)

    result_docs = []
    min_conf = 1.0
    for doc in documents:
        min_conf = min(min_conf, doc.confidence)
        result_docs.append({
            "doc_type": doc.doc_type,
            "fields": doc.fields,
            "confidence": doc.confidence,
            "parse_mode": doc.parse_mode,
            "parse_errors": doc.parse_errors,
        })

    return {
        "documents": result_docs,
        "doc_count": len(result_docs),
        "min_confidence": round(min_conf, 3),
    }


# ══════════════════════════════════════════════════════════════════
# Tool 2: 계약·청구이력 조회
# ══════════════════════════════════════════════════════════════════

def lookup_contract(policy_no: str) -> dict:
    """
    계약번호로 계약 정보 + 청구 이력을 조회.

    Args:
        policy_no: 계약번호 (예: "POL-2024-00001")

    Returns:
        {
            "contract": { ... } or None,
            "claims_history": { ... } or None,
            "contract_found": true/false,
        }
    """
    from src.utils.data_loader import get_contract, get_claims_history

    contract = get_contract(policy_no)
    history = get_claims_history(policy_no)

    return {
        "contract": contract,
        "claims_history": history,
        "contract_found": contract is not None,
    }


# ══════════════════════════════════════════════════════════════════
# Tool 3: 약관 검색 (RAG)
# ══════════════════════════════════════════════════════════════════

def search_policy(
    query: str,
    top_k: int = 5,
    min_score: float = 0.0,
) -> dict:
    """
    약관·기준 문서에서 쿼리와 관련된 조항을 검색.

    Args:
        query:     검색 쿼리 (예: "입원일당 면책기간 기준")
        top_k:     반환할 최대 결과 수
        min_score: 최소 유사도 점수

    Returns:
        {
            "chunks": [
                {
                    "text": "...",
                    "score": 0.87,
                    "source": "standard_policy.md",
                    "section": "제5조 입원일당",
                },
                ...
            ],
            "count": 3,
        }
    """
    try:
        from src.rag.retriever import retrieve_raw

        chunks = retrieve_raw(query, top_k=top_k, min_score=min_score)
        result_chunks = []
        for chunk in chunks:
            result_chunks.append({
                "text": chunk.text,
                "score": round(chunk.score, 4),
                "source": chunk.metadata.get("source", ""),
                "section": chunk.metadata.get("section", ""),
                "doc_type": chunk.metadata.get("doc_type", ""),
            })

        return {"chunks": result_chunks, "count": len(result_chunks)}

    except Exception as exc:
        logger.warning("RAG 검색 실패: %s", exc)
        return {"chunks": [], "count": 0, "error": str(exc)}


def search_policy_for_context(
    claim_context_dict: dict,
    top_k: int = 5,
    min_score: float = 0.0,
) -> dict:
    """
    ClaimContext 기반으로 약관 검색 (여러 쿼리 자동 생성).

    Args:
        claim_context_dict: ClaimContext 의 핵심 필드 dict
            (kcd_code, diagnosis, surgery_name, claimed_coverage_types 등)
        top_k:     반환할 최대 결과 수
        min_score: 최소 유사도 점수

    Returns:
        RAG 검색 결과 dict
    """
    try:
        from src.rag.retriever import retrieve, build_queries_from_context
        from src.schemas import ClaimContext

        # dict 에서 최소한의 ClaimContext 복원
        ctx = ClaimContext(
            claim_id=claim_context_dict.get("claim_id", ""),
            policy_no=claim_context_dict.get("policy_no", ""),
            claim_date=claim_context_dict.get("claim_date", ""),
            accident_date=claim_context_dict.get("accident_date", ""),
            admission_date=claim_context_dict.get("admission_date"),
            discharge_date=claim_context_dict.get("discharge_date"),
            hospital_days=claim_context_dict.get("hospital_days"),
            kcd_code=claim_context_dict.get("kcd_code", "UNKNOWN"),
            diagnosis=claim_context_dict.get("diagnosis", ""),
            surgery_name=claim_context_dict.get("surgery_name"),
            surgery_code=claim_context_dict.get("surgery_code"),
            covered_self_pay=claim_context_dict.get("covered_self_pay"),
            non_covered_amount=claim_context_dict.get("non_covered_amount"),
            submitted_doc_types=claim_context_dict.get("submitted_doc_types", []),
            claimed_coverage_types=claim_context_dict.get("claimed_coverage_types", []),
        )

        result = retrieve(ctx, top_k=top_k, min_score=min_score)

        chunks = []
        for chunk in result.chunks:
            chunks.append({
                "text": chunk.text,
                "score": round(chunk.score, 4),
                "source": chunk.metadata.get("source", ""),
                "section": chunk.metadata.get("section", ""),
            })

        return {
            "chunks": chunks,
            "count": len(chunks),
            "queries_used": result.query_texts,
        }

    except Exception as exc:
        logger.warning("컨텍스트 기반 RAG 검색 실패: %s", exc)
        return {"chunks": [], "count": 0, "error": str(exc)}


# ══════════════════════════════════════════════════════════════════
# Tool 4: 룰엔진 교차검증
# ══════════════════════════════════════════════════════════════════

def validate_with_rules(claim_context_dict: dict) -> dict:
    """
    기존 룰엔진으로 심사를 실행하여 교차검증 결과를 반환.

    Agent의 LLM 판정과 비교하기 위한 용도.

    Args:
        claim_context_dict: ClaimContext 를 dict 로 변환한 것
                           (또는 ClaimContext 객체 직접 전달)

    Returns:
        {
            "decision": "지급",
            "total_payment": 450000,
            "applied_rules": [...],
            "breakdown": {...},
            "reviewer_flag": false,
            "denial_reason": null,
        }
    """
    from src.rules.rule_engine import run_rules
    from src.schemas import ClaimContext

    # dict → ClaimContext 변환 (이미 ClaimContext면 그대로 사용)
    if isinstance(claim_context_dict, ClaimContext):
        ctx = claim_context_dict
    else:
        ctx = ClaimContext(
            claim_id=claim_context_dict.get("claim_id", ""),
            policy_no=claim_context_dict.get("policy_no", ""),
            claim_date=claim_context_dict.get("claim_date", ""),
            accident_date=claim_context_dict.get("accident_date", ""),
            admission_date=claim_context_dict.get("admission_date"),
            discharge_date=claim_context_dict.get("discharge_date"),
            hospital_days=claim_context_dict.get("hospital_days"),
            kcd_code=claim_context_dict.get("kcd_code", "UNKNOWN"),
            diagnosis=claim_context_dict.get("diagnosis", ""),
            surgery_name=claim_context_dict.get("surgery_name"),
            surgery_code=claim_context_dict.get("surgery_code"),
            covered_self_pay=claim_context_dict.get("covered_self_pay"),
            non_covered_amount=claim_context_dict.get("non_covered_amount"),
            submitted_doc_types=claim_context_dict.get("submitted_doc_types", []),
            claimed_coverage_types=claim_context_dict.get("claimed_coverage_types", []),
            raw_documents=claim_context_dict.get("raw_documents", []),
            parse_confidence_min=claim_context_dict.get("parse_confidence_min", 1.0),
            billing_items=claim_context_dict.get("billing_items", []),
            chronic_onset_flag=claim_context_dict.get("chronic_onset_flag", False),
        )

    decision = run_rules(ctx)

    return {
        "decision": decision.decision,
        "total_payment": decision.total_payment,
        "applied_rules": [
            {
                "rule_id": r.rule_id,
                "status": r.status,
                "reason": r.reason,
                "value": r.value,
            }
            for r in decision.applied_rules
        ],
        "breakdown": decision.breakdown,
        "reviewer_flag": decision.reviewer_flag,
        "reviewer_reason": decision.reviewer_reason,
        "denial_reason": decision.denial_reason,
        "denial_coverages": decision.denial_coverages,
    }


# ══════════════════════════════════════════════════════════════════
# Tool 5: 담보별 보험금 산정
# ══════════════════════════════════════════════════════════════════

def calculate_amount(
    coverage_type: str,
    contract_info: dict,
    hospital_days: Optional[int] = None,
    covered_self_pay: Optional[int] = None,
    non_covered: Optional[int] = None,
    surgery_code: Optional[str] = None,
) -> dict:
    """
    개별 담보의 보험금을 산정.

    Agent가 룰엔진 전체를 돌리지 않고, 특정 담보의 금액만
    빠르게 계산하고 싶을 때 사용.

    Args:
        coverage_type:   담보 유형 ("IND" | "SIL" | "SUR")
        contract_info:   계약 정보 dict (coverages 포함)
        hospital_days:   입원일수 (IND 산정용)
        covered_self_pay: 급여 본인부담금 (SIL 산정용)
        non_covered:     비급여 (SIL 산정용)
        surgery_code:    수술코드 (SUR 산정용)

    Returns:
        {
            "coverage_type": "IND",
            "amount": 300000,
            "formula": "3일 × 100,000원/일",
            "details": {...},
        }
    """
    if not contract_info:
        return {
            "coverage_type": coverage_type,
            "amount": 0,
            "error": "계약 정보 없음",
        }

    coverages = contract_info.get("coverages", [])
    target = None
    for cov in coverages:
        if cov.get("type") == coverage_type:
            target = cov
            break

    if not target:
        return {
            "coverage_type": coverage_type,
            "amount": 0,
            "error": f"{coverage_type} 담보 미가입",
        }

    if coverage_type == "IND" and hospital_days is not None:
        # 입원일당 = (입원일수 - 면책일수) × 일당
        deductible_days = target.get("deductible_days", 0)
        daily_amount = target.get("daily_amount", 0)
        payable_days = max(0, hospital_days - deductible_days)
        amount = payable_days * daily_amount
        return {
            "coverage_type": "IND",
            "amount": amount,
            "formula": f"{payable_days}일 × {daily_amount:,}원/일",
            "details": {
                "hospital_days": hospital_days,
                "deductible_days": deductible_days,
                "payable_days": payable_days,
                "daily_amount": daily_amount,
            },
        }

    elif coverage_type == "SIL" and covered_self_pay is not None:
        # 실손의료비 (간이 산정)
        generation = target.get("generation", 4)
        deductible = target.get("deductible", 0)
        covered_pay = covered_self_pay or 0
        non_cov = non_covered or 0
        total = covered_pay + non_cov
        amount = max(0, total - deductible)
        return {
            "coverage_type": "SIL",
            "amount": amount,
            "formula": f"({covered_pay:,} + {non_cov:,}) - 자기부담금 {deductible:,}",
            "details": {
                "generation": generation,
                "covered_self_pay": covered_pay,
                "non_covered": non_cov,
                "deductible": deductible,
            },
        }

    elif coverage_type == "SUR" and surgery_code is not None:
        # 수술비 (분류별 고정 금액)
        surgery_amount = target.get("amount", 0)
        return {
            "coverage_type": "SUR",
            "amount": surgery_amount,
            "formula": f"수술코드 {surgery_code} → {surgery_amount:,}원",
            "details": {
                "surgery_code": surgery_code,
                "base_amount": surgery_amount,
            },
        }

    return {
        "coverage_type": coverage_type,
        "amount": 0,
        "error": f"{coverage_type} 산정에 필요한 정보 부족",
    }


# ══════════════════════════════════════════════════════════════════
# Tool 메타데이터 (LangChain Tool 래핑 시 사용)
# ══════════════════════════════════════════════════════════════════

TOOL_DEFINITIONS = [
    {
        "name": "parse_documents",
        "description": "서류 폴더의 모든 문서를 파싱하여 구조화된 데이터 추출 (진단서, 입원확인서, 영수증 등)",
        "function": parse_documents,
    },
    {
        "name": "lookup_contract",
        "description": "계약번호로 보험 계약 정보와 과거 청구 이력을 조회",
        "function": lookup_contract,
    },
    {
        "name": "search_policy",
        "description": "약관·보험 기준 문서에서 관련 조항을 벡터 검색",
        "function": search_policy,
    },
    {
        "name": "validate_with_rules",
        "description": "기존 룰엔진으로 심사를 실행하여 교차검증 결과 반환",
        "function": validate_with_rules,
    },
    {
        "name": "calculate_amount",
        "description": "특정 담보(입원일당/실손/수술비)의 보험금을 산정",
        "function": calculate_amount,
    },
]
