"""보고 멘트 생성 — 데이터 수집 + Claude API 보고서 작성."""

from core.database import get_connection, get_uploaded_months, get_cases_by_month
from core.aggregator import (
    product_tag_matrix, month_over_month,
    get_special_cases, get_cost_comparison,
)
from core.llm_client import generate_report
from config import SPECIAL_CASE_THRESHOLD, JUDGMENT_EXCHANGE, JUDGMENT_COMPLAINT


def _format_cost(amount: float) -> str:
    return f"{amount:,.0f}"


def _get_previous_month(months: list[str], current: str) -> str | None:
    """현재 월의 이전 월을 찾는다."""
    try:
        idx = months.index(current)
        if idx + 1 < len(months):
            return months[idx + 1]  # months는 내림차순
    except ValueError:
        pass
    return None


def collect_report_context(conn, current_month: str, previous_month: str) -> dict:
    """보고서 생성에 필요한 모든 데이터를 수집."""

    # 비용 비교
    cost = get_cost_comparison(conn, current_month, previous_month)

    # 건수
    cur_cases = get_cases_by_month(conn, current_month)
    prev_cases = get_cases_by_month(conn, previous_month)

    # 증감 분석
    mom = month_over_month(conn, current_month, previous_month)

    # 주요 증가 원인
    increase_lines = []
    for product, tag, delta in mom.get("top_increases", [])[:10]:
        increase_lines.append(f"  - {product} / {tag}: +{delta}건")
    increase_text = "\n".join(increase_lines) if increase_lines else "  (특이사항 없음)"

    # 특이 품목
    special = get_special_cases(conn, current_month, SPECIAL_CASE_THRESHOLD)

    special_lines = []
    for product, case_list in {**special["exchange"], **special["complaint"]}.items():
        special_lines.append(f"  - {product}: {len(case_list)}건")
    special_text = "\n".join(special_lines) if special_lines else "  (해당 없음)"

    # 세트교환요구 상세
    exchange_lines = []
    for product, case_list in special["exchange"].items():
        exchange_lines.append(f"  ▶ {product} ({len(case_list)}건)")
        for c in case_list[:5]:
            notes = (c.get("action_notes") or "")[:50]
            exchange_lines.append(f"    - {notes}")
    exchange_text = "\n".join(exchange_lines) if exchange_lines else "  (해당 없음)"

    # 고객불만 상세
    complaint_lines = []
    for product, case_list in special["complaint"].items():
        complaint_lines.append(f"  ▶ {product} ({len(case_list)}건)")
        for c in case_list[:5]:
            notes = (c.get("action_notes") or "")[:50]
            complaint_lines.append(f"    - {notes}")
    complaint_text = "\n".join(complaint_lines) if complaint_lines else "  (해당 없음)"

    delta_pct_str = f"{cost['delta_pct']:+.1f}%"

    return {
        "current_month": current_month,
        "previous_month": previous_month,
        "current_cost": _format_cost(cost["current_cost"]),
        "previous_cost": _format_cost(cost["previous_cost"]),
        "delta": f"{cost['delta']:+,.0f}",
        "delta_pct": delta_pct_str,
        "total_cases": len(cur_cases),
        "prev_total_cases": len(prev_cases),
        "increase_contributors": increase_text,
        "special_products": special_text,
        "exchange_requests": exchange_text,
        "customer_complaints": complaint_text,
    }


def generate_full_report(conn, current_month: str, previous_month: str) -> dict:
    """전체 보고서 생성.

    Returns:
        {"report_text": str, "key_findings": list[str], "context": dict}
    """
    context = collect_report_context(conn, current_month, previous_month)

    try:
        result = generate_report(context)
    except ValueError as e:
        # API 키 미설정 시 기본 보고서 생성
        result = _generate_fallback_report(context)

    result["context"] = context
    return result


def _generate_fallback_report(context: dict) -> dict:
    """Claude API 없이 기본 템플릿으로 보고서 생성."""
    report = f"""# {context['current_month']} 하자보수비 보고

## 1. 하자보수비 현황
- 당월({context['current_month']}): {context['current_cost']}원
- 전월({context['previous_month']}): {context['previous_cost']}원
- 증감: {context['delta']}원 ({context['delta_pct']})

## 2. 건수 현황
- 당월: {context['total_cases']}건
- 전월: {context['prev_total_cases']}건

## 3. 주요 증가 원인
{context['increase_contributors']}

## 4. 품목별 특이사항 (월 {SPECIAL_CASE_THRESHOLD}건 이상)
{context['special_products']}

### ▶ 세트교환요구
{context['exchange_requests']}

### ▶ 고객 불만
{context['customer_complaints']}
"""
    return {
        "report_text": report,
        "key_findings": [
            f"당월 하자보수비: {context['current_cost']}원 (전월 대비 {context['delta_pct']})",
            f"당월 총 {context['total_cases']}건",
        ],
    }
