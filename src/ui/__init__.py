"""
Streamlit UI 디자인 시스템.

Toss 디자인 원칙 기반 CSS 토큰 + 컴포넌트 스타일.
st.markdown()으로 주입하여 보험금 심사 대시보드 스타일을 적용한다.

디자인 토큰:
  - 컬러: --color-primary, --color-success, --color-danger, --color-warning
  - 그레이: --gray-50 ~ --gray-900
  - 간격: --space-xs(4px) ~ --space-xl(32px)
  - 모서리: --radius-sm(8px), --radius-md(12px), --radius-lg(16px)
"""

CUSTOM_CSS = """
<style>
/* ═══════════════════════════════════════════════════════════
   디자인 토큰 (CSS Custom Properties)
   ═══════════════════════════════════════════════════════════ */
:root {
    /* 브랜드 컬러 */
    --color-primary: #1B64DA;
    --color-primary-light: #E8F0FE;
    --color-primary-dark: #1150B0;

    /* 시맨틱 컬러 */
    --color-success: #00C853;
    --color-success-bg: #E8F5E9;
    --color-success-text: #1B5E20;
    --color-danger: #F44336;
    --color-danger-bg: #FFEBEE;
    --color-danger-text: #B71C1C;
    --color-warning: #FF9800;
    --color-warning-bg: #FFF3E0;
    --color-warning-text: #E65100;
    --color-info: #2196F3;
    --color-info-bg: #E3F2FD;

    /* 그레이 스케일 */
    --gray-50:  #F9FAFB;
    --gray-100: #F2F4F6;
    --gray-200: #E5E8EB;
    --gray-300: #D1D6DB;
    --gray-400: #B0B8C1;
    --gray-500: #8B95A1;
    --gray-600: #6B7684;
    --gray-700: #4E5968;
    --gray-800: #333D4B;
    --gray-900: #191F28;

    /* 간격 */
    --space-xs: 4px;
    --space-sm: 8px;
    --space-md: 16px;
    --space-lg: 24px;
    --space-xl: 32px;
    --space-2xl: 48px;

    /* 모서리 */
    --radius-sm: 8px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-full: 999px;

    /* 그림자 */
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.08);
    --shadow-md: 0 2px 8px rgba(0,0,0,0.08);
    --shadow-lg: 0 4px 16px rgba(0,0,0,0.1);

    /* 타이포 */
    --font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Segoe UI", sans-serif;
}


/* ═══════════════════════════════════════════════════════════
   Streamlit 기본 요소 오버라이드
   ═══════════════════════════════════════════════════════════ */

/* 전체 폰트 */
html, body, [class*="css"] {
    font-family: var(--font-family) !important;
}

/* 메인 영역 상단 여백 축소 */
.block-container {
    padding-top: 2rem !important;
    max-width: 1100px !important;
}

/* Streamlit 컬럼 카드 높이: min-height로 통일 (flex 체인 사용 불가) */

/* 사이드바 */
[data-testid="stSidebar"] {
    background: var(--gray-50) !important;
    border-right: 1px solid var(--gray-200) !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
    font-size: 0.9rem;
}

/* 기본 버튼 스타일 개선 */
.stButton > button {
    border-radius: var(--radius-md) !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: var(--shadow-md);
}

/* Primary 버튼 */
.stButton > button[kind="primary"] {
    background: var(--color-primary) !important;
    border: none !important;
    color: white !important;
}

/* st.tabs 언더라인 */
.stTabs [data-baseweb="tab-highlight"] {
    background-color: var(--color-primary) !important;
}
.stTabs [data-baseweb="tab"] {
    font-weight: 600 !important;
    color: var(--gray-600) !important;
}
.stTabs [aria-selected="true"] {
    color: var(--color-primary) !important;
}

/* st.expander */
.streamlit-expanderHeader {
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    color: var(--gray-800) !important;
}

/* 파일 업로더 */
[data-testid="stFileUploader"] {
    border-radius: var(--radius-lg) !important;
}

/* st.metric 큰 숫자 강조 */
[data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    font-weight: 700 !important;
    color: var(--gray-900) !important;
}


/* ═══════════════════════════════════════════════════════════
   히어로 업로드 영역
   ═══════════════════════════════════════════════════════════ */
.hero-section {
    background: white;
    border: 2px dashed var(--gray-300);
    border-radius: var(--radius-lg);
    padding: var(--space-2xl) var(--space-xl);
    text-align: center;
    margin-bottom: var(--space-xl);
    transition: border-color 0.3s ease;
}
.hero-section:hover {
    border-color: var(--color-primary);
}
.hero-section h2 {
    color: var(--gray-900);
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: var(--space-sm);
}
.hero-section p {
    color: var(--gray-500);
    font-size: 0.95rem;
    margin: 0;
}


/* ═══════════════════════════════════════════════════════════
   시나리오 카드
   ═══════════════════════════════════════════════════════════ */
.scenario-card {
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: var(--radius-lg);
    padding: var(--space-lg);
    transition: all 0.2s ease;
    cursor: default;
}
.scenario-card:hover {
    border-color: var(--color-primary);
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
}
.scenario-card .card-header {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    margin-bottom: var(--space-md);
}
.scenario-card .card-avatar {
    font-size: 1.8rem;
    line-height: 1;
}
.scenario-card .card-name {
    font-size: 1rem;
    font-weight: 700;
    color: var(--gray-900);
}
.scenario-card .card-age {
    font-size: 0.85rem;
    color: var(--gray-500);
}
.scenario-card .card-diagnosis {
    font-size: 0.85rem;
    color: var(--gray-700);
    margin-bottom: var(--space-sm);
    padding: var(--space-xs) var(--space-sm);
    background: var(--gray-50);
    border-radius: var(--radius-sm);
    display: inline-block;
}
.scenario-card .card-amount {
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--gray-900);
}


/* ═══════════════════════════════════════════════════════════
   섹션 제목 (좌측 컬러 바)
   ═══════════════════════════════════════════════════════════ */
.section-title {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    margin: var(--space-xl) 0 var(--space-md) 0;
    padding-left: var(--space-md);
    border-left: 4px solid var(--color-primary);
}
.section-title h3 {
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--gray-900);
    margin: 0;
}


/* ═══════════════════════════════════════════════════════════
   프로필 카드
   ═══════════════════════════════════════════════════════════ */
.profile-card {
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: var(--radius-lg);
    padding: var(--space-lg);
    box-shadow: var(--shadow-sm);
    min-height: 260px;
}
.profile-card .profile-header {
    display: flex;
    align-items: center;
    gap: var(--space-md);
    margin-bottom: var(--space-md);
    padding-bottom: var(--space-md);
    border-bottom: 1px solid var(--gray-100);
}
.profile-card .profile-avatar {
    font-size: 2.5rem;
    line-height: 1;
    background: var(--color-primary-light);
    width: 56px;
    height: 56px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
}
.profile-card .profile-name {
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--gray-900);
}
.profile-card .profile-sub {
    font-size: 0.85rem;
    color: var(--gray-500);
}
.profile-card .profile-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-sm) var(--space-lg);
}
.profile-card .profile-dt {
    font-size: 0.8rem;
    color: var(--gray-500);
    margin: 0;
}
.profile-card .profile-dd {
    font-size: 0.9rem;
    color: var(--gray-800);
    font-weight: 500;
    margin: 0 0 var(--space-xs) 0;
}


/* ═══════════════════════════════════════════════════════════
   청구 요약 카드
   ═══════════════════════════════════════════════════════════ */
.claim-summary {
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: var(--radius-lg);
    padding: var(--space-lg);
    box-shadow: var(--shadow-sm);
    min-height: 260px;
}
.claim-summary .summary-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-sm) var(--space-lg);
}
.claim-summary .summary-dt {
    font-size: 0.8rem;
    color: var(--gray-500);
    margin: 0;
}
.claim-summary .summary-dd {
    font-size: 0.9rem;
    color: var(--gray-800);
    font-weight: 500;
    margin: 0 0 var(--space-xs) 0;
}


/* ═══════════════════════════════════════════════════════════
   상태 칩 (Status Chip)
   ═══════════════════════════════════════════════════════════ */
.status-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 10px;
    border-radius: var(--radius-full);
    font-size: 0.78rem;
    font-weight: 600;
    line-height: 1.6;
}
.status-chip-pass {
    background: var(--color-success-bg);
    color: var(--color-success-text);
}
.status-chip-fail {
    background: var(--color-danger-bg);
    color: var(--color-danger-text);
}
.status-chip-flagged {
    background: var(--color-warning-bg);
    color: var(--color-warning-text);
}
.status-chip-skip {
    background: var(--gray-100);
    color: var(--gray-600);
}


/* ═══════════════════════════════════════════════════════════
   큰 숫자 강조 (Toss 스타일)
   ═══════════════════════════════════════════════════════════ */
.metric-highlight {
    text-align: center;
    padding: var(--space-lg) 0;
}
.metric-highlight .metric-value {
    font-size: 2.2rem;
    font-weight: 700;
    color: var(--gray-900);
    line-height: 1.2;
}
.metric-highlight .metric-label {
    font-size: 0.9rem;
    color: var(--gray-500);
    margin-top: var(--space-xs);
}


/* ═══════════════════════════════════════════════════════════
   심사 조건 타임라인
   ═══════════════════════════════════════════════════════════ */
.timeline-step {
    display: flex;
    gap: var(--space-md);
    padding: var(--space-sm) 0;
    position: relative;
    min-height: 56px;
}
.timeline-step::before {
    content: '';
    position: absolute;
    left: 13px;
    top: 36px;
    bottom: -8px;
    width: 2px;
    background: var(--gray-200);
}
.timeline-step:last-child::before {
    display: none;
}
.timeline-step .timeline-icon {
    flex-shrink: 0;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    z-index: 1;
    background: white;
    border: 2px solid var(--gray-200);
}
.timeline-step .timeline-icon-pass {
    border-color: var(--color-success);
    color: var(--color-success);
}
.timeline-step .timeline-icon-fail {
    border-color: var(--color-danger);
    color: var(--color-danger);
    background: var(--color-danger-bg);
}
.timeline-step .timeline-icon-flagged {
    border-color: var(--color-warning);
    color: var(--color-warning);
    background: var(--color-warning-bg);
}
.timeline-step .timeline-icon-skip {
    border-color: var(--gray-300);
    color: var(--gray-400);
}
.timeline-step .timeline-body {
    flex: 1;
    min-width: 0;
}
.timeline-step .timeline-title {
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--gray-800);
    margin: 0;
    display: flex;
    align-items: center;
    gap: var(--space-sm);
}
.timeline-step .timeline-reason {
    font-size: 0.82rem;
    color: var(--gray-600);
    margin: 2px 0 0 0;
    line-height: 1.4;
}
.timeline-step .timeline-reason-fail {
    color: var(--color-danger-text);
    font-weight: 500;
}


/* ═══════════════════════════════════════════════════════════
   판정 결과 배너 (리뉴얼)
   ═══════════════════════════════════════════════════════════ */
.decision-banner {
    padding: var(--space-lg) var(--space-xl);
    border-radius: var(--radius-lg);
    text-align: center;
    margin: var(--space-md) 0;
}
.decision-pay {
    background: var(--color-success-bg);
    border: 2px solid var(--color-success);
    color: var(--color-success-text);
}
.decision-deny {
    background: var(--color-danger-bg);
    border: 2px solid var(--color-danger);
    color: var(--color-danger-text);
}
.decision-hold {
    background: #FFF8E1;
    border: 2px solid var(--color-warning);
    color: var(--color-warning-text);
}
.decision-review {
    background: var(--color-warning-bg);
    border: 2px solid var(--color-warning);
    color: var(--color-warning-text);
}


/* ═══════════════════════════════════════════════════════════
   담보별 산정 카드
   ═══════════════════════════════════════════════════════════ */
.coverage-card {
    border-radius: var(--radius-md);
    padding: var(--space-md);
    text-align: center;
    border: 1px solid var(--gray-200);
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 160px;
}
.coverage-card .coverage-name {
    font-size: 0.9rem;
    font-weight: 600;
    margin-bottom: var(--space-xs);
}
.coverage-card .coverage-amount {
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--gray-900);
}
.coverage-card .coverage-formula {
    font-size: 0.78rem;
    color: var(--gray-500);
    margin-top: auto;
    padding-top: var(--space-xs);
}


/* ═══════════════════════════════════════════════════════════
   프로그레스 스테퍼 (4단계)
   ═══════════════════════════════════════════════════════════ */
.progress-stepper {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: var(--space-lg) 0;
    margin-bottom: var(--space-lg);
}
.progress-stepper .step {
    flex: 1;
    text-align: center;
    position: relative;
}
.progress-stepper .step::after {
    content: '';
    position: absolute;
    top: 18px;
    left: 50%;
    width: 100%;
    height: 2px;
    background: var(--gray-200);
}
.progress-stepper .step:last-child::after {
    display: none;
}
.progress-stepper .step-circle {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    font-weight: 700;
    margin-bottom: var(--space-xs);
    position: relative;
    z-index: 1;
}
.progress-stepper .step-done .step-circle {
    background: var(--color-primary);
    color: white;
}
.progress-stepper .step-active .step-circle {
    background: white;
    border: 3px solid var(--color-primary);
    color: var(--color-primary);
    animation: pulse-ring 1.5s infinite;
}
.progress-stepper .step-pending .step-circle {
    background: var(--gray-100);
    border: 2px solid var(--gray-300);
    color: var(--gray-400);
}
.progress-stepper .step-label {
    font-size: 0.78rem;
    color: var(--gray-600);
    font-weight: 500;
}
.progress-stepper .step-done .step-label {
    color: var(--color-primary);
    font-weight: 600;
}
.progress-stepper .step-active .step-label {
    color: var(--color-primary);
    font-weight: 700;
}
@keyframes pulse-ring {
    0% { box-shadow: 0 0 0 0 rgba(27, 100, 218, 0.3); }
    70% { box-shadow: 0 0 0 8px rgba(27, 100, 218, 0); }
    100% { box-shadow: 0 0 0 0 rgba(27, 100, 218, 0); }
}


/* ═══════════════════════════════════════════════════════════
   규칙 상태 아이콘 (하위 호환)
   ═══════════════════════════════════════════════════════════ */
.rule-pass    { color: var(--color-success); font-weight: bold; }
.rule-fail    { color: var(--color-danger);  font-weight: bold; }
.rule-skip    { color: var(--gray-500); }
.rule-flagged { color: var(--color-warning); font-weight: bold; }


/* ═══════════════════════════════════════════════════════════
   사이드바 이력 (리뉴얼)
   ═══════════════════════════════════════════════════════════ */
.history-item {
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: var(--radius-md);
    padding: var(--space-sm) var(--space-md);
    margin-bottom: var(--space-sm);
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    transition: border-color 0.2s;
}
.history-item:hover {
    border-color: var(--color-primary);
}
.history-item .hist-icon {
    font-size: 1.2rem;
    flex-shrink: 0;
}
.history-item .hist-body {
    flex: 1;
    min-width: 0;
}
.history-item .hist-id {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--gray-800);
}
.history-item .hist-amount {
    font-size: 0.78rem;
    color: var(--gray-500);
}


/* ═══════════════════════════════════════════════════════════
   사이드바 로고
   ═══════════════════════════════════════════════════════════ */
.sidebar-logo {
    text-align: center;
    padding: var(--space-md) 0 var(--space-lg) 0;
    border-bottom: 1px solid var(--gray-200);
    margin-bottom: var(--space-lg);
}
.sidebar-logo .logo-icon {
    font-size: 2rem;
    margin-bottom: var(--space-xs);
}
.sidebar-logo .logo-title {
    font-size: 1rem;
    font-weight: 700;
    color: var(--gray-900);
}
.sidebar-logo .logo-sub {
    font-size: 0.75rem;
    color: var(--gray-500);
}


/* ═══════════════════════════════════════════════════════════
   대시보드 그리드
   ═══════════════════════════════════════════════════════════ */
.dashboard-grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-md);
}
.dashboard-grid-3 {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: var(--space-md);
}


/* ═══════════════════════════════════════════════════════════
   안내 문구 (빈 상태)
   ═══════════════════════════════════════════════════════════ */
.empty-state {
    text-align: center;
    padding: var(--space-2xl) var(--space-lg);
    color: var(--gray-400);
}
.empty-state .empty-icon {
    font-size: 2.5rem;
    margin-bottom: var(--space-md);
}
.empty-state p {
    font-size: 0.95rem;
    color: var(--gray-500);
}


/* ═══════════════════════════════════════════════════════════
   주의·알림 배너
   ═══════════════════════════════════════════════════════════ */
.alert-banner {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: var(--space-sm) var(--space-md);
    border-radius: var(--radius-md);
    font-size: 0.85rem;
    font-weight: 500;
    margin: var(--space-sm) 0;
}
.alert-banner-warning {
    background: var(--color-warning-bg);
    color: var(--color-warning-text);
    border: 1px solid var(--color-warning);
}
.alert-banner-danger {
    background: var(--color-danger-bg);
    color: var(--color-danger-text);
    border: 1px solid var(--color-danger);
}
.alert-banner-info {
    background: var(--color-info-bg);
    color: #0D47A1;
    border: 1px solid var(--color-info);
}


/* ═══════════════════════════════════════════════════════════
   TASK-H1: 핵심 문제점 상단 알림
   ═══════════════════════════════════════════════════════════ */
.key-issues-box {
    background: linear-gradient(135deg, #FFF3E0 0%, #FFECB3 100%);
    border: 1.5px solid #FFB74D;
    border-radius: var(--radius-lg);
    padding: var(--space-md) var(--space-lg);
    margin-bottom: var(--space-lg);
}
.key-issues-box.severity-high {
    background: linear-gradient(135deg, #FFEBEE 0%, #FFCDD2 100%);
    border-color: #EF5350;
}
.key-issues-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--gray-900);
    margin-bottom: var(--space-sm);
    display: flex;
    align-items: center;
    gap: var(--space-xs);
}
.key-issues-list {
    list-style: none;
    padding: 0;
    margin: 0;
}
.key-issues-list li {
    font-size: 0.88rem;
    color: var(--gray-700);
    padding: 4px 0;
    display: flex;
    align-items: flex-start;
    gap: var(--space-xs);
    line-height: 1.5;
}


/* ═══════════════════════════════════════════════════════════
   TASK-H2: 신뢰도 대시보드
   ═══════════════════════════════════════════════════════════ */
.confidence-dashboard {
    background: var(--gray-50);
    border-radius: var(--radius-lg);
    padding: var(--space-md) var(--space-lg);
    margin: var(--space-md) 0;
    border: 1px solid var(--gray-200);
}
.confidence-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--space-md);
}
.confidence-overall {
    font-size: 1.8rem;
    font-weight: 800;
    letter-spacing: -0.5px;
}
.risk-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.5px;
}
.risk-very-low {
    background: #E0F2F1;
    color: #00695C;
}
.risk-low {
    background: #E8F5E9;
    color: #2E7D32;
}
.risk-medium {
    background: #FFF3E0;
    color: #E65100;
}
.risk-high {
    background: #FFEBEE;
    color: #C62828;
}
.risk-critical {
    background: #F3E5F5;
    color: #6A1B9A;
    animation: pulse-critical 1.5s ease-in-out infinite;
}
@keyframes pulse-critical {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.7; }
}
/* A-6: confidence_factors 세부 요인 */
.confidence-factors-section {
    margin-top: var(--space-md);
    padding-top: var(--space-md);
    border-top: 1px solid var(--gray-100);
}
.factors-title {
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--gray-700);
    margin-bottom: var(--space-sm);
    letter-spacing: 0.3px;
}
.factors-grid {
    display: flex;
    flex-direction: column;
    gap: 8px;
}
.factor-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 10px;
    background: white;
    border-radius: var(--radius-sm);
    border: 1px solid var(--gray-100);
}
.factor-icon {
    font-size: 1rem;
    flex-shrink: 0;
    width: 24px;
    text-align: center;
}
.factor-body {
    flex: 1;
    min-width: 0;
}
.factor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 3px;
}
.factor-label {
    font-size: 0.72rem;
    font-weight: 500;
    color: var(--gray-600);
}
.factor-value {
    font-size: 0.78rem;
    font-weight: 700;
}
.factor-bar-bg {
    height: 4px;
    background: var(--gray-100);
    border-radius: 2px;
    overflow: hidden;
}
.factor-bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s ease;
}
/* A-6: risk action 가이드 */
.risk-action-box {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: var(--space-md);
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    border-left: 4px solid transparent;
}
.risk-action-icon {
    font-size: 1.2rem;
    flex-shrink: 0;
}
.risk-action-body {
    flex: 1;
}
.risk-action-title {
    font-size: 0.78rem;
    font-weight: 700;
    margin-bottom: 2px;
}
.risk-action-desc {
    font-size: 0.72rem;
    line-height: 1.4;
}
.action-very-low {
    background: #E0F2F1;
    border-left-color: #00695C;
    color: #004D40;
}
.action-low {
    background: #E8F5E9;
    border-left-color: #2E7D32;
    color: #1B5E20;
}
.action-medium {
    background: #FFF3E0;
    border-left-color: #E65100;
    color: #BF360C;
}
.action-high {
    background: #FFEBEE;
    border-left-color: #C62828;
    color: #B71C1C;
}
.action-critical {
    background: #F3E5F5;
    border-left-color: #6A1B9A;
    color: #4A148C;
    animation: pulse-critical 1.5s ease-in-out infinite;
}
/* A-7: 심사 라우팅 카드 */
.review-routing-card {
    margin-top: var(--space-md);
    padding: 14px 16px;
    border-radius: var(--radius-md);
    border: 1px solid var(--gray-100);
    border-left: 5px solid var(--gray-300);
    background: var(--gray-50);
}
.routing-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-sm);
}
.routing-action {
    display: flex;
    align-items: center;
    gap: 8px;
}
.routing-action-icon {
    font-size: 1.1rem;
}
.routing-action-label {
    font-size: 0.85rem;
    font-weight: 800;
    letter-spacing: 0.3px;
}
.routing-badges {
    display: flex;
    gap: 6px;
    align-items: center;
}
.routing-priority-badge, .routing-time-badge {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.68rem;
    font-weight: 600;
    background: white;
    border: 1px solid var(--gray-200);
}
.priority-low { color: var(--gray-500); }
.priority-normal { color: var(--gray-700); }
.priority-high { color: #E65100; border-color: #FFB74D; background: #FFF8E1; }
.priority-urgent { color: #C62828; border-color: #EF9A9A; background: #FFEBEE; }
.priority-critical { color: #6A1B9A; border-color: #CE93D8; background: #F3E5F5; animation: pulse-critical 1.5s ease-in-out infinite; }
.routing-details {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: var(--space-sm);
}
.routing-detail-item {
    padding: 6px 10px;
    background: white;
    border-radius: var(--radius-sm);
    border: 1px solid var(--gray-100);
}
.routing-detail-label {
    font-size: 0.68rem;
    font-weight: 500;
    color: var(--gray-500);
    margin-bottom: 2px;
}
.routing-detail-value {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--gray-800);
}
.routing-checklist {
    margin-top: var(--space-sm);
    padding: 10px 12px;
    background: white;
    border-radius: var(--radius-sm);
    border: 1px solid var(--gray-100);
}
.routing-checklist-title {
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--gray-700);
    margin-bottom: 6px;
}
.routing-check-list {
    list-style: none;
    padding: 0;
    margin: 0;
}
.routing-check-item {
    font-size: 0.72rem;
    color: var(--gray-600);
    padding: 3px 0;
    border-bottom: 1px solid var(--gray-50);
    line-height: 1.5;
}
.routing-check-item:last-child {
    border-bottom: none;
}
/* 라우팅 액션별 보더 색상 */
.routing-auto { border-left-color: #00695C; }
.routing-standard { border-left-color: #2E7D32; }
.routing-enhanced { border-left-color: #E65100; }
.routing-senior { border-left-color: #C62828; }
.routing-mandatory { border-left-color: #6A1B9A; animation: pulse-critical 1.5s ease-in-out infinite; }
.confidence-gauges {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-sm);
}
.gauge-item {
    text-align: center;
    padding: var(--space-sm);
    background: white;
    border-radius: var(--radius-sm);
    border: 1px solid var(--gray-100);
}
.gauge-label {
    font-size: 0.72rem;
    color: var(--gray-500);
    margin-bottom: 4px;
    font-weight: 500;
}
.gauge-bar-bg {
    height: 6px;
    background: var(--gray-100);
    border-radius: 3px;
    overflow: hidden;
    margin: 6px 0;
}
.gauge-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s ease;
}
.gauge-value {
    font-size: 0.95rem;
    font-weight: 700;
    color: var(--gray-900);
}


/* ═══════════════════════════════════════════════════════════
   TASK-H3: Agent 스트리밍 스테퍼
   ═══════════════════════════════════════════════════════════ */
.agent-stepper {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-xs);
    margin: var(--space-sm) 0;
}
.agent-step {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border-radius: 16px;
    font-size: 0.78rem;
    font-weight: 500;
    background: var(--gray-100);
    color: var(--gray-500);
}
.agent-step.step-done {
    background: #E8F5E9;
    color: #2E7D32;
}
.agent-step.step-active {
    background: #E3F2FD;
    color: #1565C0;
    font-weight: 700;
    animation: pulse-step 1.5s ease-in-out infinite;
}
.agent-step.step-error {
    background: #FFEBEE;
    color: #C62828;
}
@keyframes pulse-step {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}


/* ═══════════════════════════════════════════════════════════
   TASK-H4: 사이드바 모드 배지
   ═══════════════════════════════════════════════════════════ */
.mode-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.72rem;
    font-weight: 600;
}
.mode-badge-agent {
    background: #E3F2FD;
    color: #1565C0;
}
.mode-badge-rule {
    background: var(--gray-100);
    color: var(--gray-600);
}


/* ═══════════════════════════════════════════════════════════
   TASK-5: 심사 파이프라인 플로우차트
   ═══════════════════════════════════════════════════════════ */
.audit-flow {
    display: flex;
    align-items: center;
    gap: 0;
    padding: var(--space-md) var(--space-sm);
    overflow-x: auto;
    margin: var(--space-md) 0;
}
.audit-node {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    min-width: 80px;
    padding: var(--space-sm) var(--space-md);
    border-radius: var(--radius-md);
    border: 2px solid var(--gray-200);
    background: white;
    transition: all 0.2s ease;
}
.audit-node-pass {
    border-color: var(--color-success);
    background: var(--color-success-bg);
}
.audit-node-fail {
    border-color: var(--color-danger);
    background: var(--color-danger-bg);
}
.audit-node-flagged {
    border-color: var(--color-warning);
    background: var(--color-warning-bg);
}
.audit-node-skip {
    border-color: var(--gray-300);
    background: var(--gray-50);
}
.audit-node-icon {
    font-size: 1.3rem;
    line-height: 1;
}
.audit-node-label {
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--gray-700);
    text-align: center;
    white-space: nowrap;
}
.audit-arrow {
    font-size: 1.1rem;
    color: var(--gray-400);
    margin: 0 2px;
    flex-shrink: 0;
}


/* ═══════════════════════════════════════════════════════════
   TASK-5: 서류 확인 매트릭스
   ═══════════════════════════════════════════════════════════ */
.doc-matrix-wrap {
    overflow-x: auto;
    margin: var(--space-md) 0;
}
.doc-matrix {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
    table-layout: fixed;
}
.doc-matrix-th {
    background: var(--gray-50);
    color: var(--gray-700);
    font-weight: 600;
    padding: 10px 14px;
    text-align: center;
    border-bottom: 2px solid var(--gray-200);
    white-space: nowrap;
    vertical-align: middle;
}
.doc-matrix-td {
    padding: 10px 14px;
    text-align: center;
    border-bottom: 1px solid var(--gray-100);
    font-size: 1.1rem;
    vertical-align: middle;
}
.doc-matrix-cov {
    font-weight: 600;
    padding: 10px 14px;
    text-align: left;
    border-bottom: 1px solid var(--gray-100);
    white-space: nowrap;
    border-left: 4px solid var(--gray-300);
    vertical-align: middle;
    width: 30%;
}
.doc-matrix-cov-pass { border-left-color: var(--color-success); color: var(--color-success-text); }
.doc-matrix-cov-fail { border-left-color: var(--color-danger); color: var(--color-danger-text); }
.doc-matrix-cov-flagged { border-left-color: var(--color-warning); color: var(--color-warning-text); }
.doc-matrix-cov-skip { border-left-color: var(--gray-300); color: var(--gray-500); }
.doc-ok { color: var(--color-success); }
.doc-missing { color: var(--color-danger); }
.doc-na { color: var(--gray-400); }


/* ═══════════════════════════════════════════════════════════
   TASK-5: 담보 카드 상단 배지
   ═══════════════════════════════════════════════════════════ */
.cov-badge {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 2px 10px;
    border-radius: var(--radius-full);
    margin-bottom: 6px;
}
.cov-badge-pass {
    background: var(--color-success-bg);
    color: var(--color-success-text);
}
.cov-badge-fail {
    background: var(--color-danger-bg);
    color: var(--color-danger-text);
}
.cov-badge-flagged {
    background: var(--color-warning-bg);
    color: var(--color-warning-text);
}
.cov-badge-skip {
    background: var(--gray-100);
    color: var(--gray-500);
}


/* ═══════════════════════════════════════════════════════════
   TASK-6: 시나리오 카드 난이도/태그 강화
   ═══════════════════════════════════════════════════════════ */
.scenario-card-enhanced {
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: var(--radius-lg);
    padding: var(--space-lg);
    transition: all 0.2s ease;
    cursor: default;
    border-left: 5px solid var(--gray-300);
    display: flex;
    flex-direction: column;
    min-height: 240px;
    box-sizing: border-box;
}
.scenario-card-enhanced:hover {
    border-color: var(--color-primary);
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
}
.scenario-card-enhanced.card-border-pass { border-left-color: var(--color-success); }
.scenario-card-enhanced.card-border-fail { border-left-color: var(--color-danger); }
.scenario-card-enhanced.card-border-flagged { border-left-color: var(--color-warning); }
.scenario-card-enhanced.card-border-review { border-left-color: #2196F3; }
.scenario-card-enhanced.card-border-hold { border-left-color: var(--gray-400); }

.scenario-card-enhanced .card-header {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    margin-bottom: var(--space-sm);
}
.scenario-card-enhanced .card-avatar {
    font-size: 1.8rem;
    line-height: 1;
}
.scenario-card-enhanced .card-name {
    font-size: 1rem;
    font-weight: 700;
    color: var(--gray-900);
}
.scenario-card-enhanced .card-age {
    font-size: 0.85rem;
    color: var(--gray-500);
}
.scenario-card-enhanced .card-diagnosis {
    font-size: 0.85rem;
    color: var(--gray-700);
    margin-bottom: var(--space-sm);
    padding: var(--space-xs) var(--space-sm);
    background: var(--gray-50);
    border-radius: var(--radius-sm);
    display: block;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.scenario-card-enhanced .card-amount {
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--gray-900);
}

.card-difficulty {
    font-size: 0.75rem;
    color: var(--gray-500);
    margin-left: auto;
}

.card-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-bottom: var(--space-sm);
    min-height: 22px;
    max-height: 48px;
    overflow: hidden;
}
.card-tag {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 600;
    padding: 1px 7px;
    border-radius: var(--radius-full);
    background: var(--color-primary-light);
    color: var(--color-primary);
    white-space: nowrap;
}


/* ═══════════════════════════════════════════════════════════
   Executive Summary Card (Step 4 최상단)
   ═══════════════════════════════════════════════════════════ */
.result-summary {
    border-radius: var(--radius-lg);
    padding: var(--space-lg) var(--space-xl);
    margin-bottom: var(--space-lg);
    border: 2px solid var(--gray-200);
    background: white;
}
.result-summary.rs-pay {
    background: linear-gradient(135deg, #E8F5E9 0%, #C8E6C9 100%);
    border-color: var(--color-success);
}
.result-summary.rs-deny {
    background: linear-gradient(135deg, #FFEBEE 0%, #FFCDD2 100%);
    border-color: var(--color-danger);
}
.result-summary.rs-partial {
    background: linear-gradient(135deg, #FFF3E0 0%, #FFE0B2 100%);
    border-color: var(--color-warning);
}
.result-summary.rs-review {
    background: linear-gradient(135deg, #FFF3E0 0%, #FFECB3 100%);
    border-color: var(--color-warning);
}
.result-summary.rs-hold {
    background: linear-gradient(135deg, var(--gray-50) 0%, var(--gray-100) 100%);
    border-color: var(--gray-300);
}

.rs-header {
    display: flex;
    align-items: center;
    gap: var(--space-md);
    margin-bottom: var(--space-sm);
}
.rs-icon {
    font-size: 2.8rem;
    line-height: 1;
    flex-shrink: 0;
    width: 56px;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.rs-main {
    flex: 1;
}
.rs-decision {
    font-size: 1rem;
    font-weight: 700;
    color: var(--gray-700);
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.rs-amount {
    font-size: 2.4rem;
    font-weight: 800;
    color: var(--gray-900);
    line-height: 1.2;
}

.rs-reason {
    font-size: 0.92rem;
    color: var(--gray-700);
    margin-bottom: var(--space-sm);
    line-height: 1.5;
}

.rs-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: var(--space-md);
}
.rs-chip {
    display: inline-block;
    font-size: 0.75rem;
    font-weight: 500;
    padding: 2px 10px;
    border-radius: var(--radius-full);
    background: rgba(255,255,255,0.7);
    color: var(--gray-700);
    border: 1px solid rgba(0,0,0,0.08);
}

.rs-pipeline {
    display: flex;
    align-items: center;
    gap: 0;
    padding-top: var(--space-sm);
    border-top: 1px solid rgba(0,0,0,0.08);
    overflow-x: auto;
}
.rs-pipe-node {
    font-size: 0.72rem;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: var(--radius-sm);
    white-space: nowrap;
    background: rgba(255,255,255,0.6);
}
.rs-pipe-pass { color: var(--color-success-text); }
.rs-pipe-fail { color: var(--color-danger-text); }
.rs-pipe-flagged { color: var(--color-warning-text); }
.rs-pipe-skip { color: var(--gray-500); }
.rs-pipe-arrow {
    font-size: 0.8rem;
    color: var(--gray-400);
    margin: 0 2px;
    flex-shrink: 0;
}

/* ── Result Summary: 조건 통과 요약 + 이슈 리스트 ────────── */
.rs-conditions-summary {
    font-size: 0.82rem;
    color: var(--gray-600);
    padding: var(--space-sm) 0;
    border-top: 1px solid rgba(0,0,0,0.06);
    margin-top: var(--space-sm);
}
.rs-cond-total { color: var(--gray-500); }
.rs-cond-pass { color: var(--color-success-text); font-weight: 600; }
.rs-cond-fail { color: var(--color-danger-text); font-weight: 600; }
.rs-cond-sep { color: var(--gray-400); margin: 0 6px; }

.rs-issues-compact {
    list-style: none;
    padding: 0;
    margin: var(--space-sm) 0 0 0;
}
.rs-issue-item {
    font-size: 0.82rem;
    color: var(--gray-700);
    padding: 6px 10px;
    margin-bottom: 4px;
    background: rgba(0,0,0,0.03);
    border-radius: var(--radius-sm);
    border-left: 3px solid var(--color-warning);
}

/* ── Zone 구분 디바이더 ──────────────────────────────────── */
.zone-divider {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: var(--space-xl) 0 var(--space-lg) 0;
    padding: 0;
}
.zone-divider::before,
.zone-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--gray-200);
}
.zone-divider-label {
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--gray-400);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    white-space: nowrap;
}

/* ── Coverage 카드 거부 사유 인라인 ───────────────────────── */
.cov-denial-reason {
    font-size: 0.78rem;
    color: var(--color-danger-text);
    background: rgba(255,59,48,0.08);
    border-radius: var(--radius-sm);
    padding: 6px 8px;
    margin-top: var(--space-xs);
    border-left: 2px solid var(--color-danger);
}

/* ── AI 추론 패널 ────────────────────────────────────────── */
.ai-reasoning-panel {
    background: linear-gradient(135deg, #F0F4FF 0%, #E8EEFF 100%);
    border: 1px solid #C6DEFF;
    border-radius: var(--radius-lg);
    padding: var(--space-lg);
    margin-top: var(--space-lg);
}
.ai-reasoning-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: var(--space-md);
}
.ai-reasoning-avatar {
    font-size: 1.5rem;
}
.ai-reasoning-title {
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--color-primary);
}
.ai-reasoning-body {
    font-size: 0.85rem;
    color: var(--gray-700);
    line-height: 1.7;
}
.ai-reasoning-body p {
    margin-bottom: var(--space-sm);
}

/* ── 워터폴 차트 ─────────────────────────────────────────── */
.wf-chart {
    background: white;
    border: 1px solid var(--gray-100);
    border-radius: var(--radius-lg);
    padding: var(--space-md);
    margin-bottom: var(--space-md);
}
.wf-title {
    font-size: 0.85rem;
    font-weight: 700;
    color: var(--gray-700);
    margin-bottom: var(--space-md);
}
.wf-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
}
.wf-label {
    font-size: 0.8rem;
    color: var(--gray-600);
    min-width: 110px;
    text-align: right;
}
.wf-bar-wrap {
    flex: 1;
    height: 20px;
    background: var(--gray-50);
    border-radius: 4px;
    overflow: hidden;
}
.wf-bar {
    height: 100%;
    border-radius: 4px;
    transition: width 0.8s cubic-bezier(0.4,0,0.2,1);
}
.wf-value {
    font-size: 0.82rem;
    font-weight: 700;
    min-width: 90px;
}

/* ── Clause block hover ──────────────────────────────────── */
.clause-block {
    transition: outline 0.3s ease;
}

/* ═══════════════════════════════════════════════════════════
   TASK-6: Evidence Detail — 산정 상세 시각화
   ═══════════════════════════════════════════════════════════ */

/* ── 산식 박스 ─────────────────────────────────────────── */
.ev-formula-box {
    background: linear-gradient(135deg, #EBF5FF 0%, #F0F7FF 100%);
    border: 1px solid #C6DEFF;
    border-radius: var(--radius-lg);
    padding: var(--space-md);
    margin-bottom: var(--space-md);
}
.ev-formula-title {
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--color-primary);
    margin-bottom: var(--space-xs);
    letter-spacing: 0.02em;
}
.ev-formula-row {
    padding: 3px 0;
    line-height: 1.6;
}
.ev-formula-label {
    font-weight: 600;
    color: var(--gray-800);
    font-size: 0.85rem;
    margin-right: var(--space-xs);
}
.ev-formula-expr {
    font-size: 0.88rem;
    color: var(--gray-700);
    font-variant-numeric: tabular-nums;
}
.ev-formula-expr strong {
    color: var(--color-primary);
    font-size: 1rem;
}
.ev-gen-badge {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 2px 10px;
    border-radius: var(--radius-full);
    background: #E8F4FD;
    color: #1976D2;
    border: 1px solid #BBDEFB;
}
.ev-inferred {
    font-size: 0.72rem;
    font-weight: 500;
    color: #F57C00;
    background: #FFF3E0;
    padding: 1px 6px;
    border-radius: var(--radius-sm);
}

/* ── 주요 항목 테이블 ──────────────────────────────────── */
.ev-table-wrap {
    margin-bottom: var(--space-md);
}
.ev-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
}
.ev-table th {
    text-align: left;
    font-weight: 700;
    color: var(--gray-600);
    padding: 6px 10px;
    border-bottom: 2px solid var(--gray-200);
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.ev-table td {
    padding: 7px 10px;
    border-bottom: 1px solid var(--gray-100);
    vertical-align: top;
}
.ev-table tbody tr:nth-child(even) {
    background: rgba(0,0,0,0.015);
}
.ev-table tbody tr:hover {
    background: rgba(0,0,0,0.03);
}
.ev-key {
    font-weight: 600;
    color: var(--gray-700);
    white-space: nowrap;
    width: 35%;
}
.ev-val {
    color: var(--gray-800);
    word-break: break-word;
}

/* ── IND coverages_applied 서브테이블 ─────────────────── */
.ev-sub-title {
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--gray-700);
    margin-bottom: var(--space-xs);
}
.ev-sub-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.78rem;
}
.ev-sub-table th {
    text-align: center;
    font-weight: 600;
    color: var(--gray-500);
    padding: 5px 6px;
    border-bottom: 2px solid var(--gray-200);
    font-size: 0.72rem;
}
.ev-sub-table td {
    text-align: center;
    padding: 6px;
    border-bottom: 1px solid var(--gray-100);
}
.ev-sub-table td:first-child {
    text-align: left;
    font-weight: 500;
}
.ev-sub-table td:last-child {
    font-weight: 700;
    color: var(--color-primary);
}

/* ── 약관 인용 블록 ────────────────────────────────────── */
.ev-clause-block {
    background: var(--gray-50);
    border-radius: var(--radius-lg);
    padding: var(--space-md);
    margin-bottom: var(--space-md);
    border: 1px solid var(--gray-100);
}
.ev-clause-header {
    font-size: 0.78rem;
    font-weight: 700;
    color: var(--color-primary);
    margin-bottom: var(--space-xs);
}
.ev-clause-title {
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--gray-800);
    margin-bottom: var(--space-xs);
}
blockquote.ev-clause-text {
    margin: 0;
    padding: 10px 14px;
    border-left: 3px solid var(--color-primary);
    background: rgba(255,255,255,0.7);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    font-size: 0.8rem;
    color: var(--gray-600);
    line-height: 1.65;
    font-style: normal;
}
.ev-legal-note {
    margin-top: var(--space-sm);
    font-size: 0.72rem;
    color: var(--gray-500);
    font-style: italic;
    padding-left: 2px;
}

/* ── 기타 정보 접이식 ──────────────────────────────────── */
details.ev-misc {
    margin-top: var(--space-xs);
}
details.ev-misc summary {
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--gray-500);
    cursor: pointer;
    padding: 4px 0;
}
details.ev-misc summary:hover {
    color: var(--gray-700);
}

/* ══════════════════════════════════════════════════════ */
/* 2차 심사 (추가 영수증) UI                              */
/* ══════════════════════════════════════════════════════ */
.sec-assess-box {
    background: linear-gradient(135deg, #FFF8E1 0%, #FFFDE7 100%);
    border: 1.5px solid #FFD54F;
    border-radius: var(--radius-lg);
    padding: var(--space-lg);
    margin-top: var(--space-md);
}
.sec-assess-box .sec-title {
    font-size: 1.05rem;
    font-weight: 800;
    color: #F57F17;
    margin-bottom: var(--space-xs);
}
.sec-assess-box .sec-desc {
    font-size: 0.82rem;
    color: var(--gray-600);
    margin-bottom: var(--space-sm);
}
.sec-result-card {
    background: white;
    border: 1.5px solid #A5D6A7;
    border-radius: var(--radius-lg);
    padding: var(--space-md) var(--space-lg);
    margin-top: var(--space-sm);
}
.sec-result-card.sec-fail {
    border-color: #EF9A9A;
}
.sec-result-header {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    margin-bottom: var(--space-sm);
}
.sec-result-header .sec-icon {
    font-size: 1.6rem;
}
.sec-result-header .sec-label {
    font-size: 1rem;
    font-weight: 700;
    color: var(--gray-900);
}
.sec-result-header .sec-amount {
    font-size: 1.3rem;
    font-weight: 900;
    color: #2E7D32;
    margin-left: auto;
}
.sec-result-card.sec-fail .sec-result-header .sec-amount {
    color: #C62828;
    font-size: 1rem;
}
.sec-compare-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: var(--space-sm);
    font-size: 0.82rem;
}
.sec-compare-table th {
    background: #F5F5F5;
    font-weight: 700;
    padding: 6px 10px;
    text-align: right;
    border-bottom: 1.5px solid #E0E0E0;
    color: var(--gray-700);
}
.sec-compare-table th:first-child {
    text-align: left;
}
.sec-compare-table td {
    padding: 5px 10px;
    text-align: right;
    border-bottom: 1px solid #F0F0F0;
    font-variant-numeric: tabular-nums;
}
.sec-compare-table td:first-child {
    text-align: left;
    font-weight: 600;
    color: var(--gray-700);
}
.sec-compare-table tr.sec-total {
    background: #E8F5E9;
    font-weight: 800;
}
.sec-compare-table tr.sec-total td {
    border-top: 2px solid #66BB6A;
    border-bottom: none;
    color: #1B5E20;
    font-size: 0.88rem;
}
.sec-receipt-info {
    display: flex;
    gap: var(--space-md);
    flex-wrap: wrap;
    margin-top: var(--space-xs);
}
.sec-receipt-chip {
    background: #FFF3E0;
    border: 1px solid #FFB74D;
    border-radius: var(--radius-full);
    padding: 3px 12px;
    font-size: 0.78rem;
    font-weight: 600;
    color: #E65100;
}

/* ══════════════════════════════════════════════════════════ */
/* C-6: OCR 정확도 리포트                                    */
/* ══════════════════════════════════════════════════════════ */
.ocr-report {
    margin-top: var(--space-sm);
}
.ocr-doc-row {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: 8px 12px;
    border-radius: var(--radius-md);
    margin-bottom: 4px;
    font-size: 0.82rem;
    transition: background 0.15s;
}
.ocr-doc-row:hover {
    background: rgba(0,0,0,0.02);
}
.ocr-doc-icon {
    font-size: 1.1rem;
    width: 24px;
    text-align: center;
    flex-shrink: 0;
}
.ocr-doc-name {
    font-weight: 700;
    color: var(--gray-800);
    min-width: 110px;
}
.ocr-doc-mode {
    font-size: 0.72rem;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: var(--radius-full);
    text-transform: uppercase;
    letter-spacing: 0.03em;
}
.ocr-mode-regex  { background: #E8F5E9; color: #2E7D32; }
.ocr-mode-llm    { background: #E3F2FD; color: #1565C0; }
.ocr-mode-hybrid { background: #FFF3E0; color: #E65100; }
.ocr-mode-vision { background: #F3E5F5; color: #7B1FA2; }
.ocr-mode-ocr    { background: #ECEFF1; color: #455A64; }
.ocr-conf-bar-bg {
    flex: 1;
    height: 8px;
    background: #EEEEEE;
    border-radius: 4px;
    overflow: hidden;
    min-width: 80px;
}
.ocr-conf-bar {
    height: 100%;
    border-radius: 4px;
    transition: width 0.4s ease;
}
.ocr-conf-bar.conf-high   { background: linear-gradient(90deg, #66BB6A, #43A047); }
.ocr-conf-bar.conf-medium { background: linear-gradient(90deg, #FFA726, #FB8C00); }
.ocr-conf-bar.conf-low    { background: linear-gradient(90deg, #EF5350, #E53935); }
.ocr-conf-pct {
    font-size: 0.78rem;
    font-weight: 700;
    min-width: 38px;
    text-align: right;
    font-variant-numeric: tabular-nums;
}
.ocr-conf-pct.conf-high   { color: #2E7D32; }
.ocr-conf-pct.conf-medium { color: #E65100; }
.ocr-conf-pct.conf-low    { color: #C62828; }
.ocr-field-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    margin-top: 4px;
    padding-left: 36px;
}
.ocr-field-chip {
    font-size: 0.7rem;
    padding: 1px 7px;
    border-radius: var(--radius-full);
    background: #F5F5F5;
    color: var(--gray-600);
    border: 1px solid #E0E0E0;
}
.ocr-field-chip.ocr-extracted { background: #E8F5E9; border-color: #A5D6A7; color: #1B5E20; }
.ocr-field-chip.ocr-missing   { background: #FFEBEE; border-color: #EF9A9A; color: #B71C1C; }
.ocr-summary-bar {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    padding: 10px 14px;
    background: linear-gradient(135deg, #F5F5F5 0%, #FAFAFA 100%);
    border: 1px solid #E0E0E0;
    border-radius: var(--radius-lg);
    margin-bottom: var(--space-sm);
    font-size: 0.82rem;
}
.ocr-summary-stat {
    font-weight: 700;
    color: var(--gray-800);
}
.ocr-error-item {
    font-size: 0.75rem;
    color: #C62828;
    padding-left: 36px;
    line-height: 1.5;
}

/* ══════════════════════════════════════════════════════════════
   B-2: 비교 뷰 (Comparison View)
   ══════════════════════════════════════════════════════════════ */

/* 헤더 */
.cmp-header {
    display: flex;
    align-items: center;
    gap: var(--space-md);
    padding: var(--space-lg);
    background: linear-gradient(135deg, #E3F2FD 0%, #F3E5F5 100%);
    border-radius: var(--radius-lg);
    margin-bottom: var(--space-lg);
    border: 1px solid #BBDEFB;
}
.cmp-header-icon {
    font-size: 2.5rem;
}
.cmp-header-title {
    font-size: 1.3rem;
    font-weight: 800;
    color: var(--gray-900);
}
.cmp-header-desc {
    font-size: 0.85rem;
    color: var(--gray-600);
    margin-top: 2px;
}

/* 집계 요약 바 */
.cmp-summary-bar {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-md);
    padding: 12px 18px;
    background: linear-gradient(135deg, #F5F5F5 0%, #FAFAFA 100%);
    border: 1px solid #E0E0E0;
    border-radius: var(--radius-lg);
    font-size: 0.85rem;
}
.cmp-summary-stat {
    font-weight: 700;
    color: var(--gray-800);
    white-space: nowrap;
}
.cmp-summary-detail {
    font-size: 0.8rem;
    color: var(--gray-500);
    margin-left: auto;
}

/* 판정 카드 */
.cmp-decision-card {
    background: #fff;
    border: 1.5px solid #E0E0E0;
    border-radius: var(--radius-md);
    padding: var(--space-md);
    transition: box-shadow 0.2s;
    min-height: 140px;
}
.cmp-decision-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.08);
}
.cmp-decision-card.rs-pay { border-left: 5px solid #43A047; }
.cmp-decision-card.rs-deny { border-left: 5px solid #C62828; }
.cmp-decision-card.rs-partial { border-left: 5px solid #F57F17; }
.cmp-decision-card.rs-review { border-left: 5px solid #FF8F00; }
.cmp-decision-card.rs-hold { border-left: 5px solid #9E9E9E; }

.cmp-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-sm);
}
.cmp-card-id {
    font-size: 0.82rem;
    font-weight: 700;
    color: var(--gray-700);
    font-variant-numeric: tabular-nums;
}
.cmp-card-badge {
    font-size: 0.75rem;
    font-weight: 700;
    padding: 2px 10px;
    border-radius: var(--radius-full);
    background: var(--gray-100);
    color: var(--gray-700);
}
.cmp-card-amount {
    font-size: 1.4rem;
    font-weight: 900;
    color: var(--gray-900);
    font-variant-numeric: tabular-nums;
    margin-bottom: var(--space-xs);
}
.cmp-card-reason {
    font-size: 0.78rem;
    color: var(--gray-500);
    line-height: 1.4;
    margin-top: var(--space-xs);
}
.cmp-routing-badge {
    font-size: 0.72rem;
    color: #1565C0;
    background: #E3F2FD;
    border-radius: var(--radius-full);
    padding: 2px 8px;
    margin-top: var(--space-xs);
    display: inline-block;
}
.cmp-fraud-badge {
    font-size: 0.72rem;
    color: #C62828;
    background: #FFEBEE;
    border-radius: var(--radius-full);
    padding: 2px 8px;
    margin-top: var(--space-xs);
    display: inline-block;
    font-weight: 700;
}

/* 담보별 비교 테이블 */
.cmp-coverage-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.84rem;
    margin-top: var(--space-sm);
}
.cmp-coverage-table th {
    background: #F5F5F5;
    font-weight: 700;
    padding: 8px 12px;
    text-align: right;
    border-bottom: 2px solid #E0E0E0;
    color: var(--gray-700);
}
.cmp-coverage-table th:first-child {
    text-align: left;
}
.cmp-coverage-table td {
    padding: 7px 12px;
    text-align: right;
    border-bottom: 1px solid #F0F0F0;
    font-variant-numeric: tabular-nums;
}
.cmp-coverage-table td:first-child {
    text-align: left;
    font-weight: 600;
    color: var(--gray-700);
}
.cmp-diff-row {
    background: #FFF8E1 !important;
}
.cmp-diff-row td { color: #E65100; }
.cmp-diff-row td:first-child { color: var(--gray-800); }
.cmp-na {
    color: var(--gray-400);
    font-style: italic;
}
.cmp-total-row {
    background: #E8F5E9;
    font-weight: 800;
}
.cmp-total-row td {
    border-top: 2px solid #66BB6A;
    border-bottom: none;
    color: #1B5E20;
    font-size: 0.88rem;
}
.cmp-total-amount {
    font-weight: 900;
}

/* 신뢰도 비교 카드 */
.cmp-conf-card {
    background: #fff;
    border: 1px solid #E0E0E0;
    border-radius: var(--radius-md);
    padding: var(--space-md);
}
.cmp-conf-id {
    font-size: 0.82rem;
    font-weight: 700;
    color: var(--gray-700);
    margin-bottom: var(--space-sm);
}
.cmp-conf-overall {
    display: flex;
    align-items: center;
    gap: var(--space-sm);
    margin-bottom: var(--space-xs);
}
.cmp-conf-gauge-track {
    flex: 1;
    height: 10px;
    background: var(--gray-100);
    border-radius: var(--radius-full);
    overflow: hidden;
}
.cmp-conf-gauge-fill {
    height: 100%;
    border-radius: var(--radius-full);
    transition: width 0.6s ease;
}
.cmp-conf-score {
    font-size: 1.1rem;
    font-weight: 900;
    min-width: 44px;
    text-align: right;
}
.cmp-conf-risk {
    font-size: 0.75rem;
    font-weight: 700;
    margin-bottom: var(--space-sm);
}
.cmp-conf-na {
    font-size: 0.82rem;
    color: var(--gray-400);
    font-style: italic;
    padding: var(--space-md) 0;
}

/* 신뢰도 세부 바 */
.cmp-conf-sub {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
}
.cmp-conf-sub-label {
    font-size: 0.7rem;
    color: var(--gray-600);
    min-width: 62px;
}
.cmp-conf-sub-track {
    flex: 1;
    height: 5px;
    background: var(--gray-100);
    border-radius: var(--radius-full);
    overflow: hidden;
}
.cmp-conf-sub-fill {
    height: 100%;
    border-radius: var(--radius-full);
    transition: width 0.4s ease;
}
.cmp-conf-sub-val {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--gray-600);
    min-width: 30px;
    text-align: right;
}

/* 룰 비교 테이블 */
.cmp-rules-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
    margin-top: var(--space-sm);
}
.cmp-rules-table th {
    background: #F5F5F5;
    font-weight: 700;
    padding: 8px 12px;
    text-align: center;
    border-bottom: 2px solid #E0E0E0;
    color: var(--gray-700);
}
.cmp-rules-table th:first-child {
    text-align: left;
}
.cmp-rules-table td {
    padding: 6px 12px;
    text-align: center;
    border-bottom: 1px solid #F0F0F0;
    font-size: 0.8rem;
}
.cmp-rules-table .cmp-rule-name {
    text-align: left;
    font-weight: 600;
    color: var(--gray-700);
}

/* ═══════════════════════════════════════════════════════════
   애니메이션 시스템 — 입장 / 로딩 / 결과 공개
   ═══════════════════════════════════════════════════════════ */

/* ── 입장 애니메이션 (Entrance) ── */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(24px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes fadeInScale {
    from { opacity: 0; transform: scale(0.92); }
    to   { opacity: 1; transform: scale(1); }
}
@keyframes slideInRight {
    from { opacity: 0; transform: translateX(30px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes slideInLeft {
    from { opacity: 0; transform: translateX(-30px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes slideDown {
    from { opacity: 0; transform: translateY(-16px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* ── 로딩/처리 애니메이션 (Loading) ── */
@keyframes shimmer {
    0%   { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
@keyframes spin {
    from { transform: rotate(0deg); }
    to   { transform: rotate(360deg); }
}
@keyframes progressGlow {
    0%, 100% { box-shadow: 0 0 8px rgba(27,100,218,0.3); }
    50%      { box-shadow: 0 0 20px rgba(27,100,218,0.6); }
}
@keyframes drawLine {
    from { width: 0; }
    to   { width: 100%; }
}

/* ── 결과 공개 애니메이션 (Result Reveal) ── */
@keyframes revealBounce {
    0%   { opacity: 0; transform: scale(0.3); }
    50%  { opacity: 1; transform: scale(1.08); }
    70%  { transform: scale(0.95); }
    100% { transform: scale(1); }
}
@keyframes countUp {
    from { opacity: 0; transform: translateY(12px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes glowPulseGreen {
    0%, 100% { box-shadow: 0 0 8px rgba(0,200,83,0.2); }
    50%      { box-shadow: 0 0 24px rgba(0,200,83,0.5); }
}
@keyframes glowPulseRed {
    0%, 100% { box-shadow: 0 0 8px rgba(244,67,54,0.2); }
    50%      { box-shadow: 0 0 24px rgba(244,67,54,0.5); }
}
@keyframes glowPulseOrange {
    0%, 100% { box-shadow: 0 0 8px rgba(255,152,0,0.2); }
    50%      { box-shadow: 0 0 24px rgba(255,152,0,0.5); }
}

/* ── 특수 효과 ── */
@keyframes checkDraw {
    0%   { stroke-dashoffset: 24; }
    100% { stroke-dashoffset: 0; }
}
@keyframes floatUp {
    0%   { opacity: 0; transform: translateY(8px); }
    60%  { opacity: 1; }
    100% { opacity: 0; transform: translateY(-20px); }
}
@keyframes borderGlow {
    0%, 100% { border-color: var(--color-primary-light); }
    50%      { border-color: var(--color-primary); }
}

/* ═══════════════════════════════════════════════════════════
   애니메이션 유틸리티 클래스
   ═══════════════════════════════════════════════════════════ */

/* 입장 애니메이션 — 순차 등장용 딜레이 */
.anim-fade-in-up {
    animation: fadeInUp 0.5s ease-out backwards;
}
.anim-fade-in-scale {
    animation: fadeInScale 0.4s ease-out backwards;
}
.anim-slide-in-right {
    animation: slideInRight 0.5s ease-out backwards;
}
.anim-slide-in-left {
    animation: slideInLeft 0.5s ease-out backwards;
}
.anim-slide-down {
    animation: slideDown 0.4s ease-out backwards;
}
.anim-reveal-bounce {
    animation: revealBounce 0.6s cubic-bezier(0.34, 1.56, 0.64, 1) backwards;
}
.anim-count-up {
    animation: countUp 0.8s ease-out backwards;
}

/* 순차 딜레이 */
.anim-delay-1 { animation-delay: 0.1s; }
.anim-delay-2 { animation-delay: 0.2s; }
.anim-delay-3 { animation-delay: 0.3s; }
.anim-delay-4 { animation-delay: 0.4s; }
.anim-delay-5 { animation-delay: 0.5s; }
.anim-delay-6 { animation-delay: 0.6s; }
.anim-delay-7 { animation-delay: 0.7s; }
.anim-delay-8 { animation-delay: 0.8s; }
.anim-delay-9 { animation-delay: 0.9s; }
.anim-delay-10 { animation-delay: 1.0s; }

/* Shimmer 로딩 스켈레톤 */
.shimmer-placeholder {
    background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: var(--radius-md);
    min-height: 80px;
}
.shimmer-text {
    background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
    background-size: 200% 100%;
    animation: shimmer 1.5s infinite;
    border-radius: var(--radius-sm);
    height: 16px;
    margin-bottom: 8px;
}
.shimmer-text.short { width: 60%; }
.shimmer-text.medium { width: 80%; }

/* 스피너 */
.anim-spinner {
    display: inline-block;
    width: 20px;
    height: 20px;
    border: 3px solid var(--gray-200);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
}
.anim-spinner-lg {
    width: 40px;
    height: 40px;
    border-width: 4px;
}

/* 결과별 글로우 */
.glow-success {
    animation: glowPulseGreen 2s ease-in-out infinite;
}
.glow-danger {
    animation: glowPulseRed 2s ease-in-out infinite;
}
.glow-warning {
    animation: glowPulseOrange 2s ease-in-out infinite;
}

/* 프로그레스 바 글로우 */
.progress-glow {
    animation: progressGlow 1.5s ease-in-out infinite;
}

/* 카드 호버 3D 틸트 */
.hover-tilt {
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}
.hover-tilt:hover {
    transform: translateY(-4px) perspective(1000px) rotateX(2deg);
    box-shadow: 0 12px 24px rgba(0,0,0,0.1);
}

/* 카드 호버 리프트 (심플) */
.hover-lift {
    transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.hover-lift:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 20px rgba(0,0,0,0.1);
}

/* 보더 글로우 애니메이션 */
.anim-border-glow {
    animation: borderGlow 2s ease-in-out infinite;
}

/* 프로세싱 단계 연결선 드로우 */
.step-connector-draw {
    height: 3px;
    background: var(--color-primary);
    animation: drawLine 0.6s ease-out forwards;
}

/* ═══════════════════════════════════════════════════════════
   시나리오 카드 순차 등장 강화
   ═══════════════════════════════════════════════════════════ */
.scenario-card-enhanced {
    animation: fadeInUp 0.5s ease-out backwards;
}
.scenario-card-enhanced:hover {
    transform: translateY(-4px) perspective(1000px) rotateX(2deg) !important;
    box-shadow: 0 12px 28px rgba(27,100,218,0.15) !important;
    border-color: var(--color-primary) !important;
}

/* ═══════════════════════════════════════════════════════════
   결과 요약 카드 애니메이션
   ═══════════════════════════════════════════════════════════ */
.result-summary.anim-active {
    animation: fadeInScale 0.6s ease-out backwards;
}
.result-summary .rs-icon {
    animation: revealBounce 0.8s cubic-bezier(0.34, 1.56, 0.64, 1) 0.2s backwards;
}
.result-summary .rs-amount {
    animation: countUp 0.8s ease-out 0.4s backwards;
}
.result-summary .rs-pipeline {
    animation: fadeInUp 0.5s ease-out 0.6s backwards;
}

/* 결과별 글로우 적용 */
.result-summary.decision-approved {
    animation: fadeInScale 0.6s ease-out backwards, glowPulseGreen 3s ease-in-out 1s infinite;
}
.result-summary.decision-denied {
    animation: fadeInScale 0.6s ease-out backwards, glowPulseRed 3s ease-in-out 1s infinite;
}
.result-summary.decision-hold {
    animation: fadeInScale 0.6s ease-out backwards, glowPulseOrange 3s ease-in-out 1s infinite;
}

/* ═══════════════════════════════════════════════════════════
   커버리지 카드 순차 슬라이드
   ═══════════════════════════════════════════════════════════ */
.coverage-card.anim-active {
    animation: slideInRight 0.5s ease-out backwards;
}
.coverage-card.anim-active:hover {
    transform: translateY(-4px) perspective(1000px) rotateX(2deg);
    box-shadow: 0 12px 24px rgba(0,0,0,0.1);
}

/* ═══════════════════════════════════════════════════════════
   타임라인 순차 등장
   ═══════════════════════════════════════════════════════════ */
.timeline-step.anim-active {
    animation: fadeInUp 0.4s ease-out backwards;
}

/* ═══════════════════════════════════════════════════════════
   신뢰도 게이지 fill 애니메이션
   ═══════════════════════════════════════════════════════════ */
.conf-gauge-fill.anim-active {
    animation: fadeInScale 0.3s ease-out backwards;
}

/* ═══════════════════════════════════════════════════════════
   프로세싱 스테퍼 강화
   ═══════════════════════════════════════════════════════════ */
.step-active .anim-spinner {
    margin-right: 4px;
}

/* ═══════════════════════════════════════════════════════════
   알림 배너 슬라이드 다운
   ═══════════════════════════════════════════════════════════ */
.key-issues-box.anim-active {
    animation: slideDown 0.5s ease-out backwards;
}

/* ═══════════════════════════════════════════════════════════
   프로파일 카드 페이드인
   ═══════════════════════════════════════════════════════════ */
.profile-card.anim-active {
    animation: fadeInUp 0.5s ease-out backwards;
}
.claim-summary.anim-active {
    animation: fadeInUp 0.5s ease-out 0.15s backwards;
}

/* ═══════════════════════════════════════════════════════════
   모바일 반응형
   ═══════════════════════════════════════════════════════════ */
@media (max-width: 768px) {
    .confidence-gauges {
        grid-template-columns: repeat(2, 1fr) !important;
    }
    .audit-flow {
        flex-wrap: wrap !important;
    }
    .rs-amount {
        font-size: 1.6rem !important;
    }
    .cmp-header {
        padding: 16px !important;
    }
    .ev-formula-box {
        flex-direction: column !important;
    }
}

/* ═══════════════════════════════════════════════════════════
   인증 페이지
   ═══════════════════════════════════════════════════════════ */
.auth-container {
    max-width: 440px;
    margin: 48px auto 0;
    padding: 40px 36px 32px;
    background: #fff;
    border-radius: var(--radius-lg, 16px);
    box-shadow: 0 4px 24px rgba(0,0,0,.06);
    border: 1px solid var(--gray-200, #E5E8EB);
}
.auth-logo {
    text-align: center;
    margin-bottom: 32px;
}
.auth-logo .logo-icon {
    font-size: 2.8rem;
    margin-bottom: 8px;
}
.auth-logo .logo-title {
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--gray-900, #191F28);
}
.auth-logo .logo-sub {
    font-size: 0.82rem;
    color: var(--gray-500, #8B95A1);
    margin-top: 4px;
}
.auth-footer {
    text-align: center;
    margin-top: 24px;
    font-size: 0.78rem;
    color: var(--gray-400, #B0B8C1);
}
.admin-user-card {
    background: var(--gray-50, #F9FAFB);
    border: 1px solid var(--gray-200, #E5E8EB);
    border-radius: var(--radius-md, 12px);
    padding: 14px;
    margin-bottom: 10px;
}
.admin-user-card .user-name {
    font-weight: 700;
    color: var(--gray-900, #191F28);
    font-size: 0.95rem;
}
.admin-user-card .user-meta {
    font-size: 0.8rem;
    color: var(--gray-500, #8B95A1);
    margin-top: 4px;
}
.admin-user-card .user-reason {
    font-size: 0.82rem;
    color: var(--gray-700, #4E5968);
    margin-top: 8px;
    padding: 8px;
    background: #fff;
    border-radius: var(--radius-sm, 8px);
    border: 1px solid var(--gray-200, #E5E8EB);
}
.status-badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 100px;
    font-size: 0.72rem;
    font-weight: 600;
}
.status-badge.pending {
    background: #FFF3E0;
    color: #E65100;
    border: 1px solid #FFB74D;
}
.status-badge.approved {
    background: #E8F5E9;
    color: #2E7D32;
    border: 1px solid #81C784;
}
.status-badge.rejected {
    background: #FFEBEE;
    color: #C62828;
    border: 1px solid #E57373;
}

</style>
"""


def inject_css():
    """Streamlit 페이지에 커스텀 CSS 주입."""
    import streamlit as st
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
