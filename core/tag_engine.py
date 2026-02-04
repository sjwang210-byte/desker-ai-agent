"""태그 추출, 정규화, 동의어 매칭 엔진."""

from rapidfuzz import fuzz, process

from config import FUZZY_MATCH_THRESHOLD
from core.database import (
    get_all_tags, get_all_synonyms, add_new_tag_candidate,
)
from utils.korean_utils import normalize_text


def find_matching_tag(raw_text: str, conn) -> dict | None:
    """규칙 기반으로 가장 적합한 태그를 찾는다.

    순서: 정확 매치 → 동의어 매치 → 퍼지 매치.

    Returns:
        {"tag_id": int, "standard_tag": str, "confidence": float, "method": str}
        또는 None
    """
    if not raw_text:
        return None

    normalized = normalize_text(raw_text)
    tags = get_all_tags(conn)
    synonyms = get_all_synonyms(conn)

    # 1) 정확 매치 (정규화 후)
    for t in tags:
        if normalize_text(t["standard_tag"]) == normalized:
            return {
                "tag_id": t["id"],
                "standard_tag": t["standard_tag"],
                "confidence": 1.0,
                "method": "exact",
            }

    # 2) 동의어 매치
    for syn, tag_id in synonyms.items():
        if normalize_text(syn) == normalized:
            tag = next((t for t in tags if t["id"] == tag_id), None)
            if tag:
                return {
                    "tag_id": tag_id,
                    "standard_tag": tag["standard_tag"],
                    "confidence": 0.95,
                    "method": "synonym",
                }

    # 3) 퍼지 매치
    tag_texts = {t["id"]: t["standard_tag"] for t in tags}
    all_candidates = list(tag_texts.values())
    if not all_candidates:
        return None

    result = process.extractOne(
        normalized,
        [normalize_text(c) for c in all_candidates],
        scorer=fuzz.ratio,
    )
    if result and result[1] >= FUZZY_MATCH_THRESHOLD:
        idx = result[2]
        tag_id = list(tag_texts.keys())[idx]
        return {
            "tag_id": tag_id,
            "standard_tag": all_candidates[idx],
            "confidence": result[1] / 100.0,
            "method": "fuzzy",
        }

    return None


def suggest_similar_tags(raw_text: str, conn, top_n: int = 5) -> list[dict]:
    """유사 태그 Top-N 추천 (퍼지 매치 기반)."""
    if not raw_text:
        return []

    normalized = normalize_text(raw_text)
    tags = get_all_tags(conn)
    if not tags:
        return []

    tag_texts = [(t["id"], t["standard_tag"]) for t in tags]
    results = process.extract(
        normalized,
        [normalize_text(t[1]) for t in tag_texts],
        scorer=fuzz.ratio,
        limit=top_n,
    )

    suggestions = []
    for match_text, score, idx in results:
        tag_id, standard_tag = tag_texts[idx]
        suggestions.append({
            "tag_id": tag_id,
            "standard_tag": standard_tag,
            "similarity": score / 100.0,
        })

    return suggestions


def process_case_rule_based(case: dict, conn) -> list[dict]:
    """단일 케이스를 규칙 기반으로 태깅 시도.

    조치결과특이사항 + 요구내역 텍스트를 분석하여 태그를 매칭.

    Returns:
        [{"tag_id": int, "standard_tag": str, "confidence": float,
          "method": str, "ai_raw_text": str}, ...]
    """
    action = case.get("action_notes") or ""
    request = case.get("request_details") or ""
    combined = f"{action} {request}".strip()

    if not combined:
        return []

    # 기존 태그 사전의 각 태그가 텍스트에 포함되어 있는지 확인
    tags = get_all_tags(conn)
    matches = []

    for t in tags:
        tag_text = t["standard_tag"]
        norm_tag = normalize_text(tag_text)
        norm_combined = normalize_text(combined)

        # 태그가 텍스트에 직접 포함?
        if norm_tag in norm_combined:
            matches.append({
                "tag_id": t["id"],
                "standard_tag": tag_text,
                "confidence": 0.85,
                "method": "contains",
                "ai_raw_text": tag_text,
            })

    return matches
