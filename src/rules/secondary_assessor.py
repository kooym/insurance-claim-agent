"""
2차 심사 엔진 — 추가 영수증 1건을 받아 실손의료비 추가 지급액을 산정한다.

워크플로우:
  1차 심사 완료 → 사용자가 추가 영수증(진료비영수증) 이미지 업로드
  → Vision OCR 파싱(parse_receipt_image) → 2차 심사 엔진(이 모듈)
  → 추가 지급 여부 및 금액 산정

설계 원칙:
  - 2차 심사는 실손의료비(SIL-001)만 재계산한다.
    (입원일당·수술비 등 정액형 담보는 영수증 추가와 무관)
  - 1차 심사에서 부지급/보류 판정이 났으면 2차 심사도 불가.
  - 4세대 비급여 항목별 연간 한도는 1차에서 이미 소진한 분을 차감.
  - 1회 추가 영수증만 지원 (3차, 4차 없음).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional

from src.schemas import ClaimContext, ClaimDecision, ParsedDocument, RuleResult
from src.rules.rule_engine import rule_sil


# ══════════════════════════════════════════════════════════════════
# 2차 심사 결과 스키마
# ══════════════════════════════════════════════════════════════════
@dataclass
class SecondaryAssessmentResult:
    """2차 심사(추가 영수증) 결과."""

    claim_id: str
    success: bool                         # 2차 심사 정상 완료 여부
    reason: str                           # 사람이 읽을 수 있는 설명

    # ── 새 영수증 정보 ─────────────────────────────────────────────
    new_covered_self_pay: int = 0         # 추가 영수증 급여 본인부담금
    new_non_covered: int = 0              # 추가 영수증 비급여 본인부담금

    # ── 2차 SIL-001 산정 결과 ──────────────────────────────────────
    secondary_sil_result: Optional[RuleResult] = None
    additional_payment: int = 0           # 2차에서 추가 지급되는 금액

    # ── 1차 vs 2차 비교표 ──────────────────────────────────────────
    comparison: dict = field(default_factory=dict)
    # {
    #   "primary_sil_amount": int,
    #   "secondary_sil_amount": int,
    #   "additional_payment": int,
    #   "primary_covered": int,
    #   "primary_non_covered": int,
    #   "secondary_covered": int,
    #   "secondary_non_covered": int,
    #   "generation": int,
    #   "care_type": str,
    # }

    # ── 4세대 한도 추적 ────────────────────────────────────────────
    gen4_cap_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """UI 표시용 딕셔너리 변환."""
        d = {
            "claim_id": self.claim_id,
            "success": self.success,
            "reason": self.reason,
            "new_covered_self_pay": self.new_covered_self_pay,
            "new_non_covered": self.new_non_covered,
            "additional_payment": self.additional_payment,
            "comparison": self.comparison,
            "gen4_cap_notes": self.gen4_cap_notes,
        }
        if self.secondary_sil_result:
            d["secondary_sil_evidence"] = self.secondary_sil_result.evidence
        return d


# ══════════════════════════════════════════════════════════════════
# 헬퍼: ParsedDocument → 금액 추출
# ══════════════════════════════════════════════════════════════════

def _extract_amounts_from_receipt(doc: ParsedDocument) -> tuple[int, int, list[dict]]:
    """
    ParsedDocument(진료비영수증 Vision OCR 결과)에서 금액 3종을 추출한다.

    Returns:
        (covered_self_pay, non_covered, billing_items)
    """
    f = doc.fields

    # 1) receipt_summary (Vision OCR 전용 필드) 우선
    summary = f.get("receipt_summary", {})
    covered = _safe_int(summary.get("covered_self_pay"))
    non_cov = _safe_int(summary.get("non_covered_subtotal"))

    # 2) 표준 키 폴백
    if covered is None:
        covered = _safe_int(f.get("covered_self_pay"))
    if non_cov is None:
        non_cov = _safe_int(f.get("non_covered"))

    # 3) receipt_line_items → billing_items 변환 (4세대 한도용)
    billing_items: list[dict] = []
    special_items = f.get("special_items", [])
    for si in special_items:
        billing_items.append({
            "item_code": si.get("item_code", ""),
            "item_name": si.get("item_name", ""),
            "is_noncovered": True,
            "amount": _safe_int(si.get("amount")) or 0,
            "sessions": si.get("sessions", 1),
        })

    # line_items에서 비급여 항목도 수집
    for li in f.get("receipt_line_items", []):
        nc_amt = _safe_int(li.get("non_covered"))
        if nc_amt and nc_amt > 0:
            billing_items.append({
                "item_code": li.get("item_code", ""),
                "item_name": li.get("category", ""),
                "is_noncovered": True,
                "amount": nc_amt,
                "sessions": 1,
            })

    return (covered or 0, non_cov or 0, billing_items)


def _safe_int(val) -> Optional[int]:
    """안전하게 int 변환. 실패 시 None."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


# ══════════════════════════════════════════════════════════════════
# 1차 SIL 결과 추출
# ══════════════════════════════════════════════════════════════════

def _get_primary_sil_result(decision: ClaimDecision) -> Optional[RuleResult]:
    """1차 ClaimDecision에서 SIL-001 결과를 꺼낸다."""
    for r in decision.applied_rules:
        if r.rule_id == "SIL-001" and r.status in ("PASS", "FLAGGED"):
            return r
    return None


# ══════════════════════════════════════════════════════════════════
# 메인 함수
# ══════════════════════════════════════════════════════════════════

def assess_secondary_receipt(
    primary_ctx: ClaimContext,
    primary_decision: ClaimDecision,
    receipt_doc: ParsedDocument,
) -> SecondaryAssessmentResult:
    """
    2차 심사: 추가 영수증 1건으로 실손의료비 추가 지급액 산정.

    Args:
        primary_ctx:      1차 심사에 사용된 ClaimContext
        primary_decision: 1차 심사 결과 ClaimDecision
        receipt_doc:      추가 영수증 파싱 결과 (parse_receipt_image 반환값)

    Returns:
        SecondaryAssessmentResult
    """
    claim_id = primary_ctx.claim_id

    # ── 전제 조건 검증 ─────────────────────────────────────────────
    if primary_decision.decision in ("부지급", "보류"):
        return SecondaryAssessmentResult(
            claim_id=claim_id,
            success=False,
            reason=(
                f"1차 심사 결과가 '{primary_decision.decision}'이므로 "
                f"2차 심사를 진행할 수 없습니다. "
                f"사유: {primary_decision.denial_reason or '서류 미비'}"
            ),
        )

    primary_sil = _get_primary_sil_result(primary_decision)
    if primary_sil is None:
        return SecondaryAssessmentResult(
            claim_id=claim_id,
            success=False,
            reason="1차 심사에서 실손의료비(SIL-001) 산정 결과가 없습니다. 실손 담보 미가입이거나 미청구 상태입니다.",
        )

    # ── 영수증에서 금액 추출 ───────────────────────────────────────
    new_covered, new_non_covered, new_billing_items = _extract_amounts_from_receipt(receipt_doc)

    if new_covered == 0 and new_non_covered == 0:
        return SecondaryAssessmentResult(
            claim_id=claim_id,
            success=False,
            reason="추가 영수증에서 급여/비급여 금액을 추출할 수 없습니다. 영수증을 확인해 주세요.",
        )

    # ── 2차 전용 ClaimContext 생성 ─────────────────────────────────
    secondary_ctx = copy.deepcopy(primary_ctx)
    secondary_ctx.covered_self_pay = new_covered
    secondary_ctx.non_covered_amount = new_non_covered
    secondary_ctx.billing_items = new_billing_items

    # 추가 영수증을 raw_documents에 추가
    secondary_ctx.raw_documents = list(primary_ctx.raw_documents) + [receipt_doc]

    # ── SIL-001 재계산 ─────────────────────────────────────────────
    secondary_sil = rule_sil(secondary_ctx)

    if secondary_sil.status != "PASS":
        return SecondaryAssessmentResult(
            claim_id=claim_id,
            success=False,
            reason=f"2차 실손의료비 산정 실패: {secondary_sil.reason}",
            new_covered_self_pay=new_covered,
            new_non_covered=new_non_covered,
            secondary_sil_result=secondary_sil,
        )

    # ── 추가 지급액 = 2차 SIL 산정액 (새 영수증에 대한 독립 산정) ──
    additional_payment = int(secondary_sil.value or 0)

    # ── 1차 vs 2차 비교표 구성 ─────────────────────────────────────
    primary_evidence = primary_sil.evidence or {}
    secondary_evidence = secondary_sil.evidence or {}

    comparison = {
        "primary_sil_amount": int(primary_sil.value or 0),
        "secondary_sil_amount": additional_payment,
        "additional_payment": additional_payment,
        "total_combined": int(primary_sil.value or 0) + additional_payment,
        "primary_covered": primary_evidence.get("covered_self_pay", 0),
        "primary_non_covered": primary_evidence.get("non_covered_amount", 0),
        "secondary_covered": new_covered,
        "secondary_non_covered": new_non_covered,
        "generation": secondary_evidence.get("silson_generation", 0),
        "care_type": secondary_evidence.get("care_type", ""),
        "primary_copay": primary_evidence.get("copay_applied", 0),
        "secondary_copay": secondary_evidence.get("copay_applied", 0),
        "primary_formula": primary_evidence.get("formula", ""),
        "secondary_formula": secondary_evidence.get("formula", ""),
    }

    # 4세대 한도 메모
    gen4_notes = secondary_evidence.get("sil_4gen_cap_details", [])

    # ── 결과 조립 ──────────────────────────────────────────────────
    gen = secondary_evidence.get("silson_generation", "?")
    care = secondary_evidence.get("care_type", "?")
    reason = (
        f"2차 심사 완료 — 실손 {gen}세대 ({care})\n"
        f"추가 영수증: 급여 {new_covered:,}원, 비급여 {new_non_covered:,}원\n"
        f"추가 지급액: {additional_payment:,}원\n"
        f"(1차 {int(primary_sil.value or 0):,}원 + 2차 {additional_payment:,}원 "
        f"= 합계 {comparison['total_combined']:,}원)"
    )

    return SecondaryAssessmentResult(
        claim_id=claim_id,
        success=True,
        reason=reason,
        new_covered_self_pay=new_covered,
        new_non_covered=new_non_covered,
        secondary_sil_result=secondary_sil,
        additional_payment=additional_payment,
        comparison=comparison,
        gen4_cap_notes=gen4_notes,
    )
