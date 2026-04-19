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

import feedparser
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "briefing.json"
OUTPUT_DIR = ROOT / "collected"
OUTPUT_PATH = OUTPUT_DIR / "openai.json"

DEFAULT_URL = "https://openai.com/news/rss.xml"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def compute_window(_time_kst: str | None = None) -> tuple[datetime, datetime]:
    """최근 24시간 창 (KST)."""
    end = datetime.now(ZoneInfo("Asia/Seoul"))
    start = end - timedelta(days=1)
    return start, end


def to_kst(dt_struct) -> datetime | None:
    if not dt_struct:
        return None
    try:
        naive = datetime(*dt_struct[:6])
        return naive.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Seoul"))
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
        feed = feedparser.parse(url)
        for entry in feed.entries:
            published_kst = to_kst(entry.get("published_parsed"))
            if published_kst and not (start_kst <= published_kst <= end_kst):
                continue

            items.append(
                {
                    "title": entry.get("title", "").strip(),
                    "url": entry.get("link", ""),
                    "source_name": "OpenAI",
                    "lead": entry.get("summary", "").strip() or entry.get("description", "").strip(),
                    "published_at": published_kst.isoformat(timespec="seconds") if published_kst else None,
                    "category": entry.get("tags", [{}])[0].get("term", "") if entry.get("tags") else "",
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
