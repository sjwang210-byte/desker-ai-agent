"""Claude API 래퍼 — 원인 추출, 보고서 생성."""

import os
import time
import json

import anthropic
from dotenv import load_dotenv

from config import ANTHROPIC_MODEL, BATCH_SIZE
from prompts.cause_extraction import (
    SYSTEM_PROMPT, BATCH_TEMPLATE, CASE_ITEM_TEMPLATE, EXTRACTION_TOOL,
)
from prompts.report_writing import REPORT_SYSTEM, REPORT_USER_TEMPLATE, REPORT_TOOL
from prompts.product_extraction import (
    SYSTEM_PROMPT as PRODUCT_SYSTEM,
    USER_TEMPLATE as PRODUCT_USER_TEMPLATE,
    EXTRACTION_TOOL as PRODUCT_TOOL,
    COMPARISON_SYSTEM,
    COMPARISON_USER_TEMPLATE,
    COMPARISON_TOOL,
)

load_dotenv()

MAX_RETRIES = 3
RETRY_DELAYS = [1, 3, 10]


def _get_client() -> anthropic.Anthropic:
    # Streamlit Cloud secrets 우선, 없으면 환경변수
    api_key = ""
    try:
        import streamlit as st
        api_key = st.secrets.get("ANTHROPIC_API_KEY", "")
    except Exception:
        pass
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your-api-key-here":
        raise ValueError(
            "ANTHROPIC_API_KEY가 설정되지 않았습니다. "
            ".env 파일 또는 Streamlit secrets에 API 키를 입력하세요."
        )
    return anthropic.Anthropic(api_key=api_key)


def _call_with_retry(func, *args, **kwargs):
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except anthropic.RateLimitError:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAYS[attempt])
            else:
                raise
        except anthropic.APIError:
            raise


def extract_causes_batch(cases: list[dict], tag_dictionary: list[str]) -> list[dict]:
    """여러 케이스를 배치로 원인 추출.

    Args:
        cases: [{"case_id": int, "product_group": str, "product": str,
                 "action_notes": str, "request_details": str}, ...]
        tag_dictionary: 기존 태그 문자열 리스트

    Returns:
        [{"case_index": 1, "tags": [...], "summary": str}, ...]
    """
    client = _get_client()

    # 케이스 텍스트 조립
    cases_text = ""
    for i, case in enumerate(cases, 1):
        cases_text += CASE_ITEM_TEMPLATE.format(
            index=i,
            product_group=case.get("product_group") or "(미분류)",
            product=case.get("product") or "(미분류)",
            action_notes=case.get("action_notes") or "(없음)",
            request_details=case.get("request_details") or "(없음)",
        )

    user_message = BATCH_TEMPLATE.format(count=len(cases), cases_text=cases_text)
    system_prompt = SYSTEM_PROMPT.format(
        tag_dictionary="\n".join(f"- {t}" for t in tag_dictionary) if tag_dictionary else "(태그 사전 비어있음)"
    )

    def _call():
        return client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            tools=[EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "submit_cause_tags"},
        )

    response = _call_with_retry(_call)

    # tool_use 블록 추출
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_cause_tags":
            return block.input.get("cases", [])

    return []


def generate_report(report_context: dict) -> dict:
    """보고서 멘트 자동 생성.

    Args:
        report_context: REPORT_USER_TEMPLATE의 포맷 변수들

    Returns:
        {"report_text": str, "key_findings": list[str]}
    """
    client = _get_client()

    user_message = REPORT_USER_TEMPLATE.format(**report_context)

    def _call():
        return client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=REPORT_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
            tools=[REPORT_TOOL],
            tool_choice={"type": "tool", "name": "submit_report"},
        )

    response = _call_with_retry(_call)

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_report":
            return block.input

    return {"report_text": "", "key_findings": []}


def extract_product_info(url: str, structured_data: str, page_content: str,
                         fallback_image: str = "") -> dict:
    """제품 페이지에서 정보 추출.

    Args:
        url: 원본 URL
        structured_data: JSON-LD / 메타태그 데이터 (문자열)
        page_content: 정제된 HTML 본문
        fallback_image: scraper에서 미리 추출한 이미지 URL

    Returns:
        {"product_name": str, "brand": str, "price": int, ...}
    """
    client = _get_client()

    user_message = PRODUCT_USER_TEMPLATE.format(
        url=url,
        structured_data=structured_data,
        page_content=page_content,
    )

    def _call():
        return client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=2048,
            system=PRODUCT_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
            tools=[PRODUCT_TOOL],
            tool_choice={"type": "tool", "name": "submit_product_info"},
        )

    response = _call_with_retry(_call)

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_product_info":
            result = block.input
            # scraper에서 추출한 이미지 URL로 보완
            if fallback_image and not result.get("image_url"):
                result["image_url"] = fallback_image
            return result

    return {"product_name": "추출 실패", "brand": "정보 없음", "price": 0,
            "price_display": "정보 없음", "image_url": fallback_image,
            "country_of_origin": "정보 없음", "materials": "정보 없음",
            "size": "정보 없음", "review_summary": {}, "notable_features": []}


def compare_products(products: list[dict]) -> dict:
    """여러 제품 비교 분석 (USP 도출).

    Args:
        products: extract_product_info() 결과 리스트

    Returns:
        {"products_analysis": [...], "market_summary": str, "recommendation": str}
    """
    client = _get_client()

    products_text = ""
    for i, p in enumerate(products, 1):
        review = p.get("review_summary", {})
        products_text += (
            f"\n[제품 {i}]\n"
            f"제품명: {p.get('product_name', '정보 없음')}\n"
            f"브랜드: {p.get('brand', '정보 없음')}\n"
            f"가격: {p.get('price_display', '정보 없음')}\n"
            f"소재: {p.get('materials', '정보 없음')}\n"
            f"크기: {p.get('size', '정보 없음')}\n"
            f"리뷰 요약: {review.get('summary_text', '정보 없음')}\n"
            f"주요 특징: {', '.join(p.get('notable_features', []))}\n"
        )

    user_message = COMPARISON_USER_TEMPLATE.format(
        count=len(products), products_text=products_text
    )

    def _call():
        return client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=COMPARISON_SYSTEM,
            messages=[{"role": "user", "content": user_message}],
            tools=[COMPARISON_TOOL],
            tool_choice={"type": "tool", "name": "submit_comparison"},
        )

    response = _call_with_retry(_call)

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_comparison":
            return block.input

    return {"products_analysis": [], "market_summary": "", "recommendation": ""}


def extract_products_batch(urls_and_content: list[dict],
                           progress_callback=None) -> list[dict]:
    """여러 제품을 순차 추출 (rate limit 고려).

    Args:
        urls_and_content: [{"url": str, "structured_data": str,
                            "page_content": str, "image_url": str}, ...]
        progress_callback: (current, total, phase) -> None

    Returns:
        [{"url": str, ...extracted fields..., "error": bool}, ...]
    """
    results = []
    total = len(urls_and_content)

    for i, item in enumerate(urls_and_content):
        try:
            extracted = extract_product_info(
                url=item["url"],
                structured_data=item["structured_data"],
                page_content=item["page_content"],
                fallback_image=item.get("image_url", ""),
            )
            extracted["url"] = item["url"]
            extracted["error"] = False
            results.append(extracted)
        except Exception as e:
            results.append({
                "url": item["url"],
                "product_name": "추출 실패",
                "brand": "정보 없음",
                "price": 0,
                "price_display": "정보 없음",
                "image_url": item.get("image_url", ""),
                "country_of_origin": "정보 없음",
                "materials": "정보 없음",
                "options": [],
                "size": "정보 없음",
                "review_summary": {},
                "notable_features": [],
                "error": True,
                "error_message": str(e),
            })

        if progress_callback:
            progress_callback(i + 1, total, "extract")

    return results


def process_cases_in_batches(all_cases: list[dict], tag_dictionary: list[str],
                             batch_size: int = BATCH_SIZE,
                             progress_callback=None) -> list[dict]:
    """전체 케이스를 배치로 나누어 처리.

    Args:
        progress_callback: (current, total) → None  진행 상태 콜백

    Returns:
        모든 케이스의 결과 리스트
    """
    all_results = []
    total = len(all_cases)

    for i in range(0, total, batch_size):
        batch = all_cases[i:i + batch_size]
        try:
            results = extract_causes_batch(batch, tag_dictionary)

            # case_id 매핑
            for r in results:
                case_idx = r.get("case_index", 1) - 1
                actual_idx = i + case_idx
                if actual_idx < total:
                    r["db_case_id"] = all_cases[actual_idx].get("id")

            all_results.extend(results)
        except Exception as e:
            # 실패한 배치는 에러 정보와 함께 기록
            for j, case in enumerate(batch):
                all_results.append({
                    "case_index": j + 1,
                    "db_case_id": case.get("id"),
                    "tags": [],
                    "summary": f"오류: {str(e)}",
                    "error": True,
                })

        if progress_callback:
            progress_callback(min(i + batch_size, total), total)

    return all_results
