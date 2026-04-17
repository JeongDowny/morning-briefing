"""Slack Incoming Webhook 으로 섹션별 메시지 3개 전송.

입력: summarized.json (Claude 네이티브 요약 결과) 또는 filtered.json (폴백)
환경변수: SLACK_WEBHOOK_URL
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
COLLECTED_DIR = ROOT / "collected"
SUMMARIZED_PATH = COLLECTED_DIR / "summarized.json"
FILTERED_PATH = COLLECTED_DIR / "filtered.json"

MAX_BLOCKS_PER_MESSAGE = 45  # Slack 50 블록 한계에서 안전 마진

SECTION_ORDER = [
    ("naver_", "📈 경제뉴스"),
    ("openai_rss", "🤖 AI / 개발 소식"),
    ("anthropic_html", "🤖 AI / 개발 소식"),
    ("threads_", "🧵 Threads 하이라이트"),
]


def load_input() -> dict[str, Any]:
    if SUMMARIZED_PATH.exists():
        with SUMMARIZED_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    if FILTERED_PATH.exists():
        with FILTERED_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
            return {"sources": data.get("sources", []), "fallback_mode": True}
    print("[send_slack] 입력 파일 없음", file=sys.stderr)
    sys.exit(1)


def group_by_section(sources: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for src in sources:
        source_name = src.get("source", "")
        section_label = None
        for prefix, label in SECTION_ORDER:
            if source_name.startswith(prefix) or source_name == prefix:
                section_label = label
                break
        if section_label is None:
            section_label = "📰 기타"
        grouped.setdefault(section_label, []).append(src)
    return grouped


def item_block(item: dict[str, Any], fallback_mode: bool) -> dict[str, Any]:
    title = item.get("title", "").strip()
    url = item.get("originallink") or item.get("link") or item.get("url") or ""
    press = item.get("press", "")
    summary = item.get("summary", "")

    parts: list[str] = []
    if url:
        parts.append(f"• <{url}|{title}>")
    else:
        parts.append(f"• *{title}*")
    if press:
        parts.append(f"  _{press}_")
    if summary and not fallback_mode:
        parts.append(f"  ▸ {summary}")

    return {
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(parts)},
    }


def build_section_messages(
    section_label: str,
    sources: list[dict[str, Any]],
    date_str: str,
    fallback_mode: bool,
) -> list[list[dict[str, Any]]]:
    """한 섹션을 하나 이상의 Slack 메시지(블록 리스트 여러 개)로 분할."""
    header_block = {
        "type": "header",
        "text": {"type": "plain_text", "text": f"{section_label} | {date_str}"},
    }

    item_blocks = [
        item_block(item, fallback_mode)
        for src in sources
        for item in src.get("items", [])
    ]
    if not item_blocks:
        return []

    messages: list[list[dict[str, Any]]] = []
    current = [header_block]
    for ib in item_blocks:
        if len(current) >= MAX_BLOCKS_PER_MESSAGE:
            messages.append(current)
            current = [{
                "type": "header",
                "text": {"type": "plain_text", "text": f"{section_label} (이어서)"},
            }]
        current.append(ib)
    messages.append(current)
    return messages


def post_webhook(webhook_url: str, blocks: list[dict[str, Any]]) -> None:
    resp = requests.post(webhook_url, json={"blocks": blocks}, timeout=15)
    if not resp.ok:
        print(f"[send_slack] 전송 실패 {resp.status_code}: {resp.text}", file=sys.stderr)
    resp.raise_for_status()


def main() -> int:
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("[send_slack] SLACK_WEBHOOK_URL 환경변수 필요", file=sys.stderr)
        return 1

    data = load_input()
    fallback_mode = data.get("fallback_mode", False)
    sources = data.get("sources", [])
    if not sources:
        print("[send_slack] 전송할 항목 없음", file=sys.stderr)
        return 0

    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d (%a)")
    grouped = group_by_section(sources)

    label_order = ["📈 경제뉴스", "🤖 AI / 개발 소식", "🧵 Threads 하이라이트", "📰 기타"]

    sent = 0
    for label in label_order:
        if label not in grouped:
            continue
        for blocks in build_section_messages(label, grouped[label], today_kst, fallback_mode):
            post_webhook(webhook_url, blocks)
            sent += 1
            time.sleep(0.5)

    print(f"[send_slack] 전송 완료: {sent}개 메시지", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
