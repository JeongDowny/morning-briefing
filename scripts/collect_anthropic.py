"""Anthropic 공식 블로그 HTML 스크래핑 (공식 RSS 없음).

URL: https://www.anthropic.com/news
출력: collected/anthropic.json
"""
from __future__ import annotations

import json
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
OUTPUT_PATH = OUTPUT_DIR / "anthropic.json"

DEFAULT_URL = "https://www.anthropic.com/news"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def compute_window(time_kst: str) -> tuple[datetime, datetime]:
    h, m = map(int, time_kst.split(":"))
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    end = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if now < end:
        end = end - timedelta(days=1)
    start = end - timedelta(days=1)
    return start, end


def parse_anthropic_news(html: str) -> list[dict[str, Any]]:
    """Anthropic /news 페이지에서 article 카드 추출.

    선택자는 현재 DOM 기준 추정 — 변경 시 업데이트 필요.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, Any]] = []

    for a in soup.select("a[href^='/news/']"):
        href = a.get("href", "")
        if href == "/news" or href == "/news/":
            continue
        title_el = a.select_one("h2, h3, h4, [class*='title'], [class*='heading']")
        title = title_el.get_text(strip=True) if title_el else a.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        lead = ""
        for cand in a.find_all(["p", "div", "span"]):
            text = cand.get_text(strip=True)
            if len(text) > len(lead) and text != title:
                lead = text

        published = None
        time_el = a.select_one("time")
        if time_el and time_el.get("datetime"):
            published = time_el.get("datetime")

        url = href if href.startswith("http") else f"https://www.anthropic.com{href}"

        items.append(
            {
                "title": title,
                "url": url,
                "source_name": "Anthropic",
                "lead": lead[:500] if lead else "",
                "published_at": published,
                "category": "",
            }
        )

    seen = set()
    unique = []
    for it in items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        unique.append(it)
    return unique


def collect() -> dict[str, Any]:
    config = load_config()
    dev_cfg = config.get("dev_news", {})
    if not dev_cfg.get("enabled", False):
        print("[collect_anthropic] dev_news.enabled=false → 스킵", file=sys.stderr)
        return {"source": "anthropic_html", "items": []}

    url = DEFAULT_URL
    for src in dev_cfg.get("sources", []):
        if src.get("name") == "Anthropic":
            url = src.get("url", DEFAULT_URL)
            break

    time_kst = config.get("schedule", {}).get("time_kst", "08:00")
    start_kst, end_kst = compute_window(time_kst)

    now_iso = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    items: list[dict[str, Any]] = []

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        parsed = parse_anthropic_news(resp.text)

        for item in parsed:
            pub = item.get("published_at")
            if pub:
                try:
                    pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Seoul"))
                    if not (start_kst <= pub_dt <= end_kst):
                        continue
                except Exception:
                    pass
            items.append(item)

        print(
            f"[collect_anthropic] {len(items)}건 수집 (parsed {len(parsed)}, filtered by window)",
            file=sys.stderr,
        )
    except Exception as e:
        print(f"[collect_anthropic] 수집 실패: {e}", file=sys.stderr)

    return {
        "source": "anthropic_html",
        "collected_at": now_iso,
        "window_start": start_kst.isoformat(timespec="seconds"),
        "window_end": end_kst.isoformat(timespec="seconds"),
        "items": items,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)
    result = collect()
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(
        f"[collect_anthropic] 저장 완료: {OUTPUT_PATH.relative_to(ROOT)} (총 {len(result['items'])}건)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
