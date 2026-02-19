"""스펙 포지셔닝 분석용 Plotly 차트 빌더."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

_FONT = dict(family="Malgun Gothic, sans-serif")
_TEMPLATE = "plotly_white"

# 카테고리별 스타일
_CATEGORY_STYLE = {
    "프리미엄": {"color": "#9C27B0", "symbol": "diamond", "size": 12},
    "가성비":   {"color": "#4CAF50", "symbol": "triangle-up", "size": 12},
    "보급형":   {"color": "#2196F3", "symbol": "circle", "size": 10},
    "과잉스펙": {"color": "#FF9800", "symbol": "square", "size": 10},
}
_OUR_STYLE = {"color": "#E53935", "symbol": "star", "size": 20}


def build_positioning_map(
    scored_df: pd.DataFrame,
    column_config: dict,
    categories: dict[str, str],
    our_product: dict | None = None,
    show_quadrant_lines: bool = True,
    show_labels: bool = True,
) -> go.Figure:
    """X=가격, Y=스펙 점수 스캐터 포지셔닝 맵을 생성한다."""
    fig = go.Figure()

    product_col = column_config["product_col"]
    price_col = column_config["price_col"]
    spec_cols = column_config["spec_cols"]

    # 카테고리별 트레이스 추가
    for cat_name, style in _CATEGORY_STYLE.items():
        mask = scored_df[product_col].map(
            lambda name, cn=cat_name: categories.get(str(name)) == cn
        )
        subset = scored_df[mask]
        if subset.empty:
            continue

        hover_texts = []
        for _, row in subset.iterrows():
            parts = [f"<b>{row[product_col]}</b>"]
            parts.append(f"가격: {row[price_col]:,.0f}")
            parts.append(f"스펙 점수: {row['spec_score']:.1f}")
            for sc in spec_cols:
                parts.append(f"{sc}: {row[sc]}")
            hover_texts.append("<br>".join(parts))

        fig.add_trace(go.Scatter(
            x=subset[price_col],
            y=subset["spec_score"],
            mode="markers+text" if show_labels else "markers",
            name=cat_name,
            text=subset[product_col] if show_labels else None,
            textposition="top center",
            textfont=dict(size=9),
            hovertext=hover_texts,
            hoverinfo="text",
            marker=dict(
                color=style["color"],
                symbol=style["symbol"],
                size=style["size"],
                line=dict(width=1, color="white"),
            ),
        ))

    # 우리 제품 표시
    if our_product:
        fig.add_trace(go.Scatter(
            x=[our_product["price"]],
            y=[our_product["spec_score"]],
            mode="markers+text",
            name="우리 제품",
            text=[our_product["product_name"]],
            textposition="top center",
            textfont=dict(size=11, color=_OUR_STYLE["color"]),
            hovertext=[
                f"<b>{our_product['product_name']}</b><br>"
                f"가격: {our_product['price']:,.0f}<br>"
                f"스펙 점수: {our_product['spec_score']:.1f}<br>"
                f"카테고리: {our_product['category']}<br>"
                f"가치 지수: {our_product['value_index']:.1f}"
            ],
            hoverinfo="text",
            marker=dict(
                color=_OUR_STYLE["color"],
                symbol=_OUR_STYLE["symbol"],
                size=_OUR_STYLE["size"],
                line=dict(width=2, color="darkred"),
            ),
            showlegend=True,
        ))

    # 사분면 선
    if show_quadrant_lines and len(scored_df) >= 4:
        median_price = scored_df[price_col].median()
        median_score = scored_df["spec_score"].median()

        fig.add_hline(
            y=median_score, line_dash="dash", line_color="gray", opacity=0.4,
            annotation_text=f"스펙 중앙값: {median_score:.1f}",
            annotation_position="top left",
            annotation_font_size=10,
            annotation_font_color="gray",
        )
        fig.add_vline(
            x=median_price, line_dash="dash", line_color="gray", opacity=0.4,
            annotation_text=f"가격 중앙값: {median_price:,.0f}",
            annotation_position="top right",
            annotation_font_size=10,
            annotation_font_color="gray",
        )

        # 사분면 라벨
        x_min, x_max = scored_df[price_col].min(), scored_df[price_col].max()
        y_min, y_max = scored_df["spec_score"].min(), scored_df["spec_score"].max()
        x_pad = (x_max - x_min) * 0.05
        y_pad = (y_max - y_min) * 0.05

        quadrant_labels = [
            ((x_min + median_price) / 2, (median_score + y_max) / 2, "가성비 우수"),
            ((median_price + x_max) / 2, (median_score + y_max) / 2, "프리미엄"),
            ((x_min + median_price) / 2, (y_min + median_score) / 2, "보급형"),
            ((median_price + x_max) / 2, (y_min + median_score) / 2, "과잉 가격"),
        ]
        for qx, qy, qlabel in quadrant_labels:
            fig.add_annotation(
                x=qx, y=qy, text=qlabel,
                showarrow=False,
                font=dict(size=14, color="rgba(0,0,0,0.1)"),
            )

    fig.update_layout(
        title="스펙 기반 제품 포지셔닝 맵",
        xaxis_title="가격",
        yaxis_title="가중 스펙 점수 (0-100)",
        font=_FONT,
        template=_TEMPLATE,
        height=650,
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1,
        ),
        xaxis=dict(tickformat=","),
    )

    return fig


def build_weight_bar_chart(
    weights: dict[str, float],
    title: str = "스펙 가중치 분포",
) -> go.Figure:
    """가중치 분포를 수평 바 차트로 표시한다."""
    sorted_items = sorted(weights.items(), key=lambda x: x[1], reverse=True)
    names = [item[0] for item in sorted_items]
    values = [item[1] for item in sorted_items]

    fig = go.Figure(go.Bar(
        x=values, y=names, orientation="h",
        text=[f"{v:.1%}" for v in values],
        textposition="outside",
        marker_color="#1E88E5",
    ))
    fig.update_layout(
        title=title, font=_FONT, template=_TEMPLATE,
        height=max(300, len(names) * 35),
        xaxis_title="가중치",
        yaxis=dict(autorange="reversed"),
    )
    return fig


def build_spec_radar_chart(
    products: list[dict],
    spec_cols: list[str],
    title: str = "스펙 비교 레이더 차트",
) -> go.Figure:
    """선택 제품들의 정규화된 스펙을 레이더 차트로 비교한다."""
    fig = go.Figure()

    for product in products:
        r_values = [product.get(f"{sc}_norm", 0) for sc in spec_cols]
        r_values.append(r_values[0])  # 폴리곤 닫기
        theta = list(spec_cols) + [spec_cols[0]]

        fig.add_trace(go.Scatterpolar(
            r=r_values, theta=theta,
            name=product.get("product_name", ""),
            fill="toself",
            opacity=0.6,
        ))

    fig.update_layout(
        title=title, font=_FONT, template=_TEMPLATE,
        polar=dict(radialaxis=dict(visible=True, range=[0, 1])),
        height=500,
    )
    return fig
