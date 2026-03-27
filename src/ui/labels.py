"""
코드 → 한글 라벨 매핑 중앙 모듈.

모든 사용자 대면 텍스트에서 내부 코드(COM-001, IND-001, K35.8 등)를
한글 라벨로 변환할 때 이 모듈을 참조한다.

사용 예:
    from src.ui.labels import RULE_LABELS, get_kcd_name, get_insured_profile
    label = RULE_LABELS.get("COM-001", "알 수 없는 규칙")
    diagnosis = get_kcd_name("K35.8")   # "급성 충수염"
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# ── 프로젝트 루트 ──────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_REF_DIR = _PROJECT_ROOT / "data" / "reference"
_TEST_DIR = _PROJECT_ROOT / "data" / "test_cases"


# ══════════════════════════════════════════════════════════════
# 1. 룰 코드 → 한글 라벨
# ══════════════════════════════════════════════════════════════

RULE_LABELS: dict[str, str] = {
    # 공통 선행 규칙
    "COM-001": "계약 유효성 확인",
    "COM-002": "면책기간 확인",
    "COM-003": "KCD 면책사유 확인",
    "COM-004": "중복·반복 청구 확인",
    # 서류 확인
    "DOC-CHECK": "서류 완비 확인",
    # 담보별 산정
    "IND-001": "입원일당 산정",
    "SIL-001": "실손의료비 산정",
    "SUR-001": "수술비 산정",
    # 사기 탐지
    "FRD-003": "반복청구 탐지",
    "FRD-007": "비급여 비중 과다 확인",
    # 품질·후처리
    "CONF-001": "파싱 신뢰도 확인",
    "CHRONIC-ONSET": "만성질환 발병일 확인",
    "CONDITIONAL-EXCLUSION": "조건부 면책사유 확인",
}


# ══════════════════════════════════════════════════════════════
# 2. 담보 코드 → (아이콘 + 한글명, 배경색, 텍스트색)
# ══════════════════════════════════════════════════════════════

COVERAGE_LABELS: dict[str, tuple[str, str, str]] = {
    # (표시명, 배경색, 텍스트색)
    "IND-001": ("🏥 입원일당",    "#E8F5E9", "#2E7D32"),
    "SIL-001": ("💊 실손의료비",  "#E3F2FD", "#1565C0"),
    "SUR-001": ("🔪 수술비",      "#FFF3E0", "#E65100"),
    # 확장 가능 — 향후 담보 추가 시 여기에 등록
    "IND-002": ("🏥 입원일당(재해)", "#E8F5E9", "#2E7D32"),
    "SIL-002": ("💊 실손의료비(통원)", "#E3F2FD", "#1565C0"),
}

def get_coverage_label(rule_id: str) -> tuple[str, str, str]:
    """담보 코드의 (표시명, 배경색, 텍스트색)을 반환. 미등록이면 기본값."""
    return COVERAGE_LABELS.get(rule_id, (f"📋 {rule_id}", "#F5F5F5", "#424242"))


# ══════════════════════════════════════════════════════════════
# 3. 판정 결과 설정
# ══════════════════════════════════════════════════════════════

DECISION_CONFIG: dict[str, dict] = {
    "지급": {
        "icon": "✅", "label": "지급",
        "description": "보험금이 정상 지급돼요",
        "css_class": "decision-pay",
        "color": "#00C853", "bg": "#E8F5E9", "text": "#1B5E20",
    },
    "부지급": {
        "icon": "❌", "label": "부지급",
        "description": "약관에 따라 보험금을 지급하지 않아요",
        "css_class": "decision-deny",
        "color": "#F44336", "bg": "#FFEBEE", "text": "#B71C1C",
    },
    "보류": {
        "icon": "⏸️", "label": "보류",
        "description": "추가 서류가 필요해요",
        "css_class": "decision-hold",
        "color": "#FF9800", "bg": "#FFF8E1", "text": "#E65100",
    },
    "검토필요": {
        "icon": "⚠️", "label": "검토필요",
        "description": "담당자 추가 확인이 필요해요",
        "css_class": "decision-review",
        "color": "#FF9800", "bg": "#FFF3E0", "text": "#E65100",
    },
    "일부지급": {
        "icon": "⚡", "label": "일부지급",
        "description": "한도 적용으로 일부 금액만 지급돼요",
        "css_class": "decision-review",
        "color": "#FF9800", "bg": "#FFF3E0", "text": "#E65100",
    },
}

def get_decision_config(decision: str) -> dict:
    """판정 유형의 표시 설정을 반환. 미등록이면 보류 스타일."""
    return DECISION_CONFIG.get(decision, DECISION_CONFIG["보류"])


# ══════════════════════════════════════════════════════════════
# 4. 룰 상태 → 한글 라벨
# ══════════════════════════════════════════════════════════════

STATUS_LABELS: dict[str, tuple[str, str, str]] = {
    # (한글명, 아이콘, 컬러)
    "PASS":    ("통과", "✅", "#00C853"),
    "FAIL":    ("실패", "❌", "#F44336"),
    "FLAGGED": ("주의", "⚠️", "#FF9800"),
    "SKIP":    ("생략", "⏭️", "#9E9E9E"),
}

def get_status_label(status: str) -> tuple[str, str, str]:
    """상태 코드의 (한글명, 아이콘, 컬러)를 반환."""
    return STATUS_LABELS.get(status, ("알 수 없음", "❓", "#9E9E9E"))


# ══════════════════════════════════════════════════════════════
# 5. KCD 코드 → 한글 진단명 조회
# ══════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _load_kcd_map() -> dict[str, str]:
    """kcd_exclusion_map.json에서 KCD 코드→한글 설명 딕셔너리를 구축."""
    path = _REF_DIR / "kcd_exclusion_map.json"
    if not path.exists():
        return {}

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    result: dict[str, str] = {}

    # absolute_exclusions → detail 딕셔너리
    for category in data.get("absolute_exclusions", {}).values():
        if isinstance(category, str):  # _desc 같은 메타 필드 스킵
            continue
        if isinstance(category, dict):
            for code, desc in category.get("detail", {}).items():
                result[code] = desc
            # desc 필드도 코드 그룹 전체 설명으로 등록
            for code in category.get("codes", []):
                if code not in result:
                    result[code] = category.get("desc", "")

    # conditional_exclusions → desc
    for category in data.get("conditional_exclusions", {}).values():
        if isinstance(category, str):
            continue
        if isinstance(category, dict):
            for code in category.get("codes", []):
                if code not in result:
                    result[code] = category.get("desc", "")

    # auto_pay_eligible → common_diseases
    for item in data.get("auto_pay_eligible", {}).get("common_diseases", []):
        code = item.get("code", "")
        desc = item.get("desc", "")
        if code and desc:
            result[code] = desc

    return result


def get_kcd_name(code: str) -> str:
    """KCD 코드의 한글 진단명을 반환. 없으면 빈 문자열."""
    if not code:
        return ""
    kcd_map = _load_kcd_map()

    # 정확 매칭
    if code in kcd_map:
        return kcd_map[code]

    # 앞 3자리 prefix 매칭 (예: K35.8 → K35)
    prefix = code[:3]
    if prefix in kcd_map:
        return kcd_map[prefix]

    return ""


def format_kcd(code: str) -> str:
    """KCD 코드를 '코드 한글명' 형태로 포매팅. (예: 'K35.8 급성 충수염')"""
    if not code:
        return ""
    name = get_kcd_name(code)
    if name:
        return f"{code} {name}"
    return code


# ══════════════════════════════════════════════════════════════
# 6. 수술 등급 → 설명·금액 조회
# ══════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _load_surgery_data() -> dict:
    """surgery_classification.json 전체를 로드."""
    path = _REF_DIR / "surgery_classification.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_surgery_class_info(surgery_class: int | str) -> dict:
    """수술 등급의 (명칭, 급여액) 정보를 반환.

    Returns:
        {"class": 3, "name": "표준 개복·복강경 수술", "benefit": 500000}
    """
    data = _load_surgery_data()
    cls_str = str(surgery_class)

    definitions = data.get("_class_definitions", {})
    benefits = data.get("_benefit", {})

    return {
        "class": int(cls_str) if cls_str.isdigit() else 0,
        "name": definitions.get(cls_str, f"{cls_str}종 수술"),
        "benefit": benefits.get(cls_str, 0),
    }


def get_surgery_name(code: str | None = None, name: str | None = None) -> str:
    """수술 코드 또는 수술명으로 수술 정보 텍스트를 반환."""
    data = _load_surgery_data()
    for entry in data.get("surgery_map", []):
        if code and entry.get("code") == code:
            cls_info = get_surgery_class_info(entry.get("class", 0))
            return f"{entry['name']} ({cls_info['class']}종)"
        if name and name in entry.get("name", ""):
            cls_info = get_surgery_class_info(entry.get("class", 0))
            return f"{entry['name']} ({cls_info['class']}종)"
    # 매칭 실패 시 원본 반환
    return name or code or ""


# ══════════════════════════════════════════════════════════════
# 7. 계약 DB → 피보험자 프로필 조회
# ══════════════════════════════════════════════════════════════

@lru_cache(maxsize=8)
def _load_contracts_db() -> dict:
    """contracts_db.json 로드."""
    path = _REF_DIR / "contracts_db.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_all_insured_profiles() -> list[dict]:
    """모든 피보험자 프로필 목록 반환 (피보험자 검색/조회 UI용).

    Returns:
        [get_insured_profile(policy_no) 결과, ...] 전체 리스트.
    """
    db = _load_contracts_db()
    contracts = db.get("contracts", {})
    profiles = []
    for policy_no in contracts:
        p = get_insured_profile(policy_no)
        if p:
            profiles.append(p)
    return profiles


def get_insured_profile(policy_no: str) -> dict | None:
    """증권번호로 피보험자 프로필을 조회.

    Returns:
        {
            "name": "홍길동", "gender": "M", "gender_label": "남",
            "birth_date": "1979-05-12", "age": 47,
            "product_name": "무배당 스마트종합보험 (2020년형)",
            "silson_generation": 3, "generation_label": "3세대",
            "contract_date": "2020-03-15", "status": "유효",
            "coverages": [{"code": "IND001", "name": "입원일당 (질병)"}, ...]
        }
        없으면 None.
    """
    db = _load_contracts_db()
    contract = db.get("contracts", {}).get(policy_no)
    if not contract:
        return None

    insured = contract.get("insured", {})
    birth_date = insured.get("birth_date", "")

    # 나이 계산 (birth_date = "1979-05-12")
    age = 0
    if birth_date:
        try:
            birth_year = int(birth_date[:4])
            from datetime import date
            age = date.today().year - birth_year
        except (ValueError, IndexError):
            pass

    gender = insured.get("gender", "")
    gender_label = {"M": "남", "F": "여"}.get(gender, gender)

    gen = contract.get("silson_generation", 0)
    gen_label = f"{gen}세대" if gen else ""

    # 가입 담보 목록
    coverages_raw = contract.get("coverages", {})
    coverage_list = []
    if isinstance(coverages_raw, dict):
        for cov_code, cov_data in coverages_raw.items():
            coverage_list.append({
                "code": cov_code,
                "name": cov_data.get("coverage_name", cov_code),
                "type": cov_data.get("type", ""),
                "status": cov_data.get("status", ""),
            })

    return {
        "name": insured.get("name", ""),
        "gender": gender,
        "gender_label": gender_label,
        "birth_date": birth_date,
        "age": age,
        "id_masked": insured.get("id_masked", ""),
        "policy_no": policy_no,
        "product_name": contract.get("product_name", ""),
        "product_code": contract.get("product_code", ""),
        "silson_generation": gen,
        "generation_label": gen_label,
        "contract_date": contract.get("contract_date", ""),
        "expiry_date": contract.get("expiry_date", ""),
        "status": contract.get("status", ""),
        "premium_status": contract.get("premium_status", ""),
        "coverages": coverage_list,
    }


# ══════════════════════════════════════════════════════════════
# 8. 시나리오 카드 데이터 조회
# ══════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _load_scenarios() -> list[dict]:
    """scenarios.json 로드."""
    path = _TEST_DIR / "scenarios.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── 시나리오 난이도 & 테스트 포인트 태그 매핑 (TASK-6) ────────
_SCENARIO_META: dict[str, tuple[int, list[str]]] = {
    # (난이도 1~4, 테스트포인트 태그들)
    "CLM-2024-001": (1, ["정상지급", "IND+SIL"]),
    "CLM-2024-002": (2, ["비급여과다", "검토필요", "SUR+SIL"]),
    "CLM-2024-003": (2, ["KCD면책", "알코올", "부지급"]),
    "CLM-2024-004": (1, ["서류미비", "보류"]),
    "CLM-2024-005": (1, ["정상지급", "IND+SIL+SUR"]),
    "CLM-2024-006": (3, ["면책기간", "일부지급", "IND-FAIL"]),
    "CLM-2024-007": (3, ["조건부면책", "정신질환", "특약미가입"]),
    "CLM-2024-008": (3, ["재해입원", "면책0일", "IND재해담보"]),
    "CLM-2024-009": (3, ["수술종초과", "SUR-FAIL", "일부지급"]),
    "CLM-2024-010": (1, ["계약실효", "미납", "즉시부지급"]),
    "CLM-2024-011": (4, ["4세대실손", "비급여한도캡", "도수치료"]),
    "CLM-2024-012": (4, ["수술코드추론", "KCD기반", "SUR-FLAGGED"]),
    "CLM-2024-013": (3, ["반복청구", "만성질환", "발병일불명"]),
    # Agent 전용 시나리오 (B-1)
    "CLM-2024-101": (1, ["Agent전용", "고신뢰도", "자동승인", "auto_approve"]),
    "CLM-2024-102": (4, ["Agent전용", "서류불일치", "교차검증", "senior_review"]),
    "CLM-2024-103": (4, ["Agent전용", "사기의심", "과잉입원", "mandatory_hold"]),
    "CLM-2024-104": (4, ["Agent전용", "담보해석경계", "미용vs기능", "enhanced_review"]),
    "CLM-2024-105": (3, ["Agent전용", "복합담보", "재해+합병증", "dual_kcd"]),
}


def _get_scenario_meta(claim_id: str) -> tuple[int, list[str]]:
    """시나리오 난이도(1~4)와 태그 리스트를 반환."""
    return _SCENARIO_META.get(claim_id, (1, []))


def get_scenario_cards() -> list[dict]:
    """18개 시나리오(기본 13 + Agent전용 5)의 카드 표시용 요약 데이터를 반환.

    Returns:
        [{
            "claim_id": "CLM-2024-001",
            "name": "홍길동", "gender": "M", "gender_icon": "👨",
            "birth_year": 1979, "age": 47,
            "diagnosis": "급성 충수염", "kcd_code": "K35.8",
            "kcd_display": "K35.8 급성 충수염",
            "surgery": "복강경 충수절제술 (3종)" | None,
            "hospital_days": 5,
            "decision": "지급", "decision_icon": "✅",
            "total_payment": 454000,
            "policy_no": "POL-20200315-001",
            "scenario_desc": "정상 지급 (IND+SIL)",
            "claimed_coverages": ["IND", "SIL", "SUR"],
            "reviewer_flag": False,
        }, ...]
    """
    scenarios = _load_scenarios()
    cards = []

    for sc in scenarios:
        insured = sc.get("insured", {})
        claim = sc.get("claim", {})
        expected = sc.get("expected_result", {})
        policy = sc.get("policy", {})

        gender = insured.get("gender", "")
        birth_year = insured.get("birth_year", 0)
        from datetime import date
        age = date.today().year - birth_year if birth_year else 0

        kcd = claim.get("kcd_code", "")
        diagnosis = claim.get("diagnosis", "")
        kcd_display = f"{kcd} {diagnosis}" if kcd and diagnosis else (kcd or diagnosis)

        # 수술 정보
        surgery_info = claim.get("surgery", {})
        surgery_text = None
        if surgery_info.get("performed"):
            s_name = surgery_info.get("surgery_name", "")
            s_class = surgery_info.get("surgery_class", 0)
            surgery_text = f"{s_name} ({s_class}종)" if s_class else s_name

        decision = expected.get("decision", "")
        decision_cfg = get_decision_config(decision)

        # 난이도 & 테스트 포인트 태그 (TASK-6)
        claim_id = sc.get("claim_id", "")
        difficulty, tags = _get_scenario_meta(claim_id)

        cards.append({
            "claim_id": claim_id,
            "name": insured.get("name", ""),
            "gender": gender,
            "gender_icon": "👨" if gender == "M" else "👩",
            "birth_year": birth_year,
            "age": age,
            "diagnosis": diagnosis,
            "kcd_code": kcd,
            "kcd_display": kcd_display,
            "surgery": surgery_text,
            "hospital_days": claim.get("hospital_days", 0),
            "decision": decision,
            "decision_icon": decision_cfg["icon"],
            "total_payment": expected.get("total_payment", 0),
            "policy_no": policy.get("policy_no", ""),
            "scenario_desc": sc.get("_scenario", ""),
            "claimed_coverages": claim.get("claimed_coverage_types", []),
            "reviewer_flag": expected.get("reviewer_flag", False),
            "difficulty": difficulty,
            "tags": tags,
        })

    return cards


# ══════════════════════════════════════════════════════════════
# 9. 금액·숫자 포맷 유틸
# ══════════════════════════════════════════════════════════════

def fmt_amount(amount: int | float | None) -> str:
    """금액을 '1,234,000원' 형태로 포매팅. None/0이면 '0원'."""
    if not amount:
        return "0원"
    return f"{int(amount):,}원"


def fmt_days(days: int | None) -> str:
    """일수를 'N일' 형태로 포매팅."""
    if not days:
        return "0일"
    return f"{days}일"


def fmt_percent(value: float | None) -> str:
    """비율을 'N%' 형태로 포매팅 (소수점 없이)."""
    if value is None:
        return "0%"
    return f"{int(value * 100)}%" if value < 1 else f"{int(value)}%"


# ══════════════════════════════════════════════════════════════════
# Evidence 필드 한글 매핑 (TASK-3: 산정 상세 시각화)
# ══════════════════════════════════════════════════════════════════

# ── 공통 필드 ─────────────────────────────────────────────────
_EVIDENCE_COMMON: dict[str, str] = {
    "benefit_amount": "지급 금액",
    "formula": "산출 산식",
    "policy_clause": "적용 약관",
    "clause_ref": "약관 조항",
    "clause_title": "조항 제목",
    "clause_text": "조항 본문",
    "legal_basis": "법적 근거",
    "coverage_code": "담보 코드",
    "coverage_name": "담보명",
}

# ── IND (입원일당) 전용 ──────────────────────────────────────
_EVIDENCE_IND: dict[str, str] = {
    "claim_nature": "청구 유형",
    "kcd_code": "상병 코드(KCD)",
    "hospital_days_claimed": "청구 입원일수",
    "payable_days": "인정 입원일수",
    "daily_amount": "1일 입원비",
    "daily_benefit": "1일 입원비",
    "waiting_days": "면책일수",
    "deductible_days": "면책일수",
    "coverages_applied": "적용 담보 내역",
}

# ── SIL (실손의료비) 전용 ────────────────────────────────────
_EVIDENCE_SIL: dict[str, str] = {
    "silson_generation": "실손 세대",
    "care_type": "진료 구분",
    "covered_self_pay": "급여 본인부담금",
    "non_covered_amount": "비급여 금액",
    "non_covered_capped": "비급여 한도적용액",
    "copay_rate_covered": "급여 자기부담률",
    "copay_rate_non_covered": "비급여 자기부담률",
    "copay_applied": "자기부담금 합계",
    "sil_4gen_cap_details": "4세대 한도 상세",
}

# ── SUR (수술비) 전용 ────────────────────────────────────────
_EVIDENCE_SUR: dict[str, str] = {
    "surgery_code": "수술 코드",
    "surgery_name": "수술명",
    "surgery_class": "수술 분류등급",
    "inferred_from_kcd": "KCD 기반 추론 여부",
    "kcd_candidates_used": "참조 KCD 코드",
}

# ── 통합 매핑 (공통 + 전체 전용) ─────────────────────────────
_EVIDENCE_FIELD_LABELS: dict[str, str] = {
    **_EVIDENCE_COMMON,
    **_EVIDENCE_IND,
    **_EVIDENCE_SIL,
    **_EVIDENCE_SUR,
}

# ── 담보 유형별 표시 순서 (이 순서대로 테이블에 렌더링) ────────
EVIDENCE_DISPLAY_ORDER: dict[str, list[str]] = {
    "IND": [
        "benefit_amount", "formula",
        "hospital_days_claimed", "payable_days", "waiting_days", "deductible_days",
        "daily_amount", "daily_benefit",
        "claim_nature", "kcd_code",
        "coverages_applied",
        "policy_clause", "clause_title", "clause_text", "legal_basis",
    ],
    "SIL": [
        "benefit_amount", "formula",
        "silson_generation", "care_type",
        "covered_self_pay", "non_covered_amount", "non_covered_capped",
        "copay_rate_covered", "copay_rate_non_covered", "copay_applied",
        "coverage_name", "coverage_code",
        "policy_clause", "clause_title", "clause_text", "legal_basis",
    ],
    "SUR": [
        "benefit_amount", "formula",
        "surgery_name", "surgery_code", "surgery_class",
        "inferred_from_kcd", "kcd_candidates_used",
        "coverage_name", "coverage_code",
        "policy_clause", "clause_title", "clause_text", "legal_basis",
    ],
}

# ── 금액 포맷이 필요한 필드 ──────────────────────────────────
_EVIDENCE_AMOUNT_FIELDS = frozenset({
    "benefit_amount", "daily_amount", "daily_benefit",
    "covered_self_pay", "non_covered_amount", "non_covered_capped",
    "copay_applied",
})

# ── 비율 포맷이 필요한 필드 ──────────────────────────────────
_EVIDENCE_RATE_FIELDS = frozenset({
    "copay_rate_covered", "copay_rate_non_covered",
})

# ── 일수 포맷이 필요한 필드 ──────────────────────────────────
_EVIDENCE_DAYS_FIELDS = frozenset({
    "hospital_days_claimed", "payable_days",
    "waiting_days", "deductible_days",
})


def get_evidence_label(key: str) -> str:
    """evidence 필드 키를 한글 레이블로 변환. 미등록 키는 원문 반환."""
    return _EVIDENCE_FIELD_LABELS.get(key, key)


def get_evidence_type(rule_id: str) -> str:
    """rule_id 에서 담보 유형 접두사 추출 (IND/SIL/SUR/기타)."""
    prefix = rule_id.split("-")[0].upper() if rule_id else ""
    return prefix if prefix in EVIDENCE_DISPLAY_ORDER else "ETC"


def fmt_evidence_value(key: str, value) -> str:
    """evidence 필드 값을 적절한 포맷으로 변환."""
    if value is None:
        return "—"
    if key in _EVIDENCE_AMOUNT_FIELDS:
        return fmt_amount(value)
    if key in _EVIDENCE_RATE_FIELDS:
        return fmt_percent(value)
    if key in _EVIDENCE_DAYS_FIELDS:
        return fmt_days(value)
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, (list, dict)):
        return None  # 복합 타입은 별도 렌더링 필요 → None 반환
    return str(value)
