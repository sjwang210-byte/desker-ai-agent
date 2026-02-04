"""보고서 생성 & 내보내기 페이지."""

import streamlit as st

from core.database import get_connection, get_uploaded_months
from core.report_generator import generate_full_report
from core.aggregator import product_tag_matrix
from utils.export_utils import export_report_to_excel, export_report_to_word

st.header("보고서 생성")

conn = get_connection()
months = get_uploaded_months(conn)

if not months:
    st.info("먼저 데이터를 업로드하세요.")
    st.stop()

# ── 월 선택 ──
c1, c2 = st.columns(2)
with c1:
    current_month = st.selectbox("당월", months, index=0, key="report_current")
with c2:
    prev_options = [m for m in months if m != current_month]
    if prev_options:
        previous_month = st.selectbox("전월", prev_options, key="report_previous")
    else:
        st.warning("전월 비교를 위해 2개월 이상의 데이터가 필요합니다.")
        previous_month = None

st.divider()

# ── 보고서 생성 ──
if previous_month and st.button("보고서 생성", type="primary"):
    with st.spinner("보고서 생성 중..."):
        try:
            result = generate_full_report(conn, current_month, previous_month)
            st.session_state["report_result"] = result
            st.session_state["report_month"] = current_month
            st.session_state["report_prev_month"] = previous_month
        except Exception as e:
            st.error(f"보고서 생성 오류: {e}")

# ── 결과 표시 ──
if "report_result" in st.session_state:
    result = st.session_state["report_result"]
    context = result.get("context", {})

    # 핵심 발견사항
    findings = result.get("key_findings", [])
    if findings:
        st.subheader("핵심 발견사항")
        for f in findings:
            st.markdown(f"- {f}")

    st.divider()

    # 보고서 멘트 (편집 가능)
    st.subheader("보고서 멘트")
    report_text = st.text_area(
        "보고서 내용 (편집 가능)",
        value=result.get("report_text", ""),
        height=500,
        key="report_text_area",
    )

    # 내보내기 버튼
    st.divider()
    st.subheader("내보내기")

    col1, col2, col3 = st.columns(3)

    with col1:
        # 엑셀 내보내기
        try:
            matrix = product_tag_matrix(
                conn, st.session_state.get("report_month", "")
            )
        except Exception:
            matrix = None

        excel_data = export_report_to_excel(report_text, context, matrix)
        st.download_button(
            "Excel 다운로드",
            data=excel_data,
            file_name=f"하자보수비_보고서_{context.get('current_month', '')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col2:
        # 워드 내보내기
        word_data = export_report_to_word(report_text, context)
        st.download_button(
            "Word 다운로드",
            data=word_data,
            file_name=f"하자보수비_보고서_{context.get('current_month', '')}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    with col3:
        # 클립보드 복사 (Streamlit은 직접 클립보드 지원 안 함 → 텍스트 표시)
        if st.button("텍스트 복사용 표시"):
            st.code(report_text, language=None)

conn.close()
