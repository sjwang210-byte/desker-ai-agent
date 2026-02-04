"""사용자 스타일 학습 — 피드백 기반 추천 개선."""

from core.database import get_connection, add_synonym, get_all_tags, get_all_synonyms
from core.tag_engine import find_matching_tag
from utils.korean_utils import normalize_text


def build_training_pairs(conn, year_month: str | None = None) -> list[dict]:
    """확정된 태그에서 (원문, 태그) 학습 쌍 추출.

    Returns:
        [{"text": "조치결과 원문", "tag": "표준 태그", "tag_id": int}, ...]
    """
    sql = """
        SELECT rc.action_notes, rc.request_details,
               td.standard_tag, td.id as tag_id
        FROM case_tags ct
        JOIN repair_cases rc ON ct.case_id = rc.id
        JOIN tag_dictionary td ON ct.tag_id = td.id
        WHERE ct.is_final = 1
    """
    params = []
    if year_month:
        sql += " AND rc.year_month = ?"
        params.append(year_month)

    rows = conn.execute(sql, params).fetchall()
    pairs = []
    for r in rows:
        text = f"{r['action_notes'] or ''} {r['request_details'] or ''}".strip()
        if text:
            pairs.append({
                "text": text,
                "tag": r["standard_tag"],
                "tag_id": r["tag_id"],
            })
    return pairs


def update_synonym_from_feedback(conn, ai_raw_text: str, confirmed_tag_id: int):
    """사용자가 AI 제안을 수정/확정한 경우, 원문을 동의어로 자동 등록."""
    if not ai_raw_text:
        return

    normalized = normalize_text(ai_raw_text)
    if not normalized:
        return

    # 이미 정확 매치되는 태그/동의어가 있으면 추가 불필요
    match = find_matching_tag(ai_raw_text, conn)
    if match and match["tag_id"] == confirmed_tag_id and match["method"] in ("exact", "synonym"):
        return

    try:
        add_synonym(conn, normalized, confirmed_tag_id)
    except Exception:
        pass  # 중복 무시


def get_similar_past_cases(conn, case: dict, top_n: int = 3) -> list[dict]:
    """유사한 과거 확정 케이스를 검색 (간단한 키워드 기반).

    Returns:
        [{"action_notes": str, "tag": str, "product_group": str}, ...]
    """
    action = case.get("action_notes") or ""
    product = case.get("product_group") or ""

    if not action:
        return []

    # 같은 품목군에서 확정된 케이스 중 가장 유사한 것
    sql = """
        SELECT rc.action_notes, rc.request_details, rc.product_group,
               td.standard_tag
        FROM case_tags ct
        JOIN repair_cases rc ON ct.case_id = rc.id
        JOIN tag_dictionary td ON ct.tag_id = td.id
        WHERE ct.is_final = 1 AND rc.id != ?
    """
    params = [case.get("id", 0)]

    if product:
        sql += " AND rc.product_group = ?"
        params.append(product)

    sql += " ORDER BY rc.created_at DESC LIMIT ?"
    params.append(top_n * 5)  # 후보를 넉넉히 가져와서 필터링

    rows = conn.execute(sql, params).fetchall()

    # 간단한 유사도: 공통 키워드 수
    from utils.korean_utils import extract_keywords
    target_kw = set(extract_keywords(action))

    scored = []
    for r in rows:
        past_text = f"{r['action_notes'] or ''} {r['request_details'] or ''}"
        past_kw = set(extract_keywords(past_text))
        overlap = len(target_kw & past_kw)
        if overlap > 0:
            scored.append((overlap, dict(r)))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [s[1] for s in scored[:top_n]]
