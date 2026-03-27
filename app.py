"""
보험금 심사 Agent — Streamlit 4단계 Wizard 웹 애플리케이션.

Toss 디자인 원칙 기반 보험 심사역 전용 UI.
Customer Journey (4-Step Wizard):
  ① 피보험자 선택  — 시나리오 갤러리 / 피보험자 검색·조회 / 신규 등록
  ② 서류 접수      — 파일 업로드 / 테스트 시나리오 자동 로드
  ③ 심사 진행      — 4-step 프로세싱 (서류분석→정보조합→규칙적용→결과생성)
  ④ 결과 확인      — 대시보드 + 약관 근거 + 일부지급 표시 + 다운로드

실행: streamlit run app.py
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DOC_PARSE_MODE", "regex")

import streamlit as st

from config.settings import SAMPLE_DOCS_PATH, OUTPUT_DIR, PROJECT_ROOT as PROJ
from src.agents.orchestrator import process_claim
from src.ocr.doc_parser import parse_claim_documents
from src.ui import inject_css
from src.ui.components import (
    # 홈 화면
    render_hero_upload,
    render_scenario_gallery,
    # 피보험자 조회/등록 (TASK-C2)
    render_patient_lookup,
    render_new_patient_form,
    # 결과 대시보드
    render_insured_profile,
    render_claim_summary,
    render_review_conditions,
    render_coverage_breakdown_v2,
    # 약관 근거 (TASK-C2)
    render_clause_reference,
    # 프로세싱
    render_processing_stepper,
    # Agent UI (TASK-H1~H3)
    render_confidence_dashboard,
    render_agent_stepper,
    # Executive Summary + 심사 플로우 시각화
    render_result_summary,
    render_doc_check_matrix,
    # 2차 심사 (C-5)
    render_secondary_assessment,
    # OCR 정확도 리포트 (C-6)
    render_ocr_quality_report,
    # 사이드바 / 유틸
    render_history_sidebar,
    render_dev_tools,
    render_download_section,
    # 비교 뷰 (B-2)
    render_comparison_view,
    # JS 동적 애니메이션
    inject_dynamic_animations,
    # Step 3→4 결과 공개 리빌
    render_step4_reveal,
    # AI 추론 패널
    render_ai_reasoning_panel,
    # Step 3 shimmer
    render_shimmer_preview,
)
from src.ui.labels import get_decision_config, fmt_amount
from src.auth.manager import AuthManager
from src.ui.auth_ui import render_login_page, render_admin_panel, render_logout_button


# ══════════════════════════════════════════════════════════════
# 페이지 설정
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="보험금 심사 Agent",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()


# ══════════════════════════════════════════════════════════════
# 세션 상태 초기화
# ══════════════════════════════════════════════════════════════
_DEFAULTS = {
    "history": [],
    # Wizard 단계 제어
    "wizard_step": 1,          # 1~4
    # Step 1: 피보험자 선택
    "selected_claim_id": None,
    "selected_policy_no": None,
    "selected_patient": None,
    # Step 2: 서류
    "uploaded_files_cache": None,
    "doc_dir": None,
    "claim_date": None,
    # Step 3→4: 결과
    "current_decision": None,
    "current_ctx": None,
    # Agent 모드 (TASK-E4)
    "agent_mode": False,
    # 2차 심사 결과 (C-5)
    "secondary_result": None,
    # 커스텀 계약 (TASK-C2/C3)
    "custom_contracts": [],
    # 인증
    "authenticated": False,
    "current_user": None,
}
for key, default in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ══════════════════════════════════════════════════════════════
# 인증 게이트 — 미인증 시 로그인 페이지만 표시
# ══════════════════════════════════════════════════════════════
_auth_manager = AuthManager()

if not st.session_state["authenticated"]:
    user = render_login_page(_auth_manager)
    if user:
        st.session_state["authenticated"] = True
        st.session_state["current_user"] = user
        st.rerun()
    st.stop()

# ── 여기부터는 인증된 사용자만 접근 ────────────────────────────


# ── 앱 시작 시 커스텀 계약 복원 ───────────────────────────────
if "custom_loaded" not in st.session_state:
    try:
        from src.utils.data_loader import load_custom_contracts
        load_custom_contracts()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("커스텀 계약 복원 실패: %s", e)
    st.session_state["custom_loaded"] = True

# ── 앱 시작 시 RAG 인덱스 확인 (TASK-E3) ─────────────────────
if "rag_index_checked" not in st.session_state:
    import threading

    def _bg_ensure_index() -> None:
        """RAG 인덱스를 백그라운드에서 확인/빌드한다 (앱 기동 블로킹 방지)."""
        try:
            from src.rag.indexer import ensure_index
            ensure_index()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("RAG 인덱스 빌드 실패: %s", e)

    threading.Thread(target=_bg_ensure_index, daemon=True).start()
    st.session_state["rag_index_checked"] = True


# ── 테스트 케이스 목록 로드 ───────────────────────────────────
TEST_INPUTS_PATH = PROJ / "data" / "test_cases" / "test_inputs.json"
test_inputs_data = json.loads(TEST_INPUTS_PATH.read_text("utf-8"))
TEST_CASES = {t["claim_id"]: t for t in test_inputs_data["test_inputs"]}


# ══════════════════════════════════════════════════════════════
# 유틸: 단계 전환 함수
# ══════════════════════════════════════════════════════════════
def _go_step(step: int):
    """Wizard 단계를 전환."""
    st.session_state.wizard_step = step


def _reset_wizard():
    """Wizard 초기화 — 새 심사 시작."""
    st.session_state.wizard_step = 1
    st.session_state.selected_claim_id = None
    st.session_state.selected_policy_no = None
    st.session_state.selected_patient = None
    st.session_state.uploaded_files_cache = None
    st.session_state.doc_dir = None
    st.session_state.claim_date = None
    st.session_state.current_decision = None
    st.session_state.current_ctx = None
    st.session_state.secondary_result = None


# ══════════════════════════════════════════════════════════════
# 사이드바
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        """<div class="sidebar-logo">
            <div class="logo-icon">🏥</div>
            <div class="logo-title">보험금 심사 Agent</div>
            <div class="logo-sub">AI 자동 심사 시스템 v3.0</div>
        </div>""",
        unsafe_allow_html=True,
    )

    # ── 사용자 정보 ──────────────────────────────────────────
    _cur_user = st.session_state.get("current_user") or {}
    st.markdown(
        f'<div style="padding:4px 0 8px;font-size:0.82rem;color:#8B95A1">'
        f'👤 <strong>{_cur_user.get("name", "")}</strong>'
        f' ({_cur_user.get("username", "")})</div>',
        unsafe_allow_html=True,
    )

    # Wizard 단계 표시
    step_labels = ["① 피보험자", "② 서류", "③ 심사", "④ 결과"]
    current = st.session_state.wizard_step
    steps_html = ""
    for i, label in enumerate(step_labels, 1):
        if i < current:
            steps_html += f'<div style="color:#00C471;font-size:0.85rem">✅ {label}</div>'
        elif i == current:
            steps_html += f'<div style="color:#3182F6;font-weight:700;font-size:0.85rem">▶ {label}</div>'
        else:
            steps_html += f'<div style="color:#8B95A1;font-size:0.85rem">○ {label}</div>'
    st.markdown(
        f'<div style="padding:12px 0;border-bottom:1px solid #E5E8EB;margin-bottom:12px">{steps_html}</div>',
        unsafe_allow_html=True,
    )

    # ── Agent 모드 토글 (TASK-E4 + H4 + T2 통합) ────────────
    from src.llm.client import (
        is_available as _llm_available,
        get_client as _get_llm_client,
        get_client_error as _get_llm_error,
    )
    from src.llm.usage_tracker import get_today_usage
    import logging as _logging

    _toggle_logger = _logging.getLogger("agent_toggle")

    # 수동 재시도: 사이드바에서 '재연결' 누르면 클라이언트 싱글턴 완전 리셋
    if st.session_state.get("_retry_llm_connect"):
        from src.llm.client import reset_client as _reset_llm
        _reset_llm()
        st.session_state["_retry_llm_connect"] = False

    _api_ready = _llm_available()
    _usage = get_today_usage()
    _limit_reached = _usage["remaining"] <= 0

    # 🔍 디버그: 토글 상태 로깅 (Streamlit 콘솔에서 확인 가능)
    _toggle_logger.info(
        "Toggle: api_ready=%s, client=%s, usage=%s/%s, unlimited=%s, error=%s",
        _api_ready,
        type(_get_llm_client()).__name__ if _api_ready else "None",
        _usage.get("count", "?"), _usage.get("limit", "?"),
        _usage.get("unlimited", False),
        _get_llm_error(),
    )

    # ── 한도 초과 시 세션 상태를 먼저 False 로 강제 ──
    if _limit_reached:
        st.session_state["agent_mode"] = False

    if _api_ready:
        # on_change 콜백: 위젯 key → agent_mode 동기화
        def _sync_toggle():
            st.session_state["agent_mode"] = st.session_state["_agent_toggle_widget"]

        # ── 위젯 key 초기값을 agent_mode 와 동기화 ──
        if "_agent_toggle_widget" not in st.session_state:
            st.session_state["_agent_toggle_widget"] = st.session_state.get("agent_mode", False)

        # 한도 초과 시 위젯도 OFF 으로 맞춤
        if _limit_reached:
            st.session_state["_agent_toggle_widget"] = False

        st.toggle(
            "🤖 AI Agent 모드",
            key="_agent_toggle_widget",
            disabled=_limit_reached,
            on_change=_sync_toggle,
            help=(
                "⚡ 일일 한도 도달 — 내일 자동 리셋돼요"
                if _limit_reached
                else "ON: LLM 심사 추론 + 룰엔진 교차검증\nOFF: 룰 기반 심사 (기본)"
            ),
        )

        # 상태 배지 표시
        _is_unlimited = _usage.get("unlimited", False)
        if st.session_state["agent_mode"]:
            used = _usage["count"]
            limit = _usage["limit"]
            badge_text = f"🤖 Agent {used}건 (∞ 무제한)" if _is_unlimited else f"🤖 Agent {used}/{limit}"
            st.markdown(
                f'<div class="mode-badge mode-badge-agent" style="margin-bottom:8px">'
                f'{badge_text}</div>',
                unsafe_allow_html=True,
            )
        elif _limit_reached:
            st.markdown(
                '<div class="mode-badge mode-badge-rule" style="margin-bottom:8px">'
                '⚡ 한도 도달 — 룰 모드</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="mode-badge mode-badge-rule" style="margin-bottom:8px">'
                '🔧 룰 기반</div>',
                unsafe_allow_html=True,
            )
    else:
        # ── API 미연결: 실제 에러 원인 표시 + 재시도 버튼 ──
        st.session_state["agent_mode"] = False
        _err_reason = _get_llm_error() or "API 키/엔드포인트 미설정"
        st.toggle(
            "🤖 AI Agent 모드",
            value=False,
            disabled=True,
            help=f"⚠️ {_err_reason}",
        )
        st.markdown(
            f'<div class="mode-badge mode-badge-rule" style="margin-bottom:8px">'
            f'🔧 룰 기반 — {_err_reason}</div>',
            unsafe_allow_html=True,
        )
        if st.button("🔄 API 재연결 시도", key="_btn_retry_llm", use_container_width=True):
            st.session_state["_retry_llm_connect"] = True
            st.rerun()

    render_history_sidebar(st.session_state.history)

    st.markdown("---")
    if st.button("🏠 새 심사 시작", use_container_width=True):
        _reset_wizard()
        st.rerun()

    # ── 관리자 패널 (admin 전용) ──────────────────────────────
    if st.session_state.get("current_user", {}).get("role") == "admin":
        st.markdown("---")
        render_admin_panel(_auth_manager)

    # ── 로그아웃 ──────────────────────────────────────────────
    st.markdown("---")
    if render_logout_button():
        st.session_state["authenticated"] = False
        st.session_state["current_user"] = None
        st.rerun()


# ══════════════════════════════════════════════════════════════
# 메인 영역 — Wizard 단계 분기
# ══════════════════════════════════════════════════════════════
step = st.session_state.wizard_step


# ──────────────────────────────────────────────────────────────
# STEP 1: 피보험자 선택
# ──────────────────────────────────────────────────────────────
if step == 1:
    st.markdown(
        '<div class="section-title"><h3>① 피보험자를 선택해 주세요</h3></div>',
        unsafe_allow_html=True,
    )

    tab_scenario, tab_search, tab_new = st.tabs([
        "🧪 테스트 시나리오",
        "🔎 피보험자 검색",
        "📝 신규 등록",
    ])

    # ── 탭 1: 시나리오 갤러리 ─────────────────────────────────
    with tab_scenario:
        selected_scenario = render_scenario_gallery()
        if selected_scenario:
            case = TEST_CASES.get(selected_scenario, {})
            st.session_state.selected_claim_id = selected_scenario
            st.session_state.selected_policy_no = case.get("policy_no", "")
            st.session_state.claim_date = case.get("claim_date", "")
            st.session_state.doc_dir = str(SAMPLE_DOCS_PATH / selected_scenario)
            _go_step(3)  # 시나리오는 서류가 이미 있으므로 Step 3으로 직행
            st.rerun()

    # ── 탭 2: 피보험자 검색 ───────────────────────────────────
    with tab_search:
        selected_profile = render_patient_lookup()
        if selected_profile:
            st.session_state.selected_patient = selected_profile
            st.session_state.selected_policy_no = selected_profile.get("policy_no", "")
            _go_step(2)  # 서류 접수 단계로
            st.rerun()

    # ── 탭 3: 신규 등록 ──────────────────────────────────────
    with tab_new:
        new_profile = render_new_patient_form()
        if new_profile:
            st.session_state.selected_patient = new_profile
            st.session_state.selected_policy_no = new_profile.get("policy_no", "")
            _go_step(2)  # 서류 접수 단계로
            st.rerun()

    # 개발자 도구
    st.markdown("<br>", unsafe_allow_html=True)
    render_dev_tools(st.session_state.history)


# ──────────────────────────────────────────────────────────────
# STEP 2: 서류 접수
# ──────────────────────────────────────────────────────────────
elif step == 2:
    st.markdown(
        '<div class="section-title"><h3>② 청구 서류를 접수해 주세요</h3></div>',
        unsafe_allow_html=True,
    )

    # 선택된 피보험자 요약
    patient = st.session_state.get("selected_patient")
    if patient:
        avatar = "👨‍💼" if patient.get("gender") == "M" else "👩‍💼"
        st.markdown(
            f'<div class="alert-banner alert-banner-info">'
            f'{avatar} <strong>{patient.get("name", "")}</strong> '
            f'({patient.get("policy_no", "")}) 님의 서류를 접수해 주세요.'
            f'</div>',
            unsafe_allow_html=True,
        )

    # 청구 정보 입력
    col_id, col_date = st.columns(2)
    with col_id:
        claim_id = st.text_input(
            "청구번호",
            value=st.session_state.get("selected_claim_id") or "CLM-UPLOAD-001",
            key="step2_claim_id",
        )
    with col_date:
        claim_date = st.text_input(
            "청구일자 (YYYY-MM-DD)",
            value=st.session_state.get("claim_date") or "2024-11-20",
            key="step2_claim_date",
        )

    # 파일 업로드
    uploaded = render_hero_upload()

    col_back, _, col_next = st.columns([1, 2, 1])
    with col_back:
        if st.button("⬅️ 이전 단계", use_container_width=True):
            _go_step(1)
            st.rerun()
    with col_next:
        if st.button("🚀 심사 시작하기", type="primary", use_container_width=True, key="step2_run"):
            if not uploaded:
                st.error("청구 서류를 올려주세요.")
                st.stop()

            # 업로드 파일 저장
            upload_dir = PROJ / "data" / "uploads" / claim_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            for uf in uploaded:
                # 파일명 sanitize — 경로 순회 방지
                safe_name = Path(uf.name).name
                (upload_dir / safe_name).write_bytes(uf.getvalue())

            st.session_state.selected_claim_id = claim_id
            st.session_state.claim_date = claim_date
            st.session_state.doc_dir = str(upload_dir)
            st.session_state.uploaded_files_cache = uploaded
            _go_step(3)
            st.rerun()


# ──────────────────────────────────────────────────────────────
# STEP 3: 심사 진행 (4-step 프로세싱)
# ──────────────────────────────────────────────────────────────
elif step == 3:
    claim_id = st.session_state.selected_claim_id
    policy_no = st.session_state.selected_policy_no
    claim_date = st.session_state.claim_date or "2024-11-20"
    doc_dir = Path(st.session_state.doc_dir) if st.session_state.doc_dir else None

    if not claim_id or not doc_dir:
        st.error("심사할 정보가 없어요. 처음부터 다시 시작해 주세요.")
        if st.button("🏠 처음으로"):
            _reset_wizard()
            st.rerun()
        st.stop()

    if not doc_dir.exists():
        st.error(f"서류 폴더를 찾을 수 없어요: {doc_dir}")
        if st.button("🏠 처음으로"):
            _reset_wizard()
            st.rerun()
        st.stop()

    _is_agent_mode = st.session_state.get("agent_mode", False)

    st.markdown(
        '<div class="section-title"><h3>③ 심사를 진행하고 있어요</h3></div>',
        unsafe_allow_html=True,
    )

    # Agent 모드 표시
    if _is_agent_mode:
        st.markdown(
            '<div class="mode-badge mode-badge-agent" style="margin-bottom:12px">'
            '🤖 AI Agent 모드로 심사 중</div>',
            unsafe_allow_html=True,
        )

    # 진행 스테퍼 placeholder
    stepper_placeholder = st.empty()
    # Agent 모드: 8-노드 스테퍼 placeholder
    agent_stepper_ph = st.empty() if _is_agent_mode else None

    # ── Agent 모드 분기 ──────────────────────────────────────
    if _is_agent_mode:
        # Agent 모드: LangGraph claim_graph 로 전체 처리
        with agent_stepper_ph.container():
            render_agent_stepper(current_node="parse_docs", completed_nodes=[])

        completed_nodes: list[str] = []

        def _agent_progress(info: dict):
            """Agent 그래프 진행 콜백."""
            node = info.get("step", "")
            if node and node not in completed_nodes:
                completed_nodes.append(node)
            if agent_stepper_ph:
                with agent_stepper_ph.container():
                    render_agent_stepper(
                        current_node=node,
                        completed_nodes=completed_nodes[:-1] if completed_nodes else [],
                    )

        with st.status("🤖 AI Agent 심사 진행 중...", expanded=True) as sa:
            try:
                from src.agents.claim_graph import run_agent_claim
                decision = run_agent_claim(
                    claim_id=claim_id,
                    policy_no=policy_no,
                    claim_date=claim_date,
                    doc_dir=str(doc_dir),
                    on_progress=_agent_progress,
                )
                # context 도 가져오기
                from src.agents.orchestrator import build_claim_context
                documents = parse_claim_documents(doc_dir)
                ctx = build_claim_context(claim_id, policy_no, claim_date, documents)

                cfg = get_decision_config(decision.decision)
                sa.update(
                    label=f"🤖 AI 심사 완료 — {cfg['icon']} {cfg['label']} ({fmt_amount(decision.total_payment)})",
                    state="complete",
                )
            except Exception as exc:
                st.warning(f"⚠️ Agent 모드 실패, 룰 기반으로 전환: {exc}")
                # 폴백: 기존 룰 기반 처리
                documents = parse_claim_documents(doc_dir)
                from src.agents.orchestrator import build_claim_context
                ctx = build_claim_context(claim_id, policy_no, claim_date, documents)
                from src.rules.rule_engine import run_rules
                decision = run_rules(ctx)
                from src.agents.result_writer import write_results
                write_results(decision, ctx)
                sa.update(label="⚖️ 룰 기반 심사 완료 (폴백)", state="complete")

        # Agent 스테퍼 최종 상태
        if agent_stepper_ph:
            with agent_stepper_ph.container():
                render_agent_stepper(
                    current_node="",
                    completed_nodes=[
                        "parse_docs", "build_context", "lookup_contract",
                        "search_policy", "llm_reason", "rule_validate",
                        "finalize", "write_results",
                    ],
                )

    # ── 룰 기반 모드 ─────────────────────────────────────────
    else:
        # STEP 3-1: 서류 분석
        stepper_placeholder.empty()
        with stepper_placeholder.container():
            render_processing_stepper(0, "서류에서 정보를 추출하고 있어요")
            render_shimmer_preview()
        with st.status("📄 서류를 분석하고 있어요...", expanded=True) as s1:
            documents = parse_claim_documents(doc_dir)
            for doc in documents:
                conf_pct = f"{doc.confidence:.0%}"
                icon = "✅" if doc.confidence >= 0.8 else "⚠️"
                st.write(f"{icon} **{doc.doc_type}** — 신뢰도 {conf_pct}")
            s1.update(label=f"📄 서류 분석 완료 ({len(documents)}건)", state="complete")

        # STEP 3-2: 정보 조합
        stepper_placeholder.empty()
        with stepper_placeholder.container():
            render_processing_stepper(1, "여러 서류의 정보를 하나로 합치고 있어요")
        with st.status("🔗 청구 정보를 조합하고 있어요...", expanded=True) as s2:
            from src.agents.orchestrator import build_claim_context
            ctx = build_claim_context(claim_id, policy_no, claim_date, documents)

            from src.ui.labels import format_kcd
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("진단", format_kcd(ctx.kcd_code))
            c2.metric("입원일수", f"{ctx.hospital_days or 0}일")
            c3.metric("급여 본인부담", fmt_amount(ctx.covered_self_pay))
            c4.metric("비급여", fmt_amount(ctx.non_covered_amount))

            if ctx.chronic_onset_flag:
                st.warning("⚠️ 만성질환 발병일을 확인할 수 없어 입원일 기준으로 판단해요")

            s2.update(label="🔗 청구 정보 조합 완료", state="complete")

        # STEP 3-3: 심사 규칙 적용
        stepper_placeholder.empty()
        with stepper_placeholder.container():
            render_processing_stepper(2, "계약 유효성, 면책기간, 담보별 산정 중이에요")
        with st.status("⚖️ 심사 규칙을 적용하고 있어요...", expanded=True) as s3:
            from src.rules.rule_engine import run_rules
            decision = run_rules(ctx)

            from src.ui.labels import RULE_LABELS, get_status_label
            for rule in decision.applied_rules:
                label = RULE_LABELS.get(rule.rule_id, rule.rule_id)
                _, icon, _ = get_status_label(rule.status)
                amount = f" — **{fmt_amount(rule.value)}**" if rule.value else ""
                st.write(f"{icon} **{label}**: {rule.reason[:80]}{amount}")

            cfg = get_decision_config(decision.decision)
            s3.update(
                label=f"⚖️ 심사 완료 — {cfg['icon']} {cfg['label']} ({fmt_amount(decision.total_payment)})",
                state="complete",
            )

        # STEP 3-4: 결과 생성
        stepper_placeholder.empty()
        with stepper_placeholder.container():
            render_processing_stepper(3, "심사 결과 문서를 생성하고 있어요")
        with st.status("✍️ 결과를 정리하고 있어요...", expanded=True) as s4:
            from src.agents.result_writer import write_results
            write_results(decision, ctx)

            output_path = OUTPUT_DIR / claim_id
            if output_path.exists():
                for f in sorted(output_path.glob("*")):
                    st.write(f"📄 {f.name}")
            s4.update(label="✍️ 결과 생성 완료", state="complete")

        # 스테퍼 최종 완료 표시
        stepper_placeholder.empty()
        with stepper_placeholder.container():
            render_processing_stepper(-1, "")  # 모든 단계 완료

    # ── 완료 → 세션 저장 & Step 4 전환 (공통) ─────────────────
    st.session_state.current_decision = decision
    st.session_state.current_ctx = ctx
    st.session_state.history.append({
        "claim_id": claim_id,
        "decision": decision.decision,
        "total_payment": decision.total_payment,
    })
    st.session_state.uploaded_files_cache = None

    st.success("✅ 심사가 완료되었어요! 결과를 확인해 보세요.")
    st.session_state["_show_reveal"] = True
    _go_step(4)
    st.rerun()


# ──────────────────────────────────────────────────────────────
# STEP 4: 결과 확인 대시보드
# ──────────────────────────────────────────────────────────────
elif step == 4:
    decision = st.session_state.current_decision
    ctx = st.session_state.current_ctx

    if not decision:
        st.warning("심사 결과가 없어요. 처음부터 다시 시작해 주세요.")
        if st.button("🏠 처음으로"):
            _reset_wizard()
            st.rerun()
        st.stop()

    # ── 결과 공개 리빌 애니메이션 (Step 3→4 전환 시 1회) ────
    render_step4_reveal(decision)

    # ── Step 4 탭: 심사 결과 / 비교 뷰 ───────────────────────
    tab_result, tab_compare = st.tabs(["📋 심사 결과", "⚖️ 비교 뷰"])

    with tab_result:

        # ═══════════════════════════════════════════════════════
        # Zone 1: 판정 결과
        # ═══════════════════════════════════════════════════════
        st.markdown(
            '<div class="zone-divider anim-fade-in-up">'
            '<span class="zone-divider-label">판정 결과</span></div>',
            unsafe_allow_html=True,
        )
        render_result_summary(decision, ctx)

        # ═══════════════════════════════════════════════════════
        # Zone 2: 서류 / 계약 확인
        # ═══════════════════════════════════════════════════════
        st.markdown(
            '<div class="zone-divider anim-fade-in-up anim-delay-1">'
            '<span class="zone-divider-label">서류 · 계약 확인</span></div>',
            unsafe_allow_html=True,
        )
        col_profile, col_claim = st.columns(2)
        with col_profile:
            st.markdown(
                '<div class="section-title"><h3>👤 피보험자 정보</h3></div>',
                unsafe_allow_html=True,
            )
            render_insured_profile(ctx)
        with col_claim:
            st.markdown(
                '<div class="section-title"><h3>📋 청구 요약</h3></div>',
                unsafe_allow_html=True,
            )
            render_claim_summary(ctx)

        st.markdown(
            '<div class="section-title"><h3>📋 보종별 서류 확인</h3></div>',
            unsafe_allow_html=True,
        )
        render_doc_check_matrix(decision, ctx)

        if ctx and getattr(ctx, "raw_documents", []):
            with st.expander("🔍 서류 파싱 품질 리포트", expanded=False):
                render_ocr_quality_report(ctx)

        # ═══════════════════════════════════════════════════════
        # Zone 3: 보험금 산정
        # ═══════════════════════════════════════════════════════
        st.markdown(
            '<div class="zone-divider anim-fade-in-up anim-delay-2">'
            '<span class="zone-divider-label">보험금 산정</span></div>',
            unsafe_allow_html=True,
        )
        if decision.breakdown or getattr(decision, "denial_coverages", []):
            st.markdown(
                '<div class="section-title"><h3>💰 보장항목별 산정 금액</h3></div>',
                unsafe_allow_html=True,
            )
            render_coverage_breakdown_v2(decision)

        st.markdown(
            '<div class="section-title"><h3>⚖️ 심사 조건 확인 결과</h3></div>',
            unsafe_allow_html=True,
        )
        render_review_conditions(decision.applied_rules)
        render_clause_reference(decision.applied_rules)

        # ═══════════════════════════════════════════════════════
        # Zone 4: AI 분석 (Agent 모드에서만)
        # ═══════════════════════════════════════════════════════
        render_confidence_dashboard(decision)
        render_ai_reasoning_panel(decision)

        # ═══════════════════════════════════════════════════════
        # Zone 5: 추가 작업
        # ═══════════════════════════════════════════════════════
        render_secondary_assessment(decision, ctx)

        with st.expander("📄 원본 데이터 (decision.json)", expanded=False):
            output_path = OUTPUT_DIR / decision.claim_id
            decision_file = output_path / "decision.json"
            if decision_file.exists():
                st.json(json.loads(decision_file.read_text("utf-8")))
            else:
                st.info("결과 파일이 아직 생성되지 않았어요.")

        with st.expander("📥 결과 파일 내려받기", expanded=False):
            output_path = OUTPUT_DIR / decision.claim_id
            render_download_section(output_path)

        render_dev_tools(st.session_state.history)

    # ── 비교 뷰 탭 (B-2) ─────────────────────────────────────
    with tab_compare:
        render_comparison_view()

    # ── JS 동적 애니메이션 주입 (게이지 fill, 카운트업 등) ───
    inject_dynamic_animations()

    # ── 하단 네비게이션 ───────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    col_reset, _, _ = st.columns([1, 2, 1])
    with col_reset:
        if st.button("🏠 새 심사 시작하기", type="primary", use_container_width=True):
            _reset_wizard()
            st.rerun()
