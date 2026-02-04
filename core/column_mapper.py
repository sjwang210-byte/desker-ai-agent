"""컬럼 매핑 로직 — 자동 제안, 저장, 불러오기."""

from rapidfuzz import fuzz

from config import DEFAULT_COLUMN_MAPPING


def suggest_mapping(headers: list[str],
                    default_map: dict[str, str] | None = None) -> dict[str, str]:
    """엑셀 헤더 목록을 보고 내부 키에 대한 매핑을 자동 제안.

    Returns:
        {"product_group": "품목군", "product": "제품", ...}
        매칭되지 않은 키는 빈 문자열.
    """
    if default_map is None:
        default_map = DEFAULT_COLUMN_MAPPING

    suggested = {}
    for key, default_col in default_map.items():
        # 1) 정확 매치
        if default_col in headers:
            suggested[key] = default_col
            continue

        # 2) 퍼지 매치
        best_score = 0
        best_match = ""
        for h in headers:
            if not h:
                continue
            score = fuzz.ratio(default_col, h)
            if score > best_score:
                best_score = score
                best_match = h
        suggested[key] = best_match if best_score >= 60 else ""

    return suggested


def validate_mapping(mapping: dict[str, str], headers: list[str]) -> list[str]:
    """매핑이 유효한지 검사. 오류 메시지 리스트 반환 (빈 리스트 = OK)."""
    errors = []
    required_keys = ["action_notes", "request_details"]

    for key in required_keys:
        col = mapping.get(key, "")
        if not col:
            errors.append(f"필수 컬럼 '{key}'이(가) 매핑되지 않았습니다.")
        elif col not in headers:
            errors.append(f"'{col}' 컬럼이 엑셀 헤더에 존재하지 않습니다.")

    return errors
