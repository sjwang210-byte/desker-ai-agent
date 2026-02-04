"""엑셀 업로드 & 컬럼 매핑 페이지."""

import streamlit as st
import pandas as pd
from pathlib import Path

from config import UPLOAD_DIR, DEFAULT_COLUMN_MAPPING, COLUMN_DISPLAY_NAMES, COST_SHEET_TOTAL_COLUMN
from core.database import (
    get_connection, file_exists, insert_file_record,
    insert_cases_bulk, save_column_mapping, load_column_mapping,
)
from core.excel_parser import (
    detect_sheets, extract_headers, parse_data_sheet,
    parse_cost_sheet, get_year_month_from_filename,
)
from core.column_mapper import suggest_mapping, validate_mapping
from utils.file_utils import compute_file_hash, save_uploaded_file

st.header("엑셀 업로드")

# ── 1. 파일 업로드 ──
uploaded_file = st.file_uploader(
    "월별 하자보수비 엑셀 파일을 업로드하세요",
    type=["xlsx", "xls"],
    help="예: 하자보수비(브랜드)_26년01월 1.xlsx",
)

if uploaded_file is None:
    st.info("엑셀 파일을 업로드하면 시트 감지 및 컬럼 매핑이 시작됩니다.")
    st.stop()

# ── 파일 해시 & 중복 확인 ──
file_bytes = uploaded_file.getvalue()
file_hash = compute_file_hash(file_bytes)
conn = get_connection()

if file_exists(conn, file_hash):
    st.warning("이미 업로드된 파일입니다 (동일 파일 해시).")
    st.stop()

# ── 2. 임시 저장 & 시트 감지 ──
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
tmp_path = UPLOAD_DIR / uploaded_file.name
tmp_path.write_bytes(file_bytes)

sheets_info = detect_sheets(tmp_path)

st.subheader("시트 감지 결과")
col1, col2 = st.columns(2)

with col1:
    if sheets_info["data_sheets"]:
        data_sheet_names = [s["name"] for s in sheets_info["data_sheets"]]
        selected_data_sheet = st.selectbox("데이터 시트 선택", data_sheet_names)
    else:
        selected_data_sheet = st.selectbox("데이터 시트 선택", sheets_info["all_sheets"])

with col2:
    if sheets_info["cost_sheets"]:
        cost_sheet_names = [s["name"] for s in sheets_info["cost_sheets"]]
        selected_cost_sheet = st.selectbox("비용 시트 선택", cost_sheet_names)
    else:
        cost_options = ["(없음)"] + sheets_info["all_sheets"]
        selected_cost_sheet = st.selectbox("비용 시트 선택", cost_options)
        if selected_cost_sheet == "(없음)":
            selected_cost_sheet = None

# ── 3. 연-월 감지 ──
auto_ym = get_year_month_from_filename(uploaded_file.name)
year_month = st.text_input(
    "데이터 연-월 (YYYY-MM)",
    value=auto_ym or "",
    help="예: 2026-01",
)
if not year_month:
    st.warning("연-월을 입력해주세요.")
    st.stop()

# ── 4. 컬럼 매핑 ──
st.subheader("컬럼 매핑")

headers = extract_headers(tmp_path, selected_data_sheet)
headers_clean = [h for h in headers if h]

# 기존 매핑 불러오기 시도
saved_mapping = load_column_mapping(conn)
if saved_mapping:
    initial_mapping = saved_mapping
    st.caption("이전 저장된 매핑을 불러왔습니다.")
else:
    initial_mapping = suggest_mapping(headers_clean)
    st.caption("자동 제안된 매핑입니다. 필요 시 수정하세요.")

mapping = {}
options_with_empty = ["(선택 안 함)"] + headers_clean

for key, display in COLUMN_DISPLAY_NAMES.items():
    default_col = initial_mapping.get(key, "")
    if default_col in headers_clean:
        default_idx = headers_clean.index(default_col) + 1  # +1 for "(선택 안 함)"
    else:
        default_idx = 0

    selected = st.selectbox(
        display,
        options_with_empty,
        index=default_idx,
        key=f"map_{key}",
    )
    mapping[key] = selected if selected != "(선택 안 함)" else ""

# ── 매핑 검증 ──
errors = validate_mapping(mapping, headers_clean)
if errors:
    for e in errors:
        st.error(e)

# ── 5. 미리보기 ──
st.subheader("데이터 미리보기")
try:
    active_mapping = {k: v for k, v in mapping.items() if v}
    preview_data = parse_data_sheet(tmp_path, selected_data_sheet, active_mapping)

    if preview_data:
        # 매핑된 컬럼만 추출하여 미리보기
        preview_cols = ["row_number"] + [k for k in active_mapping.keys()]
        preview_df = pd.DataFrame(preview_data)
        display_cols = [c for c in preview_cols if c in preview_df.columns]
        st.dataframe(preview_df[display_cols].head(10), use_container_width=True)
        st.caption(f"총 {len(preview_data)}건")
    else:
        st.warning("파싱된 데이터가 없습니다.")
except Exception as e:
    st.error(f"파싱 오류: {e}")
    preview_data = []

# ── 비용 시트 미리보기 ──
total_cost = None
if selected_cost_sheet:
    try:
        total_cost = parse_cost_sheet(tmp_path, selected_cost_sheet, COST_SHEET_TOTAL_COLUMN)
        if total_cost:
            st.metric("월 총 하자보수비", f"{total_cost:,.0f}원")
    except Exception as e:
        st.warning(f"비용 시트 파싱 오류: {e}")

# ── 6. DB 저장 ──
st.divider()
if st.button("DB에 저장", type="primary", disabled=bool(errors) or not preview_data):
    try:
        with st.spinner("저장 중..."):
            # 파일 레코드
            file_id = insert_file_record(
                conn,
                filename=uploaded_file.name,
                file_hash=file_hash,
                year_month=year_month,
                sheet_name_data=selected_data_sheet,
                sheet_name_cost=selected_cost_sheet or "",
                total_cost=total_cost,
                row_count=len(preview_data),
            )

            # 케이스 레코드 — year_month 주입
            for rec in preview_data:
                rec["year_month"] = year_month

            insert_cases_bulk(conn, file_id, preview_data)

            # 컬럼 매핑 저장
            save_column_mapping(conn, {k: v for k, v in mapping.items() if v})

            conn.commit()

        st.success(f"{len(preview_data)}건이 성공적으로 저장되었습니다. (파일 ID: {file_id})")
        st.balloons()

    except Exception as e:
        conn.rollback()
        st.error(f"저장 실패: {e}")
    finally:
        conn.close()
