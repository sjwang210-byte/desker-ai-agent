"""스펙 기반 포지셔닝 분석 핵심 로직.

엑셀 파싱, 컬럼 자동 감지, 가중치 계산, 정규화·점수화, 제품 분류.
Streamlit 의존 없음 — 순수 데이터 처리 모듈.
"""

from __future__ import annotations

import re
from typing import BinaryIO

import numpy as np
import pandas as pd


# ── 컬럼명 패턴 (자동 감지용) ──

_PRODUCT_PATTERNS = re.compile(
    r"^(제품명?|제품\s*이름|상품명?|product[\s_]?name|name|모델명?|model)$",
    re.IGNORECASE,
)

_PRICE_PATTERNS = re.compile(
    r"^(가격|price|판매가|정가|소비자가|단가|selling[\s_]?price)$",
    re.IGNORECASE,
)

_CATEGORY_PATTERNS = re.compile(
    r"^(카테고리|category|분류|구분|브랜드|brand|type|유형)$",
    re.IGNORECASE,
)

_EXCLUDE_PATTERNS = re.compile(
    r"(url|링크|link|이미지|image|비고|note|memo|메모|번호|no\.?$|^id$)",
    re.IGNORECASE,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 엑셀 파싱
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def parse_spec_excel(
    file: str | BinaryIO,
    sheet_name: str | int = 0,
) -> pd.DataFrame:
    """스펙 엑셀을 읽어 정제된 DataFrame을 반환한다.

    - 컬럼명 공백 정리
    - 완전 빈 행 제거
    - 숫자 컬럼의 콤마 제거 및 변환
    """
    df = pd.read_excel(file, sheet_name=sheet_name, engine="openpyxl")

    # 컬럼명 정리
    df.columns = [str(c).strip() for c in df.columns]

    # 완전 빈 행 제거
    df = df.dropna(how="all").reset_index(drop=True)

    # 숫자 변환 시도 (콤마 포함 문자열 → 숫자)
    for col in df.columns:
        if df[col].dtype == object:
            converted = df[col].apply(_try_numeric)
            if converted.notna().sum() > len(df) * 0.5:
                # 절반 이상 숫자로 변환 가능하면 숫자 컬럼으로 간주
                if converted.notna().sum() >= df[col].notna().sum() * 0.8:
                    df[col] = converted

    return df


def _try_numeric(val):
    """문자열을 숫자로 변환 시도. 콤마·단위 제거."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float)):
        return val
    s = str(val).strip().replace(",", "").replace("원", "").replace("₩", "")
    try:
        return float(s)
    except ValueError:
        return np.nan


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 컬럼 자동 감지
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def auto_detect_columns(df: pd.DataFrame) -> dict:
    """DataFrame 컬럼을 자동으로 product_col, price_col, category_col, spec_cols로 분류한다.

    Returns:
        {
            "product_col": str | None,
            "price_col": str | None,
            "category_col": str | None,
            "spec_cols": list[str],
        }
    """
    product_col = None
    price_col = None
    category_col = None
    used = set()

    # 1차: 정규식 패턴 매칭
    for col in df.columns:
        col_stripped = col.strip()
        if not product_col and _PRODUCT_PATTERNS.match(col_stripped):
            product_col = col
            used.add(col)
        elif not price_col and _PRICE_PATTERNS.match(col_stripped):
            price_col = col
            used.add(col)
        elif not category_col and _CATEGORY_PATTERNS.match(col_stripped):
            category_col = col
            used.add(col)

    # 2차: 폴백 — 첫 번째 문자열 컬럼 → 제품명, 첫 번째 숫자 컬럼 → 가격
    if not product_col:
        for col in df.columns:
            if col not in used and df[col].dtype == object:
                product_col = col
                used.add(col)
                break

    if not price_col:
        for col in df.columns:
            if col not in used and pd.api.types.is_numeric_dtype(df[col]):
                price_col = col
                used.add(col)
                break

    # 나머지 → 스펙 컬럼 (제외 패턴 필터링)
    spec_cols = []
    for col in df.columns:
        if col in used:
            continue
        if _EXCLUDE_PATTERNS.search(col.strip()):
            continue
        spec_cols.append(col)

    return {
        "product_col": product_col,
        "price_col": price_col,
        "category_col": category_col,
        "spec_cols": spec_cols,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 가중치 계산
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calculate_variance_weights(
    df: pd.DataFrame,
    spec_cols: list[str],
) -> dict[str, float]:
    """각 스펙 컬럼의 변동계수(CV = std/|mean|)를 계산하여 가중치를 도출한다.

    분산이 큰(= 제품 간 차이가 큰) 항목에 높은 가중치를 부여.
    합계 1.0으로 정규화.
    """
    cv_scores: dict[str, float] = {}

    for col in spec_cols:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 2:
            cv_scores[col] = 0.0
            continue

        mean = series.mean()
        std = series.std()

        if abs(mean) > 1e-10:
            cv = std / abs(mean)
        else:
            cv = std
        cv_scores[col] = max(cv, 0.0)

    total = sum(cv_scores.values())
    if total > 0:
        return {k: v / total for k, v in cv_scores.items()}
    else:
        n = len(spec_cols) or 1
        return {k: 1.0 / n for k in spec_cols}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 정규화 및 점수화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _normalize_minmax(series: pd.Series) -> pd.Series:
    """단일 시리즈를 min-max 0-1 범위로 정규화."""
    min_val = series.min()
    max_val = series.max()
    if max_val == min_val:
        return pd.Series(0.5, index=series.index)
    return (series - min_val) / (max_val - min_val)


def normalize_and_score(
    df: pd.DataFrame,
    column_config: dict,
    weights: dict[str, float],
) -> pd.DataFrame:
    """모든 스펙 컬럼을 정규화하고 가중 합산하여 spec_score(0-100)를 계산한다.

    - 숫자 컬럼: min-max → 0~1
    - 텍스트 컬럼: 정렬 후 ordinal 인코딩 → 0~1
    - spec_score = Σ(정규화값 × 가중치) × 100
    """
    result = df.copy()
    spec_cols = column_config["spec_cols"]

    for col in spec_cols:
        if pd.api.types.is_numeric_dtype(result[col]):
            numeric = pd.to_numeric(result[col], errors="coerce").fillna(0)
            result[f"{col}_norm"] = _normalize_minmax(numeric)
        else:
            # 텍스트 → ordinal 인코딩
            unique_sorted = sorted(result[col].dropna().unique())
            n = max(len(unique_sorted) - 1, 1)
            mapping = {v: i / n for i, v in enumerate(unique_sorted)}
            result[f"{col}_norm"] = result[col].map(mapping).fillna(0.5)

    # 가중 합산
    score = pd.Series(0.0, index=result.index)
    for col in spec_cols:
        w = weights.get(col, 0)
        score += result[f"{col}_norm"] * w
    result["spec_score"] = score * 100

    return result.sort_values("spec_score", ascending=False).reset_index(drop=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 제품 분류
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def classify_products(
    scored_df: pd.DataFrame,
    product_col: str,
    price_col: str,
    score_col: str = "spec_score",
) -> dict[str, str]:
    """제품을 4개 포지셔닝 카테고리로 분류한다.

    중앙값 기준:
    - 프리미엄: 고가격 + 고스펙
    - 가성비: 저가격 + 고스펙
    - 보급형: 저가격 + 저스펙
    - 과잉스펙: 고가격 + 저스펙
    """
    median_price = scored_df[price_col].median()
    median_score = scored_df[score_col].median()

    categories: dict[str, str] = {}
    for _, row in scored_df.iterrows():
        name = str(row[product_col])
        high_price = row[price_col] >= median_price
        high_score = row[score_col] >= median_score

        if high_price and high_score:
            categories[name] = "프리미엄"
        elif not high_price and high_score:
            categories[name] = "가성비"
        elif not high_price and not high_score:
            categories[name] = "보급형"
        else:
            categories[name] = "과잉스펙"

    return categories


def calculate_value_index(
    scored_df: pd.DataFrame,
    price_col: str,
    score_col: str = "spec_score",
) -> pd.Series:
    """가치 지수 = spec_score / 정규화_가격 × 100.

    높을수록 가격 대비 스펙이 우수함.
    """
    price_norm = _normalize_minmax(scored_df[price_col])
    # 가격이 0인 경우 방지
    price_norm = price_norm.replace(0, 0.01)
    return (scored_df[score_col] / price_norm).round(1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시뮬레이션
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def simulate_our_product(
    our_specs: dict,
    scored_df: pd.DataFrame,
    column_config: dict,
    weights: dict[str, float],
) -> dict:
    """시뮬레이션 제품의 스펙 점수와 포지셔닝을 계산한다.

    기존 제품 데이터의 min/max를 기준으로 정규화하고
    동일한 가중치 모델을 적용한다.

    Args:
        our_specs: {"product_name": str, "price": float, "스펙1": val, ...}

    Returns:
        {
            "product_name": str,
            "price": float,
            "spec_score": float,
            "category": str,
            "value_index": float,
            "rank": int,
            "percentile": float,
            "normalized_specs": dict,
        }
    """
    product_col = column_config["product_col"]
    price_col = column_config["price_col"]
    spec_cols = column_config["spec_cols"]

    normalized_specs: dict[str, float] = {}
    score = 0.0

    for col in spec_cols:
        val = our_specs.get(col)
        if val is None:
            normalized_specs[col] = 0.5
            score += 0.5 * weights.get(col, 0)
            continue

        if pd.api.types.is_numeric_dtype(scored_df[col]):
            numeric_val = float(val)
            col_min = scored_df[col].min()
            col_max = scored_df[col].max()
            if col_max == col_min:
                norm = 0.5
            else:
                norm = (numeric_val - col_min) / (col_max - col_min)
                norm = max(0.0, min(1.0, norm))  # 클리핑
        else:
            unique_sorted = sorted(scored_df[col].dropna().unique())
            n = max(len(unique_sorted) - 1, 1)
            mapping = {v: i / n for i, v in enumerate(unique_sorted)}
            norm = mapping.get(val, 0.5)

        normalized_specs[col] = round(norm, 4)
        score += norm * weights.get(col, 0)

    spec_score = score * 100

    # 가격 정규화 (가치 지수용)
    our_price = float(our_specs.get("price", 0))
    price_min = scored_df[price_col].min()
    price_max = scored_df[price_col].max()
    if price_max == price_min:
        price_norm = 0.5
    else:
        price_norm = (our_price - price_min) / (price_max - price_min)
    price_norm = max(price_norm, 0.01)
    value_index = round(spec_score / price_norm, 1)

    # 사분면 분류
    median_price = scored_df[price_col].median()
    median_score = scored_df["spec_score"].median()
    high_price = our_price >= median_price
    high_score = spec_score >= median_score

    if high_price and high_score:
        category = "프리미엄"
    elif not high_price and high_score:
        category = "가성비"
    elif not high_price and not high_score:
        category = "보급형"
    else:
        category = "과잉스펙"

    # 순위 & 백분위
    all_scores = sorted(scored_df["spec_score"].tolist() + [spec_score], reverse=True)
    rank = all_scores.index(spec_score) + 1
    percentile = (1 - (rank - 1) / len(all_scores)) * 100

    return {
        "product_name": our_specs.get("product_name", "우리 제품"),
        "price": our_price,
        "spec_score": round(spec_score, 1),
        "category": category,
        "value_index": value_index,
        "rank": rank,
        "percentile": round(percentile, 1),
        "normalized_specs": normalized_specs,
    }
