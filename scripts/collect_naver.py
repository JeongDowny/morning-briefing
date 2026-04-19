"""네이버 경제뉴스 수집.

두 가지 모드 (briefing.json 의 enabled 플래그로 on/off):

1. 키워드 검색 (keyword_search) — 추천, 진짜 경제 뉴스
   - 네이버 개발자 API `/v1/search/news.json` 호출
   - 환경변수: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET
   - 키워드별로 pubDate 기준 최신 per_keyword 건 수집
   - window (직전 24시간) 필터 적용

2. 경제지 랭킹 (ranking) — 옵션, "많이 본 뉴스" 중 경제 전문지 화이트리스트
   - 클릭 많은 기사 기반이라 연예·사회 섞일 수 있음
   - keyword_search 가 충분하면 비활성 권장

출력: collected/naver.json
"""
from __future__ import annotations

import html as html_mod
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "briefing.json"
OUTPUT_DIR = ROOT / "collected"
OUTPUT_PATH = OUTPUT_DIR / "naver.json"

NAVER_RANKING_URL = "https://news.naver.com/main/ranking/popularDay.naver"
NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def compute_window(_time_kst: str | None = None) -> tuple[datetime, datetime]:
    """최근 24시간 창 (KST) — 언제 실행되든 일관되게 '지금 기준 지난 24시간'."""
    end = datetime.now(ZoneInfo("Asia/Seoul"))
    start = end - timedelta(days=1)
    return start, end


def strip_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    return html_mod.unescape(text).strip()


def parse_pubdate(s: str) -> datetime | None:
    if not s:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Seoul"))
        return dt.astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        return None


def domain_from_url(url: str) -> str:
    m = re.search(r"https?://([^/]+)", url or "")
    if not m:
        return ""
    host = m.group(1).lower()
    # 대표 언론사 도메인 → 한글 이름 매핑 (점진적 확장)
    mapping = {
        "www.hankyung.com": "한국경제",
        "n.news.naver.com": "",  # 네이버 래퍼는 press 비움
        "www.mk.co.kr": "매일경제",
        "www.edaily.co.kr": "이데일리",
        "www.mt.co.kr": "머니투데이",
        "biz.chosun.com": "조선비즈",
        "www.asiae.co.kr": "아시아경제",
        "www.sedaily.com": "서울경제",
        "www.fnnews.com": "파이낸셜뉴스",
        "www.hankookilbo.com": "한국일보",
        "www.donga.com": "동아일보",
        "www.chosun.com": "조선일보",
        "www.yna.co.kr": "연합뉴스",
        "news.kbs.co.kr": "KBS",
        "imnews.imbc.com": "MBC",
        "news.sbs.co.kr": "SBS",
        "news.jtbc.co.kr": "JTBC",
        "www.ytn.co.kr": "YTN",
    }
    return mapping.get(host, host)


# ─── 키워드 검색 ───────────────────────────────────────────────────

def fetch_keyword(client_id: str, client_secret: str, keyword: str, display: int, sort: str) -> list[dict[str, Any]]:
    resp = requests.get(
        NAVER_SEARCH_URL,
        params={"query": keyword, "display": display, "sort": sort},
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])


def collect_keyword_search(cfg: dict[str, Any], start_kst: datetime, end_kst: datetime) -> list[dict[str, Any]]:
    ks = cfg.get("naver_news", {}).get("keyword_search", {})
    if not ks.get("enabled"):
        print("[collect_naver] keyword_search 비활성 → 스킵", file=sys.stderr)
        return []

    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("[collect_naver] NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수 필요", file=sys.stderr)
        return []

    keywords = ks.get("keywords", [])
    per_keyword = ks.get("per_keyword", 3)
    sort = ks.get("sort", "date")

    seen_urls: set[str] = set()
    collected: list[dict[str, Any]] = []

    for kw in keywords:
        term = kw.get("term", "").strip() if isinstance(kw, dict) else str(kw).strip()
        category = kw.get("category", "") if isinstance(kw, dict) else ""
        if not term:
            continue
        try:
            items = fetch_keyword(client_id, client_secret, term, display=per_keyword * 3, sort=sort)
        except Exception as e:
            print(f"[collect_naver] '{term}' 검색 실패: {e}", file=sys.stderr)
            continue

        kept = 0
        for it in items:
            pub = parse_pubdate(it.get("pubDate", ""))
            if pub and not (start_kst <= pub <= end_kst):
                continue
            origlink = it.get("originallink") or it.get("link", "")
            if origlink in seen_urls:
                continue
            seen_urls.add(origlink)
            collected.append({
                "title": strip_html(it.get("title", "")),
                "link": it.get("link", ""),
                "originallink": origlink,
                "press": domain_from_url(origlink),
                "lead": strip_html(it.get("description", "")),
                "published_at": pub.isoformat(timespec="seconds") if pub else None,
                "keyword": term,
                "category": category,
            })
            kept += 1
            if kept >= per_keyword:
                break
        print(f"[collect_naver] #{term} → {kept}건", file=sys.stderr)

    return collected


# ─── 랭킹 (옵션) ─────────────────────────────────────────────────────

def fetch_ranking_html() -> str:
    resp = requests.get(
        NAVER_RANKING_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    resp.encoding = "euc-kr"
    return resp.text


def extract_press_name(header_text: str) -> str:
    if not header_text:
        return ""
    return header_text.split("랭킹")[0].strip()


def parse_ranking(html: str, press_whitelist: list[str], top_n: int) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    boxes = soup.select("div.rankingnews_box")
    whitelist_set = {p.strip() for p in press_whitelist}

    collected: list[dict[str, Any]] = []
    rank = 0
    for box in boxes:
        press_el = box.select_one(".rankingnews_name, strong.rankingnews_name, a.rankingnews_name")
        press = extract_press_name(press_el.get_text(strip=True) if press_el else "")
        if press not in whitelist_set:
            continue
        for li in box.select("ul.rankingnews_list li"):
            a_el = li.select_one("a.list_title, a[href*='n.news.naver.com']")
            if not a_el:
                continue
            title = a_el.get_text(strip=True)
            url = a_el.get("href", "")
            if not title or not url:
                continue
            rank += 1
            collected.append({
                "rank": rank,
                "title": title,
                "url": url,
                "press": press,
                "lead": None,
                "category": "랭킹",
            })
            if rank >= top_n:
                return collected
    return collected


def collect_ranking(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    rcfg = cfg.get("naver_news", {}).get("ranking", {})
    if not rcfg.get("enabled"):
        return []
    whitelist = rcfg.get("press_whitelist", [])
    top_n = rcfg.get("top_n", 10)
    if not whitelist:
        return []
    try:
        html = fetch_ranking_html()
        items = parse_ranking(html, whitelist, top_n)
        print(f"[collect_naver] 랭킹 → {len(items)}건", file=sys.stderr)
        return items
    except Exception as e:
        print(f"[collect_naver] 랭킹 수집 실패: {e}", file=sys.stderr)
        return []


# ─── 엔트리포인트 ────────────────────────────────────────────────────

def main() -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)
    cfg = load_config()

    time_kst = cfg.get("schedule", {}).get("time_kst", "08:00")
    start_kst, end_kst = compute_window(time_kst)

    now_iso = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")

    items = collect_keyword_search(cfg, start_kst, end_kst)
    items.extend(collect_ranking(cfg))

    result = {
        "source": "naver_ranking",
        "collected_at": now_iso,
        "window_start": start_kst.isoformat(timespec="seconds"),
        "window_end": end_kst.isoformat(timespec="seconds"),
        "items": items,
    }

    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(
        f"[collect_naver] 저장 완료: {OUTPUT_PATH.relative_to(ROOT)} (총 {len(items)}건)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
