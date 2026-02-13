"""고객 프로파일 분석용 Plotly 차트 빌더."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_FONT = dict(family="Malgun Gothic, sans-serif")
_TEMPLATE = "plotly_white"


def stacked_bar_chart(
    result_df: pd.DataFrame,
    attribute_values: list[str],
    title: str = "고객 프로파일 분포",
    orientation: str = "h",
) -> go.Figure:
    """100% 스택 바 차트로 카테고리별 속성값 비중을 표시한다."""
    if result_df.empty:
        fig = go.Figure()
        fig.update_layout(title=title, font=_FONT, template=_TEMPLATE)
        return fig

    categories = result_df["category"].tolist()

    fig = go.Figure()
    for attr in attribute_values:
        if attr not in result_df.columns:
            continue
        vals = result_df[attr].tolist()
        fig.add_trace(go.Bar(
            name=attr,
            x=vals if orientation == "h" else categories,
            y=categories if orientation == "h" else vals,
            orientation=orientation,
            text=[f"{v:.1f}%" for v in vals],
            textposition="inside",
            insidetextanchor="middle",
            hovertemplate=f"{attr}: %{{text}}<extra></extra>",
        ))

    fig.update_layout(
        barmode="stack",
        title=title,
        font=_FONT,
        template=_TEMPLATE,
        height=max(400, len(categories) * 40),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
        ),
        margin=dict(l=150),
    )

    if orientation == "h":
        fig.update_xaxes(title_text="비율 (%)", range=[0, 100])
        fig.update_yaxes(title_text="", autorange="reversed")
    else:
        fig.update_yaxes(title_text="비율 (%)", range=[0, 100])
        fig.update_xaxes(title_text="")

    return fig


def pie_chart(
    result_df: pd.DataFrame,
    category_value: str,
    attribute_values: list[str],
    title: str | None = None,
) -> go.Figure:
    """특정 카테고리의 속성값 비중을 파이 차트로 표시한다."""
    row = result_df[result_df["category"] == category_value]
    if row.empty:
        fig = go.Figure()
        fig.update_layout(
            title=title or category_value, font=_FONT, template=_TEMPLATE,
        )
        return fig

    row = row.iloc[0]
    labels = [a for a in attribute_values if a in row.index]
    values = [row[a] for a in labels]

    fig = px.pie(
        names=labels,
        values=values,
        title=title or f"{category_value} 고객 프로파일",
        template=_TEMPLATE,
    )
    fig.update_layout(font=_FONT)
    fig.update_traces(
        texttemplate="%{label}<br>%{value:.1f}%",
        textposition="inside",
    )
    return fig


def grouped_bar_integrated(
    integrated_results: dict[str, pd.DataFrame],
    category_value: str,
    title: str | None = None,
) -> go.Figure:
    """3개 차원을 서브플롯으로 나란히 표시하는 막대 차트."""
    dims = list(integrated_results.keys())
    n_dims = len(dims)

    if n_dims == 0:
        fig = go.Figure()
        fig.update_layout(title="데이터 없음", font=_FONT, template=_TEMPLATE)
        return fig

    fig = make_subplots(
        rows=1, cols=n_dims,
        subplot_titles=dims,
        horizontal_spacing=0.08,
    )

    colors = px.colors.qualitative.Set2

    for i, dim in enumerate(dims, 1):
        df = integrated_results[dim]
        if df.empty:
            continue

        attr_cols = [
            c for c in df.columns
            if not c.endswith("_abs") and c != "합계"
        ]
        values = [df[attr].iloc[0] for attr in attr_cols]

        fig.add_trace(
            go.Bar(
                x=attr_cols,
                y=values,
                marker_color=colors[: len(attr_cols)],
                text=[f"{v:.1f}%" for v in values],
                textposition="outside",
                showlegend=False,
            ),
            row=1,
            col=i,
        )
        max_val = max(values) if values else 100
        fig.update_yaxes(range=[0, max_val * 1.3], row=1, col=i)

    fig.update_layout(
        title=title or f"'{category_value}' 통합 고객 프로파일",
        font=_FONT,
        template=_TEMPLATE,
        height=420,
    )

    return fig
