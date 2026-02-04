"""보고서 작성 프롬프트 템플릿."""

REPORT_SYSTEM = """당신은 데스커(Desker) 월말 하자보수비 보고서를 작성하는 전문가입니다.
아래 데이터를 기반으로 정해진 형식에 맞춰 보고서를 작성해주세요.

보고서 형식:
1. 전월/당월 하자보수비 금액 비교
2. 전월 대비 증감 현황 문장 (금액 및 퍼센트)
3. [증가 시] 주요 원인 bullet points (품목×원인별)
4. [품목별 특이사항 보고] 섹션
   - 월 5건 이상이고 반복 원인이 있는 품목만 포함
   - ▶ 세트교환요구 하위 리스트 (해당 품목의 세트교환요구 건 상세)
   - ▶ 고객 불만 하위 리스트 (해당 품목의 고객불만 건 상세)

문체: 공식 비즈니스 한국어, 간결하고 데이터 기반.
숫자는 천 단위 콤마 포함.
"""

REPORT_USER_TEMPLATE = """다음 데이터로 {current_month} 하자보수비 보고서를 작성해주세요:

■ 하자보수비 현황
  당월({current_month}): {current_cost}원
  전월({previous_month}): {previous_cost}원
  증감: {delta}원 ({delta_pct})

■ 당월 총 건수: {total_cases}건 / 전월 총 건수: {prev_total_cases}건

■ 주요 증가 원인 (품목×원인별 건수 증감):
{increase_contributors}

■ 월 5건 이상 품목 (판정형태별):
{special_products}

■ 세트교환요구 건:
{exchange_requests}

■ 고객 불만 건:
{customer_complaints}
"""

REPORT_TOOL = {
    "name": "submit_report",
    "description": "생성된 하자보수비 보고서 멘트를 제출합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "report_text": {
                "type": "string",
                "description": "전체 보고서 멘트 (마크다운 형식)"
            },
            "key_findings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "핵심 발견사항 리스트"
            }
        },
        "required": ["report_text", "key_findings"]
    }
}
