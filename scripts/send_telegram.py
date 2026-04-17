"""텔레그램 봇으로 섹션별 메시지 3개 전송.

입력: summarized.json (Claude 네이티브 요약 결과) 또는 filtered.json (요약 미실행 시 폴백)
환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

메시지 분할 정책:
- 섹션 단위로 별도 메시지 (경제뉴스 / AI·개발소식 / Threads)
- 섹션 내용이 4000자 초과 시 해당 섹션만 추가 분할
"""
from __future__ import annotations

import json
import os
import re
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

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LEN = 4000  # 4096 한계에서 안전 마진

SECTION_ORDER = [
    ("naver_", "📈 경제뉴스"),
    ("openai_rss", "🤖 AI / 개발 소식"),
    ("anthropic_html", "🤖 AI / 개발 소식"),
    ("threads_", "🧵 Threads 하이라이트"),
]

# MarkdownV2 이스케이프가 필요한 문자들
MDV2_ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!"


def escape_mdv2(text: str) -> str:
    """MarkdownV2 특수문자 이스케이프."""
    if not text:
        return ""
    # 백슬래시 먼저 처리
    text = text.replace("\\", "\\\\")
    for ch in MDV2_ESCAPE_CHARS:
        text = text.replace(ch, f"\\{ch}")
    return text


def load_input() -> dict[str, Any]:
    # 요약본 우선, 없으면 filtered 폴백 (요약 단계가 실패해도 헤드라인만큼은 발송)
    if SUMMARIZED_PATH.exists():
        with SUMMARIZED_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    if FILTERED_PATH.exists():
        with FILTERED_PATH.open(encoding="utf-8") as f:
            data = json.load(f)
            # filtered.json → summarized-like 형식으로 변환 (summary 없이 title만)
            return {"sources": data.get("sources", []), "fallback_mode": True}
    print("[send_telegram] 입력 파일 없음 (summarized.json 또는 filtered.json)", file=sys.stderr)
    sys.exit(1)


def group_by_section(sources: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """수집 소스들을 3개 섹션 버킷으로 그룹핑."""
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


def format_item_line(item: dict[str, Any], fallback_mode: bool) -> str:
    title = item.get("title", "").strip()
    url = item.get("originallink") or item.get("link") or item.get("url") or ""
    press = item.get("press", "")
    summary = item.get("summary", "")

    # 제목 + 링크
    title_esc = escape_mdv2(title)
    press_esc = escape_mdv2(press) if press else ""

    lines = []
    if url:
        lines.append(f"• [{title_esc}]({url})" + (f" _{press_esc}_" if press_esc else ""))
    else:
        lines.append(f"• *{title_esc}*" + (f" _{press_esc}_" if press_esc else ""))

    # 요약
    if summary and not fallback_mode:
        summary_esc = escape_mdv2(summary)
        lines.append(f"  ▸ {summary_esc}")

    return "\n".join(lines)


def build_section_messages(
    section_label: str,
    sources: list[dict[str, Any]],
    date_str: str,
    fallback_mode: bool,
) -> list[str]:
    """한 섹션을 하나 이상의 텔레그램 메시지 텍스트로 분할."""
    header = f"*{escape_mdv2(section_label)}* \\| {escape_mdv2(date_str)}"
    item_blocks: list[str] = []
    for src in sources:
        for item in src.get("items", []):
            item_blocks.append(format_item_line(item, fallback_mode))

    if not item_blocks:
        return []  # 섹션에 항목 없으면 아예 발송 안 함

    messages: list[str] = []
    current = header
    for block in item_blocks:
        candidate = f"{current}\n\n{block}"
        if len(candidate) > MAX_MESSAGE_LEN:
            messages.append(current)
            current = f"{escape_mdv2(section_label)} \\(이어서\\)\n\n{block}"
        else:
            current = candidate
    messages.append(current)
    return messages


def send_message(token: str, chat_id: str, text: str) -> dict[str, Any]:
    resp = requests.post(
        TELEGRAM_API.format(token=token),
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        },
        timeout=15,
    )
    if not resp.ok:
        print(f"[send_telegram] 전송 실패 {resp.status_code}: {resp.text}", file=sys.stderr)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[send_telegram] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수 필요", file=sys.stderr)
        return 1

    data = load_input()
    fallback_mode = data.get("fallback_mode", False)
    sources = data.get("sources", [])
    if not sources:
        print("[send_telegram] 전송할 항목 없음", file=sys.stderr)
        return 0

    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d (%a)")
    grouped = group_by_section(sources)

    # 섹션 순서: 경제 → AI → Threads
    section_order_labels = ["📈 경제뉴스", "🤖 AI / 개발 소식", "🧵 Threads 하이라이트", "📰 기타"]

    sent = 0
    for label in section_order_labels:
        if label not in grouped:
            continue
        messages = build_section_messages(label, grouped[label], today_kst, fallback_mode)
        for msg in messages:
            send_message(token, chat_id, msg)
            sent += 1
            time.sleep(0.5)  # rate limit 여유

    print(f"[send_telegram] 전송 완료: {sent}개 메시지", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
