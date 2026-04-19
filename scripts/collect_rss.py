"""범용 RSS 수집기.

dev_news.sources 에서 type=rss 인 모든 항목을 순회하며 수집.
소스 1개당 1파일 (collected/rss-{slug}.json) 로 저장 — manage_seen.py 가 개별 처리하기 쉽도록.

환경변수: 없음 (모든 소스는 공개 RSS)
새 소스 추가: config/briefing.json 의 dev_news.sources 배열에 한 줄 추가.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import feedparser
import requests
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "briefing.json"
OUTPUT_DIR = ROOT / "collected"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
FETCH_TIMEOUT = 15


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


def slugify(name: str) -> str:
    s = name.lower().replace(" ", "-")
    s = re.sub(r"[^a-z0-9\-]", "", s)
    return s.strip("-")


def fetch_feed(url: str) -> Any:
    """UA 헤더 포함 fetch 후 feedparser 로 파싱. bearblog 등 일부는 UA 없으면 403."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def collect_one(name: str, url: str, start: datetime, end: datetime) -> dict[str, Any]:
    slug = slugify(name) or "unknown"
    source_key = f"{slug}_rss"

    try:
        feed = fetch_feed(url)
    except Exception as e:
        print(f"[collect_rss] {name} fetch 실패: {e}", file=sys.stderr)
        return {"source": source_key, "source_name": name, "items": []}

    items: list[dict[str, Any]] = []
    for entry in feed.entries:
        published_kst = to_kst(entry.get("published_parsed")) or to_kst(entry.get("updated_parsed"))
        if published_kst and not (start <= published_kst <= end):
            continue

        lead = (entry.get("summary") or entry.get("description") or "").strip()
        # 길이 제한
        lead = re.sub(r"<[^>]+>", " ", lead)  # 간단한 HTML 태그 제거
        lead = re.sub(r"\s+", " ", lead).strip()[:800]

        items.append(
            {
                "title": entry.get("title", "").strip(),
                "url": entry.get("link", ""),
                "source_name": name,
                "lead": lead,
                "published_at": published_kst.isoformat(timespec="seconds") if published_kst else None,
                "category": (entry.get("tags", [{}])[0].get("term", "") if entry.get("tags") else ""),
            }
        )

    return {"source": source_key, "source_name": name, "items": items}


def main() -> int:
    cfg = load_config()
    dev_cfg = cfg.get("dev_news", {})
    if not dev_cfg.get("enabled", False):
        print("[collect_rss] dev_news.enabled=false → 스킵", file=sys.stderr)
        return 0

    start_kst, end_kst = compute_window()
    now_iso = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")

    OUTPUT_DIR.mkdir(exist_ok=True)

    rss_sources = [s for s in dev_cfg.get("sources", []) if s.get("type") == "rss"]
    if not rss_sources:
        print("[collect_rss] RSS 소스 없음", file=sys.stderr)
        return 0

    total = 0
    for src in rss_sources:
        name = (src.get("name") or "").strip()
        url = (src.get("url") or "").strip()
        if not name or not url:
            continue
        result = collect_one(name, url, start_kst, end_kst)
        result["collected_at"] = now_iso
        result["window_start"] = start_kst.isoformat(timespec="seconds")
        result["window_end"] = end_kst.isoformat(timespec="seconds")

        slug = slugify(name) or "unknown"
        out_path = OUTPUT_DIR / f"rss-{slug}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        count = len(result["items"])
        total += count
        print(f"[collect_rss] {name}: {count}건 → {out_path.name}", file=sys.stderr)

    print(f"[collect_rss] 전체 {total}건 수집", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
