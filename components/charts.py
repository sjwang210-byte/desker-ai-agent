"""Plotly 차트 빌더."""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

_FONT = dict(family="Malgun Gothic, sans-serif")
_THEME_KWARGS = dict(template="plotly_white")


def bar_chart_product_cases(data: dict, title: str = "품목군별 건수") -> go.Figure:
    """품목군별 건수 수평 바 차트."""
    matrix = data.get("matrix", {})
    products = list(matrix.keys())
    counts = [sum(matrix[p].values()) for p in products]

    df = pd.DataFrame({"품목군": products, "건수": counts})
    df = df.sort_values("건수", ascending=True)

    fig = px.bar(df, x="건수", y="품목군", orientation="h", title=title, **_THEME_KWARGS)
    fig.update_layout(font=_FONT, height=max(300, len(products) * 30))
    return fig


def heatmap_product_cause(data: dict, title: str = "품목군 × 원인 히트맵") -> go.Figure:
    """품목군 × 원인 태그 히트맵."""
    matrix = data.get("matrix", {})
    products = data.get("products", [])
    tags = data.get("tags", [])

    z = []
    for p in products:
        row = [matrix.get(p, {}).get(t, 0) for t in tags]
        z.append(row)

    fig = go.Figure(data=go.Heatmap(
        z=z, x=tags, y=products,
        colorscale="YlOrRd",
        text=z,
        texttemplate="%{text}",
    ))
    fig.update_layout(
        title=title, font=_FONT,
        height=max(400, len(products) * 35),
        **_THEME_KWARGS,
    )
    return fig


def line_chart_trend(trend_data: dict, title: str = "월별 추이") -> go.Figure:
    """다개월 추이 라인 차트."""
    months = trend_data["months"]
    totals = [trend_data["total_by_month"].get(m, 0) for m in months]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=months, y=totals, mode="lines+markers", name="총 건수",
    ))
    fig.update_layout(title=title, font=_FONT, xaxis_title="월", yaxis_title="건수", **_THEME_KWARGS)
    return fig


def line_chart_cost_trend(trend_data: dict, title: str = "월별 하자보수비 추이") -> go.Figure:
    """다개월 비용 추이 라인 차트."""
    months = trend_data["months"]
    costs = [trend_data["cost_by_month"].get(m, 0) for m in months]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=months, y=costs, mode="lines+markers", name="하자보수비",
        hovertemplate="%{x}<br>%{y:,.0f}원",
    ))
    fig.update_layout(
        title=title, font=_FONT,
        xaxis_title="월", yaxis_title="금액 (원)",
        yaxis_tickformat=",",
        **_THEME_KWARGS,
    )
    return fig


def pie_chart_judgment_types(cases: list[dict], title: str = "판정형태 분포") -> go.Figure:
    """판정형태별 분포 파이 차트."""
    counts = {}
    for c in cases:
        jtype = c.get("judgment_type") or "(미분류)"
        counts[jtype] = counts.get(jtype, 0) + 1

    fig = px.pie(
        names=list(counts.keys()),
        values=list(counts.values()),
        title=title,
        **_THEME_KWARGS,
    )
    fig.update_layout(font=_FONT)
    return fig


def waterfall_chart_mom(mom_data: dict, title: str = "전월 대비 증감") -> go.Figure:
    """품목별 전월 대비 증감 워터폴 차트."""
    by_product = mom_data.get("by_product", {})

    # 변동이 있는 품목만, 절대값 기준 정렬
    items = [(p, d["delta"]) for p, d in by_product.items() if d["delta"] != 0]
    items.sort(key=lambda x: abs(x[1]), reverse=True)
    items = items[:15]  # 상위 15개

    if not items:
        fig = go.Figure()
        fig.update_layout(title=title, font=_FONT)
        return fig

    products = [i[0] for i in items]
    deltas = [i[1] for i in items]
    colors = ["#EF5350" if d > 0 else "#42A5F5" for d in deltas]

    fig = go.Figure(go.Bar(
        x=products, y=deltas,
        marker_color=colors,
        text=[f"+{d}" if d > 0 else str(d) for d in deltas],
        textposition="outside",
    ))
    fig.update_layout(
        title=title, font=_FONT,
        xaxis_title="품목군", yaxis_title="증감 (건)",
        **_THEME_KWARGS,
    )
    return fig


def multi_line_by_subject(trend_data: dict, subject_key: str,
                          title: str = "항목별 추이",
                          top_n: int = 10) -> go.Figure:
    """품목/태그별 다개월 추이 멀티라인."""
    months = trend_data["months"]
    data_by_subject = trend_data.get(subject_key, {})

    # 최근 월 기준 상위 N개
    last_month = months[-1] if months else None
    ranked = sorted(
        data_by_subject.items(),
        key=lambda x: x[1].get(last_month, 0),
        reverse=True,
    )[:top_n]

    fig = go.Figure()
    for subject, month_data in ranked:
        values = [month_data.get(m, 0) for m in months]
        fig.add_trace(go.Scatter(
            x=months, y=values, mode="lines+markers", name=subject,
        ))

    fig.update_layout(title=title, font=_FONT, xaxis_title="월", yaxis_title="건수", **_THEME_KWARGS)
    return fig
