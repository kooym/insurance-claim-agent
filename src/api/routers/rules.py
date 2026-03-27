"""
TASK-17: 룰 엔진 직접 실행 엔드포인트.

POST /rules/run     — ClaimContext JSON 직접 전달 → 룰 실행 → 결과 반환
GET  /rules/list    — 구현된 룰 ID + 설명 목록
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from src.api.models import RuleRunRequest, ClaimResultResponse, RuleResultOut
from src.schemas import ClaimContext
from src.rules.rule_engine import run_rules
from src.utils.date_utils import add_business_days_iso

router = APIRouter(prefix="/rules", tags=["rules"])


# 룰 메타데이터 (GET /rules/list 용)
_RULE_REGISTRY = [
    {"rule_id": "COM-001", "category": "COM", "description": "계약 유효성 확인 (상태·납입)"},
    {"rule_id": "COM-002", "category": "COM", "description": "면책기간 확인 (담보별 waiting_period_days)"},
    {"rule_id": "COM-003", "category": "COM", "description": "KCD 절대 면책사유 확인"},
    {"rule_id": "COM-004", "category": "COM", "description": "중복·단기가입·반복 청구 탐지 (FLAGGED)"},
    {"rule_id": "FRD-003", "category": "FRD", "description": "동일 면책사유 반복청구 탐지 (COM-003 FAIL 후 실행)"},
    {"rule_id": "DOC-CHECK", "category": "DOC", "description": "필수 서류 완비 여부 확인"},
    {"rule_id": "IND-001", "category": "IND", "description": "입원일당 산정 (면책일수 질병4일/재해1일 차감)"},
    {"rule_id": "SIL-001", "category": "SIL", "description": "실손의료비 산정 (세대별 자기부담금·4세대 비급여 항목 한도)"},
    {"rule_id": "SUR-001", "category": "SUR", "description": "수술비 정액 지급 (분류표·KCD 후보 추론)"},
    {"rule_id": "FRD-007", "category": "FRD", "description": "비급여 비중 과다 탐지 (FLAGGED, 처리 계속)"},
    {"rule_id": "CONF-001", "category": "CONF", "description": "서류 파싱 신뢰도 낮음 경고 (FLAGGED)"},
    {"rule_id": "CHRONIC-ONSET", "category": "CHRONIC", "description": "만성질환 발병일 불명 — 기왕증 확인 권고 (FLAGGED)"},
]


@router.get("/list", summary="룰 목록 조회")
def list_rules():
    """구현된 룰 ID, 카테고리, 설명 목록을 반환한다."""
    return {"rules": _RULE_REGISTRY, "total": len(_RULE_REGISTRY)}


@router.post(
    "/run",
    response_model=ClaimResultResponse,
    summary="룰 엔진 직접 실행",
    description=(
        "ClaimContext 필드를 JSON 바디로 전달해 룰 엔진을 직접 실행한다.\n\n"
        "서류 파싱 없이 이미 조립된 컨텍스트로 룰만 재실행하거나 테스트할 때 유용하다."
    ),
)
def run_rules_endpoint(req: RuleRunRequest):
    ctx = ClaimContext(
        claim_id=req.claim_id,
        policy_no=req.policy_no,
        claim_date=req.claim_date,
        accident_date=req.accident_date,
        admission_date=req.admission_date,
        discharge_date=req.discharge_date,
        hospital_days=req.hospital_days,
        kcd_code=req.kcd_code,
        diagnosis=req.diagnosis,
        surgery_name=req.surgery_name,
        surgery_code=req.surgery_code,
        covered_self_pay=req.covered_self_pay,
        non_covered_amount=req.non_covered_amount,
        submitted_doc_types=req.submitted_doc_types,
        claimed_coverage_types=req.claimed_coverage_types,
        billing_items=req.billing_items,
        parse_confidence_min=req.parse_confidence_min,
        chronic_onset_flag=req.chronic_onset_flag,
    )

    try:
        decision = run_rules(ctx)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"룰 실행 중 오류: {e}",
        )

    expected_pay_date = add_business_days_iso(req.claim_date, 3)

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
    )
