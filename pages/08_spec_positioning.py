"""스펙 기반 포지셔닝 분석 — 엑셀 업로드 / Convex DB 연동 → 가중 점수화 → 포지셔닝 맵 + AI 전략."""

import pandas as pd
import streamlit as st

from core.spec_analyzer import (
    auto_detect_columns,
    calculate_variance_weights,
    calculate_value_index,
    classify_products,
    normalize_and_score,
    parse_spec_excel,
    simulate_our_product,
)
from core.market_research_parser import (
    parse_market_research_excel,
    market_data_to_dataframe,
)
from core.llm_client import analyze_spec_positioning
from components.positioning_charts import (
    build_positioning_map,
    build_weight_bar_chart,
)
from components.positioning_components import (
    render_column_mapping_ui,
    render_weight_sliders,
    render_scored_data_table,
    render_simulation_form,
    render_ai_analysis,
    export_positioning_to_excel,
    export_strategy_report,
)

# ── 페이지 헤더 ──
st.header("스펙 포지셔닝 분석")
st.caption(
    "시장 제품 스펙 데이터를 업로드하면 가중 스펙 점수 기반 "
    "포지셔닝 맵을 생성하고 AI가 전략적 시사점을 분석합니다."
)

# ── 세션 상태 초기화 ──
_DEFAULTS = {
    "spec_raw_df": None,
    "spec_column_config": None,
    "spec_weights": None,
    "spec_scored_df": None,
    "spec_categories": None,
    "spec_our_product": None,
    "spec_ai_analysis": None,
    "spec_market_parsed": None,  # 시장조사 엑셀 파싱 결과
    "spec_selected_category": None,
}
for key, default in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default


def _reset_analysis():
    """분석 관련 상태를 초기화한다."""
    st.session_state.spec_scored_df = None
    st.session_state.spec_categories = None
    st.session_state.spec_our_product = None
    st.session_state.spec_ai_analysis = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 1: 데이터 소스 선택
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.subheader("1. 데이터 소스")

data_source = st.radio(
    "데이터 입력 방식",
    ["시장조사 엑셀 업로드 (전치형)", "일반 스펙 엑셀 업로드 (행=제품)", "Convex DB에서 불러오기"],
    horizontal=True,
    help="시장조사 엑셀: 제품이 열 방향으로 배치된 형식. 일반 엑셀: 제품이 행 방향.",
)

# ── 시장조사 엑셀 업로드 (전치형) ──
if data_source == "시장조사 엑셀 업로드 (전치형)":
    uploaded_file = st.file_uploader(
        "시장조사 엑셀 파일",
        type=["xlsx", "xls"],
        help="(시장조사) 시트가 포함된 엑셀. 제품=열, 속성=행 형식.",
        key="market_upload",
    )

    if uploaded_file:
        with st.spinner("시장조사 엑셀 파싱 중..."):
            parsed = parse_market_research_excel(uploaded_file)
            st.session_state.spec_market_parsed = parsed

        if not parsed["categories"]:
            st.error("'(시장조사)' 시트를 찾을 수 없습니다. 시트명에 '(시장조사)'가 포함되어야 합니다.")
        else:
            st.success(
                f"파싱 완료: **{len(parsed['categories'])}개 카테고리**, "
                f"총 **{sum(len(c['products']) for c in parsed['categories'])}개 제품**"
            )

            # Convex DB 업로드 옵션
            with st.expander("Convex DB에 저장", expanded=False):
                if st.button("DB에 업로드", type="secondary"):
                    try:
                        from core.convex_market_client import upload_market_research
                        progress = st.progress(0, text="업로드 준비 중...")

                        def _progress(current, total, msg):
                            progress.progress(
                                current / total if total > 0 else 0, text=msg,
                            )

                        session_id = upload_market_research(parsed, progress_callback=_progress)
                        progress.progress(1.0, text="업로드 완료!")
                        st.success(f"Convex DB 저장 완료 (Session: {session_id})")
                    except Exception as e:
                        st.error(f"DB 업로드 실패: {e}")

            # 카테고리 선택
            cat_names = [c["name"] for c in parsed["categories"]]
            selected_cat = st.selectbox(
                "분석할 카테고리 선택", cat_names, key="spec_cat_select",
            )

            if selected_cat:
                cat_data = next(c for c in parsed["categories"] if c["name"] == selected_cat)
                raw_df = market_data_to_dataframe(cat_data)
                st.session_state.spec_raw_df = raw_df
                st.session_state.spec_selected_category = selected_cat
                _reset_analysis()

                st.info(f"**{selected_cat}**: {len(cat_data['products'])}개 제품, 스펙 필드: {', '.join(cat_data['spec_fields']) or '(공통 필드만)'}")
                st.dataframe(raw_df, use_container_width=True, hide_index=True)

# ── 일반 스펙 엑셀 업로드 ──
elif data_source == "일반 스펙 엑셀 업로드 (행=제품)":
    uploaded_file = st.file_uploader(
        "스펙 엑셀 파일",
        type=["xlsx", "xls"],
        help="첫 행은 헤더. 제품명, 가격 + 스펙 컬럼들로 구성.",
        key="general_upload",
    )

    if uploaded_file:
        with st.spinner("엑셀 파싱 중..."):
            raw_df = parse_spec_excel(uploaded_file)
            st.session_state.spec_raw_df = raw_df
            _reset_analysis()

        st.success(f"파싱 완료: **{len(raw_df)}개 제품**, **{len(raw_df.columns)}개 컬럼**")
        st.dataframe(raw_df.head(10), use_container_width=True, hide_index=True)

# ── Convex DB에서 불러오기 ──
elif data_source == "Convex DB에서 불러오기":
    try:
        from core.convex_market_client import (
            list_sessions, get_categories, get_products_by_category,
        )

        sessions = list_sessions()
        if not sessions:
            st.info("저장된 시장조사 데이터가 없습니다. 먼저 엑셀을 업로드해주세요.")
        else:
            # 세션 선택
            session_options = {
                f"{s['filename']} ({s['totalProducts']}개 제품)": s["_id"]
                for s in sessions
            }
            selected_label = st.selectbox(
                "데이터셋 선택", list(session_options.keys()), key="db_session_select",
            )
            session_id = session_options[selected_label]

            # 카테고리 목록
            categories = get_categories(session_id)
            if categories:
                cat_options = {c["name"]: c["_id"] for c in categories}
                selected_cat_name = st.selectbox(
                    "카테고리 선택", list(cat_options.keys()), key="db_cat_select",
                )
                category_id = cat_options[selected_cat_name]

                if st.button("데이터 불러오기", type="primary"):
                    with st.spinner("DB에서 데이터 로드 중..."):
                        products = get_products_by_category(category_id)
                        cat_info = next(c for c in categories if c["_id"] == category_id)

                        # Convex 데이터 → DataFrame 변환
                        rows = []
                        for p in products:
                            row = {
                                "제품명": p["name"],
                                "브랜드": p["brand"],
                                "가격": p.get("actualPrice") or p["price"],
                            }
                            specs = p.get("specs", {})
                            if isinstance(specs, dict):
                                for k, v in specs.items():
                                    try:
                                        row[k] = float(v)
                                    except (ValueError, TypeError):
                                        row[k] = v
                            rows.append(row)

                        raw_df = pd.DataFrame(rows)
                        st.session_state.spec_raw_df = raw_df
                        st.session_state.spec_selected_category = selected_cat_name
                        _reset_analysis()

                    st.success(f"로드 완료: **{len(raw_df)}개 제품**")
                    st.dataframe(raw_df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Convex 연결 실패: {e}")
        st.caption("CONVEX_URL 환경변수를 확인해주세요.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 2: 컬럼 인식
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if st.session_state.spec_raw_df is not None:
    st.divider()
    st.subheader("2. 컬럼 인식")

    raw_df = st.session_state.spec_raw_df
    auto_config = auto_detect_columns(raw_df)

    config = render_column_mapping_ui(raw_df, auto_config)
    st.session_state.spec_column_config = config


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 3: 스펙 가중치 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if (
    st.session_state.spec_column_config
    and st.session_state.spec_column_config.get("spec_cols")
):
    st.divider()
    st.subheader("3. 스펙 가중치 설정")

    config = st.session_state.spec_column_config
    spec_cols = config["spec_cols"]
    raw_df = st.session_state.spec_raw_df

    # 기본 가중치 계산
    default_weights = calculate_variance_weights(raw_df, spec_cols)

    weight_mode = st.radio(
        "가중치 모드",
        ["자동 (분산 기반)", "수동 조정"],
        horizontal=True,
        help="자동: 제품 간 차이가 큰 항목에 높은 가중치 부여. 수동: 직접 슬라이더로 조정.",
    )

    if weight_mode == "수동 조정":
        weights = render_weight_sliders(spec_cols, default_weights)
    else:
        weights = default_weights
        fig_w = build_weight_bar_chart(weights)
        st.plotly_chart(fig_w, use_container_width=True, theme=None)

    st.session_state.spec_weights = weights


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 4: 분석 결과
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if st.session_state.spec_weights and st.session_state.spec_column_config:
    config = st.session_state.spec_column_config
    weights = st.session_state.spec_weights
    raw_df = st.session_state.spec_raw_df

    if config.get("spec_cols") and config.get("product_col") and config.get("price_col"):
        # 점수 계산
        scored_df = normalize_and_score(raw_df, config, weights)

        # 가치 지수 추가
        scored_df["value_index"] = calculate_value_index(scored_df, config["price_col"])

        # 제품 분류
        categories = classify_products(
            scored_df, config["product_col"], config["price_col"],
        )

        st.session_state.spec_scored_df = scored_df
        st.session_state.spec_categories = categories

        st.divider()
        st.subheader("4. 분석 결과")

        # 요약 지표
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("제품 수", f"{len(scored_df)}개")
        mc2.metric("스펙 항목", f"{len(config['spec_cols'])}개")
        mc3.metric("평균 스펙 점수", f"{scored_df['spec_score'].mean():.1f}")
        price_min = scored_df[config["price_col"]].min()
        price_max = scored_df[config["price_col"]].max()
        mc4.metric("가격 범위", f"{price_min:,.0f} ~ {price_max:,.0f}")

        tab1, tab2, tab3 = st.tabs(["데이터 테이블", "포지셔닝 맵", "AI 전략 분석"])

        # ── 탭 1: 데이터 테이블 ──
        with tab1:
            render_scored_data_table(scored_df, config, categories)

        # ── 탭 2: 포지셔닝 맵 ──
        with tab2:
            fig = build_positioning_map(
                scored_df, config, categories,
                our_product=st.session_state.spec_our_product,
            )
            st.plotly_chart(fig, use_container_width=True, theme=None)

            # PNG 다운로드
            try:
                img_bytes = fig.to_image(
                    format="png", width=1200, height=800, scale=2.5,
                )
                st.download_button(
                    "포지셔닝 맵 다운로드 (PNG)",
                    data=img_bytes,
                    file_name="positioning_map.png",
                    mime="image/png",
                )
            except Exception:
                st.caption(
                    "PNG 다운로드를 사용하려면 `pip install kaleido` 를 실행하세요."
                )

        # ── 탭 3: AI 전략 분석 ──
        with tab3:
            st.caption("Claude AI가 스펙-가격 데이터를 분석하여 전략적 시사점을 도출합니다.")

            if st.button("AI 전략 분석 실행", type="primary"):
                with st.spinner("AI가 시장 포지셔닝을 분석하는 중..."):
                    analysis = analyze_spec_positioning(
                        scored_df, config, categories, weights,
                        our_product=st.session_state.spec_our_product,
                    )
                    st.session_state.spec_ai_analysis = analysis

            if st.session_state.spec_ai_analysis:
                render_ai_analysis(st.session_state.spec_ai_analysis)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 5: 우리 제품 시뮬레이션
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if st.session_state.spec_scored_df is not None:
    st.divider()
    st.subheader("5. 우리 제품 시뮬레이션")
    st.caption("예상 스펙과 가격을 입력하면 포지셔닝 맵에서의 위치를 시뮬레이션합니다.")

    config = st.session_state.spec_column_config
    raw_df = st.session_state.spec_raw_df

    our_specs = render_simulation_form(config, raw_df)

    if our_specs:
        our_result = simulate_our_product(
            our_specs,
            st.session_state.spec_scored_df,
            config,
            st.session_state.spec_weights,
        )
        st.session_state.spec_our_product = our_result

        # 시뮬레이션 결과 표시
        st.markdown("---")
        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric("스펙 점수", f"{our_result['spec_score']:.1f}")
        rc2.metric("포지셔닝", our_result["category"])
        rc3.metric("순위", f"{our_result['rank']}위 / {len(st.session_state.spec_scored_df) + 1}개")
        rc4.metric("가치 지수", f"{our_result['value_index']:.1f}")

        st.info(
            f"**{our_result['product_name']}**은(는) 가격 {our_result['price']:,}원, "
            f"스펙 점수 {our_result['spec_score']:.1f}점으로 "
            f"**{our_result['category']}** 영역에 위치합니다. "
            f"(상위 {our_result['percentile']:.0f}%)"
        )
        st.caption("위의 '포지셔닝 맵' 탭에서 맵 위의 위치를 확인하세요.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 6: 내보내기
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if st.session_state.spec_scored_df is not None:
    st.divider()
    st.subheader("6. 내보내기")

    scored_df = st.session_state.spec_scored_df
    config = st.session_state.spec_column_config
    weights = st.session_state.spec_weights

    col_e1, col_e2, col_e3 = st.columns(3)

    with col_e1:
        csv = scored_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "CSV 다운로드",
            data=csv,
            file_name="cleaned_market_data.csv",
            mime="text/csv",
        )

    with col_e2:
        excel_bytes = export_positioning_to_excel(scored_df, weights, config)
        st.download_button(
            "엑셀 다운로드",
            data=excel_bytes,
            file_name="spec_positioning_analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with col_e3:
        if st.session_state.spec_ai_analysis:
            report_text = export_strategy_report(st.session_state.spec_ai_analysis)
            st.download_button(
                "전략 보고서 (TXT)",
                data=report_text.encode("utf-8"),
                file_name="strategy_report.txt",
                mime="text/plain",
            )
        else:
            st.download_button(
                "전략 보고서 (TXT)",
                data="AI 전략 분석을 먼저 실행해주세요.",
                file_name="strategy_report.txt",
                mime="text/plain",
                disabled=True,
            )
