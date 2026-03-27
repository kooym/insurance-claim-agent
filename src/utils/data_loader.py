"""
참조 데이터 로더 — JSON DB 파일을 메모리에 로드하고 조회 함수를 제공.

설계 원칙:
  - 모든 조회는 O(1) dict 접근으로 처리.
  - 원본 contracts_db.json 은 절대 수정하지 않는다.
  - 신규 등록 계약은 _custom_contracts 레지스트리에 보관하며,
    선택적으로 custom_contracts.json 별도 파일에 영속화한다.
  - get_contract() 는 커스텀 레지스트리를 우선 조회한 뒤 원본 DB 를 조회한다.
"""
from __future__ import annotations
import json
from pathlib import Path

from config.settings import (
    CONTRACTS_DB_PATH,
    CLAIMS_HISTORY_PATH,
    KCD_EXCLUSION_PATH,
    SURGERY_CLASS_PATH,
    SILSON_GEN_PATH,
    BILLING_CODES_PATH,
    INJURY_GRADE_PATH,
    RULE_CLAUSE_MAP_PATH,
    CUSTOM_CONTRACTS_PATH,
)


# mtime 기반 캐시: 파일이 변경되면 자동 재로드
_json_cache: dict[str, tuple[float, dict]] = {}


def _load_json(path: Path) -> dict:
    key = str(path)
    mtime = path.stat().st_mtime
    cached = _json_cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    _json_cache[key] = (mtime, data)
    return data


# ── 커스텀 계약 레지스트리 (런타임 + 파일 영속) ─────────────────
# 원본 contracts_db.json 은 절대 수정하지 않는다.
# 신규 등록 계약은 _custom_contracts 딕셔너리에 보관하며,
# 선택적으로 custom_contracts.json 파일에 저장/로드한다.
_custom_contracts: dict[str, dict] = {}


def register_custom_contract(profile: dict) -> None:
    """신규 등록 계약을 런타임 레지스트리에 추가.

    Args:
        profile: render_new_patient_form() 이 반환하는 프로필 dict.
                 최소 필드: policy_no, name, gender, birth_date,
                 product_name, coverages(list), status, premium_status.
    """
    policy_no = profile.get("policy_no", "")
    if not policy_no:
        return

    # 프로필 → contracts_db 호환 dict 변환
    coverages_dict: dict[str, dict] = {}
    for cov in profile.get("coverages", []):
        code = cov.get("code", "")
        if not code:
            continue
        coverages_dict[code] = {
            "coverage_code": code,
            "coverage_name": cov.get("name", code),
            "type": cov.get("type", ""),
            "status": cov.get("status", "유효"),
            # IND 기본값
            **({
                "daily_benefit": 30000,
                "max_days_per_claim": 180,
                "max_days_per_year": 365,
                "waiting_period_days": 90,
            } if cov.get("type") == "IND" else {}),
            # SIL 기본값
            **({
                "silson_generation": profile.get("silson_generation", 3),
                "copay_rate_covered": 0.2,
                "copay_rate_non_covered": 0.2,
                "min_copay": 10000,
                "annual_limit": 50000000,
                "waiting_period_days": 90,
            } if cov.get("type") == "SIL" else {}),
            # SUR 기본값
            **({
                "surgery_benefit_by_class": {
                    "1": 100000, "2": 300000,
                    "3": 500000, "4": 1000000, "5": 2000000,
                },
                "max_class_covered": 5,
                "waiting_period_days": 90,
            } if cov.get("type") == "SUR" else {}),
        }

    contract = {
        "policy_no": policy_no,
        "product_code": profile.get("product_code", "CUSTOM"),
        "product_name": profile.get("product_name", "커스텀 보험상품"),
        "silson_generation": profile.get("silson_generation", 0),
        "contract_date": profile.get("contract_date", ""),
        "expiry_date": profile.get("expiry_date", ""),
        "status": profile.get("status", "유효"),
        "premium_status": profile.get("premium_status", "정상"),
        "insured": {
            "name": profile.get("name", ""),
            "birth_date": profile.get("birth_date", ""),
            "gender": profile.get("gender", ""),
            "id_masked": profile.get("id_masked", ""),
        },
        "coverages": coverages_dict,
        "ytd_usage": {
            "insurance_year": "2024",
            "inpatient_paid_amount": 0,
            "inpatient_days_used": 0,
            "outpatient_visits_used": 0,
        },
        "product_generation": profile.get("silson_generation", 0),
        "_custom": True,
    }
    _custom_contracts[policy_no] = contract


def save_custom_contracts() -> Path:
    """런타임 커스텀 계약을 custom_contracts.json 에 저장 (원본 보존).

    Returns:
        저장된 파일 경로.
    """
    data = {
        "_meta": {
            "description": "신규 등록 계약 — 원본 contracts_db.json 과 별도 관리.",
            "note": "이 파일은 render_new_patient_form() 에서 등록된 계약만 포함.",
        },
        "contracts": _custom_contracts,
    }
    CUSTOM_CONTRACTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CUSTOM_CONTRACTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return CUSTOM_CONTRACTS_PATH


def load_custom_contracts() -> int:
    """custom_contracts.json 에서 커스텀 계약을 로드하여 레지스트리에 병합.

    Returns:
        로드된 계약 수.
    """
    if not CUSTOM_CONTRACTS_PATH.exists():
        return 0
    try:
        with open(CUSTOM_CONTRACTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        contracts = data.get("contracts", {})
        _custom_contracts.update(contracts)
        return len(contracts)
    except (json.JSONDecodeError, KeyError):
        return 0


def get_custom_contracts() -> dict[str, dict]:
    """런타임 커스텀 계약 레지스트리 전체 반환 (읽기 전용 사본)."""
    return dict(_custom_contracts)


def clear_custom_contracts() -> None:
    """런타임 커스텀 계약 레지스트리 초기화."""
    _custom_contracts.clear()


# ── 계약 DB (원본 + 커스텀 병합 조회) ──────────────────────────
def get_contract(policy_no: str) -> dict | None:
    # 커스텀 레지스트리 우선 조회 (런타임 등록 계약)
    custom = _custom_contracts.get(policy_no)
    if custom:
        return custom
    db = _load_json(CONTRACTS_DB_PATH)
    return db["contracts"].get(policy_no)


def get_coverage(policy_no: str, coverage_code: str) -> dict | None:
    contract = get_contract(policy_no)
    if not contract:
        return None
    return contract["coverages"].get(coverage_code)


def get_coverages_by_type(policy_no: str, coverage_type: str) -> list[dict]:
    """type 필드가 일치하는 담보 목록 반환 (예: 'SIL', 'IND', 'SUR')"""
    contract = get_contract(policy_no)
    if not contract:
        return []
    return [c for c in contract["coverages"].values() if c.get("type") == coverage_type]


# ── 청구 이력 DB ───────────────────────────────────────────────
def get_claims_history(policy_no: str) -> dict | None:
    db = _load_json(CLAIMS_HISTORY_PATH)
    return db["history"].get(policy_no)


# ── KCD 면책 판정 ──────────────────────────────────────────────
def check_kcd_exclusion(kcd_code: str) -> dict | None:
    """
    KCD 코드가 절대적 면책에 해당하는지 확인.
    해당하면 exclusion 정보 dict 반환, 해당 없으면 None.
    """
    db = _load_json(KCD_EXCLUSION_PATH)
    prefix3 = kcd_code[:3]
    prefix2 = kcd_code[:2]

    for category, info in db["absolute_exclusions"].items():
        if not isinstance(info, dict) or "codes" not in info:
            continue
        for code in info["codes"]:
            if kcd_code.startswith(code) or prefix3 == code or prefix2 == code:
                return {
                    "category": category,
                    "matched_code": code,
                    "denial_message": info["denial_message"],
                    "policy_clause": info["policy_clause"],
                }
    return None


# ── 수술 분류 조회 ─────────────────────────────────────────────
def get_surgery_class(surgery_code: str = None, surgery_name: str = None) -> dict | None:
    """수술 코드 또는 수술명으로 수술 종류(1~5종) 조회"""
    db = _load_json(SURGERY_CLASS_PATH)
    for item in db["surgery_map"]:
        if surgery_code and item["code"] == surgery_code:
            return item
        if surgery_name and surgery_name in item["name"]:
            return item
    return None


def get_surgery_code_by_name(surgery_name: str) -> str | None:
    """
    수술명(부분 일치) → 수술코드 조회.
    name_to_code_index 를 먼저 확인하고, 없으면 surgery_map 선형 탐색.
    """
    db = _load_json(SURGERY_CLASS_PATH)
    index = db.get("name_to_code_index", {})

    # 1차: 인덱스에서 정확 일치
    if surgery_name in index:
        return index[surgery_name]

    # 2차: 인덱스에서 부분 일치
    for key, code in index.items():
        if surgery_name in key or key in surgery_name:
            return code

    # 3차: surgery_map 선형 탐색 (부분 일치)
    for item in db["surgery_map"]:
        if surgery_name in item["name"] or item["name"] in surgery_name:
            return item["code"]

    return None


def get_surgery_codes_by_kcd(kcd_code: str) -> list[str]:
    """KCD(또는 접두) → surgery_classification.json kcd_to_surgery_codes 후보."""
    if not kcd_code or kcd_code == "UNKNOWN":
        return []
    db = _load_json(SURGERY_CLASS_PATH)
    idx = db.get("kcd_to_surgery_codes", {})
    if kcd_code in idx and isinstance(idx[kcd_code], list):
        return list(idx[kcd_code])
    prefix = (kcd_code + "   ")[:3].strip()
    if prefix in idx and isinstance(idx[prefix], list):
        return list(idx[prefix])
    return []


# ── 실손 세대 규칙 조회 ────────────────────────────────────────
def get_silson_generation_rule(generation: int) -> dict | None:
    db = _load_json(SILSON_GEN_PATH)
    for rule in db["generation_rules"]:
        if rule["generation"] == generation:
            return rule
    return None


# ── KCD 조건부면책 (정신질환 F계열, 선천기형 Q계열) ─────────────────
def check_kcd_conditional_exclusion(kcd_code: str) -> dict | None:
    """
    KCD가 조건부면책(정신질환 F계열·선천기형 Q계열)에 해당하면 정보 반환.
    F10, F11~F19는 절대면책이므로 제외. 해당 시 담당자 검토 플래그용.
    """
    db = _load_json(KCD_EXCLUSION_PATH)
    cond = db.get("conditional_exclusions", {})
    if not kcd_code or len(kcd_code) < 2:
        return None
    prefix3 = (kcd_code + "  ")[:3].strip()

    # F10, F11~F19는 절대면책 → 여기서 제외
    if prefix3.startswith("F1") and len(prefix3) >= 3:
        if prefix3 in ("F10", "F11", "F12", "F13", "F14", "F15", "F16", "F17", "F18", "F19"):
            return None

    for cat_key, info in cond.items():
        if not isinstance(info, dict) or "codes" not in info or not info["codes"]:
            continue
        for code in info["codes"]:
            if kcd_code.startswith(code) or prefix3 == code:
                return {
                    "category": cat_key,
                    "desc": info.get("desc", ""),
                    "action": info.get("action", "MANUAL_REVIEW"),
                    "coverage_code": info.get("coverage_code"),
                }
    return None


# ── 4세대 비급여 항목 한도 (billing_codes) ─────────────────────
def get_billing_codes() -> dict:
    """billing_codes.json 전체 반환. Phase2 rule_sil() 항목별 한도 적용 시 사용."""
    try:
        return _load_json(BILLING_CODES_PATH)
    except FileNotFoundError:
        return {"noncover_categories": {}, "code_prefix_mapping": {}}


def item_in_4gen_noncover_category(item_code: str, cat: dict) -> bool:
    """항목코드가 해당 4세대 비급여 카테고리에 속하는지."""
    if not item_code or not isinstance(cat, dict):
        return False
    for c in cat.get("item_codes", []):
        if c.endswith("XX") and len(c) >= 3:
            if item_code.startswith(c[:-2]):
                return True
        elif item_code == c or (len(c) >= 3 and item_code.startswith(c[:3])):
            return True
    return False


def get_4gen_noncover_category(item_code: str) -> dict | None:
    """
    항목코드(또는 prefix)로 4세대 비급여 카테고리 조회.
    반환: annual_limit_4gen, max_sessions_4gen, copay_rate_4gen 등.
    """
    db = get_billing_codes()
    categories = db.get("noncover_categories", {})
    prefix_map = db.get("code_prefix_mapping", {})

    for cat_key, cat in categories.items():
        if not isinstance(cat, dict) or "item_codes" not in cat:
            continue
        if item_in_4gen_noncover_category(item_code, cat):
            return {**cat, "_category_key": cat_key}

    for prefix, cat_key in prefix_map.items():
        if cat_key.startswith("_"):
            continue
        if item_code.startswith(prefix):
            c = categories.get(cat_key)
            if c and isinstance(c, dict):
                return {**c, "_category_key": cat_key}
    return None


# ── 부상등급 (injury_grade_table, 변호사선임비 Phase2) ───────────
def get_injury_grade_table() -> dict:
    """injury_grade_table.json 전체 반환."""
    try:
        return _load_json(INJURY_GRADE_PATH)
    except FileNotFoundError:
        return {"grade_definitions": {}, "weeks_to_grade": {}}


def get_injury_grade_by_weeks(weeks: float) -> str | None:
    """
    전치주수(치료기간) → 부상등급(1~14). 자동차보험 변호사선임비 특약용.
    weeks: 소수 가능 (예: 2.5 = 2주 3일).
    """
    table = get_injury_grade_table()
    mapping = table.get("weeks_to_grade", {})
    for range_key, grade in mapping.items():
        if range_key.startswith("_"):
            continue
        parts = range_key.split("_")
        if len(parts) != 2:
            continue
        try:
            low, high = float(parts[0]), float(parts[1])
            if low <= weeks < high:
                return grade
        except ValueError:
            continue
    return None


# ── 룰 → 약관 조항 매핑 ───────────────────────────────────────
def get_rule_clause(rule_id: str) -> dict | None:
    """
    룰 ID → 약관 조항 정보 반환.

    Parameters:
        rule_id: 룰 식별자 (예: 'COM-001', 'IND-001', 'CHRONIC-ONSET')

    Returns:
        dict with keys: policy_clause, clause_title, clause_text, legal_basis
        해당 룰이 없으면 None.
    """
    try:
        db = _load_json(RULE_CLAUSE_MAP_PATH)
    except FileNotFoundError:
        return None
    return db.get("rules", {}).get(rule_id)


def get_all_rule_clauses() -> dict:
    """
    전체 룰 → 약관 조항 매핑 딕셔너리 반환.
    {rule_id: {policy_clause, clause_title, clause_text, legal_basis}, ...}
    """
    try:
        db = _load_json(RULE_CLAUSE_MAP_PATH)
    except FileNotFoundError:
        return {}
    return db.get("rules", {})
