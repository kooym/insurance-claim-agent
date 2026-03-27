"""
비교 뷰 데이터 로더 — outputs/ 디렉토리에서 심사 결과를 로드하여 비교 가능한 형태로 변환.

B-2: 비교 뷰 UI 를 위한 데이터 계층.

설계 원칙:
  - outputs/<claim_id>/decision.json 을 읽어 ComparisonItem 으로 정규화.
  - 세션 history 와 디스크 outputs/ 를 병합해 "비교 가능 목록" 제공.
  - 로드 실패 시 None 반환 (UI 쪽에서 graceful 처리).
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config.settings import OUTPUT_DIR


# ══════════════════════════════════════════════════════════════
# 비교 항목 데이터 구조
# ══════════════════════════════════════════════════════════════

@dataclass
class ComparisonItem:
    """비교 뷰에서 사용할 정규화된 심사 결과."""
    claim_id: str
    decision: str                           # 지급|부지급|보류|검토필요|일부지급
    total_payment: int
    breakdown: dict = field(default_factory=dict)
    applied_rules_summary: list[dict] = field(default_factory=list)
    confidence: Optional[dict] = None       # ConfidenceScore.to_dict()
    review_routing: Optional[dict] = None   # ReviewRouting.to_dict()
    denial_reason: Optional[str] = None
    denial_coverages: list[dict] = field(default_factory=list)
    reviewer_flag: bool = False
    reviewer_reason: Optional[str] = None
    fraud_flag: bool = False
    fraud_reason: Optional[str] = None
    missing_docs: list[str] = field(default_factory=list)
    generated_at: Optional[str] = None
    source: str = "disk"                    # "disk" | "session"


# ══════════════════════════════════════════════════════════════
# 로더 함수
# ══════════════════════════════════════════════════════════════

def load_decision_json(claim_id: str) -> Optional[dict]:
    """outputs/<claim_id>/decision.json 을 dict 로 로드.

    Returns:
        파싱된 dict, 파일이 없거나 파싱 실패 시 None.
    """
    path = OUTPUT_DIR / claim_id / "decision.json"
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _dict_to_comparison_item(data: dict, source: str = "disk") -> ComparisonItem:
    """decision.json dict → ComparisonItem 변환."""
    # applied_rules 요약 (rule_id, status, reason, value)
    rules_raw = data.get("applied_rules", [])
    rules_summary = []
    for r in rules_raw:
        rules_summary.append({
            "rule_id": r.get("rule_id", ""),
            "status": r.get("status", ""),
            "reason": r.get("reason", ""),
            "value": r.get("value"),
        })

    return ComparisonItem(
        claim_id=data.get("claim_id", ""),
        decision=data.get("decision", ""),
        total_payment=data.get("total_payment", 0),
        breakdown=data.get("breakdown", {}),
        applied_rules_summary=rules_summary,
        confidence=data.get("confidence"),
        review_routing=data.get("review_routing"),
        denial_reason=data.get("denial_reason"),
        denial_coverages=data.get("denial_coverages", []),
        reviewer_flag=data.get("reviewer_flag", False),
        reviewer_reason=data.get("reviewer_reason"),
        fraud_flag=data.get("fraud_investigation_flag", False),
        fraud_reason=data.get("fraud_investigation_reason"),
        missing_docs=data.get("missing_docs", []),
        generated_at=data.get("generated_at"),
        source=source,
    )


def list_available_claims() -> list[str]:
    """outputs/ 디렉토리에서 decision.json 이 있는 claim_id 목록 반환.

    Returns:
        정렬된 claim_id 리스트 (예: ["CLM-2024-001", "CLM-2024-002", ...]).
    """
    if not OUTPUT_DIR.exists():
        return []
    result = []
    for d in sorted(OUTPUT_DIR.iterdir()):
        if d.is_dir() and (d / "decision.json").exists():
            result.append(d.name)
    return result


def load_comparison_items(claim_ids: list[str]) -> list[ComparisonItem]:
    """여러 claim_id 의 decision.json 을 ComparisonItem 리스트로 로드.

    Args:
        claim_ids: 로드할 claim_id 목록.

    Returns:
        로드 성공한 ComparisonItem 리스트 (실패 건은 건너뜀).
    """
    items: list[ComparisonItem] = []
    for cid in claim_ids:
        data = load_decision_json(cid)
        if data:
            items.append(_dict_to_comparison_item(data, source="disk"))
    return items


def compute_comparison_metrics(items: list[ComparisonItem]) -> dict:
    """비교 항목들의 집계 메트릭 산출.

    Returns:
        {
            "count": int,
            "total_sum": int,
            "avg_payment": int,
            "max_payment": int,
            "min_payment": int,
            "decision_distribution": {"지급": 2, "부지급": 1, ...},
            "avg_confidence": float | None,
            "has_confidence": bool,
        }
    """
    if not items:
        return {
            "count": 0, "total_sum": 0, "avg_payment": 0,
            "max_payment": 0, "min_payment": 0,
            "decision_distribution": {},
            "avg_confidence": None, "has_confidence": False,
        }

    payments = [it.total_payment for it in items]
    dist: dict[str, int] = {}
    for it in items:
        dist[it.decision] = dist.get(it.decision, 0) + 1

    # 신뢰도 평균
    conf_values = []
    for it in items:
        if it.confidence and isinstance(it.confidence, dict):
            ov = it.confidence.get("overall")
            if ov is not None:
                conf_values.append(float(ov))

    return {
        "count": len(items),
        "total_sum": sum(payments),
        "avg_payment": int(sum(payments) / len(payments)) if payments else 0,
        "max_payment": max(payments) if payments else 0,
        "min_payment": min(payments) if payments else 0,
        "decision_distribution": dist,
        "avg_confidence": round(sum(conf_values) / len(conf_values), 3) if conf_values else None,
        "has_confidence": bool(conf_values),
    }


def get_coverage_diff(items: list[ComparisonItem]) -> dict[str, list[dict]]:
    """담보별 비교 데이터 추출.

    Returns:
        {
            "IND-001": [
                {"claim_id": "CLM-2024-001", "amount": 30000, "formula": "..."},
                {"claim_id": "CLM-2024-002", "amount": None, "formula": "미산정"},
            ],
            "SIL-001": [...],
            "SUR-001": [...],
        }
    """
    all_cov_ids: set[str] = set()
    for it in items:
        all_cov_ids.update(it.breakdown.keys())

    result: dict[str, list[dict]] = {}
    for cov_id in sorted(all_cov_ids):
        cov_entries: list[dict] = []
        for it in items:
            bd = it.breakdown.get(cov_id)
            if bd:
                amt = bd.get("benefit_amount", 0)
                formula = bd.get("formula", "")
                cov_entries.append({
                    "claim_id": it.claim_id,
                    "amount": amt,
                    "formula": formula,
                })
            else:
                cov_entries.append({
                    "claim_id": it.claim_id,
                    "amount": None,
                    "formula": "미산정",
                })
        result[cov_id] = cov_entries

    return result
