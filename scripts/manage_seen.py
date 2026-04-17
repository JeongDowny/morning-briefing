"""data/seen.json 관리 — 중복 제거 필터링 및 갱신.

사용법:
  python scripts/manage_seen.py filter
    → collected/*.json 들을 읽어 seen 에 없는 항목만 collected/filtered.json 에 출력

  python scripts/manage_seen.py update
    → collected/filtered.json (또는 summarized.json) 의 항목 URL/ID 를 seen.json 에 추가하고
      retention_days 초과 항목을 정리

URL 정규화 규칙:
  1. originallink (언론사 원본 URL) 우선
  2. 없으면 link (또는 url) 필드
  → 같은 기사가 랭킹·키워드검색 양쪽에서 잡혀도 단일 항목으로 병합됨
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "briefing.json"
SEEN_PATH = ROOT / "data" / "seen.json"
COLLECTED_DIR = ROOT / "collected"
FILTERED_PATH = COLLECTED_DIR / "filtered.json"


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_seen() -> dict[str, Any]:
    if not SEEN_PATH.exists():
        return {"last_updated": None, "news": {}, "dev_blog": {}, "threads": {}}
    with SEEN_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def save_seen(seen: dict[str, Any]) -> None:
    with SEEN_PATH.open("w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def normalize_url(item: dict[str, Any]) -> str:
    """중복 판단에 쓸 정규화 URL 반환."""
    return item.get("originallink") or item.get("link") or item.get("url") or ""


def bucket_for_source(source: str) -> str:
    """수집 소스를 seen.json 버킷에 매핑."""
    if source.startswith("naver_"):
        return "news"
    if source in {"openai_rss", "anthropic_html"}:
        return "dev_blog"
    if source.startswith("threads_"):
        return "threads"
    return "news"


def cmd_filter() -> int:
    """collected/*.json 을 읽어 seen 에 없는 항목만 filtered.json 에 출력."""
    if not COLLECTED_DIR.exists():
        print("[manage_seen] collected/ 없음 — 수집 스크립트 먼저 실행하세요.", file=sys.stderr)
        return 1

    seen = load_seen()
    collected_files = sorted(
        p for p in COLLECTED_DIR.glob("*.json") if p.name != "filtered.json"
    )
    if not collected_files:
        print("[manage_seen] collected/*.json 없음", file=sys.stderr)
        return 1

    filtered_sources: list[dict[str, Any]] = []
    total_in = 0
    total_out = 0

    for path in collected_files:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        source = data.get("source", path.stem)
        bucket = bucket_for_source(source)
        bucket_seen = seen.get(bucket, {})

        new_items: list[dict[str, Any]] = []
        for item in data.get("items", []):
            total_in += 1
            url = normalize_url(item)
            if not url:
                # URL 없는 항목은 일단 통과 (Threads post ID 등은 별도 관리 대상)
                new_items.append(item)
                total_out += 1
                continue
            if url in bucket_seen:
                continue
            new_items.append(item)
            total_out += 1

        filtered_sources.append(
            {
                "source": source,
                "collected_at": data.get("collected_at"),
                "items": new_items,
            }
        )

    FILTERED_PATH.parent.mkdir(exist_ok=True)
    with FILTERED_PATH.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "filtered_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
                "sources": filtered_sources,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"[manage_seen filter] 입력 {total_in}건 → 출력 {total_out}건 (중복 제거 {total_in - total_out}건)",
        file=sys.stderr,
    )
    return 0


def cmd_update() -> int:
    """filtered.json (또는 summarized.json) 기반으로 seen.json 갱신 + 오래된 항목 정리."""
    config = load_config()
    retention_days = config.get("dedupe", {}).get("retention_days", 30)

    if not FILTERED_PATH.exists():
        print("[manage_seen update] filtered.json 없음", file=sys.stderr)
        return 1

    with FILTERED_PATH.open(encoding="utf-8") as f:
        filtered = json.load(f)

    seen = load_seen()
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    now_iso = now_kst.isoformat(timespec="seconds")
    cutoff = now_kst - timedelta(days=retention_days)

    added = 0
    for source_block in filtered.get("sources", []):
        bucket = bucket_for_source(source_block.get("source", ""))
        bucket_seen = seen.setdefault(bucket, {})
        for item in source_block.get("items", []):
            url = normalize_url(item)
            if url and url not in bucket_seen:
                bucket_seen[url] = now_iso
                added += 1

    # retention 초과 항목 정리 — news / dev_blog 만 (threads 는 post id 리스트라 별도)
    removed = 0
    for bucket_name in ("news", "dev_blog"):
        bucket = seen.get(bucket_name, {})
        to_del: list[str] = []
        for url, ts in bucket.items():
            try:
                t = datetime.fromisoformat(ts)
                if t < cutoff:
                    to_del.append(url)
            except (ValueError, TypeError):
                continue
        for url in to_del:
            del bucket[url]
        removed += len(to_del)

    seen["last_updated"] = now_iso
    save_seen(seen)
    print(
        f"[manage_seen update] 추가 {added}건, {retention_days}일 초과 제거 {removed}건",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in {"filter", "update"}:
        print("사용법: python scripts/manage_seen.py [filter|update]", file=sys.stderr)
        return 2
    return cmd_filter() if argv[1] == "filter" else cmd_update()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
