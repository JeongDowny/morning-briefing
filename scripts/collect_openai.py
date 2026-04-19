"""OpenAI 공식 블로그 RSS 수집.

RSS: https://openai.com/news/rss.xml (검증 완료: 2026-04-17)
출력: collected/openai.json

config/briefing.json 의 dev_news.enabled 가 false 면 스킵.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "briefing.json"
OUTPUT_DIR = ROOT / "collected"
OUTPUT_PATH = OUTPUT_DIR / "openai.json"

DEFAULT_URL = "https://openai.com/news/rss.xml"


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


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15


def parse_rss_date(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str).astimezone(ZoneInfo("Asia/Seoul"))
    except Exception:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Seoul"))
        except Exception:
            return None


def collect() -> dict[str, Any]:
    config = load_config()
    dev_cfg = config.get("dev_news", {})
    if not dev_cfg.get("enabled", False):
        print("[collect_openai] dev_news.enabled=false → 스킵", file=sys.stderr)
        return {"source": "openai_rss", "items": []}

    url = DEFAULT_URL
    for src in dev_cfg.get("sources", []):
        if src.get("name") == "OpenAI" and src.get("type") == "rss":
            url = src.get("url", DEFAULT_URL)
            break

    time_kst = config.get("schedule", {}).get("time_kst", "08:00")
    start_kst, end_kst = compute_window(time_kst)

    now_iso = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    items: list[dict[str, Any]] = []

    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        channel = root.find("channel")
        entries = root.findall(".//item") if channel is not None else root.findall("atom:entry", ns)

        for entry in entries:
            if channel is not None:
                title = (entry.findtext("title") or "").strip()
                link = (entry.findtext("link") or "").strip()
                summary = (entry.findtext("description") or "").strip()
                pub_str = entry.findtext("pubDate")
                category = (entry.findtext("category") or "").strip()
            else:
                title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
                link = ""
                for lel in entry.findall("atom:link", ns):
                    if lel.get("rel", "alternate") == "alternate":
                        link = lel.get("href", "")
                        break
                summary = (entry.findtext("atom:summary", namespaces=ns) or "").strip()
                pub_str = entry.findtext("atom:published", namespaces=ns)
                category = ""

            published_kst = parse_rss_date(pub_str)
            if published_kst and not (start_kst <= published_kst <= end_kst):
                continue

            items.append(
                {
                    "title": title,
                    "url": link,
                    "source_name": "OpenAI",
                    "lead": summary,
                    "published_at": published_kst.isoformat(timespec="seconds") if published_kst else None,
                    "category": category,
                }
            )
        print(
            f"[collect_openai] {len(items)}건 수집 (window: {start_kst.strftime('%m/%d %H:%M')} ~ {end_kst.strftime('%m/%d %H:%M')} KST)",
            file=sys.stderr,
        )
    except Exception as e:
        print(f"[collect_openai] 수집 실패: {e}", file=sys.stderr)

    return {
        "source": "openai_rss",
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
        f"[collect_openai] 저장 완료: {OUTPUT_PATH.relative_to(ROOT)} (총 {len(result['items'])}건)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
