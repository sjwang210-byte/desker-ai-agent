"""분석 대시보드 페이지."""

import streamlit as st

from config import SPECIAL_CASE_THRESHOLD
from core.database import get_connection, get_uploaded_months, get_cases_by_month
from core.aggregator import (
    product_tag_matrix, month_over_month, multi_month_trend,
    detect_anomalies, get_special_cases, get_cost_comparison,
)
from components.charts import (
    bar_chart_product_cases, heatmap_product_cause, line_chart_trend,
    line_chart_cost_trend, pie_chart_judgment_types, waterfall_chart_mom,
    multi_line_by_subject,
)

st.header("분석 대시보드")

conn = get_connection()
months = get_uploaded_months(conn)

if not months:
    st.info("먼저 데이터를 업로드하세요.")
    st.stop()

# ── 탭 ──
tab1, tab2, tab3, tab4 = st.tabs(["월별 현황", "전월 비교", "추세 분석", "특이 품목"])

# ═══════════════════════════════════════
# 탭 1: 월별 현황
# ═══════════════════════════════════════
with tab1:
    selected_month = st.selectbox("월 선택", months, key="tab1_month")
    cases = get_cases_by_month(conn, selected_month)
    pt_matrix = product_tag_matrix(conn, selected_month)

    # 요약 카드
    cost_row = conn.execute(
        "SELECT total_cost FROM uploaded_files WHERE year_month = ?",
        (selected_month,),
    ).fetchone()
    total_cost = cost_row["total_cost"] if cost_row and cost_row["total_cost"] else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("총 건수", f"{len(cases)}건")
    c2.metric("하자보수비", f"{total_cost:,.0f}원")
    c3.metric("태깅 건수", f"{pt_matrix['total_cases']}건")

    # 차트
    col_left, col_right = st.columns(2)
    with col_left:
        if pt_matrix["products"]:
            fig = bar_chart_product_cases(pt_matrix)
            st.plotly_chart(fig, use_container_width=True, theme=None)
    with col_right:
        if cases:
            fig = pie_chart_judgment_types(cases)
            st.plotly_chart(fig, use_container_width=True, theme=None)

    # 히트맵
    if pt_matrix["products"] and pt_matrix["tags"]:
        fig = heatmap_product_cause(pt_matrix)
        st.plotly_chart(fig, use_container_width=True, theme=None)

# ═══════════════════════════════════════
# 탭 2: 전월 비교
# ═══════════════════════════════════════
with tab2:
    if len(months) < 2:
        st.info("전월 비교를 위해 2개월 이상의 데이터가 필요합니다.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            current = st.selectbox("당월", months, index=0, key="mom_current")
        with c2:
            prev_options = [m for m in months if m != current]
            previous = st.selectbox("전월", prev_options, key="mom_previous")

        # 비용 비교
        cost_cmp = get_cost_comparison(conn, current, previous)
        c1, c2, c3 = st.columns(3)
        c1.metric("당월 비용", f"{cost_cmp['current_cost']:,.0f}원")
        c2.metric("전월 비용", f"{cost_cmp['previous_cost']:,.0f}원")
        c3.metric(
            "증감",
            f"{cost_cmp['delta']:+,.0f}원",
            delta=f"{cost_cmp['delta_pct']:+.1f}%",
        )

        # 건수 비교
        mom = month_over_month(conn, current, previous)
        c1, c2, c3 = st.columns(3)
        c1.metric("당월 건수", f"{mom['current_total']}건")
        c2.metric("전월 건수", f"{mom['previous_total']}건")
        c3.metric("증감", f"{mom['delta']:+d}건", delta=f"{mom['delta_pct']:+.1f}%")

        # 워터폴 차트
        fig = waterfall_chart_mom(mom)
        st.plotly_chart(fig, use_container_width=True, theme=None)

        # 주요 증가 원인
        if mom["top_increases"]:
            st.subheader("주요 증가 원인 (품목 × 태그)")
            import pandas as pd
            inc_df = pd.DataFrame(
                mom["top_increases"],
                columns=["품목군", "원인 태그", "증가 건수"],
            )
            st.dataframe(inc_df, use_container_width=True)

# ═══════════════════════════════════════
# 탭 3: 추세 분석
# ═══════════════════════════════════════
with tab3:
    if len(months) < 2:
        st.info("추세 분석을 위해 2개월 이상의 데이터가 필요합니다.")
    else:
        selected_months = st.multiselect(
            "분석 기간 선택",
            months,
            default=months,
            key="trend_months",
        )
        if len(selected_months) < 2:
            st.warning("2개월 이상 선택하세요.")
        else:
            selected_months.sort()
            trend = multi_month_trend(conn, selected_months)

            # 건수 추이
            fig = line_chart_trend(trend, "월별 하자보수비 건수 추이")
            st.plotly_chart(fig, use_container_width=True, theme=None)

            # 비용 추이
            fig = line_chart_cost_trend(trend, "월별 하자보수비 금액 추이")
            st.plotly_chart(fig, use_container_width=True, theme=None)

            # 품목별 추이
            st.subheader("품목군별 추이")
            fig = multi_line_by_subject(trend, "by_product_month", "품목군별 월 추이 (상위 10)")
            st.plotly_chart(fig, use_container_width=True, theme=None)

            # 태그별 추이
            st.subheader("원인 태그별 추이")
            fig = multi_line_by_subject(trend, "by_tag_month", "원인별 월 추이 (상위 10)")
            st.plotly_chart(fig, use_container_width=True, theme=None)

            # 이상 징후
            anomalies = detect_anomalies(trend)
            if anomalies:
                st.subheader("이상 징후 탐지")
                for a in anomalies:
                    icon = "📈" if a["type"] == "consecutive_increase" else "⚡"
                    st.warning(f"{icon} **{a['subject']}** — {a['detail']} ({', '.join(a['months'])})")
            else:
                st.success("이상 징후가 감지되지 않았습니다.")

# ═══════════════════════════════════════
# 탭 4: 특이 품목
# ═══════════════════════════════════════
with tab4:
    selected_month_sp = st.selectbox("월 선택", months, key="tab4_month")
    special = get_special_cases(conn, selected_month_sp)

    st.subheader(f"세트교환요구 (월 {SPECIAL_CASE_THRESHOLD}건 이상)")
    if special["exchange"]:
        for product, case_list in special["exchange"].items():
            with st.expander(f"{product} — {len(case_list)}건"):
                import pandas as pd
                df = pd.DataFrame(case_list)
                display_cols = [c for c in ["row_number", "product", "action_notes", "request_details"]
                               if c in df.columns]
                st.dataframe(df[display_cols], use_container_width=True)
    else:
        st.info("해당 건이 없습니다.")

    st.subheader(f"고객 불만 (월 {SPECIAL_CASE_THRESHOLD}건 이상)")
    if special["complaint"]:
        for product, case_list in special["complaint"].items():
            with st.expander(f"{product} — {len(case_list)}건"):
                import pandas as pd
                df = pd.DataFrame(case_list)
                display_cols = [c for c in ["row_number", "product", "action_notes", "request_details"]
                               if c in df.columns]
                st.dataframe(df[display_cols], use_container_width=True)
    else:
        st.info("해당 건이 없습니다.")

conn.close()
