"""summarized.json 을 Daily/YYYY-MM-DD.md 로 렌더링.

입력: collected/summarized.json (또는 filtered.json 폴백)
출력: Daily/{date}.md

소스별로 섹션을 나누고, Threads 는 계정별 서브섹션으로 구성.
수집 0건이면 렌더링 스킵.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SUMMARIZED_PATH = ROOT / "collected" / "summarized.json"
FILTERED_PATH = ROOT / "collected" / "filtered.json"
CONFIG_PATH = ROOT / "config" / "briefing.json"
DAILY_DIR = ROOT / "Daily"

WEEKDAYS_KR = ["월", "화", "수", "목", "금", "토", "일"]

SECTION_MAP = {
    "naver_ranking":  ("📈 경제뉴스",       "### 네이버 경제 언론사 랭킹"),
    "openai_rss":     ("🤖 AI / 개발 소식",  "### OpenAI"),
    "anthropic_html": ("🤖 AI / 개발 소식",  "### Anthropic"),
    "threads_rsshub": ("🧵 Threads",        None),  # 계정별 서브섹션
}

SECTION_ORDER = ["📈 경제뉴스", "🤖 AI / 개발 소식", "🧵 Threads", "📰 기타"]


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def load_input() -> dict[str, Any] | None:
    if SUMMARIZED_PATH.exists():
        with SUMMARIZED_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    if FILTERED_PATH.exists():
        with FILTERED_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
            return {"sources": data.get("sources", []), "date": None}
    return None


def render_article(item: dict[str, Any], include_lead: bool) -> list[str]:
    title = (item.get("title") or "").strip()
    title_ko = (item.get("title_ko") or "").strip()
    url = item.get("originallink") or item.get("link") or item.get("url") or ""
    source = item.get("press") or item.get("source_name") or ""
    summary = (item.get("summary") or "").strip()
    lead = (item.get("lead") or "").strip()

    lines = []
    if url:
        head = f"- **[{title}]({url})**"
    else:
        head = f"- **{title}**"
    if source:
        head += f" — {source}"
    lines.append(head)

    # 영문 원문 제목일 때만 한국어 번역을 추가로 표시 (title_ko 가 비어있지 않을 때)
    if title_ko:
        lines.append(f"  - ▸ *{title_ko}*")
    if summary:
        lines.append(f"  - 🤖 {summary}")
    if include_lead and lead and lead != summary:
        short = lead[:300].replace("\n", " ").strip()
        suffix = "…" if len(lead) > 300 else ""
        lines.append(f"  - 📄 *{short}{suffix}*")

    return lines


def render_threads_post(item: dict[str, Any], include_lead: bool) -> list[str]:
    url = item.get("url", "")
    title_ko = (item.get("title_ko") or "").strip()
    summary = (item.get("summary") or "").strip()
    lead = (item.get("lead") or "").strip()
    published = item.get("published_at") or ""

    display_time = ""
    if published:
        try:
            dt = datetime.fromisoformat(published)
            display_time = dt.strftime("%m-%d %H:%M")
        except Exception:
            pass

    lines = []
    head = "- "
    if url and display_time:
        head += f"**[{display_time}]({url})**"
    elif url:
        head += f"**[원문]({url})**"
    elif display_time:
        head += f"**{display_time}**"
    else:
        head += "**(post)**"
    lines.append(head)

    if title_ko:
        lines.append(f"  - ▸ *{title_ko}*")
    if summary:
        lines.append(f"  - 🤖 {summary}")
    if include_lead and lead and lead != summary:
        short = lead[:250].replace("\n", " ").strip()
        suffix = "…" if len(lead) > 250 else ""
        lines.append(f"  - 📄 *{short}{suffix}*")

    return lines


def group_sources(sources: list[dict[str, Any]]) -> dict[str, list[tuple[str | None, list[dict[str, Any]]]]]:
    grouped: dict[str, list[tuple[str | None, list[dict[str, Any]]]]] = {}
    for src in sources:
        name = src.get("source", "")
        items = src.get("items", [])
        if not items:
            continue
        section, sub = SECTION_MAP.get(name, ("📰 기타", None))
        grouped.setdefault(section, []).append((sub, items))
    return grouped


def main() -> int:
    data = load_input()
    if not data:
        print("[render_daily] 입력 JSON 없음 — 수집 단계를 먼저 실행하세요.", file=sys.stderr)
        return 1

    config = load_config()
    include_lead = config.get("output", {}).get("obsidian", {}).get("include_raw_lead", True)
    time_kst = config.get("schedule", {}).get("time_kst", "08:00")

    now = datetime.now(ZoneInfo("Asia/Seoul"))
    date_str = data.get("date") or now.strftime("%Y-%m-%d")
    try:
        dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        dt_obj = now
        date_str = now.strftime("%Y-%m-%d")
    weekday = WEEKDAYS_KR[dt_obj.weekday()]

    grouped = group_sources(data.get("sources", []))
    total = sum(len(items) for subs in grouped.values() for _, items in subs)
    if total == 0:
        print("[render_daily] 수집 항목 0건 — Daily 노트 생성 스킵", file=sys.stderr)
        return 0

    lines = [
        "---",
        f"date: {date_str}",
        "tags: [daily, briefing]",
        "---",
        "",
        f"# 🌅 모닝 브리핑 — {dt_obj.strftime('%Y년 %m월 %d일')} ({weekday})",
        "",
        f"> 수집 기간: 전일 {time_kst} ~ 오늘 {time_kst} KST · 총 {total}건",
        "",
    ]

    for section in SECTION_ORDER:
        if section not in grouped:
            continue
        lines.append(f"## {section}")
        lines.append("")
        for sub_label, items in grouped[section]:
            if section == "🧵 Threads":
                # 계정별 서브섹션
                by_handle: dict[str, dict[str, Any]] = {}
                for item in items:
                    handle = item.get("handle", "")
                    if handle not in by_handle:
                        by_handle[handle] = {"label": item.get("label", ""), "items": []}
                    by_handle[handle]["items"].append(item)
                for handle, bucket in by_handle.items():
                    label = bucket["label"]
                    header = f"### @{handle}"
                    if label:
                        header += f" — {label}"
                    lines.append(header)
                    lines.append("")
                    for item in bucket["items"]:
                        lines.extend(render_threads_post(item, include_lead))
                        lines.append("")
            else:
                if sub_label:
                    lines.append(sub_label)
                    lines.append("")
                for item in items:
                    lines.extend(render_article(item, include_lead))
                    lines.append("")

    lines.extend([
        "---",
        "",
        "## 💡 Keep",
        "",
        "> 중요 항목 아래에 `#keep` 태그를 붙이면 `Keeps.md` 에 자동 집계됩니다.",
        "> 카테고리 태그: `#거시` `#자산` `#글로벌` `#openai` `#anthropic` `#threads` `#research`",
        "",
    ])

    DAILY_DIR.mkdir(exist_ok=True)
    out_path = DAILY_DIR / f"{date_str}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[render_daily] 저장: {out_path.relative_to(ROOT)} ({total}건)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
