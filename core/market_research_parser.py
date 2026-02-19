"""시장조사 엑셀 파싱 — 전치형(제품=열) 데이터를 정규화하여 Convex 업로드용으로 변환.

시장조사 엑셀 구조:
  - 시트마다 하나의 품목 카테고리 (실내 체어, 실외 체어, 바스툴 등)
  - 행 0: 빈 행 (또는 제목)
  - 행 1: 제품명(이름)
  - 행 2: 이미지 (스킵)
  - 행 3: 브랜드
  - 행 4~: 스펙 행 (가격, 배송비, 소재, 원산지 등)
  - 제품은 열(column) 방향으로 배치됨 → 전치(transpose) 필요
"""

from __future__ import annotations

import re
from typing import BinaryIO

import numpy as np
import pandas as pd


# ── 알려진 행 라벨 → 표준 필드 매핑 ──

_FIELD_MAP = {
    "이름": "name",
    "제품명": "name",
    "브랜드": "brand",
    "가격": "price",
    "가격 (+배송비)": "price",
    "배송비": "shippingFee",
    "실판매가 (가격+배송비)": "actualPrice",
    "실판매가": "actualPrice",
    "1개당 판매가": "actualPrice",
    "판매처": "seller",
    "소재": "material",
    "원산지": "origin",
    "URL": "url",
    "url": "url",
}

_SKIP_ROWS = {"이미지", "리뷰"}  # 데이터 없는 행


def _is_market_research_sheet(sheet_name: str) -> bool:
    """시장조사 시트인지 판별 (MD 내부 시트 제외)."""
    return "(시장조사)" in sheet_name


def _clean_value(val) -> str | float | None:
    """셀 값을 정리."""
    if pd.isna(val) or val is None:
        return None
    s = str(val).strip()
    if s in ("", "NaN", "nan"):
        return None
    return s


def _try_float(val) -> float | None:
    """문자열을 숫자로 변환 시도."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if not np.isnan(val) else None
    s = str(val).strip().replace(",", "").replace("원", "").replace("₩", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_market_research_excel(
    file: str | BinaryIO,
) -> dict:
    """시장조사 엑셀을 파싱하여 카테고리별 제품 데이터를 반환한다.

    Returns:
        {
            "filename": str,
            "categories": [
                {
                    "name": str,             # 시트명 (카테고리명)
                    "spec_fields": [str],    # 스펙 필드명 목록
                    "products": [
                        {
                            "name": str,
                            "brand": str,
                            "price": float,
                            "shippingFee": str | None,
                            "actualPrice": float | None,
                            "seller": str | None,
                            "material": str | None,
                            "origin": str | None,
                            "url": str | None,
                            "specs": {field: value},
                            "isOurProduct": bool,
                        }
                    ],
                }
            ],
        }
    """
    filename = getattr(file, "name", "unknown.xlsx")
    xls = pd.ExcelFile(file, engine="openpyxl")

    result = {"filename": filename, "categories": []}

    for sheet_name in xls.sheet_names:
        if not _is_market_research_sheet(sheet_name):
            continue

        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        if df.empty or df.shape[1] < 2:
            continue

        category = _parse_sheet(df, sheet_name)
        if category and category["products"]:
            result["categories"].append(category)

    return result


def _parse_sheet(df: pd.DataFrame, sheet_name: str) -> dict | None:
    """단일 시트를 파싱하여 카테고리 데이터를 반환한다."""
    # 첫 열은 행 라벨 (이름, 브랜드, 가격 등)
    # 나머지 열은 각 제품의 값

    # 행 라벨 추출 (첫 번째 열)
    row_labels = df.iloc[:, 0].apply(
        lambda x: str(x).strip() if pd.notna(x) else ""
    ).tolist()

    # 제품 열 인덱스 (1부터)
    product_col_start = 1
    product_col_end = df.shape[1]

    # 이름 행 찾기
    name_row = None
    for i, label in enumerate(row_labels):
        if label in ("이름", "제품명"):
            name_row = i
            break

    if name_row is None:
        return None

    # 제품별 데이터 추출
    products = []
    known_fields = set()
    spec_fields = []

    for col_idx in range(product_col_start, product_col_end):
        product_name = _clean_value(df.iloc[name_row, col_idx])
        if not product_name:
            continue

        product = {
            "name": str(product_name),
            "brand": "",
            "price": 0.0,
            "shippingFee": None,
            "actualPrice": None,
            "seller": None,
            "material": None,
            "origin": None,
            "url": None,
            "specs": {},
            "isOurProduct": False,
        }

        # 우리 제품 판별 (데스커, 퍼시스 관련)
        for row_i, label in enumerate(row_labels):
            if label == "브랜드":
                brand_val = _clean_value(df.iloc[row_i, col_idx])
                if brand_val and any(
                    kw in str(brand_val) for kw in ("데스커", "퍼시스")
                ):
                    product["isOurProduct"] = True
                break

        # 각 행의 데이터를 필드에 매핑
        for row_i, label in enumerate(row_labels):
            if not label or label in _SKIP_ROWS:
                continue

            val = _clean_value(df.iloc[row_i, col_idx])
            std_field = _FIELD_MAP.get(label)

            if std_field == "name":
                continue  # 이미 처리
            elif std_field == "brand":
                product["brand"] = str(val) if val else ""
            elif std_field == "price":
                fval = _try_float(val)
                if fval is not None:
                    product["price"] = fval
            elif std_field == "shippingFee":
                product["shippingFee"] = str(val) if val else None
            elif std_field == "actualPrice":
                fval = _try_float(val)
                if fval is not None:
                    product["actualPrice"] = fval
            elif std_field == "seller":
                product["seller"] = str(val) if val else None
            elif std_field == "material":
                product["material"] = str(val) if val else None
            elif std_field == "origin":
                product["origin"] = str(val) if val else None
            elif std_field == "url":
                product["url"] = str(val) if val else None
            elif std_field is None and row_i != name_row:
                # 알 수 없는 행 → specs에 저장
                if label and val:
                    product["specs"][label] = str(val)
                    if label not in known_fields:
                        known_fields.add(label)
                        spec_fields.append(label)

        # 실판매가 계산 (없으면 가격 + 배송비로 추정)
        if product["actualPrice"] is None and product["price"] > 0:
            ship = _try_float(product.get("shippingFee"))
            if ship is not None and ship > 0:
                product["actualPrice"] = product["price"] + ship
            else:
                product["actualPrice"] = product["price"]

        products.append(product)

    # 카테고리명 정리 (시장조사) 접두어 제거
    cat_name = sheet_name.replace("(시장조사)", "").strip()

    return {
        "name": cat_name,
        "spec_fields": spec_fields,
        "products": products,
    }


def market_data_to_dataframe(
    category_data: dict,
) -> pd.DataFrame:
    """카테고리 데이터를 스펙 포지셔닝 분석용 DataFrame으로 변환한다.

    반환 DataFrame 컬럼: 제품명, 브랜드, 가격, + 스펙필드들
    """
    products = category_data["products"]
    rows = []

    for p in products:
        row = {
            "제품명": p["name"],
            "브랜드": p["brand"],
            "가격": p.get("actualPrice") or p["price"],
        }
        # 스펙 필드 추가
        for key, val in p.get("specs", {}).items():
            fval = _try_float(val)
            row[key] = fval if fval is not None else val
        rows.append(row)

    return pd.DataFrame(rows)
