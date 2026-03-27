"""
데이터 스키마 정의 — Agent 간 인터페이스 계약서.

설계 원칙:
  - 모든 Agent 는 이 파일에 정의된 dataclass 를 입력/출력으로 사용한다.
  - Agent 간 직접 dict 전달은 금지. 반드시 이 스키마를 통한다.
  - 파싱 실패(confidence 낮음)는 에러로 처리하지 않고 None 으로 흘려보낸다.
    → 규칙 엔진이 None 값 처리 방식을 결정한다.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal


# ══════════════════════════════════════════════════════════════════
# 1. 서류 파싱 결과
# ══════════════════════════════════════════════════════════════════
@dataclass
class ParsedDocument:
    """
    doc_parser (정규식 또는 LLM) 가 단일 서류 파일에서 추출한 정보.
    raw_text : OCR 또는 텍스트 파일 원문 (LLM 재파싱용으로 보존)
    fields   : 추출된 key-value 딕셔너리
    confidence: 0.0(완전 실패) ~ 1.0(완전 성공)
    """
    doc_type: str            # "진단서" | "입원확인서" | "진료비영수증" | "수술확인서" | "보험금청구서" | "진료비세부내역서" | "미분류"
    raw_text: str            # 원문 텍스트 (LLM fallback 파싱용으로 보존)
    fields: dict             # 아래 표준 키를 사용. 미추출 시 키 자체가 없음.
    parse_mode: str = "regex"  # "regex" | "llm" | "hybrid"
    confidence: float = 1.0
    parse_errors: list[str] = field(default_factory=list)

    # ── fields 딕셔너리의 표준 키 목록 (참고용 주석) ──────────────
    # kcd_code         : str   — 주 상병코드 (예: "K35.8")
    # diagnosis        : str   — 진단명 (예: "급성 충수염")
    # hospital_days    : int   — 총 입원일수
    # admission_date   : str   — 입원일 (YYYY-MM-DD)
    # discharge_date   : str   — 퇴원일 (YYYY-MM-DD)
    # covered_self_pay : int   — 급여 본인부담금 (원)
    # non_covered      : int   — 비급여 본인부담금 (원)
    # total_self_pay   : int   — 최종 본인 납부액 (원)
    # surgery_name     : str   — 수술명 (수술확인서에서 추출)
    # surgery_code     : str   — 수술코드 (surgery_classification.json 매핑 후 채움)
    # surgery_date     : str   — 수술일 (YYYY-MM-DD)
    # accident_date    : str   — 발병/사고일 (YYYY-MM-DD)
    # policy_no        : str   — 보험계약번호 (청구서에서 추출)
    # billing_items    : list[dict] — 진료비세부내역서 항목 (item_code, item_name, is_noncovered, amount, sessions)    #
    # ── Vision OCR 추가 필드 (진료비 영수증 이미지 파싱 시) ─────────
    # receipt_line_items : list[dict] — 영수증 항목별 테이블
    #     [{"category": "진찰료", "covered": 15000, "non_covered": 0, "subtotal": 15000}, ...]
    # receipt_summary   : dict — 영수증 합계 정보
    #     {"covered_subtotal", "covered_self_pay", "non_covered_subtotal",
    #      "public_insurance", "elective_care_fee", "total_self_pay"}
    # special_items     : list[dict] — 4세대 실손 특수항목 (도수치료/주사료/MRI 등)
    #     [{"item_name": str, "amount": int, "sessions": int}, ...]
    # masked_field_map  : dict — 마스킹 필드 가명 매핑
    #     {"patient_name": "홍길동(가칭)", "patient_id": "MASKED-001", ...}
    # patient_name      : str  — 환자명 (마스킹 시 가명 자동 부여)

# ══════════════════════════════════════════════════════════════════
# 2. 통합 청구 컨텍스트 (Orchestrator 가 서류들을 조립한 결과)
# ══════════════════════════════════════════════════════════════════
@dataclass
class ClaimContext:
    """
    여러 서류에서 추출한 정보를 하나로 통합한 청구 컨텍스트.
    rule_engine 의 입력값. 이 객체 안의 None 은 "정보 없음"을 의미한다.
    """
    claim_id: str
    policy_no: str
    claim_date: str           # 청구서 접수일 (YYYY-MM-DD)
    accident_date: str        # 발병/사고일 (YYYY-MM-DD). 없으면 claim_date 로 대체.

    # 입원 정보
    admission_date: Optional[str]  # 입원일
    discharge_date: Optional[str]  # 퇴원일
    hospital_days: Optional[int]   # 총 입원일수

    # 진단 정보
    kcd_code: str              # 주 상병코드. 미추출 시 "UNKNOWN".
    diagnosis: str             # 진단명

    # 수술 정보
    surgery_name: Optional[str]   # 수술명 (서류에서 추출한 원문)
    surgery_code: Optional[str]   # 수술코드 (surgery_classification.json 에서 매핑된 코드)

    # 진료비 정보
    covered_self_pay: Optional[int]    # 급여 본인부담금 (원)
    non_covered_amount: Optional[int]  # 비급여 본인부담금 (원)

    # 서류 완비 여부 판단용
    submitted_doc_types: list[str]     # 제출된 서류 유형 목록 (중복 없음)

    # 청구서에서 추출한 실제 청구 담보 유형 (빈 리스트면 계약 담보 전체 기준으로 처리)
    claimed_coverage_types: list[str] = field(default_factory=list)  # ["IND", "SIL", "SUR"]

    # 원본 파싱 결과 보존 (디버깅, LLM 재파싱용)
    raw_documents: list[ParsedDocument] = field(default_factory=list)

    # 파싱 신뢰도 요약 (낮으면 human-in-the-loop 고려)
    parse_confidence_min: float = 1.0  # 서류별 confidence 최솟값
    parse_confidence_avg: float = 1.0  # 서류별 confidence 가중평균 — 서류 유형별 가중치 반영 (A-2)

    # 진료비세부내역서 항목 (4세대 비급여 한도 등)
    billing_items: list[dict] = field(default_factory=list)

    # 만성질환 발병일 불명 플래그 (업계 표준: 입원일 폴백 + 담당자 검토)
    chronic_onset_flag: bool = False


# A-5: risk_level 5단계 변환 함수
RISK_LEVELS = ("VERY_LOW", "LOW", "MEDIUM", "HIGH", "CRITICAL")

def overall_to_risk_level(overall: float) -> str:
    """
    overall 점수를 5단계 risk_level로 변환 (A-5).

    ≥ 0.90 → VERY_LOW   (자동 처리 가능)
    ≥ 0.75 → LOW        (일반 심사)
    ≥ 0.60 → MEDIUM     (주의 필요)
    ≥ 0.40 → HIGH       (담당자 검토 권장)
    <  0.40 → CRITICAL   (반드시 담당자 확인)
    """
    if overall >= 0.90:
        return "VERY_LOW"
    if overall >= 0.75:
        return "LOW"
    if overall >= 0.60:
        return "MEDIUM"
    if overall >= 0.40:
        return "HIGH"
    return "CRITICAL"


# ══════════════════════════════════════════════════════════════════
# 3. 신뢰도 점수 (Agent 모드에서 산출)
# ══════════════════════════════════════════════════════════════════
@dataclass
class ConfidenceScore:
    """
    Agent 판정의 신뢰도 점수.

    각 필드는 0.0(완전 불확실) ~ 1.0(완전 확실) 범위.
    overall 은 가중 평균으로 산출되며, risk_level 은 overall 기반으로 결정.

    룰 모드에서는 ClaimDecision.confidence = None.
    """
    parse_confidence: float = 1.0      # 서류 파싱 품질
    rule_confidence: float = 1.0       # 룰엔진 판정 확실성 (FLAGGED 역비례)
    llm_confidence: float = 0.0        # LLM 자체 확신도 (프롬프트 요청)
    cross_validation: float = 0.0      # LLM vs 룰엔진 일치도
    overall: float = 0.0               # 가중 평균
    risk_level: str = "UNKNOWN"        # VERY_LOW | LOW | MEDIUM | HIGH | CRITICAL | UNKNOWN

    # A-6: LLM confidence 세부 요인 (UI 대시보드 표시용)
    confidence_factors: dict = field(default_factory=dict)
    # {"data_completeness": 0.9, "policy_match": 0.85, "calculation_certainty": 0.8,
    #  "ambiguity_level": 0.7, "edge_case_risk": 0.6}

    def compute_overall(self, agent_mode: bool = True) -> None:
        """가중 평균으로 overall 산출 + risk_level 결정.

        Args:
            agent_mode: True면 LLM/교차검증 포함 4요소 가중치,
                       False면 파싱+룰 중심 2요소 가중치 (룰 모드).

        risk_level 5단계 (A-5):
          VERY_LOW  (≥0.9) — 자동 처리 가능, 위험 최소
          LOW       (≥0.75) — 일반 심사, 정상 범위
          MEDIUM    (≥0.6) — 주의 필요, 일부 불확실성
          HIGH      (≥0.4) — 담당자 검토 권장
          CRITICAL  (<0.4) — 반드시 담당자 확인 필요
        """
        if agent_mode:
            # Agent 모드: 파싱 20%, 룰 30%, LLM 25%, 교차검증 25%
            self.overall = round(
                self.parse_confidence * 0.20
                + self.rule_confidence * 0.30
                + self.llm_confidence * 0.25
                + self.cross_validation * 0.25,
                3,
            )
        else:
            # 룰 모드: 파싱 40%, 룰 60% (LLM/교차검증 미사용)
            self.overall = round(
                self.parse_confidence * 0.40
                + self.rule_confidence * 0.60,
                3,
            )
        self.risk_level = overall_to_risk_level(self.overall)

    def to_dict(self) -> dict:
        d = {
            "parse_confidence": self.parse_confidence,
            "rule_confidence": self.rule_confidence,
            "llm_confidence": self.llm_confidence,
            "cross_validation": self.cross_validation,
            "overall": self.overall,
            "risk_level": self.risk_level,
        }
        if self.confidence_factors:  # A-6: 비어있지 않으면 포함
            d["confidence_factors"] = self.confidence_factors
        return d


# ══════════════════════════════════════════════════════════════════
# 3-B. 심사 라우팅 (A-7: 신뢰도 기반 자동 심사 라우팅)
# ══════════════════════════════════════════════════════════════════

# 라우팅 액션 정의
REVIEW_ACTIONS = (
    "auto_approve",     # 자동 승인 (VERY_LOW 리스크)
    "standard_review",  # 일반 심사 (LOW)
    "enhanced_review",  # 강화 심사 (MEDIUM)
    "senior_review",    # 선임 심사역 검토 (HIGH)
    "mandatory_hold",   # 필수 보류 / 부서장 승인 (CRITICAL)
)

REVIEW_PRIORITIES = ("low", "normal", "high", "urgent", "critical")


@dataclass
class ReviewRouting:
    """
    A-7: 신뢰도 기반 심사 라우팅 정보.

    risk_level과 판정 결과를 종합하여 누가, 얼마나 긴급하게,
    어떤 항목을 확인해야 하는지 결정한다.
    """
    action: str = "standard_review"       # REVIEW_ACTIONS 중 하나
    priority: str = "normal"              # low | normal | high | urgent | critical
    reviewer_level: str = "일반심사역"     # 자동처리 | 일반심사역 | 선임심사역 | 팀장 | 부서장
    checklist: list[str] = field(default_factory=list)  # 검토 체크리스트
    estimated_minutes: int = 0            # 예상 심사 소요 시간 (분)
    routing_reason: str = ""              # 라우팅 결정 사유

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "priority": self.priority,
            "reviewer_level": self.reviewer_level,
            "checklist": self.checklist,
            "estimated_minutes": self.estimated_minutes,
            "routing_reason": self.routing_reason,
        }


# ══════════════════════════════════════════════════════════════════
# 4. 단일 룰 실행 결과
# ══════════════════════════════════════════════════════════════════
@dataclass
class RuleResult:
    """
    룰 하나의 실행 결과.
    PASS    : 통과 (다음 룰로 진행)
    FAIL    : 실패 (COM/DOC 룰 실패 시 처리 중단)
    FLAGGED : 경고 (처리는 계속하되 reviewer_flag 부여)
    SKIP    : 해당 없음 (담보 미가입, 수술 없음 등)
    """
    rule_id: str
    status: Literal["PASS", "FAIL", "FLAGGED", "SKIP"]
    reason: str                       # 사람이 읽을 수 있는 판단 근거
    value: Optional[float] = None     # 계산된 보험금 (원). PASS 시에만 유효.
    evidence: dict = field(default_factory=dict)  # 감사(audit) 추적용 상세 데이터


# ══════════════════════════════════════════════════════════════════
# 5. 최종 판정 결과
# ══════════════════════════════════════════════════════════════════
@dataclass
class ClaimDecision:
    """
    rule_engine.run_rules() 의 최종 반환값.
    이 객체가 output_writer 에 전달되어 결과 문서를 생성한다.

    Agent 모드에서는 confidence 필드에 ConfidenceScore 가 주입된다.
    룰 모드에서는 confidence = None.
    """
    claim_id: str
    decision: Literal["지급", "부지급", "보류", "검토필요", "일부지급"]
    total_payment: int                # 지급 보험금 합계 (원). 부지급/보류 시 0.

    # 담보별 계산 상세 (rule_id → evidence dict)
    breakdown: dict

    # 실행된 룰 전체 목록 (감사 추적용)
    applied_rules: list[RuleResult]

    # 담당자 검토 플래그
    reviewer_flag: bool = False
    reviewer_reason: Optional[str] = None

    # 보류 사유
    missing_docs: list[str] = field(default_factory=list)

    # 부지급 사유
    denial_reason: Optional[str] = None
    policy_clause: Optional[str] = None   # 약관 조항 (예: "제2조 제1항 제3호")

    # 일부지급 시 지급 불가 담보 목록 (예: [{"rule_id": "SUR-001", "reason": "4종 초과"}])
    denial_coverages: list[dict] = field(default_factory=list)

    # 사기/이상 조사 플래그 (부지급 + 반복 청구 시 사기조사팀 통보용)
    fraud_investigation_flag: bool = False
    fraud_investigation_reason: Optional[str] = None

    # Agent 모드 신뢰도 (룰 모드에서는 None)
    confidence: Optional[ConfidenceScore] = None

    # A-7: 심사 라우팅 정보 (Agent 모드에서 자동 산출)
    review_routing: Optional[ReviewRouting] = None
