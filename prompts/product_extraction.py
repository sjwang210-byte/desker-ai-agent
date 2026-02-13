"""제품 정보 추출 프롬프트 템플릿."""

SYSTEM_PROMPT = """당신은 한국 가구 이커머스 페이지에서 제품 정보를 추출하는 전문가입니다.
주어진 HTML/텍스트 콘텐츠에서 정확한 제품 정보를 구조화된 형식으로 추출해주세요.

추출 규칙:
1. 9개 필드를 반드시 추출합니다: 제품명, 브랜드, 가격, 원산지, 소재, 옵션, 크기, 리뷰 요약, 주요 특징
2. HTML에서 확인할 수 없는 정보는 "정보 없음"으로 표시합니다.
3. 가격은 숫자만 추출합니다 (원 단위, 콤마 없이).
4. 크기는 가로×세로×높이 형식으로 통일합니다 (mm 단위, 가능한 경우).
5. 옵션은 색상, 크기 등 선택 가능한 변형을 나열합니다.
6. 리뷰가 포함된 경우, 긍정/부정 키워드를 각각 요약합니다.
7. 주요 특징은 경쟁 제품 대비 차별점이 될 수 있는 요소를 2-3개 추출합니다.
8. JSON-LD나 메타태그에 있는 구조화 데이터를 우선 참고하되, 본문 텍스트로 보완합니다.
"""

USER_TEMPLATE = """다음은 가구 제품 페이지에서 추출한 콘텐츠입니다.
제품 정보를 구조화된 형식으로 추출해주세요.

■ URL: {url}

■ 구조화된 데이터 (JSON-LD / 메타태그):
{structured_data}

■ 페이지 본문:
{page_content}
"""

EXTRACTION_TOOL = {
    "name": "submit_product_info",
    "description": "제품 페이지에서 추출한 정보를 제출합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "product_name": {
                "type": "string",
                "description": "제품명 (풀 네임)"
            },
            "brand": {
                "type": "string",
                "description": "브랜드명 또는 판매자명"
            },
            "price": {
                "type": "integer",
                "description": "판매가 (원 단위, 숫자만)"
            },
            "price_display": {
                "type": "string",
                "description": "표시 가격 (정가, 할인가 등 텍스트 포함)"
            },
            "image_url": {
                "type": "string",
                "description": "대표 제품 이미지 URL"
            },
            "country_of_origin": {
                "type": "string",
                "description": "원산지 / 제조국"
            },
            "materials": {
                "type": "string",
                "description": "주요 소재 (프레임, 상판, 패브릭 등)"
            },
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "선택 가능한 옵션 목록 (색상, 사이즈 등)"
            },
            "size": {
                "type": "string",
                "description": "크기/규격 (가로×세로×높이)"
            },
            "review_summary": {
                "type": "object",
                "properties": {
                    "total_count": {
                        "type": "integer",
                        "description": "총 리뷰 수"
                    },
                    "average_rating": {
                        "type": "number",
                        "description": "평균 평점 (5점 만점)"
                    },
                    "positive_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "긍정 키워드 (예: '디자인 만족', '배송 빠름')"
                    },
                    "negative_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "부정 키워드 (예: '조립 어려움', '색상 차이')"
                    },
                    "summary_text": {
                        "type": "string",
                        "description": "리뷰 전체 요약 (1-2문장)"
                    }
                },
                "description": "리뷰 분석 요약"
            },
            "notable_features": {
                "type": "array",
                "items": {"type": "string"},
                "description": "주요 특징 / 차별점 (2-3개)"
            }
        },
        "required": [
            "product_name", "brand", "price", "price_display", "image_url",
            "country_of_origin", "materials", "size",
            "review_summary", "notable_features"
        ]
    }
}


# ── 제품 비교 분석 ──

COMPARISON_SYSTEM = """당신은 가구 시장 분석 전문가입니다.
여러 경쟁 제품의 정보를 비교하여 각 제품의 고유 판매 포인트(USP)를 도출하고,
시장 포지셔닝을 분석해주세요.

분석 관점:
1. 가격 대비 가치 (가성비)
2. 소재 및 품질 차별화
3. 디자인 및 기능적 특징
4. 소비자 반응 (리뷰 기반)
"""

COMPARISON_USER_TEMPLATE = """다음 {count}개 가구 제품을 비교 분석해주세요:

{products_text}

각 제품별 고유 판매 포인트와 전체 시장 포지셔닝을 분석해주세요."""

COMPARISON_TOOL = {
    "name": "submit_comparison",
    "description": "제품 비교 분석 결과를 제출합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "products_analysis": {
                "type": "array",
                "description": "각 제품별 분석 결과",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_name": {
                            "type": "string",
                            "description": "제품명"
                        },
                        "unique_selling_points": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "고유 판매 포인트"
                        },
                        "strengths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "강점"
                        },
                        "weaknesses": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "약점"
                        },
                        "price_positioning": {
                            "type": "string",
                            "description": "가격 포지셔닝 (프리미엄/중가/저가)"
                        }
                    },
                    "required": ["product_name", "unique_selling_points", "strengths", "weaknesses"]
                }
            },
            "market_summary": {
                "type": "string",
                "description": "전체 시장 포지셔닝 요약 (2-3문장)"
            },
            "recommendation": {
                "type": "string",
                "description": "기획자를 위한 시사점 (2-3문장)"
            }
        },
        "required": ["products_analysis", "market_summary"]
    }
}
