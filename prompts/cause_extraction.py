"""원인 추출 프롬프트 템플릿."""

SYSTEM_PROMPT = """당신은 데스커(Desker) 사무용 가구의 하자보수 데이터를 분석하는 전문가입니다.
주어진 하자보수 텍스트에서 핵심 하자 원인 키워드를 추출해주세요.

규칙:
1. 하나의 케이스에서 1~3개의 원인 태그를 추출합니다.
2. 가능한 한 아래 기존 태그 사전의 표현을 그대로 사용하세요.
3. 기존 태그에 정확히 맞는 것이 없으면, 가장 유사한 기존 태그와 새로 제안하는 표현을 모두 반환하세요.
4. 각 태그에 대해 확신도(0.0~1.0)를 함께 반환하세요.
5. 태그는 간결한 명사구로 작성하세요 (예: "상판 휨", "서랍 레일 불량", "도장 벗겨짐").

기존 태그 사전:
{tag_dictionary}
"""

SINGLE_CASE_TEMPLATE = """다음 하자보수 케이스를 분석해주세요:

품목: {product_group} / {product}
조치결과특이사항: {action_notes}
요구내역: {request_details}

핵심 하자 원인 태그를 추출해주세요."""

BATCH_TEMPLATE = """다음 {count}건의 하자보수 케이스를 분석해주세요.
각 케이스별로 핵심 하자 원인 태그를 추출해주세요.

{cases_text}"""

CASE_ITEM_TEMPLATE = """[케이스 {index}]
품목: {product_group} / {product}
조치결과특이사항: {action_notes}
요구내역: {request_details}
"""

EXTRACTION_TOOL = {
    "name": "submit_cause_tags",
    "description": "하자보수 케이스에서 추출한 원인 태그를 제출합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cases": {
                "type": "array",
                "description": "각 케이스별 추출 결과",
                "items": {
                    "type": "object",
                    "properties": {
                        "case_index": {
                            "type": "integer",
                            "description": "케이스 번호 (1부터 시작)"
                        },
                        "tags": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "tag_text": {
                                        "type": "string",
                                        "description": "추출한 원인 태그"
                                    },
                                    "confidence": {
                                        "type": "number",
                                        "description": "확신도 (0.0~1.0)"
                                    },
                                    "matched_existing": {
                                        "type": "string",
                                        "description": "매칭된 기존 사전 태그 (없으면 빈 문자열)"
                                    },
                                    "is_new": {
                                        "type": "boolean",
                                        "description": "기존 사전에 없는 신규 태그 여부"
                                    }
                                },
                                "required": ["tag_text", "confidence", "is_new"]
                            }
                        },
                        "summary": {
                            "type": "string",
                            "description": "하자 내용 한줄 요약"
                        }
                    },
                    "required": ["case_index", "tags", "summary"]
                }
            }
        },
        "required": ["cases"]
    }
}
