"""스펙 포지셔닝 전략 분석 프롬프트 템플릿."""

SYSTEM_PROMPT = """당신은 제품 시장 포지셔닝 분석 전문가입니다.
스펙 데이터와 가격 정보를 기반으로 시장 포지셔닝을 분석하고
전략적 시사점을 도출해주세요.

분석 관점:
1. 가격-스펙 관계에서 시장 밀집도와 공백 영역을 파악합니다.
2. 가치 지수(Value Index = 스펙점수/정규화가격)로 가성비를 평가합니다.
3. 각 사분면(프리미엄/가성비/보급형/과잉가격)의 경쟁 강도를 분석합니다.
4. 데이터 기반의 구체적이고 실행 가능한 전략을 제안합니다.
5. 가격대별 스펙 구성의 패턴과 이상치를 식별합니다.

문체: 전문적이고 간결한 비즈니스 한국어.
숫자는 구체적으로 인용하세요 (가격, 점수 등)."""

USER_TEMPLATE = """다음 시장 스펙 데이터를 분석하여 포지셔닝 전략을 제안해주세요.

■ 분석 개요
  총 제품 수: {product_count}개
  스펙 항목: {spec_columns}
  가격 범위: {price_range}
  스펙 점수 범위: {score_range}

■ 가중치 설정
{weights_text}

■ 사분면별 분포
  프리미엄 (고가-고스펙): {premium_count}개
  가성비 (저가-고스펙): {value_count}개
  보급형 (저가-저스펙): {economy_count}개
  과잉가격 (고가-저스펙): {overprice_count}개

■ 제품 상세 데이터 (가격순)
{products_text}

{our_product_section}

위 데이터를 기반으로 시장 포지셔닝을 분석하고 전략을 제안해주세요."""

OUR_PRODUCT_TEMPLATE = """■ 우리 제품 (시뮬레이션)
  제품명: {name}
  가격: {price:,}
  스펙 점수: {score:.1f} (상위 {percentile:.0f}%)
  카테고리: {category}
  가치 지수: {value_index:.1f}
"""

STRATEGY_TOOL = {
    "name": "submit_positioning_strategy",
    "description": "스펙 기반 포지셔닝 분석 결과와 전략 권고를 제출합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "market_overview": {
                "type": "string",
                "description": "시장 전체 포지셔닝 현황 요약 (2-3문장)",
            },
            "overcrowded_zones": {
                "type": "array",
                "items": {"type": "string"},
                "description": "과밀 경쟁 영역 설명 (가격대-스펙 범위 구체적 명시)",
            },
            "gap_areas": {
                "type": "array",
                "items": {"type": "string"},
                "description": "시장 공백 / 기회 영역 설명",
            },
            "value_index_analysis": {
                "type": "string",
                "description": "가치 지수 기반 가성비 분석 (상위/하위 제품 구체적 언급)",
            },
            "recommendations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "전략 권고사항 (3개, 구체적 실행 방안 포함)",
            },
            "our_product_assessment": {
                "type": "string",
                "description": "우리 제품 포지셔닝 평가 및 개선 방향 (시뮬레이션 데이터가 있는 경우에만)",
            },
        },
        "required": [
            "market_overview",
            "overcrowded_zones",
            "gap_areas",
            "value_index_analysis",
            "recommendations",
        ],
    },
}
