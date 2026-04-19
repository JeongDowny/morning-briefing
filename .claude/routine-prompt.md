# Scheduled Agent 실행 프롬프트 — morning-briefing

이 파일 내용을 Claude Code Routines (`claude.ai/code/routines` 또는 `/schedule`) 의
Prompt 필드에 그대로 복사해 넣는다.

---

## 역할

`config/briefing.json` 의 `schedule.time_kst` 에 지정된 시각 (기본 08:00 KST) 에 이 레포에서 모닝 브리핑을 생성·전송·커밋한다.

**Cron 값**은 `config/briefing.json` 의 `schedule.cron_utc` 에서 확인할 수 있고, Routines 등록 시 이 값을 Trigger → Schedule 에 입력한다.

## 실행 단계 — 정확히 이 순서로

### 1. 수집 (Bash)

활성화된 소스만 자동으로 동작한다 (각 스크립트가 `enabled` 플래그를 스스로 확인해 스킵).

```bash
python scripts/collect_naver.py       # naver_news.ranking.enabled 확인 후 진행
python scripts/collect_openai.py      # dev_news.enabled 확인 후 진행
python scripts/collect_anthropic.py   # dev_news.enabled 확인 후 진행
python scripts/collect_threads.py     # threads.enabled 확인 후 진행
```

각 스크립트 완료 후 `collected/*.json` 이 생성됐는지 확인. 활성화된 소스 전체가 0건이면 구조 변경·네트워크 이슈 가능성 → 텔레그램/Slack 으로 실패 알림 후 **그 지점에서 멈춰라**.

### 2. 중복 제거 (Bash)

```bash
python scripts/manage_seen.py filter
```

`collected/filtered.json` 생성 확인.

### 3. 요약 (너가 직접)

`collected/filtered.json` 을 읽는다. 소스별 스키마가 다르므로 구분해서 처리:

- `naver_ranking`: `config/prompts/news-summary.md` 규칙 적용
- `openai_rss`, `anthropic_html`: `config/prompts/blog-summary.md` 규칙
- `threads_rsshub`: `config/prompts/threads-summary.md` 규칙

각 item 에 2~3줄 한국어 요약 생성 후 `collected/summarized.json` 으로 저장:

```json
{
  "summarized_at": "...",
  "date": "2026-04-17",
  "sources": [
    {
      "source": "naver_ranking",
      "items": [ { ..., "summary": "..." } ]
    }
  ]
}
```

### 4. Daily 노트 렌더링 (너가 직접)

`Daily/{YYYY-MM-DD}.md` 파일 생성. 활성화된 섹션만 포함:

```markdown
---
date: {YYYY-MM-DD}
tags: [daily, briefing]
---

# 🌅 모닝 브리핑 — {YYYY년 M월 D일 (요일)}

> 수집 기간: 전일 08:00 ~ 오늘 08:00 KST

## 📈 경제뉴스        ← naver_news.ranking.enabled=true 일 때만
### 네이버 경제 언론사 랭킹
1. **[제목](URL)** — 언론사
   - 🤖 요약
2. ...

## 🤖 AI / 개발 소식   ← dev_news.enabled=true 일 때만
### OpenAI
- **[제목](URL)**
  - 🤖 요약
  - 📄 *리드*

### Anthropic
- ...

## 🧵 Threads         ← threads.enabled=true 일 때만
### @swyx — AI 엔지니어링
- **[YYYY-MM-DD HH:MM](URL)**
  - 🤖 요약

---

## 💡 Keep

> 중요 항목 아래 `#keep` 태그 추가. 카테고리 태그(`#거시`, `#자산`, `#글로벌`, `#openai`, `#anthropic`, `#threads`, `#research`)는 자동 분류되어 붙어있다.
```

### 5. 메시지 전송 (Bash) — 활성화된 채널 모두로

```bash
# config.output.channels.telegram.enabled 확인 후
python scripts/send_telegram.py

# config.output.channels.slack.enabled 확인 후
python scripts/send_slack.py
```

실패해도 멈추지 말고 다음 단계로.

### 6. seen.json 갱신 (Bash)

```bash
python scripts/manage_seen.py update
```

### 7. 커밋 & 푸시 (너가 직접)

```bash
git add Daily/ data/seen.json
git commit -m "brief: {YYYY-MM-DD} 모닝 브리핑 자동 생성"
git push origin main
```

## 원칙

- **Briefing 발송은 무조건 진행**: 요약/렌더 중 일부 항목이 실패해도 나머지는 출력
- **고유명사 · 제품명 원문 유지** (GPT-X, Claude Opus, 삼성전자 등)
- **커밋 메시지는 `brief:` 접두어로 통일**
- **활성화된 모든 소스가 0건일 때는 실패 알림** 후 중단

## 환경변수 (Routine 설정에서 주입)

- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` — 키워드 검색 (M2) 에서 사용
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — Telegram 활성화 시
- `SLACK_WEBHOOK_URL` — Slack 활성화 시

> 로컬 테스트는 `python3 scripts/config_ui.py` 로 편집 UI를 열어 `.env` 에 주입. 프로덕션(Scheduled Agent)은 Claude Code Routines 환경 설정 UI에서 별도 주입.
