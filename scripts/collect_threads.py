"""Threads 팔로잉 계정별 포스트 수집 (RSSHub 경유)."""
from __future__ import annotations

import json
import sys
import time
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
OUTPUT_PATH = OUTPUT_DIR / "threads.json"


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


def fetch_account(base: str, handle: str, label: str, max_posts: int,
                  start: datetime, end: datetime) -> list[dict[str, Any]]:
    url = f"{base.rstrip('/')}/threads/{handle}"
    items: list[dict[str, Any]] = []
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        entries = root.findall(".//item") if channel is not None else []

        for entry in entries[: max_posts * 2]:
            title = (entry.findtext("title") or "").strip()
            link = (entry.findtext("link") or "").strip()
            summary = (entry.findtext("description") or "").strip()
            pub_str = entry.findtext("pubDate")
            published = parse_rss_date(pub_str)
            if published and not (start <= published <= end):
                continue

            items.append(
                {
                    "title": title,
                    "url": link,
                    "handle": handle,
                    "label": label,
                    "lead": summary,
                    "published_at": published.isoformat(timespec="seconds") if published else None,
                }
            )
            if len(items) >= max_posts:
                break
    except Exception as e:
        print(f"[collect_threads] {handle} 수집 실패: {e}", file=sys.stderr)

    return items


def collect() -> dict[str, Any]:
    config = load_config()
    threads_cfg = config.get("threads", {})
    if not threads_cfg.get("enabled", False):
        print("[collect_threads] threads.enabled=false → 스킵", file=sys.stderr)
        return {"source": "threads_rsshub", "items": []}

    base = threads_cfg.get("rsshub_base", "https://rsshub.app")
    max_posts = threads_cfg.get("max_posts_per_account", 3)
    accounts = threads_cfg.get("accounts", [])

    time_kst = config.get("schedule", {}).get("time_kst", "08:00")
    start_kst, end_kst = compute_window(time_kst)

    now_iso = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    all_items: list[dict[str, Any]] = []

    for acc in accounts:
        handle = acc.get("handle", "").strip()
        label = acc.get("label", "")
        if not handle:
            continue
        items = fetch_account(base, handle, label, max_posts, start_kst, end_kst)
        all_items.extend(items)
        print(f"[collect_threads] @{handle} → {len(items)}건", file=sys.stderr)
        time.sleep(0.5)

    return {
        "source": "threads_rsshub",
        "collected_at": now_iso,
        "window_start": start_kst.isoformat(timespec="seconds"),
        "window_end": end_kst.isoformat(timespec="seconds"),
        "items": all_items,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)
    result = collect()
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(
        f"[collect_threads] 저장 완료: {OUTPUT_PATH.relative_to(ROOT)} (총 {len(result['items'])}건)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
