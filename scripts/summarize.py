"""Google Gemini API 로 수집 항목들을 한국어로 요약.

입력: collected/filtered.json
출력: collected/summarized.json
환경변수: GEMINI_API_KEY

소스별 배치 호출 (최대 4회/일). Gemini 무료 티어 한도(1,500회/일) 내에서 넉넉.
JSON mode (response_mime_type) 로 파싱 안정화.
요약 실패 시 원본 아이템만 유지하고 pipeline 은 계속 진행.
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

from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "briefing.json"
PROMPTS_DIR = ROOT / "config" / "prompts"
FILTERED_PATH = ROOT / "collected" / "filtered.json"
SUMMARIZED_PATH = ROOT / "collected" / "summarized.json"

def prompt_for(source: str) -> str:
    """네이버 → 경제뉴스, Threads → 포스트, 나머지 RSS·HTML(GeekNews·개인 블로그 포함) → 기술 글."""
    if source.startswith("naver_"):
        return "news-summary.md"
    if source.startswith("threads_"):
        return "threads-summary.md"
    return "blog-summary.md"

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_TOKENS = 16384  # 한국어 요약 + title_ko 필드 때문에 넉넉하게


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_prompt(filename: str) -> str:
    p = PROMPTS_DIR / filename
    return p.read_text(encoding="utf-8") if p.exists() else ""


def build_user_message(items: list[dict[str, Any]], instruction: str) -> str:
    input_lines = []
    for i, item in enumerate(items):
        input_lines.append(f"### item_{i}")
        input_lines.append(f"- title: {item.get('title', '').strip()}")
        lead = (item.get("lead") or "").strip()
        if lead:
            input_lines.append(f"- lead: {lead[:600]}")
        src = item.get("press") or item.get("source_name") or item.get("handle", "")
        if src:
            input_lines.append(f"- source: {src}")
        input_lines.append("")

    input_block = "\n".join(input_lines).strip()

    return (
        f"{instruction}\n\n"
        "다음은 요약할 항목 리스트. 각 항목의 id 를 결과에 그대로 포함하고, "
        "프롬프트에 지정된 필드를 모두 채워 반환할 것. title_ko 는 한국어 원문이면 빈 문자열.\n\n"
        f"{input_block}\n\n"
        "응답은 반드시 JSON 객체만 반환 (다른 설명·마크다운 금지). "
        "누락된 id 가 없도록 입력된 모든 item 을 포함할 것."
    )


def parse_response(text: str) -> dict[str, dict[str, str]]:
    """응답 텍스트에서 JSON 추출 후 id → {summary, title_ko} 맵."""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    elif not text.startswith("{"):
        brace_start = text.find("{")
        if brace_start >= 0:
            text = text[brace_start:]
    try:
        data = json.loads(text)
    except Exception as e:
        print(f"[summarize] JSON 파싱 실패: {e}\n원문 앞부분: {text[:300]}", file=sys.stderr)
        return {}
    out: dict[str, dict[str, str]] = {}
    for s in data.get("summaries", []):
        if isinstance(s, dict) and "id" in s:
            out[str(s["id"])] = {
                "summary": (s.get("summary") or "").strip(),
                "title_ko": (s.get("title_ko") or "").strip(),
            }
    return out


def fallback_summary(lead: str) -> str:
    lead = (lead or "").strip()
    if not lead:
        return ""
    return lead[:150] + ("…" if len(lead) > 150 else "")


def _summarize_once(client, items: list[dict[str, Any]], instruction: str, model: str) -> dict[int, dict[str, str]]:
    """items 1회 배치 요약 → {로컬인덱스: {summary, title_ko}}. 빈 dict 가능 (호출 실패 포함)."""
    if not items or not instruction:
        return {}
    try:
        return _call_once(client, items, instruction, model)
    except Exception as e:
        print(f"[summarize] 호출 실패: {e}", file=sys.stderr)
        return {}


def _call_once(client, items: list[dict[str, Any]], instruction: str, model: str) -> dict[int, dict[str, str]]:
    user_msg = build_user_message(items, instruction)
    from google.genai import types
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        max_output_tokens=DEFAULT_MAX_TOKENS,
        temperature=0.3,
    )
    resp = client.models.generate_content(model=model, contents=user_msg, config=config)
    parsed = parse_response((resp.text or "").strip())  # {"item_0": {...}}
    out: dict[int, dict[str, str]] = {}
    for i in range(len(items)):
        entry = parsed.get(f"item_{i}")
        if entry:
            out[i] = entry
    return out


def summarize_source(client, items: list[dict[str, Any]], instruction: str, model: str) -> list[dict[str, Any]]:
    if not items or not instruction:
        return items

    # 1차
    got = _summarize_once(client, items, instruction, model)
    for i, item in enumerate(items):
        entry = got.get(i, {})
        item["summary"] = entry.get("summary", "")
        if entry.get("title_ko"):
            item["title_ko"] = entry["title_ko"]

    # 재시도: summary 빈 항목만 (로컬→원본 인덱스 매핑)
    missing_idx = [i for i, it in enumerate(items) if not it.get("summary")]
    if missing_idx:
        time.sleep(5)  # 무료 티어 503 은 잠깐 뒤면 풀리는 경우가 많다
        sub = [items[i] for i in missing_idx]
        retry = _summarize_once(client, sub, instruction, model)  # {로컬j: {...}}
        for j, orig_i in enumerate(missing_idx):
            entry = retry.get(j, {})
            if entry.get("summary"):
                items[orig_i]["summary"] = entry["summary"]
            if entry.get("title_ko") and not items[orig_i].get("title_ko"):
                items[orig_i]["title_ko"] = entry["title_ko"]

    # 폴백: 그래도 비면 lead 앞부분
    for it in items:
        if not it.get("summary"):
            it["summary"] = fallback_summary(it.get("lead", ""))

    return items


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[summarize] GEMINI_API_KEY 환경변수 필요", file=sys.stderr)
        return 1

    if not FILTERED_PATH.exists():
        print("[summarize] filtered.json 없음 — collect/manage_seen 먼저 실행하세요", file=sys.stderr)
        return 1

    try:
        from google import genai
    except ImportError:
        print("[summarize] `pip install google-genai` 필요", file=sys.stderr)
        return 1

    client = genai.Client(api_key=api_key)

    with FILTERED_PATH.open(encoding="utf-8") as f:
        filtered = json.load(f)

    config = load_config()
    model = config.get("summarize", {}).get("model", DEFAULT_MODEL)

    out_sources: list[dict[str, Any]] = []
    total_in, total_summarized = 0, 0
    ranked = any(it.get("rank") for src in filtered.get("sources", []) for it in src.get("items", []))

    for src_block in filtered.get("sources", []):
        source = src_block.get("source", "")
        items = src_block.get("items", [])
        total_in += len(items)

        if not items:
            out_sources.append(src_block)
            continue

        instruction = load_prompt(prompt_for(source))

        # rank.py 가 돌았으면 상위(rank 있는) 항목만 요약한다. 나머지는 제목만 접혀 나간다.
        targets = [it for it in items if it.get("rank")] if ranked else items
        if targets:
            try:
                summarize_source(client, targets, instruction, model)
                ok_count = sum(1 for it in targets if it.get("summary"))
                total_summarized += ok_count
                print(f"[summarize] {source}: {len(items)}건 중 {len(targets)}건 대상, 요약 {ok_count}건", file=sys.stderr)
            except Exception as e:
                print(f"[summarize] {source} 실패: {e}", file=sys.stderr)

        out_sources.append({
            "source": source,
            "source_name": src_block.get("source_name", ""),
            "collected_at": src_block.get("collected_at"),
            "items": items,
        })

    now = datetime.now(ZoneInfo("Asia/Seoul"))
    result = {
        "summarized_at": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "model": model,
        "sources": out_sources,
    }

    SUMMARIZED_PATH.parent.mkdir(exist_ok=True)
    with SUMMARIZED_PATH.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[summarize] 전체 {total_in}건 입력 → {total_summarized}건 요약 성공 → {SUMMARIZED_PATH.relative_to(ROOT)}", file=sys.stderr)
    return 0


def _self_check() -> None:
    assert fallback_summary("a" * 200) == "a" * 150 + "…"
    assert fallback_summary("짧은리드") == "짧은리드"
    assert fallback_summary("") == ""
    assert fallback_summary("   spaced   ") == "spaced"
    assert prompt_for("naver_ranking") == "news-summary.md"
    assert prompt_for("geeknews_rss") == "blog-summary.md"
    assert prompt_for("simon-willison_rss") == "blog-summary.md"
    assert prompt_for("anthropic_html") == "blog-summary.md"
    assert prompt_for("threads_rsshub") == "threads-summary.md"
    print("[summarize] self-check OK")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        sys.exit(0)
    sys.exit(main())
