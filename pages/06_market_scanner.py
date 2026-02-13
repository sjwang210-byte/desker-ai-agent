"""가구 시장 스캐너 — URL 입력 → 제품 정보 자동 추출 → 비교 분석."""

import streamlit as st

from config import SCANNER_MAX_URLS
from core.scraper import validate_url, fetch_pages_batch, clean_html
from core.llm_client import extract_products_batch, compare_products
from components.scanner_components import (
    render_product_card,
    render_comparison_table,
    render_usp_analysis,
    export_comparison_to_excel,
)

st.header("가구 시장 스캐너")
st.caption("경쟁 제품 URL을 입력하면 제품 정보를 자동 수집·비교합니다.")

# ── 세션 상태 초기화 ──
if "scanner_results" not in st.session_state:
    st.session_state.scanner_results = []
if "scanner_comparison" not in st.session_state:
    st.session_state.scanner_comparison = None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 1: URL 입력
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.subheader("1. 제품 URL 입력")
st.markdown(f"조사할 가구 제품 페이지 URL을 입력하세요 (최대 **{SCANNER_MAX_URLS}개**, 줄바꿈으로 구분).")

url_input = st.text_area(
    "URL 목록",
    height=200,
    placeholder="https://ohou.se/productions/12345\nhttps://www.coupang.com/vp/products/...\nhttps://brand-site.com/product/...",
    label_visibility="collapsed",
)

# URL 파싱 및 검증
raw_urls = [u.strip() for u in url_input.strip().split("\n") if u.strip()]

if raw_urls:
    if len(raw_urls) > SCANNER_MAX_URLS:
        st.error(f"URL은 최대 {SCANNER_MAX_URLS}개까지 입력할 수 있습니다. (현재 {len(raw_urls)}개)")
    else:
        invalid = [u for u in raw_urls if not validate_url(u)]
        if invalid:
            st.warning("유효하지 않은 URL이 포함되어 있습니다:")
            for u in invalid:
                st.code(u)

        valid_urls = [u for u in raw_urls if validate_url(u)]
        st.info(f"유효한 URL: **{len(valid_urls)}개** / 입력: {len(raw_urls)}개")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 2: 분석 실행
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
valid_urls = [u for u in raw_urls if validate_url(u)]

if st.button("분석 시작", type="primary", disabled=len(valid_urls) == 0):
    st.session_state.scanner_results = []
    st.session_state.scanner_comparison = None

    progress_bar = st.progress(0, text="준비 중...")
    status_container = st.empty()

    total_steps = len(valid_urls) * 2  # fetch + extract

    def update_progress(current, total, phase):
        if phase == "fetch":
            pct = current / total_steps
            progress_bar.progress(pct, text=f"페이지 가져오는 중... ({current}/{total})")
        elif phase == "extract":
            pct = (len(valid_urls) + current) / total_steps
            progress_bar.progress(pct, text=f"AI 분석 중... ({current}/{total})")

    # 2-1. 페이지 가져오기
    with st.spinner("웹 페이지를 가져오는 중..."):
        fetch_results = fetch_pages_batch(valid_urls, progress_callback=update_progress)

    # 2-2. HTML 정제 및 준비
    urls_and_content = []
    fetch_errors = []

    for result in fetch_results:
        if result["error"]:
            fetch_errors.append(result)
            continue

        structured_data, page_content, image_url = clean_html(result["html"], result["url"])
        urls_and_content.append({
            "url": result["url"],
            "structured_data": structured_data,
            "page_content": page_content,
            "image_url": image_url,
        })

    # 가져오기 실패 URL 표시
    if fetch_errors:
        with status_container.container():
            st.warning(f"{len(fetch_errors)}개 URL에서 페이지를 가져오지 못했습니다:")
            for err in fetch_errors:
                st.markdown(f"- `{err['url']}` — {err['error']}")

    # 2-3. Claude AI 추출
    if urls_and_content:
        with st.spinner("AI가 제품 정보를 분석하는 중..."):
            extracted = extract_products_batch(urls_and_content, progress_callback=update_progress)

        # 가져오기 실패한 URL도 결과에 포함
        for err in fetch_errors:
            extracted.append({
                "url": err["url"],
                "product_name": "가져오기 실패",
                "brand": "-",
                "price": 0,
                "price_display": "-",
                "image_url": "",
                "country_of_origin": "-",
                "materials": "-",
                "options": [],
                "size": "-",
                "review_summary": {},
                "notable_features": [],
                "error": True,
                "error_message": err["error"],
            })

        st.session_state.scanner_results = extracted
        progress_bar.progress(1.0, text="분석 완료!")
    else:
        st.error("모든 URL에서 페이지를 가져오지 못했습니다.")
        progress_bar.empty()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹션 3: 결과 표시
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
results = st.session_state.scanner_results

if results:
    st.divider()
    st.subheader("2. 제품 정보")

    # 성공/실패 카운트
    success = [r for r in results if not r.get("error")]
    errors = [r for r in results if r.get("error")]

    if success:
        st.success(f"**{len(success)}개** 제품 정보를 추출했습니다.")
    if errors:
        st.warning(f"**{len(errors)}개** URL에서 추출에 실패했습니다.")

    # 제품 카드
    for i, product in enumerate(results, 1):
        render_product_card(product, i)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 섹션 4: 비교 테이블
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    st.divider()
    st.subheader("3. 제품 비교표")

    df = render_comparison_table(results)

    if not df.empty:
        # 엑셀 다운로드
        excel_data = export_comparison_to_excel(results)
        st.download_button(
            label="엑셀 다운로드",
            data=excel_data,
            file_name="가구_시장조사_비교표.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 섹션 5: AI 비교 분석
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if len(success) >= 2:
        st.divider()
        st.subheader("4. AI 경쟁 분석")
        st.caption("Claude AI가 제품들의 고유 판매 포인트(USP)와 시장 포지셔닝을 분석합니다.")

        if st.button("경쟁 분석 실행"):
            with st.spinner("AI가 제품을 비교 분석하는 중..."):
                comparison = compare_products(success)
                st.session_state.scanner_comparison = comparison

        if st.session_state.scanner_comparison:
            render_usp_analysis(st.session_state.scanner_comparison)
