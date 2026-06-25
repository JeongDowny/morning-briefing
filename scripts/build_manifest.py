"""summarized.json 항목에 id 를 부여하고 data/manifest-{날짜}.json 을 생성.

텔레그램 발송(send_telegram.py)보다 먼저 실행해 manifest 를 push 해야 한다.
웹훅(api/telegram.py)이 버튼 콜백의 id 로 이 manifest 를 조회한다.

환경변수: 없음
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
COLLECTED_DIR = ROOT / "collected"
SUMMARIZED_PATH = COLLECTED_DIR / "summarized.json"
FILTERED_PATH = COLLECTED_DIR / "filtered.json"
MANIFEST_DIR = ROOT / "data"


def resolve_url(item: dict[str, Any]) -> str:
    return (item.get("originallink") or item.get("link") or item.get("url") or "").strip()


def compute_id(url: str, date_compact: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{date_compact}-{h}"


def build_manifest(data: dict[str, Any], date_compact: str) -> dict[str, Any]:
    date_iso = f"{date_compact[:4]}-{date_compact[4:6]}-{date_compact[6:8]}"
    items: dict[str, Any] = {}
    for src in data.get("sources", []):
        for item in src.get("items", []):
            url = resolve_url(item)
            if not url:
                continue  # url 없으면 아카이브 불가 → 버튼도 안 만듦
            iid = compute_id(url, date_compact)
            items[iid] = {
                "title": (item.get("title") or "").strip(),
                "url": url,
                "summary": (item.get("summary") or "").strip(),
                "source": (item.get("source_name") or "").strip(),
            }
    return {"date": date_iso, "items": items}


def cleanup_old(manifest_dir: Path, today: date, keep_days: int = 14) -> int:
    cutoff = today - timedelta(days=keep_days)
    removed = 0
    for f in manifest_dir.glob("manifest-*.json"):
        try:
            d = datetime.strptime(f.stem.replace("manifest-", ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < cutoff:
            f.unlink()
            removed += 1
    return removed


def _load_input() -> dict[str, Any] | None:
    if SUMMARIZED_PATH.exists():
        with SUMMARIZED_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    if FILTERED_PATH.exists():
        with FILTERED_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return None


def main() -> int:
    data = _load_input()
    if not data:
        print("[build_manifest] 입력 JSON 없음 — 스킵", file=sys.stderr)
        return 0

    now = datetime.now(ZoneInfo("Asia/Seoul"))
    date_compact = now.strftime("%Y%m%d")
    manifest = build_manifest(data, date_compact)

    MANIFEST_DIR.mkdir(exist_ok=True)
    out = MANIFEST_DIR / f"manifest-{manifest['date']}.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    removed = cleanup_old(MANIFEST_DIR, now.date())
    print(f"[build_manifest] {len(manifest['items'])}건 → {out.name} (오래된 {removed}개 정리)", file=sys.stderr)
    return 0


def _self_check() -> None:
    # url 폴백 체인
    assert resolve_url({"originallink": "a", "link": "b", "url": "c"}) == "a"
    assert resolve_url({"link": "b", "url": "c"}) == "b"
    assert resolve_url({"url": "c"}) == "c"
    assert resolve_url({"title": "no url"}) == ""

    # id 안정성 + 형식
    i1 = compute_id("https://x.com/a", "20260625")
    i2 = compute_id("https://x.com/a", "20260625")
    assert i1 == i2, "같은 url+날짜 → 같은 id"
    import re as _re
    assert _re.fullmatch(r"\d{8}-[0-9a-f]{8}", i1), f"id 형식 불량: {i1}"
    assert compute_id("https://x.com/b", "20260625") != i1, "다른 url → 다른 id"

    # build_manifest: 빈 url 항목 제외, 구조
    data = {"sources": [
        {"items": [
            {"title": "T1", "url": "https://x.com/1", "summary": "S1", "source_name": "GeekNews"},
            {"title": "no-url", "summary": "S2", "source_name": "GeekNews"},
        ]},
    ]}
    m = build_manifest(data, "20260625")
    assert m["date"] == "2026-06-25"
    assert len(m["items"]) == 1, "빈 url 항목은 제외"
    only_id = next(iter(m["items"]))
    assert m["items"][only_id] == {
        "title": "T1", "url": "https://x.com/1", "summary": "S1", "source": "GeekNews",
    }
    print("[build_manifest] self-check OK")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        sys.exit(0)
    sys.exit(main())
