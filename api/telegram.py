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


# --- self-check ---

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


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        sys.exit(0)
    print("이 파일은 Vercel webhook 함수입니다. 로컬 테스트는 --self-check.", file=sys.stderr)
