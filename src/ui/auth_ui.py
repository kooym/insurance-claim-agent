"""
인증 UI 컴포넌트 — 로그인, 계정 신청, 관리자 패널.

Toss 디자인 원칙 기반 인증 화면.
"""
from __future__ import annotations

import streamlit as st

from src.auth.manager import AuthManager


def render_login_page(auth: AuthManager) -> dict | None:
    """
    로그인 + 계정 신청 탭 페이지.

    Returns:
        로그인 성공 시 user dict, 실패/미입력 시 None.
    """
    # 중앙 정렬을 위한 컬럼
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(
            """<div class="auth-container">
                <div class="auth-logo">
                    <div class="logo-icon">🏥</div>
                    <div class="logo-title">보험금 심사 Agent</div>
                    <div class="logo-sub">AI 자동 심사 시스템 v3.0</div>
                </div>
            </div>""",
            unsafe_allow_html=True,
        )

        tab_login, tab_register = st.tabs(["로그인", "계정 신청"])

        # ── 로그인 탭 ────────────────────────────────────────
        with tab_login:
            with st.form("login_form", clear_on_submit=False):
                username = st.text_input(
                    "아이디", placeholder="아이디를 입력하세요", key="login_username"
                )
                password = st.text_input(
                    "비밀번호", type="password", placeholder="비밀번호를 입력하세요",
                    key="login_password",
                )
                submitted = st.form_submit_button(
                    "로그인", type="primary", use_container_width=True
                )

            if submitted and username and password:
                user, error = auth.authenticate(username, password)
                if user:
                    return user
                if error == "pending":
                    st.warning("계정 승인 대기 중입니다. 관리자 승인 후 로그인할 수 있습니다.")
                elif error == "rejected":
                    st.error("계정 요청이 거절되었습니다. 관리자에게 문의하세요.")
                else:
                    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

        # ── 계정 신청 탭 ─────────────────────────────────────
        with tab_register:
            with st.form("register_form", clear_on_submit=True):
                reg_username = st.text_input(
                    "아이디 (ID)", placeholder="3자 이상", key="reg_username"
                )
                reg_password = st.text_input(
                    "비밀번호", type="password", placeholder="6자 이상",
                    key="reg_password",
                )
                reg_password2 = st.text_input(
                    "비밀번호 확인", type="password", placeholder="비밀번호 재입력",
                    key="reg_password2",
                )
                reg_name = st.text_input(
                    "이름 (실명)", placeholder="홍길동", key="reg_name"
                )
                reg_reason = st.text_area(
                    "사유", placeholder="계정이 필요한 사유를 입력해 주세요",
                    key="reg_reason", height=80,
                )
                reg_submitted = st.form_submit_button(
                    "계정 신청", type="primary", use_container_width=True
                )

            if reg_submitted:
                if not reg_username or not reg_password or not reg_name or not reg_reason:
                    st.error("모든 항목을 입력해 주세요.")
                elif reg_password != reg_password2:
                    st.error("비밀번호가 일치하지 않습니다.")
                else:
                    ok, msg = auth.register_request(
                        reg_username, reg_password, reg_name, reg_reason
                    )
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

        st.markdown(
            '<div class="auth-footer">KT Innovation Hub</div>',
            unsafe_allow_html=True,
        )

    return None


def render_admin_panel(auth: AuthManager) -> None:
    """관리자 전용 패널 — 대기 중인 계정 요청 목록 + 승인/거절."""
    pending = auth.get_pending_requests()

    with st.expander(f"계정 관리 ({len(pending)}건 대기)", expanded=len(pending) > 0):
        if not pending:
            st.info("대기 중인 계정 요청이 없습니다.")
        else:
            for req in pending:
                st.markdown(
                    f"""<div class="admin-user-card">
                        <div class="user-name">{req['name']}
                            <span class="status-badge pending">대기</span>
                        </div>
                        <div class="user-meta">ID: {req['username']} · {req['created_at'][:10]}</div>
                        <div class="user-reason">{req['reason']}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                col_approve, col_reject = st.columns(2)
                with col_approve:
                    if st.button(
                        "승인", key=f"approve_{req['username']}",
                        type="primary", use_container_width=True,
                    ):
                        auth.approve_user(req["username"])
                        st.rerun()
                with col_reject:
                    if st.button(
                        "거절", key=f"reject_{req['username']}",
                        use_container_width=True,
                    ):
                        auth.reject_user(req["username"])
                        st.rerun()

        # 전체 사용자 목록
        all_users = auth.get_all_users()
        if all_users:
            st.markdown("---")
            st.markdown("**전체 사용자**")
            for u in all_users:
                status_cls = u.get("status", "approved")
                status_label = {"approved": "승인", "pending": "대기", "rejected": "거절"}.get(
                    status_cls, status_cls
                )
                st.markdown(
                    f'<span class="status-badge {status_cls}">{status_label}</span> '
                    f'**{u["name"]}** ({u["username"]})',
                    unsafe_allow_html=True,
                )


def render_logout_button() -> bool:
    """로그아웃 버튼 (사이드바용). True if logout clicked."""
    return st.button("로그아웃", key="btn_logout", use_container_width=True)
