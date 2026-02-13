from pathlib import Path

# ── 경로 ──
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "desker.db"
UPLOAD_DIR = DATA_DIR / "uploads"

# ── Claude API ──
ANTHROPIC_MODEL = "claude-sonnet-4-5-20250514"

# ── 태깅 임계값 ──
HIGH_CONFIDENCE_THRESHOLD = 0.9
LOW_CONFIDENCE_THRESHOLD = 0.6
FUZZY_MATCH_THRESHOLD = 80          # RapidFuzz 0-100

# ── 배치 처리 ──
BATCH_SIZE = 5                      # Claude API 1회 호출당 건수

# ── 분석 ──
SPECIAL_CASE_THRESHOLD = 5          # 월 N건 이상 시 특이 품목
TREND_MONTHS = 6                    # 기본 추이 분석 기간 (개월)
ANOMALY_CONSECUTIVE = 3             # 연속 증가 탐지 기준 (개월)
ANOMALY_ZSCORE = 2.0                # 급증 탐지 Z-score 기준

# ── 판정형태 구분 ──
JUDGMENT_EXCHANGE = "세트교환요구"
JUDGMENT_COMPLAINT = "고객불만"

# ── 엑셀 컬럼 매핑 기본값 ──
DEFAULT_COLUMN_MAPPING = {
    "product_group": "품목군",
    "product": "제품",
    "action_notes": "조치결과특이사항",
    "request_details": "요구내역",
    "judgment_type": "판정형태",
    "amount": "금액",
}

COLUMN_DISPLAY_NAMES = {
    "product_group": "품목군 (대분류)",
    "product": "제품 (소분류)",
    "action_notes": "조치결과특이사항",
    "request_details": "요구내역",
    "judgment_type": "판정형태",
    "amount": "금액",
}

# ── 비용 시트 ──
COST_SHEET_TOTAL_COLUMN = "전 체"   # 띄어쓰기 주의

# ── 시장 스캐너 ──
SCANNER_MAX_URLS = 10
SCANNER_REQUEST_TIMEOUT = 15         # URL당 요청 제한시간 (초)
SCANNER_MAX_HTML_LENGTH = 50_000     # Claude 전송용 HTML 최대 길이 (문자)
SCANNER_CONCURRENT_FETCHES = 3       # 동시 HTTP 요청 수

# ── 고객 프로파일 분석 ──
PROFILE_DIMENSIONS = {
    "자녀나이": ["초등학생", "미취학", "자녀없음", "중고등학생", "0-24개월", "성인", "(알수없음)"],
    "결혼상태": ["기혼", "미혼", "(알수없음)"],
    "가구당인원": ["2인이상", "1인", "(알수없음)"],
}
PROFILE_CATEGORY_LEVELS = ["대분류", "중분류", "소분류", "세분류", "상품"]
PROFILE_CATEGORY_COLUMNS = ["대분류", "중분류", "소분류", "세분류", "상품명", "상품ID"]
PROFILE_PAYMENT_METRICS = ["결제금액", "결제수", "결제상품수량"]
PROFILE_REFUND_METRICS = ["환불금액", "환불건수", "환불수량"]
PROFILE_DEFAULT_METRIC = "결제금액"
PROFILE_UNKNOWN_VALUE = "(알수없음)"
