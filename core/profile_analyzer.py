"""고객 프로파일 엑셀 파싱 및 비중 분석 로직."""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

import pandas as pd

from config import (
    PROFILE_DIMENSIONS,
    PROFILE_CATEGORY_COLUMNS,
    PROFILE_PAYMENT_METRICS,
    PROFILE_REFUND_METRICS,
    PROFILE_UNKNOWN_VALUE,
)

ALL_METRICS = PROFILE_PAYMENT_METRICS + PROFILE_REFUND_METRICS


# ───────────────────────────────────────────
# 파일 식별
# ───────────────────────────────────────────

def identify_file_type(
    filename: str,
    df: pd.DataFrame | None = None,
) -> str | None:
    """파일명 또는 컬럼 헤더에서 프로파일 차원(자녀나이/결혼상태/가구당인원)을 식별한다.

    Returns:
        차원 키 문자열 또는 None.
    """
    # 1) 파일명에서 키워드 검색
    for dim_key in PROFILE_DIMENSIONS:
        if dim_key in filename:
            return dim_key

    # 2) 컬럼 헤더에서 차원명 또는 속성값 검색
    if df is not None:
        col_names = " ".join(str(c) for c in df.columns)
        for dim_key, attr_values in PROFILE_DIMENSIONS.items():
            # 차원명 자체가 컬럼에 있으면 바로 매칭
            if dim_key in col_names:
                return dim_key
            # 속성값이 2개 이상 매칭되면 해당 차원
            matches = sum(1 for a in attr_values if a in col_names)
            if matches >= 2:
                return dim_key

    return None


def parse_date_range(filename: str) -> dict[str, str]:
    """파일명에서 시작일·종료일을 파싱한다.

    지원 패턴:
      - _20250101_20251231.xlsx  (YYYYMMDD)
      - _2025-01-01_2025-12-31.xlsx
    """
    # YYYYMMDD 패턴
    m = re.search(r"_(\d{8})_(\d{8})", filename)
    if m:
        s, e = m.group(1), m.group(2)
        return {
            "start": f"{s[:4]}-{s[4:6]}-{s[6:8]}",
            "end": f"{e[:4]}-{e[4:6]}-{e[6:8]}",
        }
    # YYYY-MM-DD 패턴
    m = re.search(r"_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", filename)
    if m:
        return {"start": m.group(1), "end": m.group(2)}
    return {}


# ───────────────────────────────────────────
# 엑셀 파싱
# ───────────────────────────────────────────

def parse_profile_excel(
    file: str | Path | BinaryIO,
    dimension: str,
    sheet_name: str | int = 0,
) -> pd.DataFrame:
    """고객 프로파일 엑셀을 읽어 정규화된 DataFrame을 반환한다.

    엑셀 구조 (롱 포맷 가정):
        대분류 | 중분류 | 소분류 | 세분류 | 상품명 | 상품ID | {차원컬럼} | 결제금액 | … | 환불수량

    Returns:
        DataFrame — 카테고리 컬럼 + attribute_value + 지표 컬럼.
    """
    raw_df = pd.read_excel(file, sheet_name=sheet_name, engine="openpyxl")

    # 컬럼명 공백 정리
    raw_df.columns = [str(c).strip() for c in raw_df.columns]

    # 속성 컬럼 탐지 (차원명이 컬럼에 있으면 그대로, 아니면 속성값으로 탐지)
    attr_col = _detect_attribute_column(raw_df, dimension)

    if attr_col is not None:
        # ── 롱 포맷: 속성값이 행 단위로 존재 ──
        df = _parse_long_format(raw_df, attr_col, dimension)
    else:
        # ── 와이드 포맷: 속성값이 컬럼 접두어로 존재 ──
        df = _parse_wide_format(raw_df, dimension)

    return df


def _detect_attribute_column(df: pd.DataFrame, dimension: str) -> str | None:
    """DataFrame에서 속성 컬럼을 찾는다.

    차원명(자녀나이 등)이 컬럼에 있으면 반환, 아니면 속성값이 들어있는 컬럼을 탐색.
    """
    # 차원명이 정확히 컬럼에 있는 경우
    if dimension in df.columns:
        return dimension

    # 속성값 리스트로 컬럼 내용 매칭
    attr_values = set(PROFILE_DIMENSIONS[dimension])
    for col in df.columns:
        if col in PROFILE_CATEGORY_COLUMNS or col in ALL_METRICS:
            continue
        unique_vals = set(df[col].dropna().astype(str).unique())
        overlap = unique_vals & attr_values
        if len(overlap) >= 2:
            return col

    return None


def _parse_long_format(
    raw_df: pd.DataFrame,
    attr_col: str,
    dimension: str,
) -> pd.DataFrame:
    """롱 포맷 엑셀을 정규화된 DataFrame으로 변환."""
    # 필요한 컬럼 선별
    keep_cols = []
    for expected in PROFILE_CATEGORY_COLUMNS:
        for col in raw_df.columns:
            if col == expected:
                keep_cols.append(col)
                break

    keep_cols.append(attr_col)

    for metric in ALL_METRICS:
        if metric in raw_df.columns:
            keep_cols.append(metric)

    df = raw_df[keep_cols].copy()
    df = df.rename(columns={attr_col: "attribute_value"})

    # 숫자 변환 (과학적 표기법 포함)
    for metric in ALL_METRICS:
        if metric in df.columns:
            df[metric] = pd.to_numeric(df[metric], errors="coerce").fillna(0)

    return df


def _parse_wide_format(raw_df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """와이드 포맷(속성값이 컬럼 접두어) 엑셀을 롱 포맷으로 변환."""
    attr_values = PROFILE_DIMENSIONS[dimension]

    # 카테고리 컬럼 식별
    cat_cols = [c for c in PROFILE_CATEGORY_COLUMNS if c in raw_df.columns]

    records: list[dict] = []
    for _, row in raw_df.iterrows():
        cat_data = {c: row[c] for c in cat_cols}

        for attr_val in attr_values:
            rec = {**cat_data, "attribute_value": attr_val}
            for metric in ALL_METRICS:
                col_name = _find_metric_column(raw_df.columns, attr_val, metric)
                rec[metric] = _safe_numeric(row.get(col_name)) if col_name else 0.0
            records.append(rec)

    df = pd.DataFrame(records)
    for metric in ALL_METRICS:
        if metric in df.columns:
            df[metric] = pd.to_numeric(df[metric], errors="coerce").fillna(0)
    return df


def _find_metric_column(
    columns: pd.Index,
    attr_value: str,
    metric: str,
) -> str | None:
    """속성값+지표 조합에 해당하는 컬럼명을 찾는다."""
    for col in columns:
        col_str = str(col)
        if attr_value in col_str and metric in col_str:
            return col
    return None


def _safe_numeric(val) -> float:
    """값을 float로 변환 (None, NaN, 과학적 표기법 처리)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


# ───────────────────────────────────────────
# 비중 분석 (Phase 1 핵심)
# ───────────────────────────────────────────

def compute_percentage_distribution(
    df: pd.DataFrame,
    agg_level: str,
    metric: str,
    exclude_unknown: bool = False,
) -> pd.DataFrame:
    """카테고리 레벨별 각 속성값의 비중(%)을 계산한다.

    Args:
        df: parse_profile_excel()의 결과 (롱 포맷).
        agg_level: "대분류" | "중분류" | "소분류" | "세분류" | "상품".
        metric: 집계 지표 (결제금액, 결제수, 결제상품수량).
        exclude_unknown: True이면 (알수없음) 행 제외.

    Returns:
        DataFrame — category, 속성값별 %, 속성값별 _abs, 합계.
    """
    work_df = df.copy()

    if exclude_unknown:
        work_df = work_df[work_df["attribute_value"] != PROFILE_UNKNOWN_VALUE]

    group_col = "상품명" if agg_level == "상품" else agg_level

    if group_col not in work_df.columns or metric not in work_df.columns:
        return pd.DataFrame()

    # groupby → pivot
    grouped = (
        work_df.groupby([group_col, "attribute_value"])[metric]
        .sum()
        .reset_index()
    )
    pivot = grouped.pivot_table(
        index=group_col,
        columns="attribute_value",
        values=metric,
        fill_value=0,
        aggfunc="sum",
    )

    # 합계
    pivot["합계"] = pivot.sum(axis=1)

    attr_values = [c for c in pivot.columns if c != "합계"]

    rows: list[dict] = []
    for category in pivot.index:
        row: dict = {"category": category}
        total = pivot.loc[category, "합계"]
        for attr_val in attr_values:
            abs_val = pivot.loc[category, attr_val]
            pct = round(abs_val / total * 100, 1) if total > 0 else 0.0
            row[attr_val] = pct
            row[f"{attr_val}_abs"] = abs_val
        row["합계"] = total
        rows.append(row)

    result_df = pd.DataFrame(rows)
    result_df = result_df.sort_values("합계", ascending=False).reset_index(drop=True)
    return result_df


# ───────────────────────────────────────────
# 드릴다운 (Phase 2)
# ───────────────────────────────────────────

_LEVEL_HIERARCHY = ["대분류", "중분류", "소분류", "세분류", "상품"]


def get_drilldown_data(
    df: pd.DataFrame,
    metric: str,
    exclude_unknown: bool,
    parent_level: str,
    parent_value: str,
) -> pd.DataFrame:
    """선택한 카테고리의 하위 레벨 비중 분석을 수행한다."""
    idx = _LEVEL_HIERARCHY.index(parent_level)
    if idx >= len(_LEVEL_HIERARCHY) - 1:
        return pd.DataFrame()

    child_level = _LEVEL_HIERARCHY[idx + 1]
    parent_col = "상품명" if parent_level == "상품" else parent_level

    filtered = df[df[parent_col] == parent_value]
    if filtered.empty:
        return pd.DataFrame()

    return compute_percentage_distribution(filtered, child_level, metric, exclude_unknown)


def get_child_level(current_level: str) -> str | None:
    """현재 레벨의 하위 레벨을 반환한다."""
    idx = _LEVEL_HIERARCHY.index(current_level)
    if idx >= len(_LEVEL_HIERARCHY) - 1:
        return None
    return _LEVEL_HIERARCHY[idx + 1]


# ───────────────────────────────────────────
# 통합 뷰 (Phase 2)
# ───────────────────────────────────────────

def compute_integrated_view(
    all_data: dict[str, pd.DataFrame],
    category_level: str,
    category_value: str,
    metric: str,
    exclude_unknown: bool = False,
) -> dict[str, pd.DataFrame]:
    """특정 카테고리에 대해 3개 차원의 비중을 동시에 계산한다.

    Returns:
        {차원명: 단일행 DataFrame(속성값 %, _abs, 합계)} 딕셔너리.
    """
    group_col = "상품명" if category_level == "상품" else category_level

    results: dict[str, pd.DataFrame] = {}
    for dimension, df in all_data.items():
        if group_col not in df.columns:
            continue
        filtered = df[df[group_col] == category_value]
        if filtered.empty:
            continue

        work = filtered.copy()
        if exclude_unknown:
            work = work[work["attribute_value"] != PROFILE_UNKNOWN_VALUE]

        if metric not in work.columns:
            continue

        grouped = work.groupby("attribute_value")[metric].sum()
        total = grouped.sum()

        row: dict = {}
        for attr_val, abs_val in grouped.items():
            pct = round(abs_val / total * 100, 1) if total > 0 else 0.0
            row[attr_val] = pct
            row[f"{attr_val}_abs"] = abs_val
        row["합계"] = total

        results[dimension] = pd.DataFrame([row])

    return results


def get_available_categories(df: pd.DataFrame, level: str) -> list[str]:
    """해당 레벨의 고유 카테고리 목록을 반환한다."""
    col = "상품명" if level == "상품" else level
    if col not in df.columns:
        return []
    return sorted(df[col].dropna().unique().tolist())
