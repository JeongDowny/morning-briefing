"""수집 항목을 config/interests.md 기준으로 섹션별 정렬.

입력/출력: collected/filtered.json (제자리 갱신)
환경변수: GEMINI_API_KEY

섹션(AI·개발 / 경제)마다 Gemini 1회 호출로 상위 N건을 고르고, 고른 항목에
`rank`(1부터)를 단다. 정렬만 한다 — 버리는 항목은 없다. 나머지는 Daily 노트에
제목만 접혀 남는다.

정렬이 실패하면(키 없음·503·응답 파싱 실패) 수집 순서의 앞 N건에 rank 와
`rank_fallback: true` 를 단다. 발송을 막지도, 항목을 빼지도 않는다.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "briefing.json"
INTERESTS_PATH = ROOT / "config" / "interests.md"
FILTERED_PATH = ROOT / "collected" / "filtered.json"

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TOP = {"ai": 7, "econ": 5}


def section_key(source: str) -> str | None:
    """render_daily / send_telegram 의 섹션 규칙과 같다. 정렬 대상이 아니면 None."""
    if source.startswith("naver_"):
        return "econ"
    if source.endswith("_rss") or source.endswith("_html"):
        return "ai"
    return None


def split_top(items: list[dict[str, Any]], n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(상위, 나머지). rank 가 하나라도 있으면 rank 순, 없으면 들어온 순서의 앞 n건."""
    if any(it.get("rank") for it in items):
        top = sorted((it for it in items if it.get("rank")), key=lambda it: it["rank"])
        rest = [it for it in items if not it.get("rank")]
        return top, rest
    return items[:n], items[n:]


def interests_for(section: str) -> str:
    """interests.md 에서 해당 섹션(## AI·개발 / ## 경제) 본문만."""
    if not INTERESTS_PATH.exists():
        return ""
    text = INTERESTS_PATH.read_text(encoding="utf-8")
    header = "## AI·개발" if section == "ai" else "## 경제"
    m = re.search(rf"^{re.escape(header)}\s*$(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def build_prompt(items: list[dict[str, Any]], interests: str, n: int) -> str:
    lines = []
    for i, it in enumerate(items):
        src = it.get("press") or it.get("source_name") or ""
        lead = (it.get("lead") or "").replace("\n", " ").strip()[:200]
        lines.append(f"item_{i} | {src} | {it.get('title', '').strip()} | {lead}")
    return (
        "아래 글 목록을 관심사에 가까운 순서로 골라라.\n\n"
        f"## 관심사\n{interests}\n\n"
        f"## 글 목록 (id | 출처 | 제목 | 서두)\n" + "\n".join(lines) + "\n\n"
        f"관심사에 가장 가까운 {n}개의 id 를 가까운 순서대로 고른다. "
        f"목록이 {n}개보다 적으면 전부 순서대로 넣는다. "
        "글의 품질이나 읽을 가치를 평가하지 말고, 관심사와 얼마나 가까운지만 본다.\n"
        '응답은 JSON 객체만: {"order": ["item_3", "item_0", ...]}'
    )


def parse_order(text: str, count: int, n: int) -> list[int]:
    """응답 → 유효한 인덱스 목록(중복·범위 밖 제거, 최대 n개). 실패 시 []."""
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return []
    try:
        order = json.loads(m.group(0)).get("order", [])
    except Exception:
        return []
    out: list[int] = []
    for iid in order:
        mm = re.fullmatch(r"item_(\d+)", str(iid).strip())
        if not mm:
            continue
        i = int(mm.group(1))
        if i < count and i not in out:
            out.append(i)
        if len(out) >= n:
            break
    return out


def ask_order(client, model: str, items: list[dict[str, Any]], interests: str, n: int) -> list[int]:
    from google.genai import types
    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
    prompt = build_prompt(items, interests, n)
    for attempt in range(2):  # 무료 티어 503 이 잦아 1회만 재시도
        try:
            resp = client.models.generate_content(model=model, contents=prompt, config=config)
            order = parse_order(resp.text or "", len(items), n)
            if order:
                return order
            print("[rank] 응답에서 순서를 못 읽음", file=sys.stderr)
        except Exception as e:
            print(f"[rank] 호출 실패({attempt + 1}/2): {e}", file=sys.stderr)
        if attempt == 0:
            time.sleep(5)
    return []


def apply_ranks(items: list[dict[str, Any]], order: list[int], n: int) -> None:
    for it in items:
        it.pop("rank", None)
        it.pop("rank_fallback", None)
    if order:
        for r, i in enumerate(order, start=1):
            items[i]["rank"] = r
    else:
        for r, it in enumerate(items[:n], start=1):
            it["rank"] = r
            it["rank_fallback"] = True


def main() -> int:
    if not FILTERED_PATH.exists():
        print("[rank] filtered.json 없음 — collect/manage_seen 먼저 실행하세요", file=sys.stderr)
        return 1
    data = json.loads(FILTERED_PATH.read_text(encoding="utf-8"))
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8")) if CONFIG_PATH.exists() else {}
    rcfg = cfg.get("ranking", {})
    tops = {"ai": rcfg.get("ai_top", DEFAULT_TOP["ai"]), "econ": rcfg.get("econ_top", DEFAULT_TOP["econ"])}
    model = cfg.get("summarize", {}).get("model", DEFAULT_MODEL)

    # 섹션별로 소스를 가로질러 모은다 (정렬은 섹션 단위)
    by_section: dict[str, list[dict[str, Any]]] = {"ai": [], "econ": []}
    for src in data.get("sources", []):
        key = section_key(src.get("source", ""))
        if key:
            by_section[key].extend(src.get("items", []))

    client = None
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
        except Exception as e:
            print(f"[rank] Gemini 클라이언트 생성 실패: {e}", file=sys.stderr)
    else:
        print("[rank] GEMINI_API_KEY 없음 — 수집 순서로 대신", file=sys.stderr)

    for key, items in by_section.items():
        if not items:
            continue
        n = tops[key]
        order = ask_order(client, model, items, interests_for(key), n) if client else []
        apply_ranks(items, order, n)
        how = "관심사 정렬" if order else "수집 순서(정렬 실패)"
        print(f"[rank] {key}: {len(items)}건 중 상위 {min(n, len(items))}건 — {how}", file=sys.stderr)

    FILTERED_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def _self_check() -> None:
    assert parse_order('{"order": ["item_2", "item_0", "item_2", "item_9", "x"]}', 3, 5) == [2, 0]
    assert parse_order('```json\n{"order": ["item_1"]}\n```', 3, 5) == [1]
    assert parse_order("not json", 3, 5) == []
    assert parse_order('{"order": ["item_0", "item_1", "item_2"]}', 3, 2) == [0, 1]

    items = [{"title": str(i)} for i in range(4)]
    apply_ranks(items, [2, 0], 3)
    top, rest = split_top(items, 3)
    assert [t["title"] for t in top] == ["2", "0"] and [r["title"] for r in rest] == ["1", "3"]

    apply_ranks(items, [], 3)  # 정렬 실패 → 앞 3건, 표시
    top, rest = split_top(items, 3)
    assert [t["title"] for t in top] == ["0", "1", "2"] and all(t["rank_fallback"] for t in top)
    assert [r["title"] for r in rest] == ["3"]

    plain = [{"title": "a"}, {"title": "b"}]  # rank.py 가 아예 안 돈 경우
    assert split_top(plain, 1) == ([{"title": "a"}], [{"title": "b"}])

    assert section_key("naver_ranking") == "econ" and section_key("geeknews_rss") == "ai"
    assert section_key("anthropic_html") == "ai" and section_key("threads_rsshub") is None
    print("[rank] self-check OK")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        sys.exit(0)
    sys.exit(main())
