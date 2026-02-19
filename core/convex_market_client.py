"""Convex 시장조사 데이터 클라이언트.

Python → Convex HTTP API로 시장조사 데이터를 업로드/조회.
"""

from __future__ import annotations

import os
import json

import httpx
from dotenv import load_dotenv

load_dotenv()


def _get_convex_url() -> str:
    """Convex 배포 URL을 가져온다."""
    url = ""
    try:
        import streamlit as st
        url = st.secrets.get("CONVEX_URL", "")
    except Exception:
        pass
    if not url:
        url = os.getenv("CONVEX_URL", "")
    if not url:
        raise ValueError(
            "CONVEX_URL이 설정되지 않았습니다. "
            ".env.local 파일에 CONVEX_URL을 입력하세요."
        )
    return url.rstrip("/")


def _mutation(function_name: str, args: dict) -> dict:
    """Convex mutation 호출."""
    url = _get_convex_url()
    resp = httpx.post(
        f"{url}/api/mutation",
        json={"path": function_name, "args": args, "format": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "error":
        raise RuntimeError(f"Convex mutation error: {data.get('errorMessage', 'unknown')}")
    return data.get("value")


def _query(function_name: str, args: dict) -> dict:
    """Convex query 호출."""
    url = _get_convex_url()
    resp = httpx.post(
        f"{url}/api/query",
        json={"path": function_name, "args": args, "format": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "error":
        raise RuntimeError(f"Convex query error: {data.get('errorMessage', 'unknown')}")
    return data.get("value")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 업로드
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def upload_market_research(parsed_data: dict, progress_callback=None) -> str:
    """파싱된 시장조사 데이터를 Convex에 업로드한다.

    Args:
        parsed_data: parse_market_research_excel()의 반환값
        progress_callback: (current, total, message) -> None

    Returns:
        session_id (Convex document ID)
    """
    categories = parsed_data["categories"]
    total_products = sum(len(c["products"]) for c in categories)

    # 1. 세션 생성
    session_id = _mutation("marketResearch:createSession", {
        "filename": parsed_data["filename"],
        "sheetCount": len(categories),
        "totalProducts": total_products,
        "sheets": [
            {"sheetName": c["name"], "productCount": len(c["products"])}
            for c in categories
        ],
    })

    if progress_callback:
        progress_callback(0, total_products, "세션 생성 완료")

    uploaded = 0

    for cat in categories:
        # 2. 카테고리 생성
        category_id = _mutation("marketResearch:createCategory", {
            "sessionId": session_id,
            "name": cat["name"],
            "specFields": cat["spec_fields"],
        })

        # 3. 제품 일괄 삽입 (배치 10개씩)
        batch_size = 10
        products_list = cat["products"]

        for i in range(0, len(products_list), batch_size):
            batch = products_list[i:i + batch_size]
            convex_products = []

            for p in batch:
                convex_products.append({
                    "sessionId": session_id,
                    "categoryId": category_id,
                    "name": p["name"],
                    "brand": p["brand"],
                    "price": float(p["price"]),
                    "shippingFee": p.get("shippingFee"),
                    "actualPrice": float(p["actualPrice"]) if p.get("actualPrice") else None,
                    "seller": p.get("seller"),
                    "material": p.get("material"),
                    "origin": p.get("origin"),
                    "url": p.get("url"),
                    "specs": p.get("specs", {}),
                    "isOurProduct": p.get("isOurProduct", False),
                })

            _mutation("marketResearch:insertProducts", {"products": convex_products})
            uploaded += len(batch)

            if progress_callback:
                progress_callback(uploaded, total_products, f"{cat['name']} 업로드 중...")

    return session_id


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 조회
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def list_sessions() -> list[dict]:
    """시장조사 세션 목록을 조회한다."""
    return _query("marketResearch:listSessions", {})


def get_categories(session_id: str) -> list[dict]:
    """세션의 카테고리 목록을 조회한다."""
    return _query("marketResearch:getCategories", {"sessionId": session_id})


def get_products_by_category(category_id: str) -> list[dict]:
    """카테고리별 제품 목록을 조회한다."""
    return _query("marketResearch:getProductsByCategory", {"categoryId": category_id})


def get_all_products(session_id: str) -> list[dict]:
    """세션의 전체 제품 목록을 조회한다."""
    return _query("marketResearch:getAllProducts", {"sessionId": session_id})


def delete_session(session_id: str) -> int:
    """세션과 관련 데이터를 삭제한다."""
    return _mutation("marketResearch:deleteSession", {"sessionId": session_id})
