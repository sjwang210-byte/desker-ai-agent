"""웹 페이지 크롤링 — HTML 가져오기 및 정제."""

import asyncio
import json
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from config import SCANNER_REQUEST_TIMEOUT, SCANNER_MAX_HTML_LENGTH, SCANNER_CONCURRENT_FETCHES

# Playwright는 선택적 의존성
try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

# httpx 결과 본문이 이 길이 미만이면 Playwright로 재시도
MIN_CONTENT_LENGTH = 2000

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


def validate_url(url: str) -> bool:
    """URL 형식 유효성 검사."""
    try:
        result = urlparse(url.strip())
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False


async def _fetch_single(client: httpx.AsyncClient, url: str) -> dict:
    """단일 URL에서 HTML 가져오기."""
    try:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return {"url": url, "status": resp.status_code, "html": resp.text, "error": None}
    except httpx.TimeoutException:
        return {"url": url, "status": 0, "html": "", "error": "시간 초과"}
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        msg = "접근 차단됨" if code in (403, 429) else f"HTTP {code} 오류"
        return {"url": url, "status": code, "html": "", "error": msg}
    except Exception as e:
        return {"url": url, "status": 0, "html": "", "error": f"연결 오류: {type(e).__name__}"}


async def _fetch_all(urls: list[str], progress_callback=None) -> list[dict]:
    """여러 URL을 동시에 가져오기 (세마포어로 동시성 제한)."""
    sem = asyncio.Semaphore(SCANNER_CONCURRENT_FETCHES)
    results = []

    async def _limited_fetch(client, url, idx):
        async with sem:
            result = await _fetch_single(client, url)
            if progress_callback:
                progress_callback(idx + 1, len(urls), "fetch")
            return result

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=httpx.Timeout(SCANNER_REQUEST_TIMEOUT),
    ) as client:
        tasks = [_limited_fetch(client, url, i) for i, url in enumerate(urls)]
        results = await asyncio.gather(*tasks)

    return list(results)


def _fetch_with_playwright(url: str) -> dict:
    """Playwright로 JS 렌더링 후 HTML 가져오기 (SPA 사이트 대응)."""
    if not HAS_PLAYWRIGHT:
        return {"url": url, "status": 0, "html": "", "error": "Playwright 미설치"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=USER_AGENT,
                locale="ko-KR",
                viewport={"width": 1920, "height": 1080},
            )
            context.add_init_script(
                'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            # 네트워크 요청이 완료될 때까지 대기 (SPA 렌더링)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            # 추가 대기 (동적 콘텐츠 렌더링)
            page.wait_for_timeout(3000)
            html = page.content()
            title = page.title() or ""
            browser.close()

            # 차단/CAPTCHA 페이지 감지
            lower_html = html[:1000].lower()
            if "access denied" in title.lower() or "access denied" in lower_html:
                return {"url": url, "status": 403, "html": "", "error": "접근 차단됨 (CDN 보안)"}
            if "보안 확인" in html[:500] or "captcha" in lower_html:
                return {"url": url, "status": 403, "html": "", "error": "보안 인증 필요 (CAPTCHA)"}

            return {"url": url, "status": 200, "html": html, "error": None}
    except Exception as e:
        return {"url": url, "status": 0, "html": "", "error": f"브라우저 오류: {type(e).__name__}"}


def _needs_playwright(html: str) -> bool:
    """HTML 본문이 부실하여 Playwright 재시도가 필요한지 판단."""
    if not html:
        return True
    soup = BeautifulSoup(html, "lxml")
    # script/style 제거 후 텍스트 길이 확인
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    text = soup.get_text(strip=True)
    return len(text) < MIN_CONTENT_LENGTH


def fetch_pages_batch(urls: list[str], progress_callback=None) -> list[dict]:
    """여러 URL을 동시에 가져오기.

    1차: httpx 비동기 요청
    2차: 본문이 부실한 URL은 Playwright로 JS 렌더링 재시도

    Args:
        urls: URL 리스트
        progress_callback: (current, total, phase) -> None

    Returns:
        [{"url": str, "status": int, "html": str, "error": str|None}, ...]
    """
    # 1차: httpx 비동기 요청
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _fetch_all(urls, progress_callback))
                results = future.result()
        else:
            results = loop.run_until_complete(_fetch_all(urls, progress_callback))
    except RuntimeError:
        results = asyncio.run(_fetch_all(urls, progress_callback))

    # 2차: Playwright 폴백 (본문이 부실하거나 403인 경우)
    if HAS_PLAYWRIGHT:
        for i, result in enumerate(results):
            needs_retry = (
                result["error"] == "접근 차단됨"
                or (not result["error"] and _needs_playwright(result["html"]))
            )
            if needs_retry:
                pw_result = _fetch_with_playwright(result["url"])
                if pw_result["html"] and not pw_result["error"]:
                    results[i] = pw_result
                    if progress_callback:
                        progress_callback(i + 1, len(urls), "fetch")

    return results


def extract_json_ld(soup: BeautifulSoup) -> dict | None:
    """JSON-LD 구조화된 데이터 추출 (schema.org/Product)."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            # JSON-LD가 리스트인 경우
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
            elif isinstance(data, dict):
                if data.get("@type") == "Product":
                    return data
                # @graph 안에 있는 경우
                for item in data.get("@graph", []):
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def extract_meta_tags(soup: BeautifulSoup) -> dict:
    """Open Graph 및 메타 태그에서 제품 정보 추출."""
    meta = {}
    og_mapping = {
        "og:title": "title",
        "og:image": "image",
        "og:description": "description",
        "product:price:amount": "price",
        "product:price:currency": "currency",
        "og:price:amount": "price",
    }
    for tag in soup.find_all("meta"):
        prop = tag.get("property", "") or tag.get("name", "")
        content = tag.get("content", "")
        if prop in og_mapping and content:
            meta[og_mapping[prop]] = content
    return meta


def clean_html(raw_html: str, url: str) -> tuple[str, str, str]:
    """Claude 전송용 HTML 정제.

    Returns:
        (structured_data_text, page_content, image_url)
    """
    soup = BeautifulSoup(raw_html, "lxml")

    # 1. 구조화된 데이터 추출
    json_ld = extract_json_ld(soup)
    meta_tags = extract_meta_tags(soup)

    structured_parts = []
    image_url = ""

    if json_ld:
        structured_parts.append(f"[JSON-LD]\n{json.dumps(json_ld, ensure_ascii=False, indent=2)}")
        # JSON-LD에서 이미지 URL 추출
        img = json_ld.get("image")
        if isinstance(img, list) and img:
            image_url = img[0] if isinstance(img[0], str) else img[0].get("url", "")
        elif isinstance(img, str):
            image_url = img
        elif isinstance(img, dict):
            image_url = img.get("url", "")

    if meta_tags:
        structured_parts.append(f"[메타태그]\n{json.dumps(meta_tags, ensure_ascii=False, indent=2)}")
        if not image_url:
            image_url = meta_tags.get("image", "")

    structured_data = "\n\n".join(structured_parts) if structured_parts else "(구조화 데이터 없음)"

    # 2. 불필요한 태그 제거
    for tag in soup.find_all(["script", "style", "svg", "noscript", "iframe", "link", "meta"]):
        tag.decompose()

    # 3. 주요 콘텐츠 영역 찾기 (여러 후보 중 텍스트가 가장 긴 영역 선택)
    candidates = [
        soup.find("main"),
        soup.find("article"),
        soup.find("div", {"id": re.compile(r"product|detail|content", re.I)}),
        soup.find("div", {"class": re.compile(r"product|detail|content", re.I)}),
    ]
    candidates = [c for c in candidates if c]

    if candidates:
        # 텍스트가 가장 긴 후보 선택
        main_content = max(candidates, key=lambda c: len(c.get_text(strip=True)))
        # 후보 중 가장 긴 것도 500자 미만이면 body 전체 사용
        if len(main_content.get_text(strip=True)) < 500:
            main_content = soup.body or soup
    else:
        main_content = soup.body or soup

    # 4. 텍스트 추출
    page_text = main_content.get_text(separator="\n", strip=True)

    # 5. 길이 제한
    if len(page_text) > SCANNER_MAX_HTML_LENGTH:
        page_text = page_text[:SCANNER_MAX_HTML_LENGTH] + "\n... (이하 생략)"

    return structured_data, page_text, image_url
