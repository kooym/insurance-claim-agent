"""
TASK-14, 15: 청구 처리 + 결과 조회 엔드포인트.

POST /claims/process              — 서류 디렉터리 기반 청구 처리
POST /claims/process/upload       — 파일 직접 업로드 후 청구 처리
GET  /claims/{claim_id}           — 이전 처리 결과 조회 (decision.json)
GET  /claims/{claim_id}/documents — 제출 서류 파싱 결과 조회
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from src.api.models import (
    ClaimProcessRequest, ClaimResultResponse, RuleResultOut,
    ConfidenceOut, ReviewRoutingOut,
)
from src.agents.orchestrator import process_claim
from src.utils.date_utils import add_business_days_iso
from config.settings import OUTPUT_DIR, SAMPLE_DOCS_PATH

router = APIRouter(prefix="/claims", tags=["claims"])


# ──────────────────────────────────────────────────────────────────
# TASK-15: GET /claims/{claim_id}
# ──────────────────────────────────────────────────────────────────

@router.get(
    "/{claim_id}",
    response_model=ClaimResultResponse,
    summary="청구 결과 조회",
    description="이전에 처리된 청구 결과(decision.json)를 반환한다.",
)
def get_claim_result(claim_id: str):
    decision_path = OUTPUT_DIR / claim_id / "decision.json"
    if not decision_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"청구 결과를 찾을 수 없습니다: {claim_id}. 먼저 /claims/process 를 실행하세요.",
        )
    data = json.loads(decision_path.read_text(encoding="utf-8"))
    return _decision_json_to_response(data, claim_id)


@router.get(
    "/{claim_id}/documents",
    summary="서류 파싱 결과 조회",
    description="처리로그.json 에서 서류 파싱 결과 목록을 반환한다.",
)
def get_claim_documents(claim_id: str):
    log_path = OUTPUT_DIR / claim_id / "처리로그.json"
    if not log_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"처리 로그가 없습니다: {claim_id}",
        )
    data = json.loads(log_path.read_text(encoding="utf-8"))
    return {"claim_id": claim_id, "parsed_documents": data.get("parsed_documents", [])}


# ──────────────────────────────────────────────────────────────────
# TASK-14: POST /claims/process (서류 디렉터리 기반)
# ──────────────────────────────────────────────────────────────────

@router.post(
    "/process",
    response_model=ClaimResultResponse,
    status_code=status.HTTP_200_OK,
    summary="청구 처리 (서류 디렉터리 기반)",
    description=(
        "data/sample_docs/{claim_id}/ 디렉터리의 서류를 파싱하고 룰 엔진을 실행한다.\n\n"
        "서류를 직접 업로드하려면 POST /claims/process/upload 를 사용하세요."
    ),
)
def process_claim_endpoint(req: ClaimProcessRequest):
    doc_dir = SAMPLE_DOCS_PATH / req.claim_id
    if not doc_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"서류 디렉터리가 존재하지 않습니다: {doc_dir}\n"
                "파일을 직접 업로드하려면 POST /claims/process/upload 를 사용하세요."
            ),
        )

    try:
        import os
        if req.doc_parse_mode:
            os.environ["DOC_PARSE_MODE"] = req.doc_parse_mode

        decision = process_claim(
            claim_id=req.claim_id,
            policy_no=req.policy_no,
            claim_date=req.claim_date,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"청구 처리 중 오류가 발생했습니다: {e}",
        )

    expected_pay_date = add_business_days_iso(req.claim_date, 3)
    out_dir = str(OUTPUT_DIR / req.claim_id)

    return ClaimResultResponse(
        claim_id=decision.claim_id,
        decision=decision.decision,
        total_payment=decision.total_payment,
        expected_payment_date=expected_pay_date,
        breakdown=decision.breakdown,
        applied_rules=[
            RuleResultOut(
                rule_id=r.rule_id,
                status=r.status,
                reason=r.reason,
                value=r.value,
            )
            for r in decision.applied_rules
        ],
        reviewer_flag=decision.reviewer_flag,
        reviewer_reason=decision.reviewer_reason,
        missing_docs=decision.missing_docs,
        denial_reason=decision.denial_reason,
        policy_clause=decision.policy_clause,
        fraud_investigation_flag=decision.fraud_investigation_flag,
        output_dir=out_dir,
        confidence=_build_confidence_out(decision),
        review_routing=_build_routing_out(decision),
    )


# ──────────────────────────────────────────────────────────────────
# TASK-14: POST /claims/process/upload (파일 직접 업로드)
# ──────────────────────────────────────────────────────────────────

@router.post(
    "/process/upload",
    response_model=ClaimResultResponse,
    status_code=status.HTTP_200_OK,
    summary="청구 처리 (파일 직접 업로드)",
    description=(
        "서류 파일(.txt/.pdf/.jpg/.png)을 multipart/form-data 로 업로드하고 청구를 처리한다.\n\n"
        "파일들은 임시 디렉터리에 저장 후 파싱되며, 처리 완료 후 자동 정리된다."
    ),
)
async def process_claim_upload(
    claim_id: str = Form(..., description="청구 고유 ID"),
    policy_no: str = Form(..., description="보험계약번호"),
    claim_date: str = Form(..., description="청구 접수일 (YYYY-MM-DD)"),
    doc_parse_mode: Optional[str] = Form(None, description="파싱 모드 (regex/llm/hybrid)"),
    files: list[UploadFile] = File(..., description="청구 서류 파일 목록"),
):
    # 허용 확장자 검사
    _ALLOWED_EXTENSIONS = {".txt", ".pdf", ".jpg", ".jpeg", ".png"}
    for f in files:
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in _ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"지원하지 않는 파일 형식: {f.filename} (허용: {', '.join(_ALLOWED_EXTENSIONS)})",
            )

    # 임시 디렉터리에 저장
    tmp_dir = Path(tempfile.mkdtemp()) / claim_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        for uploaded in files:
            dest = tmp_dir / (uploaded.filename or "unnamed")
            content = await uploaded.read()
            dest.write_bytes(content)

        # 임시 경로를 SAMPLE_DOCS_PATH 로 심볼릭 링크 또는 복사
        target_dir = SAMPLE_DOCS_PATH / claim_id
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(tmp_dir, target_dir)

        import os
        if doc_parse_mode:
            os.environ["DOC_PARSE_MODE"] = doc_parse_mode

        decision = process_claim(
            claim_id=claim_id,
            policy_no=policy_no,
            claim_date=claim_date,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"업로드 처리 중 오류: {e}",
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    expected_pay_date = add_business_days_iso(claim_date, 3)
    return ClaimResultResponse(
        claim_id=decision.claim_id,
        decision=decision.decision,
        total_payment=decision.total_payment,
        expected_payment_date=expected_pay_date,
        breakdown=decision.breakdown,
        applied_rules=[
            RuleResultOut(
                rule_id=r.rule_id,
                status=r.status,
                reason=r.reason,
                value=r.value,
            )
            for r in decision.applied_rules
        ],
        reviewer_flag=decision.reviewer_flag,
        reviewer_reason=decision.reviewer_reason,
        missing_docs=decision.missing_docs,
        denial_reason=decision.denial_reason,
        policy_clause=decision.policy_clause,
        fraud_investigation_flag=decision.fraud_investigation_flag,
        output_dir=str(OUTPUT_DIR / claim_id),
        confidence=_build_confidence_out(decision),
        review_routing=_build_routing_out(decision),
    )


# ──────────────────────────────────────────────────────────────────
# 내부 유틸
# ──────────────────────────────────────────────────────────────────

def _build_confidence_out(decision) -> ConfidenceOut | None:
    """A-8: ClaimDecision.confidence → ConfidenceOut 변환."""
    conf = getattr(decision, "confidence", None)
    if conf is None:
        return None
    return ConfidenceOut(
        parse_confidence=conf.parse_confidence,
        rule_confidence=conf.rule_confidence,
        llm_confidence=conf.llm_confidence,
        cross_validation=conf.cross_validation,
        overall=conf.overall,
        risk_level=conf.risk_level,
        confidence_factors=conf.confidence_factors or None,
    )


def _build_routing_out(decision) -> ReviewRoutingOut | None:
    """A-8: ClaimDecision.review_routing → ReviewRoutingOut 변환."""
    routing = getattr(decision, "review_routing", None)
    if routing is None:
        return None
    return ReviewRoutingOut(
        action=routing.action,
        priority=routing.priority,
        reviewer_level=routing.reviewer_level,
        checklist=routing.checklist,
        estimated_minutes=routing.estimated_minutes,
        routing_reason=routing.routing_reason,
    )


def _decision_json_to_response(data: dict, claim_id: str) -> ClaimResultResponse:
    # A-8: confidence + routing 불러오기
    conf_data = data.get("confidence")
    confidence_out = None
    if conf_data and isinstance(conf_data, dict):
        confidence_out = ConfidenceOut(
            parse_confidence=conf_data.get("parse_confidence", 0),
            rule_confidence=conf_data.get("rule_confidence", 0),
            llm_confidence=conf_data.get("llm_confidence", 0),
            cross_validation=conf_data.get("cross_validation", 0),
            overall=conf_data.get("overall", 0),
            risk_level=conf_data.get("risk_level", "UNKNOWN"),
            confidence_factors=conf_data.get("confidence_factors"),
        )

    routing_data = data.get("review_routing")
    routing_out = None
    if routing_data and isinstance(routing_data, dict):
        routing_out = ReviewRoutingOut(
            action=routing_data.get("action", "standard_review"),
            priority=routing_data.get("priority", "normal"),
            reviewer_level=routing_data.get("reviewer_level", "일반심사역"),
            checklist=routing_data.get("checklist", []),
            estimated_minutes=routing_data.get("estimated_minutes", 0),
            routing_reason=routing_data.get("routing_reason", ""),
        )

    return ClaimResultResponse(
        claim_id=claim_id,
        decision=data.get("decision", ""),
        total_payment=data.get("total_payment", 0),
        expected_payment_date=data.get("expected_payment_date"),
        breakdown=data.get("breakdown", {}),
        applied_rules=[
            RuleResultOut(
                rule_id=r["rule_id"],
                status=r["status"],
                reason=r["reason"],
                value=r.get("value"),
            )
            for r in data.get("applied_rules", [])
        ],
        reviewer_flag=data.get("reviewer_flag", False),
        reviewer_reason=data.get("reviewer_reason"),
        missing_docs=data.get("missing_docs", []),
        denial_reason=data.get("denial_reason"),
        policy_clause=data.get("policy_clause"),
        fraud_investigation_flag=data.get("fraud_investigation_flag", False),
        output_dir=str(OUTPUT_DIR / claim_id),
        confidence=confidence_out,
        review_routing=routing_out,
    )
