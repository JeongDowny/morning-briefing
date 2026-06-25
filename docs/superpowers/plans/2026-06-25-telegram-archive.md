# 텔레그램 원탭 아카이브 → Obsidian Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 텔레그램 브리핑의 항목별 인라인 버튼을 한 번 누르면 해당 기사가 repo 의 `Archive/` 폴더에 개별 Obsidian 노트로 영구 저장된다.

**Architecture:** GitHub Actions cron 이 발송 전 `data/manifest-{날짜}.json`(id→항목)을 만들어 push 한다. `send_telegram.py` 는 manifest 를 읽어 항목에 번호를 매기고 메시지 하단에 번호 버튼(`[📥 N]`, callback_data=id)을 붙인다. 사용자가 버튼을 누르면 Vercel Python 서버리스 함수 `api/telegram.py`(webhook)가 manifest 에서 항목을 조회해 GitHub Contents API 로 `Archive/{날짜}-{해시}.md` 를 커밋한다. DB 없음 — repo 가 저장소.

**Tech Stack:** Python 3.11(CI)/3.12(local), `requests`(기존 의존성), stdlib(`hashlib`/`hmac`/`re`/`base64`/`json`), Vercel Python Serverless Functions(`@vercel/python`), Obsidian Dataview.

## Global Constraints

- 응답/주석 한국어, 식별자 영어, 커밋 Conventional Commits 한국어.
- 새 의존성 추가 금지 — `requests` + stdlib 만. (`api/telegram.py` 는 Vercel 용 `api/requirements.txt` 에 `requests` 명시.)
- 테스트는 pytest 미사용 — 각 스크립트에 `--self-check` 플래그(assert 기반), 통과 시 종료코드 0.
- id 형식 고정: `{YYYYMMDD}-{hash8}`, `hash8 = sha1(url).hexdigest()[:8]`. callback_data ≤ 64바이트.
- manifest 파일명: `data/manifest-{YYYY-MM-DD}.json` (하이픈). id 안 날짜는 `YYYYMMDD`(하이픈 없음).
- url 해석 폴백 체인: `originallink → link → url`. 셋 다 비면 버튼/manifest 제외.
- 시크릿은 Vercel 환경변수에만. 코드/repo 하드코딩 금지.
- Archive 노트 frontmatter `title` 은 `"` 이스케이프.
- manifest 는 **반드시 발송 전에** 커밋·push.

---

### Task 1: `build_manifest.py` — id 부여 + manifest 생성 + 14일 정리

**Files:**
- Create: `scripts/build_manifest.py`

**Interfaces:**
- Consumes: `collected/summarized.json`(없으면 `collected/filtered.json`) — `{"sources":[{"items":[{title,url|link|originallink,summary,source_name},...]}]}`
- Produces:
  - `resolve_url(item: dict) -> str`
  - `compute_id(url: str, date_compact: str) -> str` (date_compact = `YYYYMMDD`)
  - `build_manifest(data: dict, date_compact: str) -> dict` → `{"date": "YYYY-MM-DD", "items": {id: {title,url,summary,source}}}`
  - `cleanup_old(manifest_dir: Path, today: date, keep_days: int = 14) -> int`
  - `data/manifest-{YYYY-MM-DD}.json` 파일

- [ ] **Step 1: Write the failing self-check**

`scripts/build_manifest.py` 하단에 self-check 부터 작성 (아직 함수 없음 → import 실패로 실패):

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/build_manifest.py --self-check`
Expected: FAIL — `NameError: name 'resolve_url' is not defined` (또는 import 단계 오류)

- [ ] **Step 3: Write the implementation**

`scripts/build_manifest.py` 전체:

```python
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


# --- self-check (위 Step 1 의 _self_check 본문을 여기에 둔다) ---


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        sys.exit(0)
    sys.exit(main())
```

(Step 1 의 `_self_check` 함수를 `# --- self-check` 주석 자리에 붙여 넣는다.)

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/build_manifest.py --self-check`
Expected: PASS — `[build_manifest] self-check OK`

- [ ] **Step 5: Smoke run against real data**

Run: `python scripts/build_manifest.py && ls data/manifest-*.json && python -c "import json,glob; p=sorted(glob.glob('data/manifest-*.json'))[-1]; d=json.load(open(p)); print('items:', len(d['items'])); print('sample id:', next(iter(d['items'])) if d['items'] else 'none')"`
Expected: `data/manifest-YYYY-MM-DD.json` 생성, items 수 출력, 샘플 id 형식 `YYYYMMDD-xxxxxxxx`.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_manifest.py
git commit -m "feat(archive): manifest 생성기 — 항목 id 부여 + 14일 보관"
```

---

### Task 2: `send_telegram.py` — 번호 매기기 + 하단 번호 버튼

**Files:**
- Modify: `scripts/send_telegram.py`

**Interfaces:**
- Consumes: 최신 `data/manifest-{today}.json` (Task 1 산출), `compute_id` 와 동일한 url→id 매핑을 manifest 역방향으로 사용 (sha1 재계산 안 함).
- Produces:
  - `load_url_to_id(date_iso: str) -> dict[str, str]` — manifest 에서 `{url: id}` 역맵
  - `build_buttons(numbered: list[tuple[int, str]]) -> dict` — `[(번호, id), …]` → 텔레그램 `inline_keyboard` (4개/행)
  - `build_section_messages(...)` 가 `list[tuple[str, dict | None]]` (텍스트, reply_markup) 반환하도록 변경
  - `send_message(token, chat_id, text, reply_markup=None)`

- [ ] **Step 1: Write the failing self-check**

`scripts/send_telegram.py` 하단에 추가:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `python scripts/send_telegram.py --self-check`
Expected: FAIL — `NameError: build_buttons` (또는 `render_one_message` 미정의)

- [ ] **Step 3: Implement — manifest 역맵 + 버튼 + 메시지 렌더 변경**

3-1. import 영역 아래 상수/헬퍼 추가:

```python
from datetime import datetime  # 기존 존재 — 중복 import 추가하지 말 것
BUTTONS_PER_ROW = 4
MANIFEST_DIR = ROOT / "data"


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
```

3-2. `format_item_line` 에 번호 prefix 추가 — 시그니처에 `number: int` 추가:

```python
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
```

3-3. 한 메시지를 렌더하는 신규 함수 (번호·버튼 한 묶음 처리):

```python
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
```

3-4. `build_section_messages` 를 4000자 분할하면서 `render_one_message` 로 묶음별 렌더하도록 교체:

```python
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
```

3-5. `send_message` 에 `reply_markup` 추가:

```python
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
```

3-6. `main()` 에서 url_to_id 로드 + 새 시그니처로 호출:

```python
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
```

3-7. 파일 맨 아래 `--self-check` 분기 추가:

```python
if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        sys.exit(0)
    sys.exit(main())
```

- [ ] **Step 4: Run to verify self-check passes**

Run: `python scripts/send_telegram.py --self-check`
Expected: PASS — `[send_telegram] self-check OK`

- [ ] **Step 5: Dry render (네트워크 없이 메시지·버튼 모양 확인)**

Run:
```bash
python - <<'PY'
import json, scripts.send_telegram as s
# 최신 manifest 로 역맵
import glob, datetime
date_iso = datetime.datetime.now().strftime("%Y-%m-%d")
u2i = s.load_url_to_id(date_iso)
data = json.load(open("collected/summarized.json"))
grouped = s.group_by_section(data["sources"])
for label, srcs in grouped.items():
    for text, kb in s.build_section_messages(label, srcs, date_iso, False, u2i):
        print("=====", label, "버튼", 0 if not kb else sum(len(r) for r in kb["inline_keyboard"]))
        print(text[:300])
PY
```
Expected: 섹션별 메시지 텍스트에 `1.`, `2.` 번호가 보이고, 버튼 수가 manifest 항목 수와 일치. (manifest 가 오늘 것 없으면 버튼 0 — 정상, Task 1 smoke 후 재확인.)

- [ ] **Step 6: Commit**

```bash
git add scripts/send_telegram.py
git commit -m "feat(archive): 텔레그램 항목 번호 + 하단 아카이브 버튼"
```

---

### Task 3: `api/telegram.py` — Vercel webhook 함수

**Files:**
- Create: `api/telegram.py`
- Create: `api/requirements.txt`
- Create: `vercel.json`

**Interfaces:**
- Consumes: 텔레그램 webhook `callback_query` POST; env `WEBHOOK_SECRET`/`TELEGRAM_BOT_TOKEN`/`GITHUB_TOKEN`/`GITHUB_REPO`.
- Produces (순수 헬퍼, self-check 대상):
  - `parse_callback_data(data: str) -> tuple[str, str] | None` → `(date_iso, hash8)` 또는 None
  - `archive_path(date_iso: str, hash8: str) -> str`
  - `slugify(name: str) -> str`
  - `build_note_markdown(item: dict, date_iso: str) -> str`
  - `secret_ok(headers: dict, expected: str) -> bool`

- [ ] **Step 1: Write the failing self-check**

`api/telegram.py` 하단:

```python
def _self_check() -> None:
    # callback_data 검증 + 날짜 변환
    assert parse_callback_data("20260625-3f9a2b1c") == ("2026-06-25", "3f9a2b1c")
    assert parse_callback_data("bad") is None
    assert parse_callback_data("20260625-XYZ") is None
    assert parse_callback_data("20260625-3f9a2b1c; rm -rf") is None  # 경로/주입 차단

    assert archive_path("2026-06-25", "3f9a2b1c") == "Archive/2026-06-25-3f9a2b1c.md"

    assert slugify("GeekNews") == "geeknews"
    assert slugify("Google DeepMind") == "google-deepmind"

    # secret 검증 (헤더 키는 텔레그램 규격)
    assert secret_ok({"x-telegram-bot-api-secret-token": "s3"}, "s3") is True
    assert secret_ok({"x-telegram-bot-api-secret-token": "nope"}, "s3") is False
    assert secret_ok({}, "s3") is False

    # 노트 마크다운
    md = build_note_markdown(
        {"title": 'Quote "X" here', "url": "https://h.io/t?id=1", "summary": "요약", "source": "GeekNews"},
        "2026-06-25",
    )
    assert 'title: "Quote \\"X\\" here"' in md, "제목 따옴표 이스케이프"
    assert "tags: [archive, geeknews]" in md
    assert "# Quote \"X\" here" in md
    assert "https://h.io/t?id=1" in md
    print("[api.telegram] self-check OK")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python api/telegram.py --self-check`
Expected: FAIL — `NameError: parse_callback_data`

- [ ] **Step 3: Implement `api/telegram.py`**

```python
"""텔레그램 인라인 버튼 콜백을 받아 Archive/ 에 개별 노트를 커밋하는 Vercel webhook.

env: WEBHOOK_SECRET, TELEGRAM_BOT_TOKEN, GITHUB_TOKEN(repo contents:write), GITHUB_REPO(owner/repo)
배포/설정은 docs/superpowers/plans 의 Task 6 런북 참고.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler
from typing import Any

import requests

CALLBACK_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})-([0-9a-f]{8})$")
GH_API = "https://api.github.com"
TG_API = "https://api.telegram.org/bot{token}/{method}"
HTTP_TIMEOUT = 10


def parse_callback_data(data: str) -> tuple[str, str] | None:
    m = CALLBACK_RE.match(data or "")
    if not m:
        return None
    y, mo, d, h = m.groups()
    return f"{y}-{mo}-{d}", h


def archive_path(date_iso: str, hash8: str) -> str:
    return f"Archive/{date_iso}-{hash8}.md"


def slugify(name: str) -> str:
    s = name.lower().replace(" ", "-")
    s = re.sub(r"[^a-z0-9\-]", "", s)
    return s.strip("-")


def build_note_markdown(item: dict[str, Any], date_iso: str) -> str:
    title = (item.get("title") or "").strip()
    url = (item.get("url") or "").strip()
    summary = (item.get("summary") or "").strip()
    source = (item.get("source") or "").strip()
    title_yaml = title.replace('"', '\\"')
    tags = "archive" + (f", {slugify(source)}" if source else "")
    return (
        "---\n"
        f'title: "{title_yaml}"\n'
        f"date: {date_iso}\n"
        f"source: {source}\n"
        f"url: {url}\n"
        f"tags: [{tags}]\n"
        "---\n\n"
        f"# {title}\n\n"
        f"> 📂 {source} · {date_iso} 아카이브\n\n"
        f"🤖 {summary}\n\n"
        f"🔗 [원문 보기]({url})\n"
    )


def secret_ok(headers: dict[str, str], expected: str) -> bool:
    got = headers.get("x-telegram-bot-api-secret-token", "")
    return bool(expected) and got == expected


# ---- 네트워크 (self-check 제외) ----

def _gh_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }


def fetch_manifest_item(repo: str, date_iso: str, iid: str) -> dict[str, Any] | None:
    raw = f"https://raw.githubusercontent.com/{repo}/main/data/manifest-{date_iso}.json"
    r = requests.get(raw, headers=_gh_headers(), timeout=HTTP_TIMEOUT)
    if r.status_code != 200:
        return None
    return r.json().get("items", {}).get(iid)


def archive_exists(repo: str, path: str) -> bool:
    r = requests.get(f"{GH_API}/repos/{repo}/contents/{path}", headers=_gh_headers(), timeout=HTTP_TIMEOUT)
    return r.status_code == 200


def commit_note(repo: str, path: str, content: str) -> int:
    payload = {
        "message": f"archive: {path}",
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": "main",
    }
    r = requests.put(f"{GH_API}/repos/{repo}/contents/{path}", headers=_gh_headers(),
                     json=payload, timeout=HTTP_TIMEOUT)
    return r.status_code  # 201 생성, 409/422 = 이미 존재(멱등)


def tg(method: str, payload: dict[str, Any]) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    requests.post(TG_API.format(token=token, method=method), json=payload, timeout=HTTP_TIMEOUT)


def answer(cb_id: str, text: str) -> None:
    tg("answerCallbackQuery", {"callback_query_id": cb_id, "text": text})


def mark_done(chat_id: int, message_id: int, reply_markup: dict[str, Any], iid: str) -> None:
    """누른 버튼 라벨을 ✅ 로 교체."""
    rows = reply_markup.get("inline_keyboard", [])
    for row in rows:
        for b in row:
            if b.get("callback_data") == iid:
                b["text"] = b["text"].replace("📥", "✅")
    tg("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                  "reply_markup": {"inline_keyboard": rows}})


def handle_update(update: dict[str, Any]) -> None:
    cq = update.get("callback_query")
    if not cq:
        return
    cb_id = cq["id"]
    iid = cq.get("data", "")
    parsed = parse_callback_data(iid)
    if not parsed:
        answer(cb_id, "잘못된 요청")
        return
    date_iso, hash8 = parsed
    repo = os.environ["GITHUB_REPO"]

    item = fetch_manifest_item(repo, date_iso, iid)
    if not item:
        answer(cb_id, "⏳ 만료된 항목")
        return

    path = archive_path(date_iso, hash8)
    msg = cq.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")
    reply_markup = msg.get("reply_markup", {"inline_keyboard": []})

    if archive_exists(repo, path):
        answer(cb_id, "이미 저장됨")
        mark_done(chat_id, message_id, reply_markup, iid)
        return

    status = commit_note(repo, path, build_note_markdown(item, date_iso))
    if status in (200, 201):
        answer(cb_id, "✅ 아카이브됨")
        mark_done(chat_id, message_id, reply_markup, iid)
    elif status in (409, 422):
        answer(cb_id, "이미 저장됨")  # 동시 탭 레이스 멱등 처리
        mark_done(chat_id, message_id, reply_markup, iid)
    else:
        answer(cb_id, "저장 실패, 잠시 후 재시도")
        print(f"[api.telegram] commit 실패 status={status} path={path}", file=sys.stderr)


class handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 (Vercel 규격)
        expected = os.environ.get("WEBHOOK_SECRET", "")
        headers = {k.lower(): v for k, v in self.headers.items()}
        if not secret_ok(headers, expected):
            self.send_response(401)
            self.end_headers()
            return
        length = int(self.headers.get("content-length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            handle_update(json.loads(body or b"{}"))
        except Exception as e:  # noqa: BLE001 — webhook 은 200 반환해야 재시도 폭주 안 함
            print(f"[api.telegram] 처리 오류: {e}", file=sys.stderr)
        self.send_response(200)
        self.end_headers()


# --- self-check (Step 1 의 _self_check 본문을 여기에) ---


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        sys.exit(0)
    print("이 파일은 Vercel webhook 함수입니다. 로컬 테스트는 --self-check.", file=sys.stderr)
```

(Step 1 의 `_self_check` 를 `# --- self-check` 자리에 붙인다.)

- [ ] **Step 4: Create `api/requirements.txt`**

```
requests
```

- [ ] **Step 5: Create `vercel.json`**

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "functions": {
    "api/telegram.py": { "runtime": "@vercel/python@4.3.0" }
  }
}
```

- [ ] **Step 6: Run self-check**

Run: `python api/telegram.py --self-check`
Expected: PASS — `[api.telegram] self-check OK`

- [ ] **Step 7: Commit**

```bash
git add api/telegram.py api/requirements.txt vercel.json
git commit -m "feat(archive): Vercel webhook — 콜백 → Archive 노트 커밋"
```

---

### Task 4: `Archive.md` 인덱스 + `Archive/` 폴더

**Files:**
- Create: `Archive.md`
- Create: `Archive/.gitkeep`

**Interfaces:** Obsidian Dataview 플러그인이 `#archive` 노트를 읽어 표로 렌더. 코드 의존 없음.

- [ ] **Step 1: Create `Archive/.gitkeep`** (빈 파일)

```bash
mkdir -p Archive && touch Archive/.gitkeep
```

- [ ] **Step 2: Create `Archive.md`**

````markdown
# 📂 아카이브

`#archive` 태그가 붙은 노트가 자동 집계됩니다. 텔레그램 브리핑의 📥 버튼으로 저장됩니다.

## 최근 30일

```dataview
TABLE source AS "출처", date AS "날짜"
FROM #archive
WHERE date >= date(today) - dur(30 days)
SORT date DESC
```

## 소스별

```dataview
TABLE rows.file.link AS "글", rows.date AS "날짜"
FROM #archive
GROUP BY source
```

## 전체 (최신순)

```dataview
TABLE source AS "출처", date AS "날짜"
FROM #archive
SORT date DESC
```
````

- [ ] **Step 3: Verify** — `Archive.md` 를 Obsidian 에서 열어 Dataview 블록이 (아직 노트 0개라) "빈 표"로 렌더되는지 확인. (CI 검증 불가 — 수동.)

- [ ] **Step 4: Commit**

```bash
git add Archive.md Archive/.gitkeep
git commit -m "feat(archive): Archive 폴더 + Dataview 인덱스 노트"
```

---

### Task 5: 워크플로 — 발송 전 manifest 스텝 + push

**Files:**
- Modify: `.github/workflows/daily-brief.yml`

**Interfaces:** Summarize 다음, Send Telegram **앞**에 manifest 생성+push 스텝 삽입.

- [ ] **Step 1: `Summarize with Gemini` 스텝 바로 뒤에 신규 스텝 삽입**

`.github/workflows/daily-brief.yml` 의 `Render Daily note` **앞**(=Summarize 뒤)에 추가:

```yaml
      - name: Build manifest and push (발송 전 필수)
        run: |
          python scripts/build_manifest.py
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/manifest-*.json
          if git diff --cached --quiet; then
            echo "manifest 변경 없음 — 커밋 스킵"
          else
            git commit -m "archive: manifest $(TZ='Asia/Seoul' date +%Y-%m-%d)"
            git push
          fi
        continue-on-error: false
```

> 주의: 이 스텝은 `continue-on-error: false` — manifest 가 원격에 없으면 버튼이 전부 죽으므로
> 실패 시 잡을 멈춘다. (다른 수집 스텝은 기존대로 continue-on-error 유지.)

- [ ] **Step 2: 마지막 commit 스텝 확인** — 기존 `Commit Daily note and seen.json` 은 `Daily/`,
`data/seen.json` 만 add 하므로 그대로 둔다 (manifest 는 이미 push 됨). 변경 없음.

- [ ] **Step 3: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/daily-brief.yml')); print('YAML OK')"`
Expected: `YAML OK` (pyyaml 없으면 `pip install pyyaml` 후 실행, 또는 `python -c "import json,sys; print('skip')"` 생략 가능 — 최소 들여쓰기 육안 확인).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/daily-brief.yml
git commit -m "ci(archive): 발송 전 manifest 생성+push 스텝 추가"
```

---

### Task 6: 1회 배포·연결 런북 (문서)

**Files:**
- Create: `docs/superpowers/plans/archive-setup-runbook.md`

**Interfaces:** 사람이 1회 수행. 코드 없음. (Vercel 계정·GitHub PAT·텔레그램 봇 토큰 전제.)

- [ ] **Step 1: 런북 작성** — 아래 내용으로 파일 생성:

````markdown
# 아카이브 webhook 1회 셋업 런북

## 1. GitHub fine-grained PAT 발급
- Settings → Developer settings → Fine-grained tokens → Generate
- Repository access: 이 repo 하나만
- Permissions: **Contents = Read and write** (그 외 전부 No access)
- 토큰 복사 → `GITHUB_TOKEN`

## 2. webhook secret 생성
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
→ 출력값을 `WEBHOOK_SECRET` 으로 사용.

## 3. Vercel 배포
```bash
npm i -g vercel   # 최초 1회
vercel link       # 이 repo 를 Vercel 프로젝트에 연결
vercel env add WEBHOOK_SECRET production       # 위 secret
vercel env add TELEGRAM_BOT_TOKEN production    # 기존 봇 토큰
vercel env add GITHUB_TOKEN production          # 1번 PAT
vercel env add GITHUB_REPO production           # 예: jeongdowny/morning-briefing
vercel --prod
```
→ 배포 URL 확인 (예 `https://morning-briefing-xxxx.vercel.app`). 엔드포인트는 `/api/telegram`.

## 4. 텔레그램 webhook 등록 (secret 동봉)
```bash
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -d "url=https://<배포도메인>/api/telegram" \
  -d "secret_token=<WEBHOOK_SECRET>" \
  -d 'allowed_updates=["callback_query"]'
```
→ `{"ok":true,...}` 확인.

## 5. 검증
- `python scripts/build_manifest.py && git add data/ && git commit -m test && git push`
- 텔레그램에서 아무 메시지에 버튼이 오도록 `python scripts/send_telegram.py` 수동 실행
  (TELEGRAM_BOT_TOKEN/CHAT_ID 환경변수 필요)
- 버튼 탭 → 몇 초 뒤 repo `Archive/` 에 노트 커밋 + 버튼이 ✅ 로 바뀌는지 확인
- 같은 버튼 다시 탭 → "이미 저장됨" 응답(멱등) 확인

## 롤백
- 텔레그램 webhook 해제: `curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"`
- 버튼 없는 기존 발송으로 되돌리려면 send_telegram 변경 revert.
````

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/archive-setup-runbook.md
git commit -m "docs(archive): webhook 1회 배포·연결 런북"
```

---

## 통합 검증 (전 Task 후)

- [ ] 로컬 전체 self-check:
```bash
python scripts/build_manifest.py --self-check && \
python scripts/send_telegram.py --self-check && \
python api/telegram.py --self-check && echo "ALL SELF-CHECKS PASS"
```
Expected: 세 줄 OK + `ALL SELF-CHECKS PASS`

- [ ] manifest→발송 dry run (Task 1 Step 5 + Task 2 Step 5) 으로 번호·버튼 수 일치 확인.
- [ ] Task 6 런북 수행 후 실제 텔레그램 버튼 탭 → `Archive/` 노트 생성 + Obsidian `Archive.md` 표 반영(수동).
