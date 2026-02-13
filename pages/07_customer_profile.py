"""고객 프로파일 분석 페이지.

상품별 고객 프로파일(자녀나이, 결혼상태, 가구당인원) 엑셀을
업로드하면 카테고리별 속성값 비중(%)을 자동 계산한다.
"""

import pandas as pd
import streamlit as st

from config import (
    PROFILE_CATEGORY_LEVELS,
    PROFILE_DIMENSIONS,
    PROFILE_DEFAULT_METRIC,
    PROFILE_PAYMENT_METRICS,
    PROFILE_UNKNOWN_VALUE,
)
from core.profile_analyzer import (
    compute_integrated_view,
    compute_percentage_distribution,
    get_available_categories,
    get_child_level,
    get_drilldown_data,
    identify_file_type,
    parse_date_range,
    parse_profile_excel,
)
from components.profile_charts import (
    grouped_bar_integrated,
    pie_chart,
    stacked_bar_chart,
)
from components.profile_components import (
    export_profile_to_excel,
    render_drilldown_selector,
    render_integrated_view,
    render_percentage_table,
    render_upload_status,
)

# ── 페이지 헤더 ──
st.header("고객 프로파일 분석")
st.caption(
    "상품별 고객 프로파일(자녀나이, 결혼상태, 가구당인원) 데이터를 "
    "업로드하고 카테고리별 비중을 분석합니다."
)

# ── 세션 상태 초기화 ──
if "profile_data" not in st.session_state:
    st.session_state.profile_data: dict = {}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 1: 데이터 업로드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.subheader("1. 데이터 업로드")

uploaded_files = st.file_uploader(
    "고객 프로파일 엑셀 파일 업로드 (최대 3개)",
    type=["xlsx", "xls"],
    accept_multiple_files=True,
    help="파일명 패턴: 상품_고객프로파일_{속성}_{시작일}_{종료일}.xlsx",
)

if uploaded_files:
    for uf in uploaded_files:
        # 이미 파싱된 파일은 건너뜀 (파일명 기준)
        already_loaded = any(
            d.get("filename") == uf.name
            for d in st.session_state.profile_data.values()
        )
        if already_loaded:
            continue

        # 차원 자동 식별
        dimension = identify_file_type(uf.name)
        if dimension is None:
            try:
                tmp_df = pd.read_excel(uf, nrows=5, engine="openpyxl")
                dimension = identify_file_type(uf.name, tmp_df)
                uf.seek(0)  # 읽기 위치 리셋
            except Exception:
                pass

        if dimension is None:
            st.error(f"파일 유형을 인식할 수 없습니다: {uf.name}")
            continue

        with st.spinner(f"'{dimension}' 파일 파싱 중..."):
            try:
                df = parse_profile_excel(uf, dimension)
                date_range = parse_date_range(uf.name)
                st.session_state.profile_data[dimension] = {
                    "df": df,
                    "attribute_values": PROFILE_DIMENSIONS[dimension],
                    "date_range": date_range,
                    "filename": uf.name,
                }
                st.success(f"'{dimension}' 파일 파싱 완료 ({len(df):,}행)")
            except Exception as e:
                st.error(f"'{uf.name}' 파싱 오류: {e}")

# 업로드 상태 표시
if st.session_state.profile_data:
    render_upload_status(st.session_state.profile_data)

    # 초기화 버튼
    if st.button("데이터 초기화", type="secondary"):
        st.session_state.profile_data = {}
        st.rerun()
else:
    st.info(
        "엑셀 파일을 업로드하면 파일명 또는 컬럼 헤더로 "
        "자녀나이/결혼상태/가구당인원을 자동 인식합니다."
    )
    st.stop()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 2: 분석 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.divider()
st.subheader("2. 분석 설정")

available_dims = list(st.session_state.profile_data.keys())

col1, col2 = st.columns(2)

with col1:
    selected_dimension = st.selectbox(
        "분석 차원",
        available_dims,
        key="profile_dim",
    )
    selected_level = st.selectbox(
        "집계 수준",
        PROFILE_CATEGORY_LEVELS,
        index=1,  # 기본값: 중분류
        key="profile_level",
    )

with col2:
    selected_metric = st.radio(
        "지표",
        PROFILE_PAYMENT_METRICS,
        index=PROFILE_PAYMENT_METRICS.index(PROFILE_DEFAULT_METRIC),
        key="profile_metric",
        horizontal=True,
    )
    c2a, c2b = st.columns(2)
    with c2a:
        exclude_unknown = st.checkbox(
            "(알수없음) 제외", value=True, key="profile_excl",
        )
    with c2b:
        show_absolute = st.checkbox(
            "절대값 함께 표시", value=False, key="profile_abs",
        )

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 3: 분석 결과
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
dim_data = st.session_state.profile_data[selected_dimension]
attr_values = [
    a for a in dim_data["attribute_values"]
    if not (exclude_unknown and a == PROFILE_UNKNOWN_VALUE)
]

result_df = compute_percentage_distribution(
    dim_data["df"],
    selected_level,
    selected_metric,
    exclude_unknown,
)

st.divider()
st.subheader("3. 분석 결과")

# 요약 지표
mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("카테고리 수", f"{len(result_df)}개")
mc2.metric("분석 차원", selected_dimension)
mc3.metric("집계 수준", selected_level)
mc4.metric("지표", selected_metric)

tab1, tab2, tab3 = st.tabs(["테이블 보기", "차트 보기", "통합 보기"])

# ── Tab 1: 테이블 보기 ──
with tab1:
    render_percentage_table(result_df, attr_values, show_absolute)

    # 엑셀 다운로드
    excel_bytes = export_profile_to_excel(
        result_df, selected_dimension, selected_metric,
        selected_level, attr_values,
    )
    st.download_button(
        "엑셀 다운로드",
        data=excel_bytes,
        file_name=(
            f"고객프로파일_{selected_dimension}"
            f"_{selected_level}_{selected_metric}.xlsx"
        ),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    # 드릴다운
    st.divider()
    st.markdown("**드릴다운 분석**")
    child_level = get_child_level(selected_level)
    drill_category = render_drilldown_selector(
        result_df, selected_level, child_level,
    )

    if drill_category and child_level:
        drill_df = get_drilldown_data(
            dim_data["df"],
            selected_metric,
            exclude_unknown,
            selected_level,
            drill_category,
        )
        if not drill_df.empty:
            st.markdown(
                f"**{selected_level}: {drill_category}** → "
                f"**{child_level}** 하위 분석"
            )
            render_percentage_table(drill_df, attr_values, show_absolute)

            # 드릴다운 차트
            fig = stacked_bar_chart(
                drill_df, attr_values,
                title=f"{drill_category} → {child_level} 분포",
            )
            st.plotly_chart(fig, use_container_width=True, theme=None)
        else:
            st.info("하위 데이터가 없습니다.")

# ── Tab 2: 차트 보기 ──
with tab2:
    chart_type = st.radio(
        "차트 유형",
        ["가로 막대", "세로 막대", "파이"],
        horizontal=True,
        key="chart_type",
    )

    if chart_type in ("가로 막대", "세로 막대"):
        orientation = "h" if chart_type == "가로 막대" else "v"
        fig = stacked_bar_chart(
            result_df,
            attr_values,
            title=f"{selected_dimension} / {selected_level} / {selected_metric} 분포",
            orientation=orientation,
        )
        st.plotly_chart(fig, use_container_width=True, theme=None)

    elif chart_type == "파이":
        if result_df.empty:
            st.info("데이터가 없습니다.")
        else:
            pie_category = st.selectbox(
                "카테고리 선택",
                result_df["category"].tolist(),
                key="pie_category",
            )
            fig = pie_chart(result_df, pie_category, attr_values)
            st.plotly_chart(fig, use_container_width=True, theme=None)

# ── Tab 3: 통합 보기 ──
with tab3:
    if len(st.session_state.profile_data) < 2:
        st.info("통합 분석을 위해 2개 이상의 프로파일 파일을 업로드하세요.")
    else:
        all_dfs = {
            dim: data["df"]
            for dim, data in st.session_state.profile_data.items()
        }

        # 카테고리 목록 (첫 번째 차원 기준)
        first_df = list(all_dfs.values())[0]
        categories = get_available_categories(first_df, selected_level)

        if not categories:
            st.info("해당 집계 수준에 카테고리가 없습니다.")
        else:
            int_category = st.selectbox(
                "카테고리 선택", categories, key="int_category",
            )

            if int_category:
                integrated = compute_integrated_view(
                    all_dfs,
                    selected_level,
                    int_category,
                    selected_metric,
                    exclude_unknown,
                )

                # 차트
                fig = grouped_bar_integrated(integrated, int_category)
                st.plotly_chart(fig, use_container_width=True, theme=None)

                # 메트릭 카드
                st.divider()
                render_integrated_view(
                    integrated, int_category, selected_metric,
                )
