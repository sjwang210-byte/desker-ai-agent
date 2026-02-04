"""집계, 전월 비교, 추이 분석, 이상 탐지."""

import json
from collections import Counter, defaultdict

from config import (
    SPECIAL_CASE_THRESHOLD, ANOMALY_CONSECUTIVE, ANOMALY_ZSCORE,
    JUDGMENT_EXCHANGE, JUDGMENT_COMPLAINT,
)
from core.database import (
    get_connection, get_tagged_cases_by_month, get_cases_by_month,
    save_snapshot, load_snapshot,
)


def product_tag_matrix(conn, year_month: str) -> dict:
    """품목군 × 원인 태그 건수 매트릭스.

    Returns:
        {
            "matrix": {품목군: {태그: 건수, ...}, ...},
            "products": [품목군 리스트],
            "tags": [태그 리스트],
            "total_cases": int,
        }
    """
    tagged = get_tagged_cases_by_month(conn, year_month)

    matrix = defaultdict(lambda: Counter())
    for row in tagged:
        product = row.get("product_group") or "(미분류)"
        tag = row.get("standard_tag") or "(미분류)"
        matrix[product][tag] += 1

    products = sorted(matrix.keys())
    all_tags = sorted(set(tag for counts in matrix.values() for tag in counts))

    return {
        "matrix": {p: dict(matrix[p]) for p in products},
        "products": products,
        "tags": all_tags,
        "total_cases": len(tagged),
    }


def month_over_month(conn, current_month: str, previous_month: str) -> dict:
    """전월 대비 증감 분석.

    Returns:
        {
            "current_total": int,
            "previous_total": int,
            "delta": int,
            "delta_pct": float,
            "by_product": {품목: {"current": int, "previous": int, "delta": int}, ...},
            "by_tag": {태그: {"current": int, "previous": int, "delta": int}, ...},
            "top_increases": [(품목, 태그, 증가건수), ...],
        }
    """
    cur_data = get_tagged_cases_by_month(conn, current_month)
    prev_data = get_tagged_cases_by_month(conn, previous_month)

    cur_by_product = Counter(r.get("product_group", "(미분류)") for r in cur_data)
    prev_by_product = Counter(r.get("product_group", "(미분류)") for r in prev_data)

    cur_by_tag = Counter(r.get("standard_tag", "(미분류)") for r in cur_data)
    prev_by_tag = Counter(r.get("standard_tag", "(미분류)") for r in prev_data)

    # 품목×태그 교차 증감
    cur_cross = Counter()
    prev_cross = Counter()
    for r in cur_data:
        cur_cross[(r.get("product_group", ""), r.get("standard_tag", ""))] += 1
    for r in prev_data:
        prev_cross[(r.get("product_group", ""), r.get("standard_tag", ""))] += 1

    all_keys = set(cur_cross.keys()) | set(prev_cross.keys())
    increases = []
    for key in all_keys:
        delta = cur_cross[key] - prev_cross[key]
        if delta > 0:
            increases.append((key[0], key[1], delta))
    increases.sort(key=lambda x: x[2], reverse=True)

    all_products = set(cur_by_product.keys()) | set(prev_by_product.keys())
    by_product = {}
    for p in all_products:
        c, pr = cur_by_product[p], prev_by_product[p]
        by_product[p] = {"current": c, "previous": pr, "delta": c - pr}

    all_tags = set(cur_by_tag.keys()) | set(prev_by_tag.keys())
    by_tag = {}
    for t in all_tags:
        c, pr = cur_by_tag[t], prev_by_tag[t]
        by_tag[t] = {"current": c, "previous": pr, "delta": c - pr}

    cur_total = len(cur_data)
    prev_total = len(prev_data)
    delta = cur_total - prev_total
    delta_pct = (delta / prev_total * 100) if prev_total else 0

    return {
        "current_total": cur_total,
        "previous_total": prev_total,
        "delta": delta,
        "delta_pct": delta_pct,
        "by_product": by_product,
        "by_tag": by_tag,
        "top_increases": increases[:10],
    }


def multi_month_trend(conn, months: list[str]) -> dict:
    """다개월 추이 데이터.

    Returns:
        {
            "months": [월 리스트],
            "total_by_month": {월: 건수, ...},
            "cost_by_month": {월: 금액, ...},
            "by_product_month": {품목: {월: 건수, ...}, ...},
            "by_tag_month": {태그: {월: 건수, ...}, ...},
        }
    """
    total_by_month = {}
    cost_by_month = {}
    by_product = defaultdict(lambda: {})
    by_tag = defaultdict(lambda: {})

    for month in months:
        cases = get_cases_by_month(conn, month)
        tagged = get_tagged_cases_by_month(conn, month)

        total_by_month[month] = len(cases)

        # 비용
        row = conn.execute(
            "SELECT total_cost FROM uploaded_files WHERE year_month = ?", (month,)
        ).fetchone()
        cost_by_month[month] = row["total_cost"] if row and row["total_cost"] else 0

        # 품목별
        product_counts = Counter(r.get("product_group", "(미분류)") for r in tagged)
        for p, cnt in product_counts.items():
            by_product[p][month] = cnt

        # 태그별
        tag_counts = Counter(r.get("standard_tag", "(미분류)") for r in tagged)
        for t, cnt in tag_counts.items():
            by_tag[t][month] = cnt

    return {
        "months": months,
        "total_by_month": total_by_month,
        "cost_by_month": cost_by_month,
        "by_product_month": dict(by_product),
        "by_tag_month": dict(by_tag),
    }


def detect_anomalies(trend_data: dict) -> list[dict]:
    """이상 징후 탐지: 연속 증가, 급증 스파이크.

    Returns:
        [{"type": "consecutive_increase"|"spike", "subject": str,
          "months": [월], "detail": str}, ...]
    """
    anomalies = []
    months = trend_data["months"]

    # 품목별 + 태그별 모두 검사
    for label, data_by_month in [
        ("품목", trend_data.get("by_product_month", {})),
        ("태그", trend_data.get("by_tag_month", {})),
    ]:
        for subject, month_data in data_by_month.items():
            values = [month_data.get(m, 0) for m in months]

            # 연속 증가 탐지
            consecutive = 0
            for i in range(1, len(values)):
                if values[i] > values[i - 1]:
                    consecutive += 1
                else:
                    consecutive = 0
                if consecutive >= ANOMALY_CONSECUTIVE:
                    anomalies.append({
                        "type": "consecutive_increase",
                        "subject": f"{label}: {subject}",
                        "months": months[i - consecutive:i + 1],
                        "detail": f"{consecutive + 1}개월 연속 증가",
                    })

            # 급증 탐지 (Z-score 기반)
            if len(values) >= 3:
                import statistics
                mean = statistics.mean(values[:-1]) if len(values) > 1 else values[0]
                stdev = statistics.stdev(values[:-1]) if len(values) > 2 else 0

                if stdev > 0 and values[-1] > 0:
                    zscore = (values[-1] - mean) / stdev
                    if zscore >= ANOMALY_ZSCORE:
                        anomalies.append({
                            "type": "spike",
                            "subject": f"{label}: {subject}",
                            "months": [months[-1]],
                            "detail": f"급증 (Z={zscore:.1f}, "
                                      f"평균 {mean:.0f} → {values[-1]}건)",
                        })

    return anomalies


def get_special_cases(conn, year_month: str,
                      threshold: int = SPECIAL_CASE_THRESHOLD) -> dict:
    """세트교환요구/고객불만 중 월 N건 이상 품목 도출.

    Returns:
        {
            "exchange": {품목: [케이스 리스트], ...},
            "complaint": {품목: [케이스 리스트], ...},
        }
    """
    cases = get_cases_by_month(conn, year_month)

    exchange_by_product = defaultdict(list)
    complaint_by_product = defaultdict(list)

    for case in cases:
        jtype = case.get("judgment_type") or ""
        product = case.get("product_group") or "(미분류)"

        if JUDGMENT_EXCHANGE in jtype:
            exchange_by_product[product].append(case)
        if JUDGMENT_COMPLAINT in jtype:
            complaint_by_product[product].append(case)

    # threshold 이상만 필터
    exchange = {p: cs for p, cs in exchange_by_product.items() if len(cs) >= threshold}
    complaint = {p: cs for p, cs in complaint_by_product.items() if len(cs) >= threshold}

    return {"exchange": exchange, "complaint": complaint}


def get_cost_comparison(conn, current_month: str, previous_month: str) -> dict:
    """전월/당월 비용 비교.

    Returns:
        {"current_cost": float, "previous_cost": float,
         "delta": float, "delta_pct": float}
    """
    cur = conn.execute(
        "SELECT total_cost FROM uploaded_files WHERE year_month = ?", (current_month,)
    ).fetchone()
    prev = conn.execute(
        "SELECT total_cost FROM uploaded_files WHERE year_month = ?", (previous_month,)
    ).fetchone()

    cur_cost = cur["total_cost"] if cur and cur["total_cost"] else 0
    prev_cost = prev["total_cost"] if prev and prev["total_cost"] else 0
    delta = cur_cost - prev_cost
    delta_pct = (delta / prev_cost * 100) if prev_cost else 0

    return {
        "current_cost": cur_cost,
        "previous_cost": prev_cost,
        "delta": delta,
        "delta_pct": delta_pct,
    }
