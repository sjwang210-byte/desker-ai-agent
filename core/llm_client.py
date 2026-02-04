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
