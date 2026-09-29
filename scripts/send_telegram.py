"""텔레그램 봇으로 짧은 브리핑 1개 전송.

입력: summarized.json (요약 결과) 또는 filtered.json (요약 미실행 시 폴백)
환경변수: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

섹션(AI·개발 → 경제)마다 rank.py 가 고른 상위 N건만 싣는다. 나머지는 제목만
Daily 노트(devhub "오늘 브리핑")에 접혀 있다. 4000자를 넘으면 이어서 쪼갠다.
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

from rank import DEFAULT_TOP, section_key, split_top

ROOT = Path(__file__).resolve().parent.parent
COLLECTED_DIR = ROOT / "collected"
SUMMARIZED_PATH = COLLECTED_DIR / "summarized.json"
FILTERED_PATH = COLLECTED_DIR / "filtered.json"
CONFIG_PATH = ROOT / "config" / "briefing.json"

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_MESSAGE_LEN = 4000  # 4096 한계에서 안전 마진

SECTIONS = [("ai", "🤖 AI / 개발"), ("econ", "📈 경제")]

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


def format_item(item: dict[str, Any], fallback_mode: bool, number: int) -> str:
    # 영문 원제는 싣지 않는다 — 한국어 제목이 있으면 그것만 (병기는 Daily 노트에)
    title = (item.get("title_ko") or item.get("title") or "").strip()
    url = item.get("originallink") or item.get("link") or item.get("url") or ""
    source = item.get("press") or item.get("source_name") or ""
    summary = (item.get("summary") or "").strip()

    head = escape_mdv2(f"{number}. ")
    head += f"[{escape_mdv2(title)}]({url})" if url else f"*{escape_mdv2(title)}*"
    if source:
        head += f" _{escape_mdv2(source)}_"
    if summary and not fallback_mode:
        return f"{head}\n  ▸ {escape_mdv2(summary)}"
    return head


def build_blocks(sources: list[dict[str, Any]], tops: dict[str, int],
                 date_str: str, fallback_mode: bool) -> list[str]:
    """메시지를 이루는 블록들 — 헤더, 섹션 제목, 항목, 꼬리말. 블록 단위로 쪼갠다."""
    by_section: dict[str, list[dict[str, Any]]] = {"ai": [], "econ": []}
    for src in sources:
        key = section_key(src.get("source", ""))
        if key:
            by_section[key].extend(src.get("items", []))

    blocks = [f"*{escape_mdv2('🌅 모닝 브리핑')}* \\| {escape_mdv2(date_str)}"]
    folded = 0
    for key, label in SECTIONS:
        items = by_section[key]
        if not items:
            continue
        top, rest = split_top(items, tops[key])
        folded += len(rest)
        suffix = "수집 순서" if any(it.get("rank_fallback") for it in top) else "관심사 순"
        blocks.append(f"*{escape_mdv2(label)}* {escape_mdv2(f'— {suffix} {len(top)} / {len(items)}건')}")
        blocks.extend(format_item(it, fallback_mode, n) for n, it in enumerate(top, start=1))
    if folded:
        blocks.append(f"_{escape_mdv2(f'나머지 {folded}건은 제목만 — devhub 오늘 브리핑')}_")
    return blocks


def pack_messages(blocks: list[str]) -> list[str]:
    """블록을 MAX_MESSAGE_LEN 안으로 묶는다. 보통 1개."""
    out: list[str] = []
    cur = ""
    for b in blocks:
        trial = f"{cur}\n\n{b}" if cur else b
        if len(trial) > MAX_MESSAGE_LEN and cur:
            out.append(cur)
            cur = b
        else:
            cur = trial
    if cur:
        out.append(cur)
    return out


def send_message(token: str, chat_id: str, text: str) -> dict[str, Any]:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    resp = requests.post(TELEGRAM_API.format(token=token), json=payload, timeout=15)
    if not resp.ok:
        print(f"[send_telegram] 전송 실패 {resp.status_code}: {resp.text}", file=sys.stderr)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not dry_run and (not token or not chat_id):
        print("[send_telegram] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 환경변수 필요", file=sys.stderr)
        return 1

    data = load_input()
    fallback_mode = data.get("fallback_mode", False)
    sources = data.get("sources", [])
    if not sources:
        print("[send_telegram] 전송할 항목 없음", file=sys.stderr)
        return 0

    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    rcfg = cfg.get("ranking", {})
    tops = {"ai": rcfg.get("ai_top", DEFAULT_TOP["ai"]), "econ": rcfg.get("econ_top", DEFAULT_TOP["econ"])}

    today_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d (%a)")
    messages = pack_messages(build_blocks(sources, tops, today_kst, fallback_mode))

    for msg in messages:
        if dry_run:
            print(msg + f"\n\n----- {len(msg)}자 -----")
            continue
        send_message(token, chat_id, msg)
        time.sleep(0.5)

    print(f"[send_telegram] 전송 완료: {len(messages)}개 메시지", file=sys.stderr)
    return 0


def _self_check() -> None:
    # 상위만 싣고, 한국어 제목 우선, 나머지 건수는 꼬리말로
    ai = [{"title": f"Post {i}", "url": f"https://x.com/{i}", "source_name": "Blog",
           "summary": "요약", **({"rank": i + 1} if i < 2 else {})} for i in range(5)]
    ai[0]["title_ko"] = "한국어 제목"
    econ = [{"title": "금리 동결", "originallink": "https://n.com/1", "press": "hankyung.com", "summary": "s"}]
    blocks = build_blocks([{"source": "blog_rss", "items": ai}, {"source": "naver_ranking", "items": econ}],
                          {"ai": 7, "econ": 5}, "2026-09-29 (Tue)", fallback_mode=False)
    text = "\n\n".join(blocks)
    assert "한국어 제목" in text and "Post 0" not in text, "title_ko 우선, 원제 병기 안 함"
    assert "Post 1" in text and "Post 2" not in text, "rank 있는 2건만"
    assert "금리 동결" in text, "경제는 rank 없으면 앞 N건"
    assert text.index("AI") < text.index("경제"), "AI 먼저"
    assert "나머지 3건" in text

    # 4000자 넘으면 블록 경계에서 쪼갠다
    msgs = pack_messages(["a" * 2500, "b" * 2500, "c" * 10])
    assert len(msgs) == 2 and msgs[1].startswith("b")
    print("[send_telegram] self-check OK")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        sys.exit(0)
    sys.exit(main())
