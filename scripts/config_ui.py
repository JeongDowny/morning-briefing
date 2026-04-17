#!/usr/bin/env python3
"""Morning Briefing 설정 편집 로컬 서버.

실행:
  python3 scripts/config_ui.py
  → http://localhost:8765 자동 오픈

기능:
  - config/briefing.json 폼 편집 + 저장
  - .env 시크릿 관리 (마스킹, 부분 업데이트)
  - Slack/Telegram 테스트 전송
  - 저장 시 git auto-commit (토글)
  - 외부 서비스 발급 가이드 내장
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "briefing.json"
ENV_PATH = ROOT / ".env"
PORT = 8765

ENV_KEYS = [
    ("NAVER_CLIENT_ID",     "네이버 검색 API Client ID"),
    ("NAVER_CLIENT_SECRET", "네이버 검색 API Client Secret"),
    ("TELEGRAM_BOT_TOKEN",  "Telegram Bot Token"),
    ("TELEGRAM_CHAT_ID",    "Telegram Chat ID"),
    ("SLACK_WEBHOOK_URL",   "Slack Incoming Webhook URL"),
]


# ─── file helpers ──────────────────────────────────────────────────────

def read_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def write_config(data: dict[str, Any]) -> None:
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    env: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def write_env(env: dict[str, str]) -> None:
    lines = ["# morning-briefing 로컬 환경변수 (gitignore 됨)", ""]
    for key, _desc in ENV_KEYS:
        if env.get(key):
            lines.append(f"{key}={env[key]}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def mask_env(env: dict[str, str]) -> dict[str, dict[str, Any]]:
    """브라우저에 넘길 마스킹된 상태. 실제 값은 절대 안 내보냄."""
    out: dict[str, dict[str, Any]] = {}
    for key, desc in ENV_KEYS:
        val = env.get(key, "")
        out[key] = {
            "desc": desc,
            "is_set": bool(val),
            "preview": ("••••" + val[-4:]) if len(val) >= 8 else ("••••" if val else ""),
        }
    return out


def git_commit_config(message: str) -> tuple[bool, str]:
    try:
        subprocess.run(
            ["git", "-C", str(ROOT), "add", "config/briefing.json"],
            check=True, capture_output=True,
        )
        result = subprocess.run(
            ["git", "-C", str(ROOT), "commit", "-m", message],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        # 변경사항 없음은 정상 케이스
        if "nothing to commit" in (result.stdout + result.stderr).lower():
            return True, "변경 없음"
        return False, result.stderr.strip() or result.stdout.strip()
    except Exception as e:
        return False, str(e)


# ─── HTML ──────────────────────────────────────────────────────────────

HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Morning Briefing — 설정</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Pretendard", "Noto Sans KR", sans-serif; }
  .tab-btn.active { background: #0f172a; color: white; }
  .kbd { font-family: ui-monospace, monospace; background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
  .row { display: grid; gap: 8px; align-items: center; }
</style>
</head>
<body class="bg-slate-50 text-slate-900">
<div class="max-w-4xl mx-auto p-6">

<header class="flex items-center justify-between mb-6">
  <div>
    <h1 class="text-2xl font-bold">🌅 Morning Briefing — 설정</h1>
    <p class="text-sm text-slate-500 mt-1">브라우저에서 편집 · 저장 버튼 클릭 시 config/briefing.json 과 .env 에 반영</p>
  </div>
  <div class="flex items-center gap-3">
    <label class="text-sm flex items-center gap-2">
      <input id="autoCommit" type="checkbox" checked> auto-commit
    </label>
    <button id="saveAll" class="bg-slate-900 text-white px-4 py-2 rounded-lg hover:bg-slate-700">💾 전체 저장</button>
  </div>
</header>

<div id="toast" class="hidden fixed top-4 right-4 bg-slate-900 text-white px-4 py-2 rounded-lg shadow-lg"></div>

<nav class="flex flex-wrap gap-2 mb-6 border-b pb-2">
  <button data-tab="channels" class="tab-btn active px-3 py-1.5 rounded-lg border bg-white hover:bg-slate-100">📡 채널</button>
  <button data-tab="secrets"  class="tab-btn px-3 py-1.5 rounded-lg border bg-white hover:bg-slate-100">🔑 시크릿</button>
  <button data-tab="ranking"  class="tab-btn px-3 py-1.5 rounded-lg border bg-white hover:bg-slate-100">📈 네이버 랭킹</button>
  <button data-tab="keywords" class="tab-btn px-3 py-1.5 rounded-lg border bg-white hover:bg-slate-100">🔍 키워드 (M2)</button>
  <button data-tab="misc"     class="tab-btn px-3 py-1.5 rounded-lg border bg-white hover:bg-slate-100">⚙️ 기타</button>
  <button data-tab="guide"    class="tab-btn px-3 py-1.5 rounded-lg border bg-white hover:bg-slate-100">📖 발급 가이드</button>
</nav>

<!-- CHANNELS -->
<section data-pane="channels" class="pane bg-white rounded-lg shadow-sm p-6">
  <h2 class="text-lg font-semibold mb-4">배포 채널</h2>
  <p class="text-sm text-slate-500 mb-4">브리핑을 받을 채널을 선택하세요. 양쪽 다 체크하면 두 곳 모두 전송됩니다.</p>

  <div class="space-y-4">
    <div class="border rounded-lg p-4">
      <label class="flex items-center justify-between">
        <span class="flex items-center gap-2">
          <input id="ch_telegram" type="checkbox" class="w-4 h-4">
          <span class="font-medium">Telegram</span>
          <span class="text-xs text-slate-400">(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 필요)</span>
        </span>
        <button id="testTelegram" class="text-sm bg-blue-500 text-white px-3 py-1 rounded hover:bg-blue-600">테스트 전송</button>
      </label>
    </div>
    <div class="border rounded-lg p-4">
      <label class="flex items-center justify-between">
        <span class="flex items-center gap-2">
          <input id="ch_slack" type="checkbox" class="w-4 h-4">
          <span class="font-medium">Slack</span>
          <span class="text-xs text-slate-400">(SLACK_WEBHOOK_URL 필요)</span>
        </span>
        <button id="testSlack" class="text-sm bg-purple-500 text-white px-3 py-1 rounded hover:bg-purple-600">테스트 전송</button>
      </label>
    </div>
  </div>
</section>

<!-- SECRETS -->
<section data-pane="secrets" class="pane hidden bg-white rounded-lg shadow-sm p-6">
  <h2 class="text-lg font-semibold mb-4">환경변수 (.env)</h2>
  <p class="text-sm text-slate-500 mb-4">값이 이미 설정된 경우 빈 칸으로 두면 유지됩니다. 새 값을 입력하면 덮어씁니다. 이 파일은 gitignore 되어 커밋되지 않습니다.</p>
  <div id="envList" class="space-y-3"></div>
  <p class="text-xs text-slate-400 mt-4">💡 프로덕션(Scheduled Agent)은 별도로 Claude Code Routines 환경변수 UI에서 설정해야 합니다. 로컬 테스트용으로만 여기 저장됩니다.</p>
</section>

<!-- KEYWORDS -->
<section data-pane="keywords" class="pane hidden bg-white rounded-lg shadow-sm p-6">
  <div class="flex items-center justify-between mb-4">
    <div>
      <h2 class="text-lg font-semibold">경제 키워드 (Open API 검색)</h2>
      <p class="text-sm text-slate-500 mt-1">카테고리별로 섹션 헤더 그룹핑에 사용됩니다.</p>
    </div>
    <button id="addKeyword" class="bg-slate-900 text-white px-3 py-1.5 rounded hover:bg-slate-700">+ 추가</button>
  </div>
  <div class="mb-4">
    <label class="flex items-center gap-2 text-sm">
      <input id="keyword_enabled" type="checkbox"> 키워드 검색 활성화 (M2 이후)
    </label>
  </div>
  <div class="grid grid-cols-3 gap-2 text-xs text-slate-500 font-medium mb-2">
    <div>키워드 (term)</div>
    <div>카테고리</div>
    <div></div>
  </div>
  <div id="keywordList" class="space-y-2"></div>
  <div class="mt-4 grid grid-cols-2 gap-4">
    <label class="text-sm">
      <span class="text-slate-500">키워드당 수집 건수 (per_keyword)</span>
      <input id="per_keyword" type="number" min="1" max="20" class="w-full border rounded px-2 py-1 mt-1">
    </label>
    <label class="text-sm">
      <span class="text-slate-500">정렬 기준 (sort)</span>
      <select id="keyword_sort" class="w-full border rounded px-2 py-1 mt-1">
        <option value="date">date (최신순)</option>
        <option value="sim">sim (관련도순)</option>
      </select>
    </label>
  </div>
</section>

<!-- RANKING -->
<section data-pane="ranking" class="pane hidden bg-white rounded-lg shadow-sm p-6">
  <div class="flex items-center justify-between mb-4">
    <div>
      <h2 class="text-lg font-semibold">네이버 경제 언론사 화이트리스트</h2>
      <p class="text-sm text-slate-500 mt-1">"많이 본 뉴스" 중 여기 등록된 언론사만 수집합니다.</p>
    </div>
    <button id="addPress" class="bg-slate-900 text-white px-3 py-1.5 rounded hover:bg-slate-700">+ 추가</button>
  </div>
  <div class="mb-4">
    <label class="flex items-center gap-2 text-sm">
      <input id="ranking_enabled" type="checkbox"> 랭킹 수집 활성화
    </label>
  </div>
  <div id="pressList" class="space-y-2"></div>
  <label class="text-sm block mt-4">
    <span class="text-slate-500">수집할 상위 건수 (top_n)</span>
    <input id="top_n" type="number" min="1" max="30" class="w-full border rounded px-2 py-1 mt-1">
  </label>
</section>

<!-- MISC -->
<section data-pane="misc" class="pane hidden bg-white rounded-lg shadow-sm p-6">
  <h2 class="text-lg font-semibold mb-4">기타 설정</h2>

  <div class="border rounded-lg p-4 mb-4 bg-slate-50">
    <h3 class="font-medium mb-2">⏰ 브리핑 발송 시각</h3>
    <label class="text-sm flex items-center gap-3">
      <span class="text-slate-600 w-28">시각 (KST)</span>
      <input id="schedule_time" type="time" class="border rounded px-2 py-1">
    </label>
    <div class="mt-3 flex items-center gap-3">
      <span class="text-sm text-slate-600 w-28">UTC Cron</span>
      <code id="schedule_cron" class="kbd bg-white border flex-1">0 23 * * *</code>
      <button id="copyCron" class="text-xs bg-slate-900 text-white px-3 py-1 rounded hover:bg-slate-700">복사</button>
    </div>
    <p class="text-xs text-slate-400 mt-2">💡 Claude Code Routines 등록 시 이 Cron 값을 그대로 입력하세요. 시각 변경하면 자동 재계산됩니다.</p>
  </div>

  <div class="grid grid-cols-2 gap-4">
    <label class="text-sm col-span-2">
      <span class="text-slate-500">중복 방지 유지 기간 (retention_days)</span>
      <input id="retention_days" type="number" min="1" max="365" class="w-full border rounded px-2 py-1 mt-1">
    </label>
    <label class="text-sm col-span-2 flex items-center gap-2">
      <input id="include_raw_lead" type="checkbox">
      <span>원문 리드 문단 같이 표시 (include_raw_lead)</span>
    </label>
  </div>
</section>

<!-- GUIDE -->
<section data-pane="guide" class="pane hidden bg-white rounded-lg shadow-sm p-6 space-y-6">
  <h2 class="text-lg font-semibold">🎯 외부 서비스 발급 가이드</h2>

  <details class="border rounded-lg p-4" open>
    <summary class="font-medium cursor-pointer">네이버 검색 API Client ID / Secret</summary>
    <ol class="list-decimal pl-5 mt-3 text-sm space-y-1 text-slate-700">
      <li><a class="text-blue-600 underline" href="https://developers.naver.com/apps/#/register" target="_blank">developers.naver.com/apps/#/register</a> 이동 (네이버 로그인 필요)</li>
      <li>애플리케이션 이름 입력 (예: morning-briefing)</li>
      <li>사용 API 에서 <strong>"검색"</strong> 체크</li>
      <li>환경 선택: <strong>WEB 설정</strong>, URL은 <span class="kbd">http://localhost</span> 입력</li>
      <li>등록 완료 후 <strong>Client ID / Client Secret</strong> 복사</li>
      <li>"🔑 시크릿" 탭에서 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 입력 후 저장</li>
    </ol>
    <p class="text-xs text-slate-400 mt-2">쿼터: 일 25,000회 (무료). 본 프로젝트는 하루 21회만 사용.</p>
  </details>

  <details class="border rounded-lg p-4">
    <summary class="font-medium cursor-pointer">Telegram Bot Token / Chat ID</summary>
    <ol class="list-decimal pl-5 mt-3 text-sm space-y-1 text-slate-700">
      <li>텔레그램 앱에서 <span class="kbd">@BotFather</span> 검색 후 대화 시작</li>
      <li><span class="kbd">/newbot</span> 입력 → 봇 이름 입력 → 봇 username 입력 (끝에 <span class="kbd">_bot</span>)</li>
      <li>BotFather가 보내주는 <strong>Token</strong> 복사 (예: <span class="kbd">1234567:AAE...</span>)</li>
      <li>방금 만든 봇을 검색해 대화창 열고 아무 메시지(<span class="kbd">/start</span> 등) 보내기</li>
      <li>브라우저에서 <span class="kbd">https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</span> 접속</li>
      <li>응답 JSON의 <span class="kbd">result[0].message.chat.id</span> 값 복사</li>
      <li>"🔑 시크릿" 탭에서 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 입력 후 저장</li>
      <li>"📡 채널" 탭에서 Telegram 활성화 + 테스트 전송 버튼 클릭</li>
    </ol>
  </details>

  <details class="border rounded-lg p-4">
    <summary class="font-medium cursor-pointer">Slack Incoming Webhook URL</summary>
    <ol class="list-decimal pl-5 mt-3 text-sm space-y-1 text-slate-700">
      <li><a class="text-blue-600 underline" href="https://api.slack.com/apps" target="_blank">api.slack.com/apps</a> 에서 <strong>Create New App</strong></li>
      <li><strong>From scratch</strong> 선택 → 앱 이름·워크스페이스 선택</li>
      <li>좌측 메뉴 <strong>Incoming Webhooks</strong> → 토글 On</li>
      <li>하단 <strong>Add New Webhook to Workspace</strong> → 브리핑 받을 채널 선택 → 허용</li>
      <li>생성된 <strong>Webhook URL</strong> 복사 (<span class="kbd">https://hooks.slack.com/services/…</span>)</li>
      <li>"🔑 시크릿" 탭에서 SLACK_WEBHOOK_URL 입력 후 저장</li>
      <li>"📡 채널" 탭에서 Slack 활성화 + 테스트 전송 버튼 클릭</li>
    </ol>
  </details>

  <details class="border rounded-lg p-4">
    <summary class="font-medium cursor-pointer">Claude Code GitHub App (Scheduled Agent 커밋 권한)</summary>
    <ol class="list-decimal pl-5 mt-3 text-sm space-y-1 text-slate-700">
      <li><a class="text-blue-600 underline" href="https://github.com/apps/claude" target="_blank">github.com/apps/claude</a> 에서 Install</li>
      <li><strong>morning-briefing</strong> 레포만 선택해 설치 (보안)</li>
      <li>추후 <span class="kbd">/schedule</span> 로 Routine 등록할 때 이 레포를 선택하면 자동 인증됨</li>
      <li>Routine 설정에서 <strong>Allow unrestricted branch pushes</strong> 반드시 ON (main 커밋용)</li>
    </ol>
  </details>
</section>

<script>
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);
let state = { config: null, env: null };

// ─── tabs ──────────────────────────
$$('.tab-btn').forEach(btn => btn.addEventListener('click', () => {
  $$('.tab-btn').forEach(b => b.classList.remove('active'));
  $$('.pane').forEach(p => p.classList.add('hidden'));
  btn.classList.add('active');
  $(`[data-pane="${btn.dataset.tab}"]`).classList.remove('hidden');
}));

// ─── toast ─────────────────────────
function toast(msg, ms = 2500) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  setTimeout(() => t.classList.add('hidden'), ms);
}

// ─── load ──────────────────────────
async function load() {
  const [cfg, env] = await Promise.all([
    fetch('/api/config').then(r => r.json()),
    fetch('/api/env').then(r => r.json()),
  ]);
  state.config = cfg;
  state.env = env;
  renderChannels();
  renderSecrets();
  renderKeywords();
  renderRanking();
  renderMisc();
}

// ─── channels ──────────────────────
function renderChannels() {
  $('#ch_telegram').checked = !!state.config.output?.channels?.telegram?.enabled;
  $('#ch_slack').checked    = !!state.config.output?.channels?.slack?.enabled;
}

// ─── secrets ───────────────────────
function renderSecrets() {
  const wrap = $('#envList');
  wrap.innerHTML = '';
  Object.entries(state.env).forEach(([key, info]) => {
    const row = document.createElement('div');
    row.className = 'grid grid-cols-[180px_1fr_auto] gap-3 items-center';
    row.innerHTML = `
      <label class="text-sm"><div class="font-medium">${key}</div><div class="text-xs text-slate-400">${info.desc}</div></label>
      <input data-envkey="${key}" type="password" autocomplete="off" placeholder="${info.is_set ? info.preview + ' (변경 시에만 입력)' : '미설정 — 값 입력'}" class="border rounded px-2 py-1 text-sm">
      <span class="text-xs ${info.is_set ? 'text-emerald-600' : 'text-slate-400'}">${info.is_set ? '✓ 설정됨' : '— 미설정'}</span>
    `;
    wrap.appendChild(row);
  });
}

// ─── keywords ──────────────────────
function renderKeywords() {
  const ks = state.config.naver_news?.keyword_search || {};
  $('#keyword_enabled').checked = !!ks.enabled;
  $('#per_keyword').value = ks.per_keyword ?? 3;
  $('#keyword_sort').value = ks.sort || 'date';
  const list = $('#keywordList');
  list.innerHTML = '';
  (ks.keywords || []).forEach((kw, idx) => list.appendChild(keywordRow(kw, idx)));
}
function keywordRow(kw, idx) {
  const row = document.createElement('div');
  row.className = 'grid grid-cols-[1fr_1fr_auto] gap-2';
  row.dataset.kwidx = idx;
  row.innerHTML = `
    <input data-field="term" value="${escapeAttr(kw.term || '')}" class="border rounded px-2 py-1 text-sm" placeholder="예: 금리">
    <input data-field="category" value="${escapeAttr(kw.category || '')}" class="border rounded px-2 py-1 text-sm" placeholder="예: 거시">
    <button class="text-red-500 hover:bg-red-50 px-2 rounded" onclick="this.parentElement.remove()">✕</button>
  `;
  return row;
}
$('#addKeyword').addEventListener('click', () => {
  $('#keywordList').appendChild(keywordRow({ term: '', category: '' }, -1));
});

// ─── ranking ───────────────────────
function renderRanking() {
  const r = state.config.naver_news?.ranking || {};
  $('#ranking_enabled').checked = !!r.enabled;
  $('#top_n').value = r.top_n ?? 10;
  const list = $('#pressList');
  list.innerHTML = '';
  (r.press_whitelist || []).forEach(name => list.appendChild(pressRow(name)));
}
function pressRow(name) {
  const row = document.createElement('div');
  row.className = 'grid grid-cols-[1fr_auto] gap-2';
  row.innerHTML = `
    <input data-field="name" value="${escapeAttr(name || '')}" class="border rounded px-2 py-1 text-sm" placeholder="예: 매일경제">
    <button class="text-red-500 hover:bg-red-50 px-2 rounded" onclick="this.parentElement.remove()">✕</button>
  `;
  return row;
}
$('#addPress').addEventListener('click', () => {
  $('#pressList').appendChild(pressRow(''));
});

// ─── misc ──────────────────────────
function renderMisc() {
  const s = state.config.schedule || {};
  $('#schedule_time').value = s.time_kst || '08:00';
  updateCron();
  $('#retention_days').value = state.config.dedupe?.retention_days ?? 30;
  $('#include_raw_lead').checked = !!state.config.output?.obsidian?.include_raw_lead;
}

// 한국 HH:MM → UTC cron 표현식 계산
function kstToUtcCron(timeKst) {
  const [h, m] = timeKst.split(':').map(Number);
  const utcHour = (h - 9 + 24) % 24;
  return `${m} ${utcHour} * * *`;
}
function updateCron() {
  const t = $('#schedule_time').value || '08:00';
  $('#schedule_cron').textContent = kstToUtcCron(t);
}
$('#schedule_time').addEventListener('input', updateCron);
$('#copyCron').addEventListener('click', async () => {
  const cron = $('#schedule_cron').textContent;
  await navigator.clipboard.writeText(cron);
  toast('📋 Cron 복사됨: ' + cron, 2000);
});

// ─── collect + validate ────────────
function collectConfig() {
  const cfg = JSON.parse(JSON.stringify(state.config));

  cfg.output = cfg.output || {};
  cfg.output.channels = cfg.output.channels || { telegram: {}, slack: {} };
  cfg.output.channels.telegram.enabled = $('#ch_telegram').checked;
  cfg.output.channels.slack.enabled = $('#ch_slack').checked;

  cfg.naver_news = cfg.naver_news || {};
  cfg.naver_news.keyword_search = cfg.naver_news.keyword_search || {};
  cfg.naver_news.keyword_search.enabled = $('#keyword_enabled').checked;
  cfg.naver_news.keyword_search.per_keyword = Number($('#per_keyword').value);
  cfg.naver_news.keyword_search.sort = $('#keyword_sort').value;
  cfg.naver_news.keyword_search.keywords = [...$$('#keywordList > div')].map(row => ({
    term: row.querySelector('[data-field="term"]').value.trim(),
    category: row.querySelector('[data-field="category"]').value.trim(),
  })).filter(k => k.term);

  cfg.naver_news.ranking = cfg.naver_news.ranking || {};
  cfg.naver_news.ranking.enabled = $('#ranking_enabled').checked;
  cfg.naver_news.ranking.top_n = Number($('#top_n').value);
  cfg.naver_news.ranking.press_whitelist = [...$$('#pressList > div')].map(row =>
    row.querySelector('[data-field="name"]').value.trim()
  ).filter(Boolean);

  cfg.schedule = cfg.schedule || {};
  cfg.schedule.time_kst = $('#schedule_time').value || '08:00';
  cfg.schedule.cron_utc = kstToUtcCron(cfg.schedule.time_kst);

  cfg.dedupe = cfg.dedupe || {};
  cfg.dedupe.retention_days = Number($('#retention_days').value);

  cfg.output.obsidian = cfg.output.obsidian || {};
  cfg.output.obsidian.include_raw_lead = $('#include_raw_lead').checked;

  return cfg;
}
function collectEnv() {
  const out = {};
  $$('input[data-envkey]').forEach(el => {
    if (el.value) out[el.dataset.envkey] = el.value;
  });
  return out;
}
function validateConfig(cfg) {
  const errors = [];
  const terms = cfg.naver_news.keyword_search.keywords.map(k => k.term);
  if (new Set(terms).size !== terms.length) errors.push('키워드에 중복이 있습니다.');
  const whitelist = cfg.naver_news.ranking.press_whitelist;
  if (new Set(whitelist).size !== whitelist.length) errors.push('언론사 화이트리스트에 중복이 있습니다.');
  return errors;
}

// ─── save all ──────────────────────
$('#saveAll').addEventListener('click', async () => {
  const cfg = collectConfig();
  const errors = validateConfig(cfg);
  if (errors.length) { toast('⚠️ ' + errors.join(' / '), 5000); return; }

  const envPatch = collectEnv();
  const autoCommit = $('#autoCommit').checked;

  const [r1, r2] = await Promise.all([
    fetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ config: cfg, auto_commit: autoCommit }) }).then(r => r.json()),
    Object.keys(envPatch).length
      ? fetch('/api/env', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(envPatch) }).then(r => r.json())
      : Promise.resolve({ ok: true, unchanged: true }),
  ]);

  if (r1.ok && r2.ok) {
    let msg = '✅ 저장 완료';
    if (r1.commit) msg += ` · ${r1.commit}`;
    if (r2.unchanged !== true) msg += ' · 시크릿 업데이트됨';
    toast(msg, 3500);
    state.config = cfg;
    await load();  // env 마스킹 상태 갱신
  } else {
    toast('❌ 저장 실패: ' + ((r1.error || '') + ' ' + (r2.error || '')), 5000);
  }
});

// ─── test sends ────────────────────
$('#testTelegram').addEventListener('click', async () => {
  toast('Telegram 테스트 중...');
  const r = await fetch('/api/test-telegram', { method: 'POST' }).then(r => r.json());
  toast(r.ok ? '✅ Telegram 전송 성공' : '❌ ' + (r.error || 'Telegram 실패'), 4000);
});
$('#testSlack').addEventListener('click', async () => {
  toast('Slack 테스트 중...');
  const r = await fetch('/api/test-slack', { method: 'POST' }).then(r => r.json());
  toast(r.ok ? '✅ Slack 전송 성공' : '❌ ' + (r.error || 'Slack 실패'), 4000);
});

function escapeAttr(s) {
  return String(s ?? '').replaceAll('&', '&amp;').replaceAll('"', '&quot;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}

load();
</script>
</div>
</body>
</html>
"""


# ─── test senders ──────────────────────────────────────────────────────

def test_telegram() -> tuple[bool, str]:
    env = read_env()
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정"
    try:
        import requests as _req
        now = datetime.now().strftime("%H:%M:%S")
        resp = _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": f"✅ *morning\\-briefing* 테스트 메시지 \\({now}\\)\n설정 UI에서 전송됨",
                "parse_mode": "MarkdownV2",
            },
            timeout=10,
        )
        if resp.ok:
            return True, "전송됨"
        return False, f"{resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, str(e)


def test_slack() -> tuple[bool, str]:
    env = read_env()
    url = env.get("SLACK_WEBHOOK_URL")
    if not url:
        return False, "SLACK_WEBHOOK_URL 미설정"
    try:
        import requests as _req
        now = datetime.now().strftime("%H:%M:%S")
        resp = _req.post(
            url,
            json={
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": "✅ morning-briefing 테스트"}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"설정 UI에서 {now} 전송됨"}},
                ],
            },
            timeout=10,
        )
        if resp.ok:
            return True, "전송됨"
        return False, f"{resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, str(e)


# ─── commit message generator ─────────────────────────────────────────

def diff_summary(old: dict[str, Any], new: dict[str, Any]) -> str:
    changes: list[str] = []
    old_kw = {k["term"] for k in old.get("naver_news", {}).get("keyword_search", {}).get("keywords", [])}
    new_kw = {k["term"] for k in new.get("naver_news", {}).get("keyword_search", {}).get("keywords", [])}
    if added := new_kw - old_kw:
        changes.append(f"키워드 추가({len(added)}): {', '.join(sorted(added))}")
    if removed := old_kw - new_kw:
        changes.append(f"키워드 제거({len(removed)}): {', '.join(sorted(removed))}")

    old_press = set(old.get("naver_news", {}).get("ranking", {}).get("press_whitelist", []))
    new_press = set(new.get("naver_news", {}).get("ranking", {}).get("press_whitelist", []))
    if added := new_press - old_press:
        changes.append(f"언론사 추가: {', '.join(sorted(added))}")
    if removed := old_press - new_press:
        changes.append(f"언론사 제거: {', '.join(sorted(removed))}")

    old_ch = old.get("output", {}).get("channels", {})
    new_ch = new.get("output", {}).get("channels", {})
    for name in ("telegram", "slack"):
        o = old_ch.get(name, {}).get("enabled", False)
        n = new_ch.get(name, {}).get("enabled", False)
        if o != n:
            changes.append(f"{name} {'활성화' if n else '비활성화'}")

    if not changes:
        return "config: 설정 업데이트"
    return "config: " + " · ".join(changes)


# ─── HTTP handler ──────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        # 콘솔에 깔끔하게
        sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] {fmt % args}\n")

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/config":
            try:
                self._send_json(200, read_config())
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return
        if self.path == "/api/env":
            self._send_json(200, mask_env(read_env()))
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/config":
            try:
                data = self._read_json()
                new_cfg = data.get("config")
                if not isinstance(new_cfg, dict):
                    self._send_json(400, {"ok": False, "error": "config 누락"})
                    return
                old_cfg = read_config()
                write_config(new_cfg)
                commit_msg = None
                if data.get("auto_commit"):
                    ok, out = git_commit_config(diff_summary(old_cfg, new_cfg))
                    commit_msg = out if ok else f"auto-commit 실패: {out}"
                self._send_json(200, {"ok": True, "commit": commit_msg})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/env":
            try:
                patch = self._read_json()
                if not isinstance(patch, dict):
                    self._send_json(400, {"ok": False, "error": "invalid body"})
                    return
                env = read_env()
                for k, v in patch.items():
                    if v:
                        env[k] = str(v)
                write_env(env)
                self._send_json(200, {"ok": True})
            except Exception as e:
                self._send_json(500, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/test-telegram":
            ok, msg = test_telegram()
            self._send_json(200, {"ok": ok, "error": None if ok else msg, "detail": msg})
            return

        if self.path == "/api/test-slack":
            ok, msg = test_slack()
            self._send_json(200, {"ok": ok, "error": None if ok else msg, "detail": msg})
            return

        self._send_json(404, {"error": "not found"})


# ─── main ──────────────────────────────────────────────────────────────

def main() -> int:
    if not CONFIG_PATH.exists():
        print(f"[config_ui] {CONFIG_PATH} 가 없습니다. 레포 루트에서 실행하세요.", file=sys.stderr)
        return 1

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"🌅 Morning Briefing 설정 UI: {url}")
    print("   (종료: Ctrl+C)\n")

    if os.environ.get("CONFIG_UI_NO_BROWSER") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
