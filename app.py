"""데스커 월말 하자보수비 분석·보고 AI 에이전트 — Streamlit 진입점."""

import streamlit as st
from core.database import init_db, get_connection

# ── 페이지 설정 ──
st.set_page_config(
    page_title="데스커 하자보수비 분석",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── DB 초기화 (최초 1회) ──
if "db_initialized" not in st.session_state:
    init_db()
    st.session_state.db_initialized = True

# ── 멀티페이지 네비게이션 ──
pages = {
    "데이터 관리": [
        st.Page("pages/01_upload.py", title="엑셀 업로드", icon="📂"),
        st.Page("pages/02_tagging.py", title="원인 태깅", icon="🏷️"),
        st.Page("pages/03_dictionary.py", title="태그 사전 관리", icon="📖"),
    ],
    "분석 & 보고": [
        st.Page("pages/04_analysis.py", title="분석 대시보드", icon="📊"),
        st.Page("pages/05_report.py", title="보고서 생성", icon="📝"),
    ],
}

nav = st.navigation(pages)
nav.run()
