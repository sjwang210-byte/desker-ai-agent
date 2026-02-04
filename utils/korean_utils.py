"""한국어 텍스트 정규화 유틸리티."""

import re


def normalize_whitespace(text: str) -> str:
    """연속 공백/탭/줄바꿈을 단일 공백으로."""
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text: str) -> str:
    """태그 비교를 위한 텍스트 정규화.

    - 소문자화 (영문)
    - 연속 공백 → 단일 공백
    - 괄호, 특수문자 제거
    - 앞뒤 공백 제거
    """
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[()（）\[\]【】<>{}]", " ", text)
    text = re.sub(r"[^\w\s가-힣]", " ", text)
    text = normalize_whitespace(text)
    return text


def extract_keywords(text: str, min_length: int = 2) -> list[str]:
    """텍스트에서 키워드(한글 2자 이상 단어) 추출."""
    if not text:
        return []
    words = re.findall(r"[가-힣]{2,}", text)
    return list(dict.fromkeys(words))  # 중복 제거, 순서 유지
