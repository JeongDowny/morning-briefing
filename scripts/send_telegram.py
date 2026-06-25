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
BUTTONS_PER_ROW = 4
MANIFEST_DIR = ROOT / "data"

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


def load_url_to_id(date_iso: str) -> dict[str, str]:
    """오늘 manifest 에서 {url: id} 역맵. 없으면 빈 dict (버튼 없이 발송)."""
    path = MANIFEST_DIR / f"manifest-{date_iso}.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        manifest = json.load(f)
    return {meta["url"]: iid for iid, meta in manifest.get("items", {}).items() if meta.get("url")}


def build_buttons(numbered: list[tuple[int, str]]) -> dict[str, Any]:
    """[(번호, id), …] → inline_keyboard (BUTTONS_PER_ROW 개/행)."""
    flat = [{"text": f"📥 {n}", "callback_data": iid} for n, iid in numbered]
    rows = [flat[i:i + BUTTONS_PER_ROW] for i in range(0, len(flat), BUTTONS_PER_ROW)]
    return {"inline_keyboard": rows}


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


def format_item_line(item: dict[str, Any], fallback_mode: bool, number: int) -> str:
    title = item.get("title", "").strip()
    url = item.get("originallink") or item.get("link") or item.get("url") or ""
    press = item.get("press", "")
    summary = item.get("summary", "")

    title_esc = escape_mdv2(title)
    press_esc = escape_mdv2(press) if press else ""
    num_esc = escape_mdv2(f"{number}. ")

    lines = []
    if url:
        lines.append(f"{num_esc}[{title_esc}]({url})" + (f" _{press_esc}_" if press_esc else ""))
    else:
        lines.append(f"{num_esc}*{title_esc}*" + (f" _{press_esc}_" if press_esc else ""))
    if summary and not fallback_mode:
        lines.append(f"  ▸ {escape_mdv2(summary)}")
    return "\n".join(lines)


def render_one_message(
    section_label: str,
    date_str: str,
    items: list[dict[str, Any]],
    url_to_id: dict[str, str],
    fallback_mode: bool,
    continued: bool = False,
) -> tuple[str, dict[str, Any] | None]:
    """items 한 묶음 → (메시지 텍스트, reply_markup). 번호는 1부터, id 있는 항목만 버튼."""
    # section_label 만 이스케이프하고, "(이어서)"·구분자는 이미 이스케이프된 리터럴로 덧붙인다
    # (전체를 한 번에 escape_mdv2 하면 백슬래시가 이중 이스케이프됨).
    label_esc = escape_mdv2(section_label) + (" \\(이어서\\)" if continued else "")
    header = f"*{label_esc}*" + ("" if continued else f" \\| {escape_mdv2(date_str)}")
    body_lines = [header, ""]
    numbered: list[tuple[int, str]] = []
    for n, item in enumerate(items, start=1):
        body_lines.append(format_item_line(item, fallback_mode, n))
        url = item.get("originallink") or item.get("link") or item.get("url") or ""
        iid = url_to_id.get(url)
        if iid:
            numbered.append((n, iid))
    text = "\n\n".join([body_lines[0]] + body_lines[2:])  # header + 항목들 (빈 줄 정리)
    kb = build_buttons(numbered) if numbered else None
    return text, kb


def build_section_messages(
    section_label: str,
    sources: list[dict[str, Any]],
    date_str: str,
    fallback_mode: bool,
    url_to_id: dict[str, str],
) -> list[tuple[str, dict[str, Any] | None]]:
    all_items: list[dict[str, Any]] = []
    for src in sources:
        all_items.extend(src.get("items", []))
    if not all_items:
        return []

    # 4000자 안에서 항목 묶음을 쪼갠다 (대략적 길이 추정 — 묶음마다 render 후 길이 확인)
    out: list[tuple[str, dict[str, Any] | None]] = []
    bucket: list[dict[str, Any]] = []
    for item in all_items:
        trial = bucket + [item]
        text, _ = render_one_message(section_label, date_str, trial, url_to_id,
                                     fallback_mode, continued=bool(out))
        if len(text) > MAX_MESSAGE_LEN and bucket:
            t, kb = render_one_message(section_label, date_str, bucket, url_to_id,
                                       fallback_mode, continued=bool(out))
            out.append((t, kb))
            bucket = [item]
        else:
            bucket = trial
    if bucket:
        t, kb = render_one_message(section_label, date_str, bucket, url_to_id,
                                   fallback_mode, continued=bool(out))
        out.append((t, kb))
    return out


def send_message(token: str, chat_id: str, text: str,
                 reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    resp = requests.post(TELEGRAM_API.format(token=token), json=payload, timeout=15)
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
    date_iso = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    url_to_id = load_url_to_id(date_iso)
    grouped = group_by_section(sources)

    section_order_labels = ["📈 경제뉴스", "🤖 AI / 개발 소식", "🧵 Threads 하이라이트", "📰 기타"]
    sent = 0
    for label in section_order_labels:
        if label not in grouped:
            continue
        for msg, kb in build_section_messages(label, grouped[label], today_kst, fallback_mode, url_to_id):
            send_message(token, chat_id, msg, kb)
            sent += 1
            time.sleep(0.5)

    print(f"[send_telegram] 전송 완료: {sent}개 메시지", file=sys.stderr)
    return 0


def _self_check() -> None:
    # build_buttons: 4개/행 wrap, callback_data=id, 라벨=번호
    kb = build_buttons([(1, "20260625-aaaaaaaa"), (2, "20260625-bbbbbbbb"),
                        (3, "20260625-cccccccc"), (4, "20260625-dddddddd"),
                        (5, "20260625-eeeeeeee")])
    rows = kb["inline_keyboard"]
    assert len(rows) == 2 and len(rows[0]) == 4 and len(rows[1]) == 1, "4개/행 wrap"
    assert rows[0][0] == {"text": "📥 1", "callback_data": "20260625-aaaaaaaa"}
    assert rows[1][0]["text"] == "📥 5"

    # 번호 매김 + 버튼 정렬: id 있는 항목만 버튼, 라벨=본문 번호
    url_to_id = {"https://x.com/1": "20260625-11111111", "https://x.com/3": "20260625-33333333"}
    items = [
        {"title": "A", "url": "https://x.com/1"},
        {"title": "B", "url": "https://x.com/2"},  # manifest 에 없음 → 버튼 없음
        {"title": "C", "url": "https://x.com/3"},
    ]
    text, kb2 = render_one_message("📈 경제뉴스", "2026-06-25", items, url_to_id, fallback_mode=False)
    assert "1\\. " in text or "1. " in text  # 번호 prefix 존재 (이스케이프 무관 느슨 체크)
    labels = [b["text"] for row in kb2["inline_keyboard"] for b in row]
    assert labels == ["📥 1", "📥 3"], f"id 있는 1,3 만 버튼: {labels}"
    print("[send_telegram] self-check OK")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        sys.exit(0)
    sys.exit(main())
