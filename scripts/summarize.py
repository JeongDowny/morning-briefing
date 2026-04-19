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
from datetime import datetime
from pathlib import Path
from typing import Any

from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "briefing.json"
PROMPTS_DIR = ROOT / "config" / "prompts"
FILTERED_PATH = ROOT / "collected" / "filtered.json"
SUMMARIZED_PATH = ROOT / "collected" / "summarized.json"

SOURCE_PROMPT = {
    "naver_ranking": "news-summary.md",
    "openai_rss": "blog-summary.md",
    "anthropic_html": "blog-summary.md",
    "threads_rsshub": "threads-summary.md",
}

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_TOKENS = 8192


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
        "다음은 요약할 항목 리스트. 각 항목의 id 를 결과에 그대로 포함해.\n\n"
        f"{input_block}\n\n"
        "응답은 반드시 아래 JSON 스키마만 사용. 다른 설명·마크다운 금지.\n"
        '{"summaries": [{"id": "item_0", "summary": "..."}, ...]}'
    )


def parse_response(text: str) -> dict[str, str]:
    """응답 텍스트에서 JSON 추출 후 id→summary 맵."""
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
    out: dict[str, str] = {}
    for s in data.get("summaries", []):
        if isinstance(s, dict) and "id" in s:
            out[str(s["id"])] = (s.get("summary") or "").strip()
    return out


def summarize_source(client, items: list[dict[str, Any]], instruction: str, model: str) -> list[dict[str, Any]]:
    if not items or not instruction:
        return items
    user_msg = build_user_message(items, instruction)

    from google.genai import types
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        max_output_tokens=DEFAULT_MAX_TOKENS,
        temperature=0.3,
    )
    resp = client.models.generate_content(
        model=model,
        contents=user_msg,
        config=config,
    )
    text = (resp.text or "").strip()
    summaries = parse_response(text)

    for i, item in enumerate(items):
        item["summary"] = summaries.get(f"item_{i}", "")
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

    for src_block in filtered.get("sources", []):
        source = src_block.get("source", "")
        items = src_block.get("items", [])
        total_in += len(items)

        if not items:
            out_sources.append(src_block)
            continue

        prompt_file = SOURCE_PROMPT.get(source, "news-summary.md")
        instruction = load_prompt(prompt_file)

        try:
            items = summarize_source(client, items, instruction, model)
            ok_count = sum(1 for it in items if it.get("summary"))
            total_summarized += ok_count
            print(f"[summarize] {source}: {len(items)}건 중 요약 {ok_count}건", file=sys.stderr)
        except Exception as e:
            print(f"[summarize] {source} 실패: {e}", file=sys.stderr)

        out_sources.append({
            "source": source,
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


if __name__ == "__main__":
    sys.exit(main())
