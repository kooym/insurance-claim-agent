"""
재사용 UI 컴포넌트 — Toss 디자인 원칙 기반 보험 심사 대시보드.

컴포넌트 구성:
  ● 홈 화면: render_hero_upload, render_scenario_gallery
  ● 피보험자 조회: render_patient_lookup (검색 + 신규 등록 폼)
  ● 결과 대시보드: render_insured_profile, render_claim_summary,
                   render_review_conditions, render_decision_dashboard,
                   render_coverage_breakdown_v2
  ● 약관 근거: render_clause_reference (룰별 약관 조항 표시)
  ● 일부지급: render_denial_coverages (지급 불가 담보 표시)
  ● 프로세싱: render_processing_stepper
  ● 사이드바: render_history_sidebar
  ● 유틸리티: render_dev_tools (RAG/API/통계 래퍼)
  ● 레거시 (하위 호환): render_decision_banner, render_breakdown_cards, render_rule_trace
"""
from __future__ import annotations
import json
import zipfile
import io
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as stc

from src.ui.labels import (
    RULE_LABELS,
    COVERAGE_LABELS,
    DECISION_CONFIG,
    STATUS_LABELS,
    get_coverage_label,
    get_decision_config,
    get_status_label,
    get_kcd_name,
    format_kcd,
    get_surgery_class_info,
    get_surgery_name,
    get_insured_profile,
    get_all_insured_profiles,
    get_scenario_cards,
    fmt_amount,
    fmt_days,
    get_evidence_label,
    get_evidence_type,
    fmt_evidence_value,
    fmt_percent,
    EVIDENCE_DISPLAY_ORDER,
)


# ══════════════════════════════════════════════════════════════
# TASK-UI-03: 히어로 업로드 영역
# ══════════════════════════════════════════════════════════════

def render_hero_upload():
    """메인 화면 히어로 — 청구 서류 업로드 영역.

    Returns:
        업로드된 파일 리스트 또는 None.
    """
    st.markdown(
        """<div class="hero-section">
            <div style="font-size:3rem; margin-bottom:8px">📋</div>
            <h2>청구 서류를 올려주세요</h2>
            <p>보험금 청구서, 진단서, 영수증 등을 올려주시면 자동으로 심사해 드려요</p>
        </div>""",
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "서류 파일 선택",
        type=["txt", "pdf", "jpg", "jpeg", "png"],
        accept_multiple_files=True,
        key="hero_file_uploader",
        label_visibility="collapsed",
    )

    if uploaded:
        st.markdown(
            f'<div class="alert-banner alert-banner-info">'
            f'📎 {len(uploaded)}개 파일이 선택되었어요: '
            f'{", ".join(f.name for f in uploaded)}'
            f'</div>',
            unsafe_allow_html=True,
        )

    return uploaded or None


# ══════════════════════════════════════════════════════════════
# TASK-UI-03: 시나리오 카드 갤러리
# ══════════════════════════════════════════════════════════════

def render_scenario_gallery() -> str | None:
    """13개 테스트 시나리오를 강화된 카드 갤러리로 표시.

    카드에 난이도(⭐), 테스트 포인트 태그, 판정별 좌측 컬러 바를 포함.

    Returns:
        클릭된 시나리오의 claim_id 또는 None.
    """
    st.markdown(
        '<div class="section-title"><h3>🧪 테스트 시나리오로 체험해 보세요</h3></div>',
        unsafe_allow_html=True,
    )
    st.caption("실제 보험 청구 사례를 기반으로 한 시나리오예요. 카드를 선택하면 바로 심사가 시작돼요.")

    cards = get_scenario_cards()
    selected_claim_id = None

    # 판정별 좌측 보더 클래스
    _BORDER_CLS = {
        "지급": "card-border-pass",
        "부지급": "card-border-fail",
        "일부지급": "card-border-flagged",
        "검토필요": "card-border-review",
        "보류": "card-border-hold",
    }

    # 3열 × N행
    for row_start in range(0, len(cards), 3):
        cols = st.columns(3)
        for i, col in enumerate(cols):
            idx = row_start + i
            if idx >= len(cards):
                break
            card = cards[idx]
            cfg = get_decision_config(card["decision"])

            with col:
                # 난이도 별 표시
                difficulty = card.get("difficulty", 1)
                stars = "⭐" * difficulty

                # 태그 칩
                tags = card.get("tags", [])
                tags_html = ""
                if tags:
                    tag_chips = "".join(f'<span class="card-tag">{t}</span>' for t in tags)
                    tags_html = f'<div class="card-tags">{tag_chips}</div>'

                # 수술 정보
                surgery_part = (
                    f'<div style="font-size:0.82rem;color:#6B7684;margin-bottom:8px">🔪 {card["surgery"]}</div>'
                    if card["surgery"] else ""
                )
                chip_class = (
                    "pass" if card["decision"] == "지급"
                    else "fail" if card["decision"] == "부지급"
                    else "flagged"
                )
                border_cls = _BORDER_CLS.get(card["decision"], "")
                delay_cls = f"anim-delay-{(idx % 9) + 1}"
                card_html = (
                    f'<div class="scenario-card-enhanced {border_cls} {delay_cls}">'
                    '<div class="card-header">'
                    f'<span class="card-avatar">{card["gender_icon"]}</span>'
                    '<div>'
                    f'<div class="card-name">{card["name"]}</div>'
                    f'<div class="card-age">{card["age"]}세 · {card["claim_id"]}</div>'
                    '</div>'
                    f'<div class="card-difficulty">{stars}</div>'
                    '</div>'
                    f'{tags_html}'
                    f'<div class="card-diagnosis">{card["kcd_display"]}</div>'
                    f'{surgery_part}'
                    '<div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px">'
                    f'<span class="status-chip status-chip-{chip_class}">{cfg["icon"]} {cfg["label"]}</span>'
                    f'<span class="card-amount">{fmt_amount(card["total_payment"])}</span>'
                    '</div>'
                    '</div>'
                )
                st.markdown(card_html, unsafe_allow_html=True)
                if st.button(
                    "심사 시작하기",
                    key=f"scenario_btn_{card['claim_id']}",
                    use_container_width=True,
                ):
                    selected_claim_id = card["claim_id"]

    return selected_claim_id


# ══════════════════════════════════════════════════════════════
# TASK-C2: 피보험자 검색 / 조회 / 신규 등록
# ══════════════════════════════════════════════════════════════

def render_patient_lookup() -> dict | None:
    """피보험자 검색·조회 UI — 증권번호 또는 이름으로 계약 DB 검색.

    Returns:
        선택된 프로필 dict (get_insured_profile 반환형) 또는 None.
    """
    st.markdown(
        '<div class="section-title"><h3>🔎 피보험자 조회</h3></div>',
        unsafe_allow_html=True,
    )
    st.caption("증권번호 또는 피보험자 이름으로 검색하세요.")

    search_col, btn_col = st.columns([4, 1])
    with search_col:
        query = st.text_input(
            "검색어",
            placeholder="예: POL-20200315-001 또는 홍길동",
            key="patient_search_query",
            label_visibility="collapsed",
        )
    with btn_col:
        search_clicked = st.button("🔍 검색", key="patient_search_btn", use_container_width=True)

    # 커스텀 등록 환자 병합
    custom_contracts = st.session_state.get("custom_contracts", [])

    selected_profile = None

    if search_clicked and query.strip():
        q = query.strip()

        # DB 프로필 검색
        all_profiles = get_all_insured_profiles()

        # session_state 커스텀 환자 추가
        for cc in custom_contracts:
            all_profiles.append(cc)

        # 필터: policy_no 정확 매칭 또는 이름 포함 매칭
        matches = [
            p for p in all_profiles
            if q == p.get("policy_no", "")
            or q in p.get("name", "")
            or q.lower() in p.get("policy_no", "").lower()
        ]

        if not matches:
            st.markdown(
                '<div class="alert-banner alert-banner-warning">'
                '🔍 검색 결과가 없어요. 증권번호 또는 이름을 확인해 주세요.'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            st.success(f"**{len(matches)}건**의 피보험자를 찾았어요.")
            st.session_state["patient_search_results"] = matches

    # 검색 결과 표시 (세션 유지)
    results = st.session_state.get("patient_search_results", [])
    if results:
        for idx, profile in enumerate(results):
            avatar = "👨‍💼" if profile.get("gender") == "M" else "👩‍💼"
            gender_label = {"M": "남", "F": "여"}.get(profile.get("gender", ""), "")
            age = profile.get("age", 0)
            status = profile.get("status", "")
            is_custom = profile.get("_custom", False)
            custom_badge = ' <span style="background:#E8F5E9;color:#2E7D32;padding:2px 6px;border-radius:4px;font-size:0.75rem">신규</span>' if is_custom else ""

            # 담보 칩
            covs = profile.get("coverages", [])
            cov_chips = " ".join(
                f'<span class="status-chip status-chip-pass" style="font-size:0.75rem">{c.get("name", c.get("code", ""))}</span>'
                for c in covs[:6]
            )
            if len(covs) > 6:
                cov_chips += f' <span style="font-size:0.75rem;color:#8B95A1">+{len(covs) - 6}</span>'

            card_html = (
                '<div class="profile-card" style="margin-bottom:12px">'
                '<div class="profile-header">'
                f'<div class="profile-avatar">{avatar}</div>'
                '<div style="flex:1">'
                f'<div class="profile-name">{profile.get("name", "")}{custom_badge}</div>'
                f'<div class="profile-sub">{gender_label} · {age}세 · {profile.get("policy_no", "")}</div>'
                '</div>'
                f'<div style="font-size:0.8rem;color:#8B95A1">{status}</div>'
                '</div>'
                '<div class="profile-grid">'
                f'<div class="profile-dt">상품명</div><div class="profile-dd">{profile.get("product_name", "-")}</div>'
                f'<div class="profile-dt">계약일</div><div class="profile-dd">{profile.get("contract_date", "-")}</div>'
                '</div>'
                f'<div style="margin-top:8px">{cov_chips}</div>'
                '</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

            if st.button(
                f"✅ {profile.get('name', '')} 선택",
                key=f"select_patient_{idx}_{profile.get('policy_no', '')}",
                use_container_width=True,
            ):
                selected_profile = profile
                st.session_state["selected_patient"] = profile

    return selected_profile


def render_new_patient_form() -> dict | None:
    """신규 피보험자 등록 폼 — session_state 기반 런타임 등록.

    등록된 계약은 st.session_state["custom_contracts"] 에 저장.
    TASK-C3 에서 custom_contracts.json 파일 저장 로직이 추가됨.

    Returns:
        새로 등록된 프로필 dict 또는 None (미등록 시).
    """
    st.markdown(
        '<div class="section-title"><h3>📝 신규 피보험자 등록</h3></div>',
        unsafe_allow_html=True,
    )
    st.caption("기존 DB에 없는 환자를 임시 등록해요. 세션 동안만 유지돼요.")

    with st.form("new_patient_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("피보험자 이름 *", placeholder="예: 김보험")
            gender = st.selectbox("성별 *", ["M", "F"], format_func=lambda g: {"M": "남", "F": "여"}[g])
            birth_date = st.text_input("생년월일 *", placeholder="YYYY-MM-DD")
        with col2:
            policy_no = st.text_input("증권번호 *", placeholder="예: POL-XXXXXXXX-XXX")
            product_name = st.text_input("상품명", placeholder="예: 무배당 종합보험")
            generation = st.selectbox("실손 세대", [0, 1, 2, 3, 4], format_func=lambda g: f"{g}세대" if g else "해당없음")

        st.markdown("**가입 담보 선택**")
        cov_col1, cov_col2, cov_col3 = st.columns(3)
        with cov_col1:
            has_ind = st.checkbox("🏥 입원일당 (IND)", value=True)
            if has_ind:
                ind_daily = st.number_input("일당 금액(원)", value=30000, step=10000, key="new_ind_daily")
        with cov_col2:
            has_sil = st.checkbox("💊 실손의료비 (SIL)", value=True)
            if has_sil:
                sil_gen = st.selectbox("실손 세대", [1, 2, 3, 4], index=2, key="new_sil_gen")
        with cov_col3:
            has_sur = st.checkbox("🔪 수술비 (SUR)", value=False)
            if has_sur:
                sur_max_class = st.selectbox("최대 수술종", [1, 2, 3, 4, 5], index=4, key="new_sur_max")

        submitted = st.form_submit_button("📋 등록하기", use_container_width=True, type="primary")

        if submitted:
            # 유효성 검증
            errors = []
            if not name.strip():
                errors.append("피보험자 이름을 입력해 주세요.")
            if not policy_no.strip():
                errors.append("증권번호를 입력해 주세요.")
            if not birth_date.strip() or len(birth_date.strip()) != 10:
                errors.append("생년월일을 YYYY-MM-DD 형식으로 입력해 주세요.")

            # 중복 확인
            existing = get_insured_profile(policy_no.strip())
            custom_list = st.session_state.get("custom_contracts", [])
            if existing or any(c.get("policy_no") == policy_no.strip() for c in custom_list):
                errors.append(f"증권번호 {policy_no.strip()} 은 이미 등록되어 있어요.")

            if errors:
                for e in errors:
                    st.error(e)
                return None

            # 담보 구성
            coverages = []
            if has_ind:
                coverages.append({
                    "code": "IND001", "name": "입원일당 (질병)",
                    "type": "IND", "status": "유효",
                })
            if has_sil:
                coverages.append({
                    "code": "SIL001", "name": "실손의료비 (입원)",
                    "type": "SIL", "status": "유효",
                })
            if has_sur:
                coverages.append({
                    "code": "SUR001", "name": "수술비 (1종~5종)",
                    "type": "SUR", "status": "유효",
                })

            # 나이 계산
            try:
                birth_year = int(birth_date.strip()[:4])
                from datetime import date
                age = date.today().year - birth_year
            except (ValueError, IndexError):
                age = 0

            new_profile = {
                "name": name.strip(),
                "gender": gender,
                "gender_label": {"M": "남", "F": "여"}.get(gender, gender),
                "birth_date": birth_date.strip(),
                "age": age,
                "id_masked": f"{birth_date.strip().replace('-', '')[:6]}-{'1' if gender == 'M' else '2'}******",
                "policy_no": policy_no.strip(),
                "product_name": product_name.strip() or "커스텀 보험상품",
                "product_code": "CUSTOM",
                "silson_generation": generation,
                "generation_label": f"{generation}세대" if generation else "",
                "contract_date": "",
                "expiry_date": "",
                "status": "유효",
                "premium_status": "정상",
                "coverages": coverages,
                "_custom": True,
            }

            # session_state에 저장
            if "custom_contracts" not in st.session_state:
                st.session_state["custom_contracts"] = []
            st.session_state["custom_contracts"].append(new_profile)

            # data_loader 레지스트리에 등록 (rule_engine 에서 조회 가능)
            try:
                from src.utils.data_loader import (
                    register_custom_contract,
                    save_custom_contracts,
                )
                register_custom_contract(new_profile)
                save_custom_contracts()
            except Exception:
                pass  # 저장 실패해도 session_state 에는 유지

            st.success(f"✅ **{name.strip()}** ({policy_no.strip()}) 님이 등록되었어요!")
            return new_profile

    return None


# ══════════════════════════════════════════════════════════════
# TASK-C2: 약관 근거 표시 컴포넌트
# ══════════════════════════════════════════════════════════════

def render_clause_reference(applied_rules: list) -> None:
    """룰별 약관 근거를 아코디언(접이식) 카드로 렌더링.

    각 RuleResult.evidence 에 _enrich_evidence() 로 주입된
    policy_clause, clause_title, clause_text, legal_basis 를 표시.

    Args:
        applied_rules: list[RuleResult] 객체들.
    """
    if not applied_rules:
        return

    # 약관 근거가 있는 룰만 필터
    rules_with_clause = [
        r for r in applied_rules
        if r.evidence.get("policy_clause")
    ]
    if not rules_with_clause:
        return

    st.markdown(
        '<div class="section-title"><h3>📜 약관 근거</h3></div>',
        unsafe_allow_html=True,
    )
    st.caption("각 심사 규칙에 적용된 보험 약관 조항이에요.")

    for idx, rule in enumerate(rules_with_clause):
        ev = rule.evidence
        label = RULE_LABELS.get(rule.rule_id, rule.rule_id)
        status_name, status_icon, _ = get_status_label(rule.status)

        clause = ev.get("policy_clause", "")
        clause_title = ev.get("clause_title", "")
        clause_text = ev.get("clause_text", "")
        legal_basis = ev.get("legal_basis", "")

        header = f"{status_icon} {label} — {clause}"

        with st.expander(header, expanded=False):
            delay_cls = f"anim-delay-{min(idx + 1, 10)}"
            clause_html = (
                f'<div class="clause-block anim-fade-in-up hover-lift {delay_cls}" '
                f'id="clause-{rule.rule_id}" '
                f'style="background:#F8F9FA;border-radius:12px;padding:16px;margin-bottom:8px">'
                f'<div style="font-weight:700;font-size:0.95rem;color:#191F28;margin-bottom:8px">'
                f'📋 {clause}'
                f'</div>'
                f'<div style="font-size:0.85rem;color:#4E5968;margin-bottom:4px">'
                f'<strong>{clause_title}</strong>'
                f'</div>'
                f'<div style="font-size:0.83rem;color:#6B7684;line-height:1.6;margin-bottom:12px;'
                f'border-left:3px solid #D1D6DB;padding-left:12px">'
                f'{clause_text}'
                f'</div>'
            )
            if legal_basis:
                clause_html += (
                    f'<div style="font-size:0.78rem;color:#8B95A1;margin-top:4px">'
                    f'⚖️ {legal_basis}'
                    f'</div>'
                )
            clause_html += '</div>'

            st.markdown(clause_html, unsafe_allow_html=True)

            # 룰 판단 결과 요약
            if rule.reason:
                reason_color = "#E53935" if rule.status in ("FAIL", "FLAGGED") else "#4E5968"
                st.markdown(
                    f'<div style="font-size:0.83rem;color:{reason_color}">'
                    f'{status_icon} {rule.reason}'
                    f'</div>',
                    unsafe_allow_html=True,
                )


def _collect_issues(decision) -> list[str]:
    """판정에서 핵심 문제점을 수집 (부지급/일부지급/보류/검토필요)."""
    issues: list[str] = []

    # 부지급 사유
    denial = getattr(decision, "denial_reason", None)
    if denial:
        clause = getattr(decision, "policy_clause", "")
        clause_text = f" ({clause})" if clause else ""
        issues.append(f"❌ {denial}{clause_text}")

    # 미비 서류
    missing = getattr(decision, "missing_docs", [])
    if missing:
        issues.append(f"📄 서류 미비: {', '.join(missing)}")

    # 일부지급 — 지급 불가 담보
    denial_covs = getattr(decision, "denial_coverages", [])
    for dc in denial_covs:
        rule_id = dc.get("rule_id", "")
        reason = dc.get("reason", "")
        name, _, _ = get_coverage_label(rule_id)
        issues.append(f"⚡ {name}: {reason}")

    # 담당자 검토 필요
    if getattr(decision, "reviewer_flag", False):
        reason = getattr(decision, "reviewer_reason", "") or "추가 확인 필요"
        issues.append(f"⚠️ 담당자 검토: {reason}")

    # 사기 조사 플래그
    if getattr(decision, "fraud_investigation_flag", False):
        fraud_reason = getattr(decision, "fraud_investigation_reason", "")
        issues.append(f"🚨 사기조사팀 통보 대상: {fraud_reason}")

    return issues


def render_result_summary(decision, context=None) -> None:
    """Executive Summary — 판정 + 금액 + 핵심사유를 한 카드에 통합.

    Step 4 최상단에 배치되어 "이 건이 뭔지" 한눈에 파악 가능.

    Args:
        decision: ClaimDecision 객체.
        context:  ClaimContext 객체 (환자 정보 표시용, None 가능).
    """
    dec = getattr(decision, "decision", "보류")
    total = getattr(decision, "total_payment", 0)
    cfg = get_decision_config(dec)

    # ── 핵심 사유 1줄 결정 ────────────────────────────────────
    reason_text = ""
    if dec == "지급":
        # 산정된 담보 목록
        breakdown = getattr(decision, "breakdown", {})
        if breakdown:
            cov_names = []
            for rid in breakdown:
                name, _, _ = get_coverage_label(rid)
                cov_names.append(name)
            reason_text = " + ".join(cov_names) + " 정상 산정"
        else:
            reason_text = cfg["description"]
    elif dec == "부지급":
        reason_text = getattr(decision, "denial_reason", "") or cfg["description"]
    elif dec == "일부지급":
        denial_covs = getattr(decision, "denial_coverages", [])
        if denial_covs:
            dc_names = []
            for dc in denial_covs[:2]:
                name, _, _ = get_coverage_label(dc.get("rule_id", ""))
                dc_names.append(name)
            reason_text = ", ".join(dc_names) + " 지급 불가"
        else:
            reason_text = cfg["description"]
    elif dec == "보류":
        missing = getattr(decision, "missing_docs", [])
        reason_text = f"부족 서류: {', '.join(missing)}" if missing else cfg["description"]
    elif dec == "검토필요":
        reason_text = getattr(decision, "reviewer_reason", "") or cfg["description"]

    # ── 핵심 이슈 수집 (key_issues 통합) ──────────────────────
    issues_html = ""
    if dec != "지급":
        issues = _collect_issues(decision)
        if issues:
            items = "".join(f'<li class="rs-issue-item">{iss}</li>' for iss in issues[:5])
            issues_html = f'<ul class="rs-issues-compact">{items}</ul>'

    # ── 조건 통과 요약 1줄 ──────────────────────────────────
    rules = getattr(decision, "applied_rules", [])
    conditions_summary = ""
    if rules:
        total_rules = len(rules)
        passed = sum(1 for r in rules if r.status == "PASS")
        failed = sum(1 for r in rules if r.status == "FAIL")
        if failed:
            conditions_summary = (
                f'<div class="rs-conditions-summary">'
                f'<span class="rs-cond-total">{total_rules}개 조건 중</span> '
                f'<span class="rs-cond-pass">{passed}개 통과</span>'
                f'<span class="rs-cond-sep">·</span>'
                f'<span class="rs-cond-fail">{failed}개 미충족</span>'
                f'</div>'
            )
        else:
            conditions_summary = (
                f'<div class="rs-conditions-summary">'
                f'<span class="rs-cond-total">{total_rules}개 조건 중</span> '
                f'<span class="rs-cond-pass">{passed}개 모두 통과</span>'
                f'</div>'
            )

    # ── 메인 HTML 조립 ───────────────────────────────────────
    # 판정별 CSS 클래스
    _DEC_CSS = {
        "지급": "rs-pay", "부지급": "rs-deny", "일부지급": "rs-partial",
        "검토필요": "rs-review", "보류": "rs-hold",
    }
    dec_cls = _DEC_CSS.get(dec, "rs-hold")

    # 판정별 글로우 애니메이션 클래스
    _DEC_ANIM = {
        "지급": "decision-approved", "부지급": "decision-denied",
        "보류": "decision-hold", "검토필요": "decision-hold",
        "일부지급": "decision-hold",
    }
    dec_anim = _DEC_ANIM.get(dec, "")

    st.markdown(
        f'<div class="result-summary {dec_cls} anim-active {dec_anim}">'
        # 상단: 아이콘 + 판정 + 금액
        f'<div class="rs-header">'
        f'<div class="rs-icon">{cfg["icon"]}</div>'
        f'<div class="rs-main">'
        f'<div class="rs-decision">{cfg["label"]}</div>'
        f'<div class="rs-amount">{fmt_amount(total)}</div>'
        f'</div>'
        f'</div>'
        # 사유 1줄
        f'<div class="rs-reason">{reason_text}</div>'
        # 조건 통과 요약
        f'{conditions_summary}'
        # 핵심 이슈 (부지급/일부지급/보류 시만)
        f'{issues_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_audit_flow(decision) -> None:
    """심사 파이프라인 수평 플로우차트 — 각 단계(COM→DOC→보종별산정→최종판정)를 노드로 시각화.

    Args:
        decision: ClaimDecision 객체 (applied_rules 사용).
    """
    rules = getattr(decision, "applied_rules", [])
    if not rules:
        return

    # 룰 ID → 단계 그룹 매핑
    _PHASE_ORDER = [
        ("계약 유효성", ["COM-001", "COM-002", "COM-003", "COM-004"]),
        ("서류 확인", ["DOC-001"]),
        ("입원일당", ["IND-001"]),
        ("실손의료비", ["SIL-001"]),
        ("수술비", ["SUR-001"]),
    ]

    # 룰 결과를 rule_id → status 맵으로
    rule_map = {r.rule_id: r.status for r in rules}

    # 각 단계의 최종 상태 결정 (FAIL > FLAGGED > PASS > SKIP)
    _PRIORITY = {"FAIL": 0, "FLAGGED": 1, "PASS": 2, "SKIP": 3}

    phases = []
    for phase_name, rule_ids in _PHASE_ORDER:
        statuses = [rule_map.get(rid) for rid in rule_ids if rid in rule_map]
        if not statuses:
            phases.append((phase_name, "skip"))
            continue
        best = min(statuses, key=lambda s: _PRIORITY.get(s, 99))
        phases.append((phase_name, best.lower()))

    # 최종 판정 추가
    dec = getattr(decision, "decision", "보류")
    dec_status_map = {"지급": "pass", "부지급": "fail", "일부지급": "flagged", "검토필요": "flagged", "보류": "skip"}
    phases.append(("최종판정", dec_status_map.get(dec, "skip")))

    # 상태별 아이콘
    _ICONS = {"pass": "✅", "fail": "❌", "flagged": "⚠️", "skip": "⬜"}

    # HTML 렌더링
    nodes_html = []
    for i, (name, status) in enumerate(phases):
        icon = _ICONS.get(status, "⬜")
        node = (
            f'<div class="audit-node audit-node-{status}">'
            f'<div class="audit-node-icon">{icon}</div>'
            f'<div class="audit-node-label">{name}</div>'
            f'</div>'
        )
        nodes_html.append(node)
        if i < len(phases) - 1:
            nodes_html.append('<div class="audit-arrow">→</div>')

    st.markdown(
        f'<div class="audit-flow">{"".join(nodes_html)}</div>',
        unsafe_allow_html=True,
    )


def render_doc_check_matrix(decision, context=None) -> None:
    """보종별 필요 서류 확인 매트릭스 — ✅/❌/➖ 아이콘 표시.

    Args:
        decision: ClaimDecision 객체 (applied_rules, breakdown 사용).
        context:  ClaimContext 객체 (submitted_doc_types 사용). None이면 생략.
    """
    rules = getattr(decision, "applied_rules", [])
    if not rules:
        return

    # 어떤 보종이 청구되었는지 파악
    rule_map = {r.rule_id: r.status for r in rules}
    breakdown = getattr(decision, "breakdown", {})

    # 보종별 필요 서류 정의
    _COV_DOCS = {
        "입원일당": {
            "rule": "IND-001",
            "docs": ["진단서", "입원확인서"],
        },
        "실손의료비": {
            "rule": "SIL-001",
            "docs": ["진단서", "진료비영수증", "진료비세부내역서"],
        },
        "수술비": {
            "rule": "SUR-001",
            "docs": ["진단서", "수술확인서"],
        },
    }

    # 제출된 서류 목록
    submitted = set()
    if context:
        submitted = set(getattr(context, "submitted_doc_types", []))

    # 참여 보종만 필터
    active_covs = {}
    for cov_name, cov_info in _COV_DOCS.items():
        rid = cov_info["rule"]
        if rid in rule_map:
            active_covs[cov_name] = cov_info

    if not active_covs:
        return

    # 모든 서류 유형 수집
    all_docs = []
    for info in active_covs.values():
        for d in info["docs"]:
            if d not in all_docs:
                all_docs.append(d)

    # 테이블 헤더
    header_cells = "".join(f'<th class="doc-matrix-th">{d}</th>' for d in all_docs)

    # 테이블 바디
    rows_html = []
    for cov_name, cov_info in active_covs.items():
        rid = cov_info["rule"]
        status = rule_map.get(rid, "SKIP")
        status_cls = status.lower()

        cells = []
        for doc in all_docs:
            if doc in cov_info["docs"]:
                if doc in submitted:
                    cells.append('<td class="doc-matrix-td doc-ok">✅</td>')
                else:
                    cells.append('<td class="doc-matrix-td doc-missing">❌</td>')
            else:
                cells.append('<td class="doc-matrix-td doc-na">➖</td>')

        name_label, _, _ = get_coverage_label(rid)
        rows_html.append(
            f'<tr>'
            f'<td class="doc-matrix-cov doc-matrix-cov-{status_cls}">{name_label}</td>'
            f'{"".join(cells)}'
            f'</tr>'
        )

    st.markdown(
        f'<div class="doc-matrix-wrap anim-fade-in-up anim-delay-3">'
        f'<table class="doc-matrix">'
        f'<thead><tr><th class="doc-matrix-th">보종</th>{header_cells}</tr></thead>'
        f'<tbody>{"".join(rows_html)}</tbody>'
        f'</table>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_denial_coverages(decision) -> None:
    """일부지급 시 지급 불가 담보를 시각적으로 표시.

    Args:
        decision: ClaimDecision 객체.
    """
    denial_covs = getattr(decision, "denial_coverages", [])
    if not denial_covs:
        return

    is_partial = getattr(decision, "decision", "") == "일부지급"
    title = "⚡ 지급 불가 담보" if is_partial else "❌ 부지급 담보"

    st.markdown(
        f'<div class="section-title"><h3>{title}</h3></div>',
        unsafe_allow_html=True,
    )
    if is_partial:
        st.caption("아래 담보는 약관 기준에 따라 지급이 불가해요. 지급 가능한 담보는 정상 산정되었어요.")

    for dc in denial_covs:
        rule_id = dc.get("rule_id", "")
        reason = dc.get("reason", "")
        clause = dc.get("policy_clause", "")
        name, bg_color, text_color = get_coverage_label(rule_id)

        clause_badge = (
            f' <span style="font-size:0.75rem;color:#8B95A1;margin-left:4px">({clause})</span>'
            if clause else ""
        )

        denial_html = (
            f'<div style="background:#FFF3E0;border-radius:12px;padding:14px 16px;margin-bottom:8px;'
            f'border-left:4px solid #FF9800">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
            f'<span style="font-size:0.85rem;font-weight:600;color:#E65100">❌ {name}</span>'
            f'{clause_badge}'
            f'</div>'
            f'<div style="font-size:0.82rem;color:#6B7684">{reason}</div>'
            f'</div>'
        )
        st.markdown(denial_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# TASK-UI-04: 피보험자 프로필 카드
# ══════════════════════════════════════════════════════════════

def render_insured_profile(context) -> None:
    """피보험자 프로필 카드 — 이 사람이 누구인지.

    Args:
        context: ClaimContext 객체 (policy_no 필드 필요).
    """
    profile = get_insured_profile(getattr(context, "policy_no", ""))

    if not profile:
        st.info("피보험자 정보를 조회할 수 없어요.")
        return

    avatar = "👨‍💼" if profile["gender"] == "M" else "👩‍💼"

    # 가입 담보 칩 HTML
    cov_chips = ""
    for cov in profile.get("coverages", []):
        cov_chips += f'<span class="status-chip status-chip-pass">{cov["name"]}</span> '

    profile_html = (
        '<div class="profile-card anim-active hover-lift">'
        '<div class="profile-header">'
        f'<div class="profile-avatar">{avatar}</div>'
        '<div>'
        f'<div class="profile-name">{profile["name"]}</div>'
        f'<div class="profile-sub">{profile["gender_label"]} · {profile["age"]}세 · {profile["id_masked"]}</div>'
        '</div>'
        '</div>'
        '<div class="profile-grid">'
        f'<div class="profile-dt">증권번호</div><div class="profile-dd">{profile["policy_no"]}</div>'
        f'<div class="profile-dt">상품명</div><div class="profile-dd">{profile["product_name"]}</div>'
        f'<div class="profile-dt">보험 세대</div><div class="profile-dd">{profile["generation_label"]}</div>'
        f'<div class="profile-dt">계약 상태</div><div class="profile-dd">{profile["status"]} · 보험료 {profile["premium_status"]}</div>'
        f'<div class="profile-dt">계약일</div><div class="profile-dd">{profile["contract_date"]}</div>'
        f'<div class="profile-dt">만기일</div><div class="profile-dd">{profile["expiry_date"]}</div>'
        '</div>'
        '<div style="margin-top:16px">'
        '<div style="font-size:0.8rem;color:#8B95A1;margin-bottom:4px">가입 담보</div>'
        f'<div>{cov_chips}</div>'
        '</div>'
        '</div>'
    )
    st.markdown(profile_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# TASK-UI-04: 청구 요약 카드
# ══════════════════════════════════════════════════════════════

def render_claim_summary(context) -> None:
    """청구 요약 카드 — 뭘 청구했는지.

    Args:
        context: ClaimContext 객체.
    """
    kcd = getattr(context, "kcd_code", "") or ""
    diagnosis = getattr(context, "diagnosis", "") or ""
    kcd_display = f"{kcd} {diagnosis}".strip() if kcd else diagnosis

    # 수술 정보
    surgery_text = "없음"
    surgery_name = getattr(context, "surgery_name", None)
    surgery_code = getattr(context, "surgery_code", None)
    if surgery_name:
        surgery_text = get_surgery_name(code=surgery_code, name=surgery_name)

    # 입원 기간
    admission = getattr(context, "admission_date", None) or ""
    discharge = getattr(context, "discharge_date", None) or ""
    days = getattr(context, "hospital_days", None)
    period_text = ""
    if admission and discharge:
        period_text = f"{admission} ~ {discharge}"
        if days:
            period_text += f" ({fmt_days(days)})"
    elif days:
        period_text = fmt_days(days)

    # 진료비
    covered = getattr(context, "covered_self_pay", None)
    non_covered = getattr(context, "non_covered_amount", None)
    total_cost = (covered or 0) + (non_covered or 0)

    cost_text = (
        f"급여 {fmt_amount(covered)} / 비급여 {fmt_amount(non_covered)}"
        if covered or non_covered else "정보 없음"
    )
    summary_html = (
        '<div class="claim-summary anim-active">'
        '<div class="summary-grid">'
        f'<div class="summary-dt">청구일</div><div class="summary-dd">{getattr(context, "claim_date", "") or "-"}</div>'
        f'<div class="summary-dt">사고/발병일</div><div class="summary-dd">{getattr(context, "accident_date", "") or "-"}</div>'
        f'<div class="summary-dt">진단명 (KCD)</div><div class="summary-dd">{kcd_display or "미상"}</div>'
        f'<div class="summary-dt">입원 기간</div><div class="summary-dd">{period_text or "해당 없음"}</div>'
        f'<div class="summary-dt">수술</div><div class="summary-dd">{surgery_text}</div>'
        f'<div class="summary-dt">진료비</div><div class="summary-dd">{cost_text}</div>'
        '</div>'
        '</div>'
    )
    st.markdown(summary_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# TASK-UI-04: 심사 조건 타임라인
# ══════════════════════════════════════════════════════════════

def render_review_conditions(applied_rules: list) -> None:
    """심사 조건을 수직 타임라인으로 표시 — 어떤 조건을 따졌는지.

    Args:
        applied_rules: list[RuleResult] 객체들.
    """
    if not applied_rules:
        st.info("적용된 심사 규칙이 없어요.")
        return

    html_parts = []
    for idx, rule in enumerate(applied_rules):
        rule_id = rule.rule_id
        status = rule.status
        reason = rule.reason or ""

        label = RULE_LABELS.get(rule_id, rule_id)
        status_name, status_icon, status_color = get_status_label(status)

        icon_cls = f"timeline-icon-{status.lower()}"
        reason_cls = "timeline-reason-fail" if status in ("FAIL", "FLAGGED") else ""
        delay_cls = f"anim-delay-{min(idx + 1, 10)}"

        # 금액 표시
        amount_badge = (
            f' <span style="font-weight:700;color:#191F28">{fmt_amount(rule.value)}</span>'
            if rule.value else ""
        )

        html_parts.append(
            f'<div class="timeline-step anim-active hover-lift {delay_cls}">'
            f'<div class="timeline-icon {icon_cls}">{status_icon}</div>'
            '<div class="timeline-body">'
            f'<p class="timeline-title">{label} '
            f'<span class="status-chip status-chip-{status.lower()}">{status_name}</span>'
            f'{amount_badge}</p>'
            f'<p class="timeline-reason {reason_cls}">{reason}</p>'
            '</div>'
            '</div>'
        )

    st.markdown("\n".join(html_parts), unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# TASK-UI-05: 최종 판정 대시보드
# ══════════════════════════════════════════════════════════════

def render_decision_dashboard(result) -> None:
    """최종 판정 대시보드 — Toss 스타일 큰 숫자 강조.

    Args:
        result: ClaimDecision 객체.
    """
    decision = getattr(result, "decision", "보류")
    total = getattr(result, "total_payment", 0)
    cfg = get_decision_config(decision)

    # 메인 판정 배너
    banner_html = (
        f'<div class="decision-banner {cfg["css_class"]}">'
        f'<div style="font-size:2rem;margin-bottom:4px">{cfg["icon"]}</div>'
        f'<div class="metric-value" style="font-size:2.2rem;font-weight:700;margin:4px 0">{fmt_amount(total)}</div>'
        f'<div style="font-size:0.95rem;margin-top:4px">{cfg["description"]}</div>'
        '</div>'
    )
    st.markdown(banner_html, unsafe_allow_html=True)

    # 부지급/보류 사유
    denial = getattr(result, "denial_reason", None)
    if denial:
        clause = getattr(result, "policy_clause", "")
        clause_text = f" ({clause})" if clause else ""
        st.markdown(
            f'<div class="alert-banner alert-banner-danger">❌ {denial}{clause_text}</div>',
            unsafe_allow_html=True,
        )

    missing = getattr(result, "missing_docs", [])
    if missing:
        st.markdown(
            f'<div class="alert-banner alert-banner-warning">📄 부족한 서류: {", ".join(missing)}</div>',
            unsafe_allow_html=True,
        )

    # 담당자 검토 필요
    if getattr(result, "reviewer_flag", False):
        reason = getattr(result, "reviewer_reason", "") or "추가 확인이 필요해요"
        st.markdown(
            f'<div class="alert-banner alert-banner-warning">⚠️ 담당자 추가 확인 필요 — {reason}</div>',
            unsafe_allow_html=True,
        )

    # 사기 조사 플래그
    if getattr(result, "fraud_investigation_flag", False):
        fraud_reason = getattr(result, "fraud_investigation_reason", "")
        st.markdown(
            f'<div class="alert-banner alert-banner-danger">🚨 사기조사팀 통보 대상 — {fraud_reason}</div>',
            unsafe_allow_html=True,
        )

    # 지급예정일
    payment_date = getattr(result, "payment_date", None)
    if payment_date:
        st.markdown(
            f'<div class="alert-banner alert-banner-info">📅 지급 예정일: {payment_date}</div>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════
# TASK-4: 산정 상세 시각화 — 수학 산식 + 한글 레이블
# ══════════════════════════════════════════════════════════════

def _render_formula_ind(ev: dict) -> str:
    """IND (입원일당) 산식 HTML 생성."""
    # coverages_applied 가 있으면 각 담보별 산식 표시
    coverages = ev.get("coverages_applied", [])
    if coverages:
        rows = []
        for cov in coverages:
            cov_name = cov.get("coverage_name", "입원일당")
            days_claimed = cov.get("hospital_days_claimed", 0)
            waiting = cov.get("waiting_days", 0)
            payable = cov.get("payable_days", 0)
            daily = cov.get("daily_benefit", 0)
            amt = cov.get("benefit_amount", 0)
            rows.append(
                f'<div class="ev-formula-row">'
                f'<span class="ev-formula-label">{cov_name}</span>'
                f'<span class="ev-formula-expr">'
                f'({fmt_days(days_claimed)} − 면책 {fmt_days(waiting)}) '
                f'× {fmt_amount(daily)} = '
                f'<strong>{fmt_amount(amt)}</strong>'
                f'</span></div>'
            )
        return "\n".join(rows)

    # fallback: 단일 산식
    days = ev.get("hospital_days_claimed", 0)
    waiting = ev.get("waiting_days", ev.get("deductible_days", 0))
    payable = ev.get("payable_days", 0)
    daily = ev.get("daily_amount", ev.get("daily_benefit", 0))
    total = ev.get("benefit_amount", 0)
    return (
        f'<div class="ev-formula-row">'
        f'<span class="ev-formula-expr">'
        f'({fmt_days(days)} − 면책 {fmt_days(waiting)}) '
        f'× {fmt_amount(daily)} = '
        f'<strong>{fmt_amount(total)}</strong>'
        f'</span></div>'
    )


def _render_formula_sil(ev: dict) -> str:
    """SIL (실손의료비) 산식 HTML 생성."""
    gen = ev.get("silson_generation", "")
    covered = ev.get("covered_self_pay", 0)
    non_cov = ev.get("non_covered_capped", ev.get("non_covered_amount", 0))
    rate_c = ev.get("copay_rate_covered", 0)
    rate_n = ev.get("copay_rate_non_covered", 0)
    copay = ev.get("copay_applied", 0)
    total = ev.get("benefit_amount", 0)

    pct_c = int((1 - rate_c) * 100) if rate_c < 1 else int(100 - rate_c)
    pct_n = int((1 - rate_n) * 100) if rate_n < 1 else int(100 - rate_n)

    gen_badge = f'<span class="ev-gen-badge">{gen}세대 실손</span>' if gen else ""

    return (
        f'<div class="ev-formula-row">{gen_badge}</div>'
        f'<div class="ev-formula-row">'
        f'<span class="ev-formula-expr">'
        f'급여 {fmt_amount(covered)} × {pct_c}% + '
        f'비급여 {fmt_amount(non_cov)} × {pct_n}%'
        f'</span></div>'
        f'<div class="ev-formula-row">'
        f'<span class="ev-formula-expr">'
        f'= 총 보상 <strong>{fmt_amount(total)}</strong>'
        f' (자기부담 {fmt_amount(copay)})'
        f'</span></div>'
    )


def _render_formula_sur(ev: dict) -> str:
    """SUR (수술비) 산식 HTML 생성."""
    s_name = ev.get("surgery_name", "")
    s_code = ev.get("surgery_code", "")
    s_class = ev.get("surgery_class", "")
    total = ev.get("benefit_amount", 0)
    inferred = ev.get("inferred_from_kcd", False)

    code_str = f' ({s_code})' if s_code else ""
    inferred_str = ' <span class="ev-inferred">[KCD 추론]</span>' if inferred else ""

    return (
        f'<div class="ev-formula-row">'
        f'<span class="ev-formula-label">{s_name}{code_str}{inferred_str}</span>'
        f'</div>'
        f'<div class="ev-formula-row">'
        f'<span class="ev-formula-expr">'
        f'{s_class}종 수술 → 정액 <strong>{fmt_amount(total)}</strong>'
        f'</span></div>'
    )


def _render_formula_generic(ev: dict) -> str:
    """기타 담보 산식 HTML (fallback)."""
    total = ev.get("benefit_amount", 0)
    formula = ev.get("formula", "")
    return (
        f'<div class="ev-formula-row">'
        f'<span class="ev-formula-expr">'
        f'{formula} = <strong>{fmt_amount(total)}</strong>'
        f'</span></div>'
    )


_FORMULA_RENDERERS = {
    "IND": _render_formula_ind,
    "SIL": _render_formula_sil,
    "SUR": _render_formula_sur,
}


def render_evidence_detail(rule_id: str, evidence: dict) -> None:
    """evidence 딕셔너리를 보험 전문가용 포맷으로 렌더링.

    구조:
      ① 핵심 산식 시각화 (수학 표기, 담보 유형별 분기)
      ② 주요 항목 테이블 (한글 레이블, 자동 포맷)
      ③ 적용 약관 인용 블록
      ④ 미등록 필드 (기타 정보)
    """
    ev_type = get_evidence_type(rule_id)  # IND / SIL / SUR / ETC

    # ── SIL-001 워터폴 차트 ────────────────────────────────────
    if rule_id == "SIL-001":
        _render_waterfall_chart(evidence)

    # ── ① 산식 시각화 ──────────────────────────────────────────
    renderer = _FORMULA_RENDERERS.get(ev_type, _render_formula_generic)
    formula_html = renderer(evidence)
    st.markdown(
        f'<div class="ev-formula-box">'
        f'<div class="ev-formula-title">📐 계산 산식</div>'
        f'{formula_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── ② 주요 항목 테이블 ────────────────────────────────────
    # 약관 관련 필드는 ③에서 별도 표시
    _clause_keys = {"policy_clause", "clause_ref", "clause_title", "clause_text", "legal_basis"}
    # 이미 산식에서 표시한 키 + 복합 타입은 테이블에서 제외
    _skip_keys = {"formula", "benefit_amount", "coverages_applied", "sil_4gen_cap_details"}
    _skip_keys |= _clause_keys

    # 표시 순서 결정
    display_order = EVIDENCE_DISPLAY_ORDER.get(ev_type, [])
    ordered_keys = [k for k in display_order if k in evidence and k not in _skip_keys]
    # 미등록 키 (순서 리스트에 없는 것)
    remaining_keys = [k for k in evidence if k not in ordered_keys and k not in _skip_keys]

    if ordered_keys:
        table_rows = []
        for key in ordered_keys:
            label = get_evidence_label(key)
            val = evidence[key]
            formatted = fmt_evidence_value(key, val)
            if formatted is None:
                # 복합 타입 (list/dict) — 건너뜀
                continue
            table_rows.append(
                f'<tr><td class="ev-key">{label}</td>'
                f'<td class="ev-val">{formatted}</td></tr>'
            )

        if table_rows:
            st.markdown(
                '<div class="ev-table-wrap">'
                '<table class="ev-table">'
                '<thead><tr><th>항목</th><th>값</th></tr></thead>'
                '<tbody>' + "\n".join(table_rows) + '</tbody>'
                '</table></div>',
                unsafe_allow_html=True,
            )

    # ── IND 특수: coverages_applied 서브테이블 ────────────────
    coverages = evidence.get("coverages_applied", [])
    if coverages and len(coverages) > 1:
        sub_rows = []
        for cov in coverages:
            sub_rows.append(
                f'<tr>'
                f'<td>{cov.get("coverage_name", "")}</td>'
                f'<td>{fmt_days(cov.get("hospital_days_claimed", 0))}</td>'
                f'<td>{fmt_days(cov.get("waiting_days", 0))}</td>'
                f'<td>{fmt_days(cov.get("payable_days", 0))}</td>'
                f'<td>{fmt_amount(cov.get("daily_benefit", 0))}</td>'
                f'<td><strong>{fmt_amount(cov.get("benefit_amount", 0))}</strong></td>'
                f'</tr>'
            )
        st.markdown(
            '<div class="ev-table-wrap">'
            '<div class="ev-sub-title">📋 적용 담보 내역</div>'
            '<table class="ev-sub-table">'
            '<thead><tr>'
            '<th>담보명</th><th>청구일수</th><th>면책</th>'
            '<th>인정일수</th><th>1일 금액</th><th>산정액</th>'
            '</tr></thead>'
            '<tbody>' + "\n".join(sub_rows) + '</tbody>'
            '</table></div>',
            unsafe_allow_html=True,
        )

    # ── ③ 적용 약관 인용 ─────────────────────────────────────
    clause_title = evidence.get("clause_title", "")
    clause_text = evidence.get("clause_text", "")
    policy_clause = evidence.get("policy_clause", evidence.get("clause_ref", ""))
    legal_basis = evidence.get("legal_basis", "")

    if clause_title or clause_text:
        clause_html = (
            f'<div class="ev-clause-block">'
            f'<div class="ev-clause-header">📜 {policy_clause}</div>'
            f'<div class="ev-clause-title">{clause_title}</div>'
            f'<blockquote class="ev-clause-text">{clause_text}</blockquote>'
        )
        if legal_basis:
            clause_html += f'<div class="ev-legal-note">⚖️ {legal_basis}</div>'
        clause_html += '</div>'
        st.markdown(clause_html, unsafe_allow_html=True)

    # ── ④ 미등록 필드 (기타 정보) ────────────────────────────
    if remaining_keys:
        misc_rows = []
        for key in remaining_keys:
            val = evidence[key]
            formatted = fmt_evidence_value(key, val)
            if formatted is None:
                formatted = json.dumps(val, ensure_ascii=False, default=str)
            label = get_evidence_label(key)
            misc_rows.append(
                f'<tr><td class="ev-key">{label}</td>'
                f'<td class="ev-val">{formatted}</td></tr>'
            )
        if misc_rows:
            st.markdown(
                '<details class="ev-misc"><summary>기타 정보</summary>'
                '<table class="ev-table">'
                '<tbody>' + "\n".join(misc_rows) + '</tbody>'
                '</table></details>',
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════
# TASK-UI-05: 담보별 산정 카드 (동적 매핑)
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
# C-6: OCR 정확도 리포트
# ══════════════════════════════════════════════════════════════

# 서류 유형별 기대 필드 (추출 여부 평가용)
_DOC_EXPECTED_FIELDS: dict[str, list[str]] = {
    "진단서": ["kcd_code", "diagnosis", "accident_date"],
    "입원확인서": ["hospital_days", "admission_date", "discharge_date"],
    "진료비영수증": ["covered_self_pay", "non_covered", "total_self_pay"],
    "수술확인서": ["surgery_name", "surgery_code", "surgery_date"],
    "보험금청구서": ["policy_no", "accident_date"],
    "진료비세부내역서": ["billing_items"],
}

_DOC_TYPE_ICON: dict[str, str] = {
    "진단서": "🩺",
    "입원확인서": "🏥",
    "진료비영수증": "🧾",
    "수술확인서": "🔪",
    "보험금청구서": "📝",
    "진료비세부내역서": "📋",
    "미분류": "❓",
}

_FIELD_LABELS: dict[str, str] = {
    "kcd_code": "상병코드",
    "diagnosis": "진단명",
    "accident_date": "사고일",
    "hospital_days": "입원일수",
    "admission_date": "입원일",
    "discharge_date": "퇴원일",
    "covered_self_pay": "급여 본인부담",
    "non_covered": "비급여",
    "total_self_pay": "납부액",
    "surgery_name": "수술명",
    "surgery_code": "수술코드",
    "surgery_date": "수술일",
    "policy_no": "계약번호",
    "billing_items": "세부항목",
    "receipt_line_items": "영수증항목",
    "receipt_summary": "영수증합계",
    "special_items": "특수항목",
}


def render_ocr_quality_report(context) -> None:
    """OCR/파싱 정확도 리포트 — 서류별 파싱 모드·신뢰도·추출 필드를 시각화.

    ClaimContext.raw_documents 에 있는 ParsedDocument 목록을 분석하여
    각 서류의 파싱 품질을 한눈에 보여준다.

    Args:
        context: ClaimContext 객체 (raw_documents 사용).
    """
    docs = getattr(context, "raw_documents", [])
    if not docs:
        return

    # ── 전체 요약 바 ───────────────────────────────────────────
    total = len(docs)
    confs = [d.confidence for d in docs]
    avg_conf = sum(confs) / total if total else 0
    min_conf = min(confs) if confs else 0
    mode_counts: dict[str, int] = {}
    for d in docs:
        m = d.parse_mode
        mode_counts[m] = mode_counts.get(m, 0) + 1

    mode_chips = " ".join(
        f'<span class="ocr-doc-mode ocr-mode-{m}">{m} ×{c}</span>'
        for m, c in sorted(mode_counts.items())
    )
    avg_cls = "conf-high" if avg_conf >= 0.8 else ("conf-medium" if avg_conf >= 0.5 else "conf-low")

    st.markdown(
        f'<div class="ocr-summary-bar">'
        f'<span>📊</span>'
        f'<span class="ocr-summary-stat">서류 {total}건</span>'
        f'<span>|</span>'
        f'<span>평균 신뢰도 <span class="ocr-conf-pct {avg_cls}">{avg_conf:.0%}</span></span>'
        f'<span>|</span>'
        f'<span>최저 <span class="ocr-conf-pct {"conf-high" if min_conf >= 0.8 else ("conf-medium" if min_conf >= 0.5 else "conf-low")}">{min_conf:.0%}</span></span>'
        f'<span>|</span>'
        f'{mode_chips}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 서류별 상세 행 ─────────────────────────────────────────
    report_html_parts = ['<div class="ocr-report anim-fade-in-up">']

    for doc in docs:
        icon = _DOC_TYPE_ICON.get(doc.doc_type, "📄")
        conf = doc.confidence
        conf_cls = "conf-high" if conf >= 0.8 else ("conf-medium" if conf >= 0.5 else "conf-low")
        mode_cls = f"ocr-mode-{doc.parse_mode}"

        # 신뢰도 바
        bar_width = max(int(conf * 100), 2)

        report_html_parts.append(
            f'<div class="ocr-doc-row">'
            f'<span class="ocr-doc-icon">{icon}</span>'
            f'<span class="ocr-doc-name">{doc.doc_type}</span>'
            f'<span class="ocr-doc-mode {mode_cls}">{doc.parse_mode}</span>'
            f'<div class="ocr-conf-bar-bg"><div class="ocr-conf-bar {conf_cls}" style="width:{bar_width}%"></div></div>'
            f'<span class="ocr-conf-pct {conf_cls}">{conf:.0%}</span>'
            f'</div>'
        )

        # 추출 필드 칩
        expected = _DOC_EXPECTED_FIELDS.get(doc.doc_type, [])
        if expected:
            chips = []
            for fld in expected:
                label = _FIELD_LABELS.get(fld, fld)
                val = doc.fields.get(fld)
                if val is not None and val != "" and val != []:
                    chips.append(f'<span class="ocr-field-chip ocr-extracted">✓ {label}</span>')
                else:
                    chips.append(f'<span class="ocr-field-chip ocr-missing">✗ {label}</span>')
            report_html_parts.append(f'<div class="ocr-field-chips">{" ".join(chips)}</div>')

        # 파싱 에러
        if doc.parse_errors:
            for err in doc.parse_errors[:3]:
                report_html_parts.append(f'<div class="ocr-error-item">⚠ {err}</div>')

    report_html_parts.append('</div>')
    st.markdown("".join(report_html_parts), unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# C-5: 2차 심사 (추가 영수증) UI
# ══════════════════════════════════════════════════════════════

def render_secondary_assessment(decision, context) -> None:
    """2차 심사 영역 — 추가 영수증 업로드 + 결과 표시.

    Step 4 하단에 배치. 1차 심사 결과가 부지급/보류가 아닌 경우에만 표시.
    SIL-001(실손의료비) 결과가 있는 경우에만 활성화.

    Args:
        decision: 1차 ClaimDecision 객체.
        context:  1차 ClaimContext 객체.
    """
    dec = getattr(decision, "decision", "")
    if dec in ("부지급", "보류"):
        return  # 부지급/보류 시 2차 심사 불가

    # SIL-001 결과 확인
    has_sil = any(
        r.rule_id == "SIL-001" and r.status in ("PASS", "FLAGGED")
        for r in getattr(decision, "applied_rules", [])
    )
    if not has_sil:
        return  # 실손 담보 없으면 2차 심사 불필요

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div class="section-title"><h3>📎 2차 심사 — 추가 영수증</h3></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sec-assess-box anim-fade-in-up">'
        '<div class="sec-title">📎 추가 영수증으로 2차 심사</div>'
        '<div class="sec-desc">'
        '진료비 영수증 이미지(JPG/PNG)를 업로드하면 실손의료비 추가 지급액을 자동 산정합니다. '
        '1차 심사와 동일한 세대별 자기부담금 공식이 적용됩니다.'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # 이미 2차 심사 결과가 세션에 있으면 바로 표시
    sec_key = "secondary_result"
    if sec_key in st.session_state and st.session_state[sec_key] is not None:
        _render_secondary_result(st.session_state[sec_key])
        # 재심사 버튼
        if st.button("🔄 다른 영수증으로 다시 심사", key="sec_retry"):
            st.session_state[sec_key] = None
            st.rerun()
        return

    # 파일 업로더
    uploaded = st.file_uploader(
        "영수증 이미지 업로드",
        type=["jpg", "jpeg", "png"],
        key="sec_receipt_upload",
        help="진료비 영수증 이미지 파일을 선택해 주세요 (JPG, PNG).",
    )

    if uploaded is not None:
        # 이미지 미리보기
        col_img, col_action = st.columns([1, 1])
        with col_img:
            try:
                st.image(uploaded.getvalue(), caption=f"📄 {uploaded.name}", use_container_width=True)
            except Exception:
                st.warning("이미지 미리보기를 표시할 수 없습니다.")
        with col_action:
            st.markdown(f"**파일명:** {uploaded.name}")
            st.markdown(f"**크기:** {uploaded.size / 1024:.1f} KB")

            if st.button("🔍 2차 심사 시작", type="primary", use_container_width=True,
                         key="sec_start_btn"):
                _run_secondary_assessment(uploaded, decision, context)


def _run_secondary_assessment(uploaded_file, decision, context) -> None:
    """2차 심사 실행 — Vision OCR → secondary_assessor."""
    import tempfile
    from pathlib import Path

    with st.spinner("🔍 영수증을 분석하고 있어요..."):
        # 임시 파일에 저장
        suffix = Path(uploaded_file.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = Path(tmp.name)

        try:
            # Vision OCR 파싱
            from src.ocr.doc_parser import parse_receipt_image
            receipt_doc = parse_receipt_image(tmp_path)

            # 2차 심사 엔진
            from src.rules.secondary_assessor import assess_secondary_receipt
            result = assess_secondary_receipt(context, decision, receipt_doc)

            st.session_state["secondary_result"] = result
            st.rerun()

        except Exception as e:
            st.error(f"2차 심사 중 오류가 발생했습니다: {e}")
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass


def _render_secondary_result(result) -> None:
    """SecondaryAssessmentResult를 UI로 렌더링."""
    if not result.success:
        st.markdown(
            f'<div class="sec-result-card sec-fail">'
            f'<div class="sec-result-header">'
            f'<span class="sec-icon">❌</span>'
            f'<span class="sec-label">2차 심사 불가</span>'
            f'<span class="sec-amount">추가 지급 없음</span>'
            f'</div>'
            f'<div style="font-size:0.85rem;color:#666;padding-top:4px">{result.reason}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    comp = result.comparison or {}
    add_pay = result.additional_payment
    primary_pay = comp.get("primary_sil_amount", 0)
    total_combined = comp.get("total_combined", add_pay)
    gen = comp.get("generation", "")
    care = comp.get("care_type", "")

    # ── 결과 카드 ─────────────────────────────────────────────
    st.markdown(
        f'<div class="sec-result-card">'
        f'<div class="sec-result-header">'
        f'<span class="sec-icon">✅</span>'
        f'<span class="sec-label">2차 심사 완료 — 실손 {gen}세대 ({care})</span>'
        f'<span class="sec-amount">+{add_pay:,}원</span>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── 영수증 정보 칩 ────────────────────────────────────────
    chips_html = (
        f'<div class="sec-receipt-info">'
        f'<span class="sec-receipt-chip">급여 {result.new_covered_self_pay:,}원</span>'
        f'<span class="sec-receipt-chip">비급여 {result.new_non_covered:,}원</span>'
        f'</div>'
    )
    st.markdown(chips_html, unsafe_allow_html=True)

    # ── 1차 vs 2차 비교표 ─────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    pri_cov = comp.get("primary_covered", 0)
    pri_nc = comp.get("primary_non_covered", 0)
    sec_cov = comp.get("secondary_covered", 0)
    sec_nc = comp.get("secondary_non_covered", 0)
    pri_copay = comp.get("primary_copay", 0)
    sec_copay = comp.get("secondary_copay", 0)

    table_html = (
        '<table class="sec-compare-table">'
        '<tr><th>항목</th><th>1차 심사</th><th>2차 심사 (추가)</th></tr>'
        f'<tr><td>급여 본인부담금</td><td>{pri_cov:,}원</td><td>{sec_cov:,}원</td></tr>'
        f'<tr><td>비급여</td><td>{pri_nc:,}원</td><td>{sec_nc:,}원</td></tr>'
        f'<tr><td>자기부담금 (공제)</td><td>-{pri_copay:,}원</td><td>-{sec_copay:,}원</td></tr>'
        f'<tr><td>실손 지급액</td><td>{primary_pay:,}원</td><td>{add_pay:,}원</td></tr>'
        f'<tr class="sec-total"><td>합계 지급액</td>'
        f'<td colspan="2" style="text-align:center;font-size:1rem">{total_combined:,}원</td></tr>'
        '</table>'
    )
    st.markdown(table_html, unsafe_allow_html=True)

    # ── 산식 표시 ─────────────────────────────────────────────
    sec_formula = comp.get("secondary_formula", "")
    if sec_formula:
        with st.expander("📐 2차 산정 산식", expanded=False):
            st.markdown(f"```\n{sec_formula}\n```")

    # ── 4세대 한도 메모 ───────────────────────────────────────
    if result.gen4_cap_notes:
        with st.expander("⚠️ 4세대 비급여 항목별 한도", expanded=False):
            for note in result.gen4_cap_notes:
                st.markdown(f"- {note}")


def render_coverage_breakdown_v2(result) -> None:
    """담보별 산정 내역 — labels.py 동적 매핑 사용.

    Args:
        result: ClaimDecision 객체 (breakdown dict 사용).
    """
    breakdown = getattr(result, "breakdown", {})
    denial_covs = getattr(result, "denial_coverages", [])
    if not breakdown and not denial_covs:
        st.markdown(
            '<div class="empty-state"><div class="empty-icon">📭</div>'
            '<p>산정된 보장항목이 없어요 (부지급 또는 보류)</p></div>',
            unsafe_allow_html=True,
        )
        return

    # 룰 결과 맵 (status badge용)
    rule_status_map = {}
    for r in getattr(result, "applied_rules", []):
        rule_status_map[r.rule_id] = r.status

    _STATUS_BADGE = {
        "PASS": ("✅ 지급", "cov-badge-pass"),
        "FAIL": ("❌ 불가", "cov-badge-fail"),
        "FLAGGED": ("⚠️ 검토", "cov-badge-flagged"),
        "SKIP": ("➖ 해당없음", "cov-badge-skip"),
    }

    # 거부 담보 사유 맵 (denial_coverages → coverage 카드에 인라인 표시)
    denial_map: dict[str, str] = {}
    for dc in denial_covs:
        denial_map[dc.get("rule_id", "")] = dc.get("reason", "")

    # 거부 담보 중 breakdown에 없는 것도 추가 표시
    all_items: list[tuple[str, dict]] = list(breakdown.items())
    for dc in denial_covs:
        rid = dc.get("rule_id", "")
        if rid and rid not in breakdown:
            all_items.append((rid, {"benefit_amount": 0, "formula": "해당 없음"}))

    num_cols = min(max(len(all_items), 1), 3)
    cols = st.columns(num_cols)
    for idx, (rule_id, evidence) in enumerate(all_items):
        name, bg_color, text_color = get_coverage_label(rule_id)
        amount = evidence.get("benefit_amount", 0)
        formula = evidence.get("formula", "")

        # 해당 보종 상태 배지
        status = rule_status_map.get(rule_id, "PASS")
        badge_text, badge_cls = _STATUS_BADGE.get(status, ("✅ 지급", "cov-badge-pass"))

        # 거부 사유 인라인
        denial_reason_html = ""
        if rule_id in denial_map:
            badge_text, badge_cls = "❌ 불가", "cov-badge-fail"
            denial_reason_html = (
                f'<div class="cov-denial-reason">{denial_map[rule_id]}</div>'
            )

        with cols[idx % num_cols]:
            delay_cls = f"anim-delay-{min(idx + 1, 10)}"
            cov_html = (
                f'<div class="coverage-card anim-active hover-tilt {delay_cls}" style="background:{bg_color}">'
                f'<div class="cov-badge {badge_cls}">{badge_text}</div>'
                f'<div class="coverage-name" style="color:{text_color}">{name}</div>'
                f'<div class="coverage-amount">{fmt_amount(amount)}</div>'
                f'<div class="coverage-formula">{formula}</div>'
                f'{denial_reason_html}'
                '</div>'
            )
            st.markdown(cov_html, unsafe_allow_html=True)

            # 확장 가능한 evidence 상세 (TASK-5: 수학 산식 시각화)
            if evidence:
                with st.expander("📐 산정 상세", expanded=False):
                    render_evidence_detail(rule_id, evidence)


# ══════════════════════════════════════════════════════════════
# TASK-UI-06: 프로세싱 스테퍼
# ══════════════════════════════════════════════════════════════

_STEP_LABELS = ["서류 분석", "정보 조합", "심사 규칙 적용", "결과 생성"]
_STEP_ICONS = ["📄", "🔗", "⚖️", "✍️"]


def render_processing_stepper(current_step: int = 0, step_message: str = "") -> None:
    """4단계 수평 프로그레스 스테퍼.

    Args:
        current_step: 현재 진행 중인 단계 (0~3). -1이면 모두 완료.
        step_message: 현재 단계의 상세 메시지.
    """
    steps_html = []
    for i, (label, icon) in enumerate(zip(_STEP_LABELS, _STEP_ICONS)):
        if current_step < 0 or i < current_step:
            cls = "step-done"
            circle_content = "✓"
        elif i == current_step:
            cls = "step-active"
            circle_content = f'<span class="anim-spinner"></span>'
        else:
            cls = "step-pending"
            circle_content = str(i + 1)

        steps_html.append(
            f'<div class="step {cls}">'
            f'<div class="step-circle">{circle_content}</div>'
            f'<div class="step-label">{label}</div>'
            '</div>'
        )

    st.markdown(
        f'<div class="progress-stepper">{"".join(steps_html)}</div>',
        unsafe_allow_html=True,
    )

    if step_message and current_step >= 0:
        st.info(step_message)


# ══════════════════════════════════════════════════════════════
# TASK-UI-06: 사이드바 이력
# ══════════════════════════════════════════════════════════════

def render_history_sidebar(history: list) -> str | None:
    """사이드바 처리 이력 카드 목록.

    Args:
        history: [{claim_id, decision, total_payment}, ...] 리스트.

    Returns:
        클릭된 이력의 claim_id 또는 None.
    """
    if not history:
        st.markdown(
            '<div class="empty-state" style="padding:16px">'
            '<div class="empty-icon">📂</div>'
            '<p style="font-size:0.85rem">처리 이력이 여기에 표시돼요</p></div>',
            unsafe_allow_html=True,
        )
        return None

    st.markdown(f"**처리 이력** ({len(history)}건)")

    selected = None
    for i, h in enumerate(reversed(history)):
        claim_id = h.get("claim_id", "")
        decision = h.get("decision", "")
        total = h.get("total_payment", 0)
        cfg = get_decision_config(decision)

        hist_html = (
            '<div class="history-item">'
            f'<span class="hist-icon">{cfg["icon"]}</span>'
            '<div class="hist-body">'
            f'<div class="hist-id">{claim_id}</div>'
            f'<div class="hist-amount">{cfg["label"]} · {fmt_amount(total)}</div>'
            '</div>'
            '</div>'
        )
        st.markdown(hist_html, unsafe_allow_html=True)

    return selected


# ══════════════════════════════════════════════════════════════
# TASK-UI-06: 개발자 도구 래퍼
# ══════════════════════════════════════════════════════════════

def render_dev_tools(history: list | None = None) -> None:
    """RAG 검색 / API 연동 / 통계를 접이식 '개발자 도구'로 묶음."""
    with st.expander("🔧 개발자 도구", expanded=False):
        dev_tab1, dev_tab2, dev_tab3 = st.tabs(
            ["🔍 약관 조회", "🔌 외부 연동", "📊 심사 현황"]
        )
        with dev_tab1:
            render_rag_search_tab()
        with dev_tab2:
            render_api_tab()
        with dev_tab3:
            render_statistics_tab(history or [])


# ══════════════════════════════════════════════════════════════
# ── 레거시 함수 (하위 호환) ───────────────────────────────────
# ══════════════════════════════════════════════════════════════

# 기존 코드에서 사용하던 상수들 — 기존 import가 깨지지 않도록 유지
_DECISION_STYLES = {
    "지급":     ("✅ 지급",       "decision-pay",    "지급 결정"),
    "부지급":   ("❌ 부지급",     "decision-deny",   "부지급 결정"),
    "보류":     ("⏸️ 보류",       "decision-hold",   "보류 — 서류 보완 필요"),
    "검토필요": ("⚠️ 검토필요",   "decision-review", "담당자 검토 필요"),
    "일부지급": ("⚡ 일부지급",    "decision-review", "한도 적용 일부 지급"),
}

_COVERAGE_NAMES = {
    "IND-001": ("🏥 입원일당", "#e8f5e9"),
    "SIL-001": ("💊 실손의료비", "#e3f2fd"),
    "SUR-001": ("🔪 수술비", "#fff3e0"),
}

_STATUS_ICONS = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️", "FLAGGED": "⚠️"}


def render_decision_banner(decision: str, total_payment: int, payment_date: str = ""):
    """[레거시] 판정 유형별 색상 배너. → render_decision_dashboard() 사용 권장."""
    icon, css_class, desc = _DECISION_STYLES.get(decision, ("?", "decision-hold", ""))
    st.markdown(
        f"""<div class="decision-banner {css_class}">
            <h2 style="margin:0">{icon}</h2>
            <h3 style="margin:0.3rem 0">총 지급액: {total_payment:,}원</h3>
            <p style="margin:0; font-size:0.9rem">{desc}</p>
            {"<p style='margin:0.2rem 0; font-size:0.85rem'>지급예정일: " + payment_date + "</p>" if payment_date else ""}
        </div>""",
        unsafe_allow_html=True,
    )


def render_breakdown_cards(breakdown: dict):
    """[레거시] 담보별 카드. → render_coverage_breakdown_v2() 사용 권장."""
    if not breakdown:
        st.info("산정된 보장항목이 없어요 (부지급 또는 보류)")
        return

    cols = st.columns(len(breakdown))
    for idx, (rule_id, evidence) in enumerate(breakdown.items()):
        name, color = _COVERAGE_NAMES.get(rule_id, (rule_id, "#f5f5f5"))
        amount = evidence.get("benefit_amount", 0)
        formula = evidence.get("formula", "")
        with cols[idx]:
            st.markdown(
                f"""<div style="background:{color}; border-radius:10px; padding:1rem; text-align:center">
                    <p style="margin:0; font-weight:600">{name}</p>
                    <h3 style="margin:0.3rem 0">{amount:,}원</h3>
                    <p style="margin:0; font-size:0.8rem; color:#555">{formula}</p>
                </div>""",
                unsafe_allow_html=True,
            )


def render_rule_trace(applied_rules: list):
    """[레거시] 규칙 실행 로그. → render_review_conditions() 사용 권장."""
    for rule in applied_rules:
        icon = _STATUS_ICONS.get(rule.status, "❓")
        amount_str = f" — **{rule.value:,.0f}원**" if rule.value else ""
        with st.expander(f"{icon} **{rule.rule_id}**: {rule.status}{amount_str}", expanded=False):
            st.write(rule.reason)
            if rule.evidence:
                st.json(rule.evidence)


# ══════════════════════════════════════════════════════════════
# 다운로드 섹션
# ══════════════════════════════════════════════════════════════

def render_download_section(output_dir: Path):
    """결과 파일 다운로드 버튼."""
    if not output_dir.exists():
        st.warning("결과 파일 폴더를 찾을 수 없어요.")
        return

    files = sorted(output_dir.glob("*"))
    if not files:
        st.info("아직 생성된 결과 파일이 없어요.")
        return

    st.markdown("#### 📥 결과 파일 내려받기")
    cols = st.columns(min(len(files), 4))
    for idx, f in enumerate(files):
        with cols[idx % 4]:
            content = f.read_bytes()
            st.download_button(
                label=f"📄 {f.name}",
                data=content,
                file_name=f.name,
                mime="application/octet-stream",
                key=f"dl_{f.name}",
            )

    # ZIP 전체 다운로드
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
    zip_buffer.seek(0)
    st.download_button(
        label="📦 전체 결과 ZIP 다운로드",
        data=zip_buffer,
        file_name=f"{output_dir.name}_results.zip",
        mime="application/zip",
        key="dl_zip",
    )


# ══════════════════════════════════════════════════════════════
# TASK-H1: 핵심 문제점 상단 알림
# ══════════════════════════════════════════════════════════════

def render_key_issues(decision, validation_result=None) -> None:
    """부지급/일부지급/검토필요/보류 시 핵심 문제점을 최상단에 배치.

    지급 판정일 때는 아무것도 렌더링하지 않는다.

    Args:
        decision:          ClaimDecision 객체.
        validation_result: ValidatorResult dict (optional, Agent 모드).
    """
    dec = getattr(decision, "decision", "")
    if dec == "지급":
        return

    issues: list[str] = []
    severity = "normal"  # normal | high

    # 1) 부지급 사유
    denial = getattr(decision, "denial_reason", None)
    if denial:
        clause = getattr(decision, "policy_clause", "")
        clause_text = f" ({clause})" if clause else ""
        issues.append(f"❌ {denial}{clause_text}")
        if dec == "부지급":
            severity = "high"

    # 2) 미비 서류
    missing = getattr(decision, "missing_docs", [])
    if missing:
        issues.append(f"📄 서류 미비: {', '.join(missing)}")

    # 3) 일부지급 — 지급 불가 담보
    denial_covs = getattr(decision, "denial_coverages", [])
    for dc in denial_covs:
        rule_id = dc.get("rule_id", "")
        reason = dc.get("reason", "")
        name, _, _ = get_coverage_label(rule_id)
        issues.append(f"⚡ {name}: {reason}")

    # 4) 담당자 검토 필요
    if getattr(decision, "reviewer_flag", False):
        reason = getattr(decision, "reviewer_reason", "") or "추가 확인 필요"
        issues.append(f"⚠️ 담당자 검토: {reason}")

    # 5) 사기 조사 플래그
    if getattr(decision, "fraud_investigation_flag", False):
        fraud_reason = getattr(decision, "fraud_investigation_reason", "")
        issues.append(f"🚨 사기조사팀 통보 대상: {fraud_reason}")
        severity = "high"

    # 6) 교차검증 불일치 (Agent 모드)
    if validation_result:
        notes = validation_result.get("notes", [])
        for note in notes:
            if note not in issues:
                issues.append(note)

    if not issues:
        return

    # 타이틀 결정
    cfg = get_decision_config(dec)
    title_map = {
        "부지급": "🚫 보험금을 지급할 수 없어요",
        "일부지급": "⚡ 일부 담보만 지급 가능해요",
        "보류": "⏸️ 심사를 완료할 수 없어요",
        "검토필요": "⚠️ 담당자 확인이 필요해요",
    }
    title = title_map.get(dec, f"{cfg['icon']} 확인이 필요한 사항이 있어요")

    severity_cls = "severity-high" if severity == "high" else ""
    items_html = "".join(f"<li>{iss}</li>" for iss in issues)

    st.markdown(
        f'<div class="key-issues-box {severity_cls} anim-active">'
        f'<div class="key-issues-title">{title}</div>'
        f'<ul class="key-issues-list">{items_html}</ul>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════
# TASK-H2: 신뢰도 대시보드
# ══════════════════════════════════════════════════════════════

def render_confidence_dashboard(decision) -> None:
    """Agent 모드 신뢰도 대시보드 (A-6 강화).

    - 4-게이지 (파싱, 룰, AI, 교차검증)
    - 5단계 risk_level 시각화 (A-5)
    - confidence_factors 세부 요인 표시 (A-6)
    - risk 레벨별 권장 조치 안내 (A-6)

    Args:
        decision: ClaimDecision 객체 (confidence: ConfidenceScore | None).
    """
    conf = getattr(decision, "confidence", None)
    if conf is None:
        return

    overall = getattr(conf, "overall", 0)
    risk = getattr(conf, "risk_level", "UNKNOWN")

    # 게이지 데이터
    gauges = [
        ("서류 파싱", getattr(conf, "parse_confidence", 0)),
        ("룰엔진", getattr(conf, "rule_confidence", 0)),
        ("AI 추론", getattr(conf, "llm_confidence", 0)),
        ("교차검증", getattr(conf, "cross_validation", 0)),
    ]

    # 색상 매핑
    def _bar_color(v: float) -> str:
        if v >= 0.8:
            return "#4CAF50"
        if v >= 0.5:
            return "#FF9800"
        return "#F44336"

    risk_cls = {
        "VERY_LOW": "risk-very-low", "LOW": "risk-low", "MEDIUM": "risk-medium",
        "HIGH": "risk-high", "CRITICAL": "risk-critical",
    }.get(risk, "risk-medium")
    risk_label = {
        "VERY_LOW": "🟢 VERY LOW", "LOW": "🟡 LOW", "MEDIUM": "🟠 MEDIUM",
        "HIGH": "🔴 HIGH", "CRITICAL": "🟣 CRITICAL",
    }.get(risk, f"⚪ {risk}")

    # ── 게이지 HTML ──
    gauges_html = ""
    for label, value in gauges:
        pct = int(value * 100)
        color = _bar_color(value)
        gauges_html += (
            f'<div class="gauge-item">'
            f'<div class="gauge-label">{label}</div>'
            f'<div class="gauge-value">{pct}%</div>'
            f'<div class="gauge-bar-bg">'
            f'<div class="gauge-bar-fill" style="width:{pct}%;background:{color}"></div>'
            f'</div>'
            f'</div>'
        )

    overall_color = _bar_color(overall)

    # ── A-6: confidence_factors 세부 요인 HTML ──
    factors = getattr(conf, "confidence_factors", {})
    factors_html = ""
    if factors:
        _FACTOR_LABELS = {
            "data_completeness": ("📋", "데이터 완비도"),
            "policy_match": ("📑", "약관 부합도"),
            "calculation_certainty": ("🔢", "산정 확실성"),
            "ambiguity_level": ("🔍", "모호성 수준"),
            "edge_case_risk": ("⚡", "예외 위험도"),
        }

        # ── 레이더 차트 SVG 생성 ──
        import math
        radar_svg = ""
        factor_keys = list(_FACTOR_LABELS.keys())
        factor_vals = [float(factors.get(k, 0)) for k in factor_keys]
        factor_names = [_FACTOR_LABELS[k][1] for k in factor_keys]
        n = len(factor_vals)
        if n >= 3:
            cx, cy, r = 120, 120, 90
            angle_offset = -math.pi / 2  # start from top

            def _polar(val, idx):
                angle = angle_offset + (2 * math.pi * idx / n)
                x = cx + r * val * math.cos(angle)
                y = cy + r * val * math.sin(angle)
                return x, y

            # grid rings
            grid_lines = ""
            for ring in [0.25, 0.5, 0.75, 1.0]:
                pts = " ".join(f"{_polar(ring, i)[0]:.1f},{_polar(ring, i)[1]:.1f}" for i in range(n))
                opacity = 0.15 if ring < 1.0 else 0.3
                grid_lines += f'<polygon points="{pts}" fill="none" stroke="#8B95A1" stroke-width="0.5" opacity="{opacity}"/>'

            # axis lines
            for i in range(n):
                x, y = _polar(1.0, i)
                grid_lines += f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#D1D6DB" stroke-width="0.5"/>'

            # data polygon
            data_pts = " ".join(f"{_polar(v, i)[0]:.1f},{_polar(v, i)[1]:.1f}" for i, v in enumerate(factor_vals))
            data_polygon = f'<polygon points="{data_pts}" fill="rgba(27,100,218,0.2)" stroke="#1B64DA" stroke-width="2"/>'

            # data dots + labels
            dots_labels = ""
            for i, (val, name) in enumerate(zip(factor_vals, factor_names)):
                x, y = _polar(val, i)
                dots_labels += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#1B64DA"/>'
                lx, ly = _polar(1.18, i)
                anchor = "middle"
                if lx < cx - 10:
                    anchor = "end"
                elif lx > cx + 10:
                    anchor = "start"
                dots_labels += f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="10" fill="#6B7684">{name}</text>'

            radar_svg = (
                f'<svg viewBox="0 0 240 240" style="width:100%;max-width:240px;margin:0 auto;display:block">'
                f'{grid_lines}{data_polygon}{dots_labels}'
                f'</svg>'
            )

        # ── 바 차트 (기존) ──
        factor_items = ""
        for factor_key, (icon, label) in _FACTOR_LABELS.items():
            val = factors.get(factor_key)
            if val is not None:
                pct = int(float(val) * 100)
                color = _bar_color(float(val))
                factor_items += (
                    f'<div class="factor-item">'
                    f'<div class="factor-icon">{icon}</div>'
                    f'<div class="factor-body">'
                    f'<div class="factor-header">'
                    f'<span class="factor-label">{label}</span>'
                    f'<span class="factor-value" style="color:{color}">{pct}%</span>'
                    f'</div>'
                    f'<div class="factor-bar-bg">'
                    f'<div class="factor-bar-fill" style="width:{pct}%;background:{color}"></div>'
                    f'</div>'
                    f'</div>'
                    f'</div>'
                )
        if factor_items:
            radar_col = f'<div style="flex:0 0 240px">{radar_svg}</div>' if radar_svg else ""
            factors_html = (
                f'<div class="confidence-factors-section">'
                f'<div class="factors-title">🧠 AI 평가 세부 요인</div>'
                f'<div style="display:flex;gap:24px;align-items:flex-start;flex-wrap:wrap">'
                f'{radar_col}'
                f'<div class="factors-grid" style="flex:1;min-width:200px">{factor_items}</div>'
                f'</div>'
                f'</div>'
            )

    # ── A-6: risk action 가이드 ──
    _RISK_ACTIONS = {
        "VERY_LOW": ("✅", "자동 처리 가능", "추가 검토 없이 처리할 수 있습니다.", "action-very-low"),
        "LOW": ("📋", "일반 심사", "표준 심사 절차에 따라 처리하세요.", "action-low"),
        "MEDIUM": ("⚠️", "주의 필요", "불확실한 항목이 있어 확인이 필요합니다.", "action-medium"),
        "HIGH": ("🔴", "담당자 검토 권장", "전문 심사역의 검토가 필요합니다.", "action-high"),
        "CRITICAL": ("🚨", "즉시 확인 필요", "반드시 담당자가 직접 확인해야 합니다.", "action-critical"),
    }
    action_icon, action_title, action_desc, action_cls = _RISK_ACTIONS.get(
        risk, ("⚪", "알 수 없음", "리스크 레벨을 확인하세요.", "action-medium")
    )
    action_html = (
        f'<div class="risk-action-box {action_cls}">'
        f'<div class="risk-action-icon">{action_icon}</div>'
        f'<div class="risk-action-body">'
        f'<div class="risk-action-title">{action_title}</div>'
        f'<div class="risk-action-desc">{action_desc}</div>'
        f'</div>'
        f'</div>'
    )

    glow_cls = "anim-border-glow" if risk in ("HIGH", "CRITICAL") else ""
    st.markdown(
        f'<div class="confidence-dashboard anim-fade-in-up anim-delay-2 {glow_cls}">'
        f'<div class="confidence-header">'
        f'<div>'
        f'<div style="font-size:0.78rem;color:#8B95A1;margin-bottom:2px">AI 신뢰도</div>'
        f'<div class="confidence-overall" style="color:{overall_color}">{int(overall * 100)}%</div>'
        f'</div>'
        f'<div class="risk-badge {risk_cls}">{risk_label}</div>'
        f'</div>'
        f'<div class="confidence-gauges">{gauges_html}</div>'
        f'{factors_html}'
        f'{action_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

    # A-7: 심사 라우팅 정보 표시
    routing = getattr(decision, "review_routing", None)
    if routing:
        _render_review_routing(routing)


def _render_review_routing(routing) -> None:
    """A-7: 심사 라우팅 카드 렌더링.

    Args:
        routing: ReviewRouting 객체.
    """
    action = getattr(routing, "action", "standard_review")
    priority = getattr(routing, "priority", "normal")
    reviewer = getattr(routing, "reviewer_level", "일반심사역")
    checklist = getattr(routing, "checklist", [])
    est_min = getattr(routing, "estimated_minutes", 0)
    reason = getattr(routing, "routing_reason", "")

    # 액션별 아이콘 + 라벨 + CSS 클래스
    _ACTION_INFO = {
        "auto_approve": ("✅", "자동 승인", "routing-auto"),
        "standard_review": ("📋", "일반 심사", "routing-standard"),
        "enhanced_review": ("🔍", "강화 심사", "routing-enhanced"),
        "senior_review": ("👨‍💼", "선임 검토", "routing-senior"),
        "mandatory_hold": ("🚨", "필수 보류", "routing-mandatory"),
    }
    action_icon, action_label, action_cls = _ACTION_INFO.get(
        action, ("📋", action, "routing-standard")
    )

    # 우선순위 배지
    _PRIORITY_INFO = {
        "low": ("▫️", "낮음", "priority-low"),
        "normal": ("▪️", "보통", "priority-normal"),
        "high": ("🔶", "높음", "priority-high"),
        "urgent": ("🔴", "긴급", "priority-urgent"),
        "critical": ("🟣", "최긴급", "priority-critical"),
    }
    pri_icon, pri_label, pri_cls = _PRIORITY_INFO.get(
        priority, ("▪️", priority, "priority-normal")
    )

    # 시간 표시
    time_str = "자동" if est_min == 0 else f"~{est_min}분"

    # 체크리스트 HTML
    checklist_html = ""
    if checklist:
        items = "".join(f'<li class="routing-check-item">{item}</li>' for item in checklist)
        checklist_html = (
            f'<div class="routing-checklist">'
            f'<div class="routing-checklist-title">📝 심사 체크리스트</div>'
            f'<ul class="routing-check-list">{items}</ul>'
            f'</div>'
        )

    st.markdown(
        f'<div class="review-routing-card {action_cls}">'
        f'<div class="routing-header">'
        f'<div class="routing-action">'
        f'<span class="routing-action-icon">{action_icon}</span>'
        f'<span class="routing-action-label">{action_label}</span>'
        f'</div>'
        f'<div class="routing-badges">'
        f'<span class="routing-priority-badge {pri_cls}">{pri_icon} {pri_label}</span>'
        f'<span class="routing-time-badge">⏱️ {time_str}</span>'
        f'</div>'
        f'</div>'
        f'<div class="routing-details">'
        f'<div class="routing-detail-item">'
        f'<span class="routing-detail-label">심사 담당</span>'
        f'<span class="routing-detail-value">{reviewer}</span>'
        f'</div>'
        f'<div class="routing-detail-item">'
        f'<span class="routing-detail-label">라우팅 사유</span>'
        f'<span class="routing-detail-value">{reason}</span>'
        f'</div>'
        f'</div>'
        f'{checklist_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════
# TASK-H3: Agent 프로세싱 스테퍼
# ══════════════════════════════════════════════════════════════

_AGENT_STEP_LABELS = [
    ("📄", "서류 파싱"),
    ("📋", "컨텍스트"),
    ("📑", "계약 조회"),
    ("📚", "약관 검색"),
    ("🤖", "AI 추론"),
    ("✅", "교차검증"),
    ("📊", "판정 확정"),
    ("📝", "결과 생성"),
]


def render_agent_stepper(current_node: str = "", completed_nodes: list | None = None,
                         error_nodes: list | None = None) -> None:
    """Agent 모드 8-노드 스트리밍 스테퍼.

    LangGraph 그래프의 각 노드 진행 상태를 표시.

    Args:
        current_node:    현재 실행 중인 노드 이름.
        completed_nodes: 완료된 노드 이름 목록.
        error_nodes:     오류 발생 노드 이름 목록.
    """
    completed = set(completed_nodes or [])
    errors = set(error_nodes or [])

    node_names = [
        "parse_docs", "build_context", "lookup_contract", "search_policy",
        "llm_reason", "rule_validate", "finalize", "write_results",
    ]

    steps_html = ""
    for (icon, label), node_name in zip(_AGENT_STEP_LABELS, node_names):
        if node_name in errors:
            cls = "step-error"
            display_icon = "✗"
        elif node_name in completed:
            cls = "step-done"
            display_icon = "✓"
        elif node_name == current_node:
            cls = "step-active"
            display_icon = icon
        else:
            cls = ""
            display_icon = icon

        steps_html += (
            f'<div class="agent-step {cls}">'
            f'{display_icon} {label}'
            f'</div>'
        )

    st.markdown(
        f'<div class="agent-stepper">{steps_html}</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════
# RAG 약관 검색 탭  (TASK-20)
# ══════════════════════════════════════════════════════════════

def render_rag_search_tab() -> None:
    """약관·기준 문서 벡터 검색 탭."""
    st.markdown("### 🔍 약관 조회")
    st.caption("보험 약관과 심사 기준을 자연어로 검색해요.")

    query = st.text_input(
        "검색어",
        placeholder="예: 입원일당 면책기간 90일",
        key="rag_query_input",
    )

    col1, col2 = st.columns(2)
    with col1:
        top_k = st.number_input("검색 결과 수", min_value=1, max_value=20, value=5, key="rag_top_k")
    with col2:
        min_score = st.slider("최소 유사도", 0.0, 1.0, 0.3, 0.05, key="rag_min_score")

    if st.button("🔍 검색", key="rag_search_btn", type="primary"):
        if not query.strip():
            st.warning("검색어를 입력해 주세요.")
            return
        with st.spinner("검색 중..."):
            try:
                from src.rag.retriever import retrieve_raw
                results = retrieve_raw(query.strip(), top_k=int(top_k), min_score=float(min_score))
                if not results:
                    st.info("관련 내용을 찾지 못했어요. 다른 검색어로 시도하거나 유사도 기준을 낮춰 보세요.")
                else:
                    st.success(f"**{len(results)}건**을 찾았어요.")
                    for i, chunk in enumerate(results, 1):
                        source = chunk.metadata.get("source", chunk.id)
                        doc_type = chunk.metadata.get("doc_type", "")
                        label = f"#{i}  유사도 {chunk.score:.3f}  |  {source}"
                        if doc_type:
                            label += f"  [{doc_type}]"
                        with st.expander(label, expanded=(i == 1)):
                            st.write(chunk.text)
                            if chunk.metadata:
                                with st.expander("메타데이터", expanded=False):
                                    st.json(chunk.metadata)
            except Exception as exc:
                st.error(f"검색 오류: {exc}")


# ══════════════════════════════════════════════════════════════
# FastAPI 연동 탭  (TASK-21)
# ══════════════════════════════════════════════════════════════

def render_api_tab() -> None:
    """FastAPI 서버 연동 탭."""
    st.markdown("### 🔌 외부 연동")

    try:
        from config.settings import API_HOST, API_PORT
        _host = "localhost" if API_HOST in ("0.0.0.0", "") else API_HOST
        base_url = f"http://{_host}:{API_PORT}"
    except Exception:
        base_url = "http://localhost:8000"

    st.info(f"API 서버 주소: `{base_url}`  |  API 서버를 먼저 실행해 주세요: `uvicorn src.api.app:app --port 8000`")

    # ── 서버 상태 ─────────────────────────────────────────────
    st.markdown("#### 🏥 서버 상태 확인")
    if st.button("🔍 상태 확인하기", key="api_health_btn"):
        try:
            import requests as _req
            resp = _req.get(f"{base_url}/health", timeout=5)
            if resp.ok:
                st.success(f"✅ API 서버가 정상 응답하고 있어요 (HTTP {resp.status_code})")
                st.json(resp.json())
            else:
                st.error(f"❌ HTTP {resp.status_code}")
        except Exception as exc:
            st.error(f"연결 실패: {exc}")

    st.markdown("---")

    # ── 룰 목록 ──────────────────────────────────────────────
    st.markdown("#### 📋 룰 목록 조회")
    if st.button("GET /rules/list", key="api_rules_btn"):
        try:
            import requests as _req
            resp = _req.get(f"{base_url}/rules/list", timeout=5)
            if resp.ok:
                st.json(resp.json())
            else:
                st.error(f"오류: HTTP {resp.status_code}")
        except Exception as exc:
            st.error(f"연결 실패: {exc}")

    st.markdown("---")

    # ── RAG 검색 (API 경유) ───────────────────────────────────
    st.markdown("#### 🔍 RAG 검색 (API 경유)")
    api_rag_query = st.text_input(
        "검색어 (API 경유)",
        placeholder="예: 비급여 한도",
        key="api_rag_query",
    )
    api_top_k = st.number_input("결과 수", min_value=1, max_value=20, value=5, key="api_rag_top_k")
    if st.button("POST /rag/search", key="api_rag_btn"):
        if not api_rag_query.strip():
            st.warning("검색어를 입력해 주세요.")
        else:
            try:
                import requests as _req
                payload = {"query": api_rag_query.strip(), "top_k": int(api_top_k)}
                resp = _req.post(f"{base_url}/rag/search", json=payload, timeout=10)
                if resp.ok:
                    st.json(resp.json())
                else:
                    st.error(f"오류: HTTP {resp.status_code} — {resp.text[:200]}")
            except Exception as exc:
                st.error(f"연결 실패: {exc}")

    st.markdown("---")

    # ── RAG 통계 ──────────────────────────────────────────────
    st.markdown("#### 📊 RAG 인덱스 통계")
    if st.button("GET /rag/stats", key="api_rag_stats_btn"):
        try:
            import requests as _req
            resp = _req.get(f"{base_url}/rag/stats", timeout=5)
            if resp.ok:
                st.json(resp.json())
            else:
                st.error(f"오류: HTTP {resp.status_code}")
        except Exception as exc:
            st.error(f"연결 실패: {exc}")


# ══════════════════════════════════════════════════════════════
# 처리 통계 대시보드  (TASK-22)
# ══════════════════════════════════════════════════════════════

def render_statistics_tab(history: list) -> None:
    """처리 이력 집계·시각화 대시보드."""
    st.markdown("### 📊 심사 현황")

    if not history:
        st.info("아직 심사한 건이 없어요. 시나리오를 선택하거나 서류를 올려 심사를 시작해 보세요.")
        return

    # ── 집계 ─────────────────────────────────────────────────
    total = len(history)
    decision_counts: dict[str, int] = {}
    total_paid = 0
    paid_list: list[int] = []
    for h in history:
        d = h.get("decision", "기타")
        decision_counts[d] = decision_counts.get(d, 0) + 1
        amt = h.get("total_payment", 0)
        total_paid += amt
        if d in ("지급", "검토필요", "일부지급"):
            paid_list.append(amt)

    pay_count = decision_counts.get("지급", 0) + decision_counts.get("검토필요", 0) + decision_counts.get("일부지급", 0)
    deny_count = decision_counts.get("부지급", 0)
    hold_count = decision_counts.get("보류", 0)
    avg_payment = int(total_paid / pay_count) if pay_count else 0

    # ── 요약 메트릭 ──────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("총 처리 건수", f"{total}건")
    c2.metric("지급 건수", f"{pay_count}건")
    c3.metric("부지급/보류", f"{deny_count + hold_count}건")
    c4.metric("총 지급액", f"{total_paid:,}원")

    st.markdown("---")

    # ── 차트 영역 ─────────────────────────────────────────────
    try:
        import pandas as pd

        col_left, col_right = st.columns(2)

        with col_left:
            st.markdown("#### 📈 판정 분포")
            df_dist = pd.DataFrame(
                list(decision_counts.items()),
                columns=["판정", "건수"],
            ).sort_values("건수", ascending=False)
            st.bar_chart(df_dist.set_index("판정"), use_container_width=True)

        with col_right:
            st.markdown("#### 💰 지급률 & 평균 지급액")
            pay_rate = (pay_count / total * 100) if total else 0
            st.metric("지급률", f"{pay_rate:.1f}%")
            st.metric("평균 지급액 (지급 건)", f"{avg_payment:,}원")
            if paid_list:
                st.metric("최대 지급액", f"{max(paid_list):,}원")
                st.metric("최소 지급액", f"{min(paid_list):,}원")

        st.markdown("---")
        st.markdown("#### 📋 최근 처리 이력 (최대 20건)")
        rows = [
            {
                "청구번호": h["claim_id"],
                "판정": h["decision"],
                "지급액": f'{h["total_payment"]:,}원',
            }
            for h in reversed(history[-20:])
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    except ImportError:
        st.warning("pandas가 설치되지 않아 상세 차트를 표시할 수 없어요.")
        st.markdown("#### 판정 분포")
        for d, cnt in sorted(decision_counts.items(), key=lambda x: -x[1]):
            icons = {"지급": "✅", "부지급": "❌", "보류": "⏸️", "검토필요": "⚠️", "일부지급": "⚡"}
            icon = icons.get(d, "•")
            st.write(f"{icon} **{d}**: {cnt}건")


# ══════════════════════════════════════════════════════════════
# B-2: 비교 뷰 — 다건 심사 결과 비교 대시보드
# ══════════════════════════════════════════════════════════════

def render_comparison_view() -> None:
    """여러 심사 결과를 나란히 비교하는 대시보드.

    outputs/ 디렉토리에서 처리 완료된 청구건을 선택하여
    판정·금액·담보별 산정·신뢰도·라우팅을 한눈에 비교한다.
    """
    from src.utils.comparison_loader import (
        list_available_claims,
        load_comparison_items,
        compute_comparison_metrics,
        get_coverage_diff,
    )

    # ── 헤더 ─────────────────────────────────────────────────
    st.markdown(
        '<div class="cmp-header anim-fade-in-scale">'
        '<div class="cmp-header-icon">⚖️</div>'
        '<div class="cmp-header-text">'
        '<div class="cmp-header-title">심사 결과 비교 뷰</div>'
        '<div class="cmp-header-desc">처리 완료된 청구건을 선택하여 판정·금액·신뢰도를 나란히 비교합니다</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    # ── 청구건 선택 ──────────────────────────────────────────
    available = list_available_claims()
    if not available:
        st.markdown(
            '<div class="empty-state" style="padding:32px">'
            '<div class="empty-icon">📂</div>'
            '<p>비교할 심사 결과가 없어요.<br>'
            '시나리오를 선택하여 심사를 완료한 뒤 비교해 보세요.</p></div>',
            unsafe_allow_html=True,
        )
        return

    selected = st.multiselect(
        "비교할 청구건 선택 (2~4건 권장)",
        options=available,
        default=available[:2] if len(available) >= 2 else available[:1],
        key="cmp_claim_selector",
        help="outputs/ 에 decision.json이 있는 청구건만 표시됩니다.",
    )

    if len(selected) < 2:
        st.info("📌 비교하려면 2건 이상을 선택해 주세요.")
        return

    # ── 데이터 로드 ──────────────────────────────────────────
    items = load_comparison_items(selected)
    if len(items) < 2:
        st.warning("선택한 건 중 일부를 로드하지 못했어요. 다른 건을 선택해 주세요.")
        return

    metrics = compute_comparison_metrics(items)

    # ── 1) 집계 요약 카드 ────────────────────────────────────
    _render_cmp_summary_cards(items, metrics)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 2) 판정 비교 그리드 ──────────────────────────────────
    _render_cmp_decision_grid(items)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 3) 담보별 금액 비교 테이블 ───────────────────────────
    cov_diff = get_coverage_diff(items)
    if cov_diff:
        _render_cmp_coverage_table(items, cov_diff)
        st.markdown("<br>", unsafe_allow_html=True)

    # ── 4) 신뢰도 비교 (있으면) ──────────────────────────────
    if metrics.get("has_confidence"):
        _render_cmp_confidence(items)
        st.markdown("<br>", unsafe_allow_html=True)

    # ── 5) 룰 실행 결과 비교 ─────────────────────────────────
    _render_cmp_rules(items)


# ── 비교 뷰 내부 컴포넌트 ────────────────────────────────────

def _render_cmp_summary_cards(items, metrics: dict) -> None:
    """비교 집계 요약 (상단 메트릭 카드)."""
    dist = metrics.get("decision_distribution", {})
    dist_text = " · ".join(f"{k} {v}건" for k, v in dist.items())
    avg_conf = metrics.get("avg_confidence")
    conf_text = f" · 평균 신뢰도 {avg_conf:.0%}" if avg_conf is not None else ""

    st.markdown(
        f'<div class="cmp-summary-bar">'
        f'<span class="cmp-summary-stat">📊 비교 대상 {metrics["count"]}건</span>'
        f'<span class="cmp-summary-stat">💰 총 합계 {metrics["total_sum"]:,}원</span>'
        f'<span class="cmp-summary-stat">📈 평균 {metrics["avg_payment"]:,}원</span>'
        f'<span class="cmp-summary-detail">{dist_text}{conf_text}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_cmp_decision_grid(items) -> None:
    """판정 + 금액 카드 그리드 — 나란히 배치."""
    st.markdown(
        '<div class="section-title"><h3>🏷️ 판정 비교</h3></div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        with col:
            cfg = get_decision_config(it.decision)
            css_cls = f"rs-{cfg['css_suffix']}" if "css_suffix" in cfg else ""

            # 라우팅 배지
            routing_badge = ""
            if it.review_routing and isinstance(it.review_routing, dict):
                action = it.review_routing.get("action", "")
                priority = it.review_routing.get("priority", "")
                reviewer = it.review_routing.get("reviewer_level", "")
                if action:
                    routing_badge = (
                        f'<div class="cmp-routing-badge">'
                        f'🔀 {reviewer} · {priority}'
                        f'</div>'
                    )

            # 사유 텍스트
            reason = ""
            if it.decision == "부지급" and it.denial_reason:
                reason = it.denial_reason
            elif it.decision == "보류" and it.missing_docs:
                reason = f"부족 서류: {', '.join(it.missing_docs)}"
            elif it.reviewer_reason:
                reason = it.reviewer_reason
            reason_html = f'<div class="cmp-card-reason">{reason}</div>' if reason else ""

            # 사기 플래그
            fraud_html = ""
            if it.fraud_flag:
                fraud_html = (
                    '<div class="cmp-fraud-badge">🚨 사기조사 대상</div>'
                )

            st.markdown(
                f'<div class="cmp-decision-card {css_cls}">'
                f'<div class="cmp-card-header">'
                f'<span class="cmp-card-id">{it.claim_id}</span>'
                f'<span class="cmp-card-badge">{cfg["icon"]} {cfg["label"]}</span>'
                f'</div>'
                f'<div class="cmp-card-amount">{it.total_payment:,}원</div>'
                f'{reason_html}'
                f'{routing_badge}'
                f'{fraud_html}'
                f'</div>',
                unsafe_allow_html=True,
            )


def _render_cmp_coverage_table(items, cov_diff: dict) -> None:
    """담보별 산정 금액 비교 테이블."""
    st.markdown(
        '<div class="section-title"><h3>💰 담보별 산정 비교</h3></div>',
        unsafe_allow_html=True,
    )

    # 테이블 헤더
    header_cells = '<th>담보</th>'
    for it in items:
        header_cells += f'<th>{it.claim_id}</th>'

    # 테이블 바디
    rows_html = ""
    for cov_id, entries in cov_diff.items():
        name, _, _ = get_coverage_label(cov_id)
        cells = f'<td>{name}</td>'
        amounts = []
        for entry in entries:
            amt = entry["amount"]
            if amt is not None:
                cells += f'<td>{amt:,}원</td>'
                amounts.append(amt)
            else:
                cells += '<td class="cmp-na">—</td>'
                amounts.append(0)

        # 차이 강조: 금액이 다르면 행 하이라이트
        row_cls = ""
        if len(set(amounts)) > 1 and any(a > 0 for a in amounts):
            row_cls = ' class="cmp-diff-row"'
        rows_html += f"<tr{row_cls}>{cells}</tr>"

    # 합계 행
    total_cells = '<td>합계</td>'
    for it in items:
        total_cells += f'<td class="cmp-total-amount">{it.total_payment:,}원</td>'
    rows_html += f'<tr class="cmp-total-row">{total_cells}</tr>'

    st.markdown(
        f'<table class="cmp-coverage-table">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>',
        unsafe_allow_html=True,
    )

    # 수식 비교 (접이식)
    with st.expander("📐 산정 수식 비교", expanded=False):
        for cov_id, entries in cov_diff.items():
            name, _, _ = get_coverage_label(cov_id)
            st.markdown(f"**{name}** (`{cov_id}`)")
            for entry in entries:
                icon = "✅" if entry["amount"] else "⬜"
                formula = entry["formula"] or "—"
                st.markdown(
                    f"- {icon} **{entry['claim_id']}**: {formula}"
                )
            st.markdown("")


def _render_cmp_confidence(items) -> None:
    """신뢰도 비교 바 차트."""
    st.markdown(
        '<div class="section-title"><h3>🎯 신뢰도 비교</h3></div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(len(items))
    for col, it in zip(cols, items):
        with col:
            conf = it.confidence
            if not conf or not isinstance(conf, dict):
                st.markdown(
                    f'<div class="cmp-conf-card">'
                    f'<div class="cmp-conf-id">{it.claim_id}</div>'
                    f'<div class="cmp-conf-na">신뢰도 없음</div></div>',
                    unsafe_allow_html=True,
                )
                continue

            overall = conf.get("overall", 0)
            risk = conf.get("risk_level", "UNKNOWN")

            # 위험 등급별 색상
            risk_colors = {
                "VERY_LOW": "#43A047",
                "LOW": "#66BB6A",
                "MEDIUM": "#FFA726",
                "HIGH": "#EF5350",
                "CRITICAL": "#C62828",
            }
            bar_color = risk_colors.get(risk, "#9E9E9E")
            pct = int(overall * 100)

            risk_labels = {
                "VERY_LOW": "매우 낮음",
                "LOW": "낮음",
                "MEDIUM": "보통",
                "HIGH": "높음",
                "CRITICAL": "심각",
            }
            risk_label = risk_labels.get(risk, risk)

            # 세부 점수 바
            sub_bars = ""
            sub_keys = [
                ("parse_confidence", "📄 파싱"),
                ("rule_confidence", "⚖️ 룰"),
                ("llm_confidence", "🤖 LLM"),
                ("cross_validation", "🔀 교차검증"),
            ]
            for key, label in sub_keys:
                val = conf.get(key, 0)
                sub_pct = int(float(val) * 100)
                sub_bars += (
                    f'<div class="cmp-conf-sub">'
                    f'<span class="cmp-conf-sub-label">{label}</span>'
                    f'<div class="cmp-conf-sub-track">'
                    f'<div class="cmp-conf-sub-fill" style="width:{sub_pct}%;background:{bar_color}"></div>'
                    f'</div>'
                    f'<span class="cmp-conf-sub-val">{sub_pct}%</span>'
                    f'</div>'
                )

            st.markdown(
                f'<div class="cmp-conf-card">'
                f'<div class="cmp-conf-id">{it.claim_id}</div>'
                f'<div class="cmp-conf-overall">'
                f'<div class="cmp-conf-gauge-track">'
                f'<div class="cmp-conf-gauge-fill" style="width:{pct}%;background:{bar_color}"></div>'
                f'</div>'
                f'<div class="cmp-conf-score">{pct}%</div>'
                f'</div>'
                f'<div class="cmp-conf-risk" style="color:{bar_color}">위험: {risk_label}</div>'
                f'{sub_bars}'
                f'</div>',
                unsafe_allow_html=True,
            )


def _render_cmp_rules(items) -> None:
    """룰 실행 결과 비교 매트릭스."""
    st.markdown(
        '<div class="section-title"><h3>⚖️ 룰 실행 비교</h3></div>',
        unsafe_allow_html=True,
    )

    # 모든 rule_id 수집 (순서 보존)
    all_rule_ids: list[str] = []
    seen: set[str] = set()
    for it in items:
        for r in it.applied_rules_summary:
            rid = r.get("rule_id", "")
            if rid and rid not in seen:
                all_rule_ids.append(rid)
                seen.add(rid)

    if not all_rule_ids:
        st.info("룰 실행 데이터가 없어요.")
        return

    # 룰별 결과 매핑
    rule_maps: list[dict] = []
    for it in items:
        rm: dict[str, dict] = {}
        for r in it.applied_rules_summary:
            rm[r.get("rule_id", "")] = r
        rule_maps.append(rm)

    # 상태 아이콘
    _icons = {"PASS": "✅", "FAIL": "❌", "FLAGGED": "⚠️", "SKIP": "⬜"}

    header_cells = '<th>룰</th>'
    for it in items:
        header_cells += f'<th>{it.claim_id}</th>'

    rows_html = ""
    for rid in all_rule_ids:
        label = RULE_LABELS.get(rid, rid)
        cells = f'<td class="cmp-rule-name">{label}</td>'
        statuses = []
        for i, it in enumerate(items):
            r = rule_maps[i].get(rid)
            if r:
                status = r.get("status", "")
                icon = _icons.get(status, "?")
                cells += f'<td title="{r.get("reason", "")}">{icon} {status}</td>'
                statuses.append(status)
            else:
                cells += '<td class="cmp-na">—</td>'
                statuses.append(None)

        # 상태가 다르면 강조
        valid_statuses = [s for s in statuses if s is not None]
        row_cls = ""
        if len(set(valid_statuses)) > 1:
            row_cls = ' class="cmp-diff-row"'
        rows_html += f"<tr{row_cls}>{cells}</tr>"

    st.markdown(
        f'<table class="cmp-rules-table">'
        f'<thead><tr>{header_cells}</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════
# AI 추론 패널 (Agent 모드)
# ══════════════════════════════════════════════════════════════

def render_ai_reasoning_panel(decision) -> None:
    """Agent 모드의 llm_reasoning 텍스트를 전용 패널에 표시."""
    reasoning = None
    # llm_reasoning이 evidence 안에 있을 수 있음
    for rule in getattr(decision, "applied_rules", []):
        r = rule.evidence.get("llm_reasoning")
        if r:
            reasoning = r
            break
    # 또는 decision 자체에 있을 수 있음
    if not reasoning:
        reasoning = getattr(decision, "llm_reasoning", None)
    if not reasoning:
        return

    # 텍스트를 HTML로 변환 (줄바꿈 / 마크다운 기본)
    import html as html_mod
    escaped = html_mod.escape(str(reasoning))
    paragraphs = escaped.replace("\n\n", "</p><p>").replace("\n", "<br>")

    st.markdown(
        f'<div class="ai-reasoning-panel anim-fade-in-up anim-delay-3">'
        f'<div class="ai-reasoning-header">'
        f'<span class="ai-reasoning-avatar">🤖</span>'
        f'<span class="ai-reasoning-title">AI 심사관 판단 근거</span>'
        f'</div>'
        f'<div class="ai-reasoning-body"><p>{paragraphs}</p></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════
# SIL-001 워터폴 차트
# ══════════════════════════════════════════════════════════════

def _render_waterfall_chart(evidence: dict) -> None:
    """SIL-001 실손 산정 흐름을 수평 워터폴로 시각화."""
    csp = evidence.get("covered_self_pay", 0)
    ncc = evidence.get("non_covered_capped", 0)
    copay = evidence.get("copay_applied", 0)
    benefit = evidence.get("benefit_amount", 0)

    if not any([csp, ncc, benefit]):
        return

    items = [
        ("급여 본인부담금", csp, "#4285F4", False),
        ("비급여(한도적용)", ncc, "#34A853", False),
        ("자기부담금 공제", -copay if copay else 0, "#EA4335", True),
        ("실손 지급액", benefit, "#1B64DA", False),
    ]

    max_val = max(abs(v) for _, v, _, _ in items) or 1
    bars_html = ""
    for label, val, color, is_negative in items:
        width = min(abs(val) / max_val * 100, 100)
        display_val = f"-{abs(val):,.0f}원" if is_negative and val != 0 else f"{val:,.0f}원"
        bar_style = f"width:{width}%;background:{color}"
        bars_html += (
            f'<div class="wf-row">'
            f'<div class="wf-label">{label}</div>'
            f'<div class="wf-bar-wrap">'
            f'<div class="wf-bar" style="{bar_style}"></div>'
            f'</div>'
            f'<div class="wf-value" style="color:{color}">{display_val}</div>'
            f'</div>'
        )

    st.markdown(
        f'<div class="wf-chart anim-fade-in-up">'
        f'<div class="wf-title">💧 실손의료비 산정 흐름</div>'
        f'{bars_html}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════
# Step 3 처리 중 Shimmer 스켈레톤
# ══════════════════════════════════════════════════════════════

def render_shimmer_preview() -> None:
    """Step 3 처리 중 Step 4 레이아웃의 반짝이는 스켈레톤 미리보기."""
    st.markdown(
        '<div style="margin-top:24px">'
        '<div class="shimmer-placeholder" style="height:120px;margin-bottom:16px;border-radius:16px"></div>'
        '<div style="display:flex;gap:16px;margin-bottom:16px">'
        '<div class="shimmer-placeholder" style="flex:1;height:180px;border-radius:12px"></div>'
        '<div class="shimmer-placeholder" style="flex:1;height:180px;border-radius:12px"></div>'
        '</div>'
        '<div class="shimmer-placeholder" style="height:80px;margin-bottom:8px;border-radius:12px"></div>'
        '<div class="shimmer-placeholder" style="height:80px;border-radius:12px"></div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════
# JS 주입: 동적 애니메이션 (Streamlit 정적 렌더링 극복)
# ══════════════════════════════════════════════════════════════

def inject_dynamic_animations():
    """게이지 바 fill 애니메이션 + 금액 카운트업을 JS로 주입."""
    stc.html("""<script>
    (function() {
        var p = window.parent.document;

        // ── 게이지/프로그레스 바: 0% → 최종값 애니메이션 ──
        ['.gauge-bar-fill', '.factor-bar-fill', '.ocr-conf-bar',
         '.cmp-conf-gauge-fill'].forEach(function(sel) {
            p.querySelectorAll(sel).forEach(function(el) {
                if (el.dataset.animated) return;
                var tw = el.style.width;
                el.style.width = '0%';
                el.style.transition = 'width 0.8s cubic-bezier(0.4,0,0.2,1)';
                requestAnimationFrame(function() {
                    requestAnimationFrame(function() {
                        el.style.width = tw;
                        el.dataset.animated = '1';
                    });
                });
            });
        });

        // ── 금액 카운트업 ──
        var amtEl = p.querySelector('.rs-amount');
        if (amtEl && !amtEl.dataset.counted) {
            amtEl.dataset.counted = '1';
            var m = amtEl.textContent.match(/([\\d,]+)/);
            if (m) {
                var target = parseInt(m[1].replace(/,/g, ''));
                if (target > 0) {
                    var suffix = amtEl.textContent.replace(/[\\d,]+/, '').trim();
                    var dur = 1200, st = performance.now();
                    (function step(now) {
                        var prog = Math.min((now - st) / dur, 1);
                        var ease = 1 - Math.pow(1 - prog, 3);
                        amtEl.textContent = Math.floor(target * ease).toLocaleString() + suffix;
                        if (prog < 1) requestAnimationFrame(step);
                    })(performance.now());
                }
            }
        }

        // ── 타임라인 → 약관 근거 스크롤 링크 ──
        p.querySelectorAll('[data-clause-link]').forEach(function(link) {
            if (link.dataset.linked) return;
            link.dataset.linked = '1';
            link.addEventListener('click', function(e) {
                e.preventDefault();
                var rid = link.getAttribute('data-clause-link');
                var target = p.querySelector('#clause-' + rid);
                if (target) {
                    target.scrollIntoView({behavior: 'smooth', block: 'center'});
                    target.style.outline = '2px solid #1B64DA';
                    target.style.outlineOffset = '4px';
                    setTimeout(function() {
                        target.style.outline = 'none';
                    }, 2000);
                }
            });
        });
    })();
    </script>""", height=0)


def render_step4_reveal(decision) -> None:
    """Step 4 최초 진입 시 풀스크린 결과 공개 오버레이 (2.5초)."""
    if not st.session_state.get("_show_reveal"):
        return
    st.session_state["_show_reveal"] = False

    dec = getattr(decision, "decision", "보류")
    total = getattr(decision, "total_payment", 0)
    cfg = get_decision_config(dec)

    color_map = {
        "지급": ("#4CAF50", "#E8F5E9"),
        "부지급": ("#F44336", "#FFEBEE"),
        "일부지급": ("#FF9800", "#FFF3E0"),
        "보류": ("#9E9E9E", "#F5F5F5"),
        "검토필요": ("#FF9800", "#FFF3E0"),
    }
    accent, bg = color_map.get(dec, ("#9E9E9E", "#F5F5F5"))

    from src.ui.labels import fmt_amount as _fmt
    amt_text = _fmt(total)

    stc.html(f"""
    <style>
    .reveal-overlay {{
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        background: {bg}; display: flex; flex-direction: column;
        align-items: center; justify-content: center; z-index: 999999;
        animation: revealFadeOut 0.5s ease-in 2s forwards;
    }}
    .reveal-icon {{
        font-size: 4rem;
        animation: revealBounceIn 0.8s cubic-bezier(0.68, -0.55, 0.265, 1.55);
    }}
    .reveal-label {{
        font-size: 1.5rem; font-weight: 800; color: {accent};
        margin-top: 12px; opacity: 0;
        animation: revealSlideUp 0.5s ease 0.3s forwards;
    }}
    .reveal-amount {{
        font-size: 2.2rem; font-weight: 900; color: #191F28;
        margin-top: 8px; opacity: 0;
        animation: revealSlideUp 0.5s ease 0.5s forwards;
    }}
    @keyframes revealBounceIn {{
        0% {{ transform: scale(0); opacity: 0; }}
        50% {{ transform: scale(1.2); }}
        100% {{ transform: scale(1); opacity: 1; }}
    }}
    @keyframes revealSlideUp {{
        from {{ transform: translateY(20px); opacity: 0; }}
        to {{ transform: translateY(0); opacity: 1; }}
    }}
    @keyframes revealFadeOut {{
        to {{ opacity: 0; pointer-events: none; }}
    }}
    </style>
    <div class="reveal-overlay">
        <div class="reveal-icon">{cfg["icon"]}</div>
        <div class="reveal-label">{cfg["label"]}</div>
        <div class="reveal-amount">{amt_text}</div>
    </div>
    <script>
    setTimeout(function() {{
        var el = document.querySelector('.reveal-overlay');
        if (el) el.remove();
    }}, 2500);
    </script>
    """, height=0)

