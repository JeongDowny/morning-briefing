# Scheduled Agent 실행 프롬프트 — morning-briefing-economy

이 파일 내용을 Claude Code Routines (`claude.ai/code/routines` 또는 `/schedule`) 의
Prompt 필드에 그대로 복사해 넣는다.

---

## 역할

`config/briefing.json` 의 `schedule.time_kst` 에 지정된 시각 (기본 08:00 KST) 에 이 레포에서 모닝 브리핑을 생성·전송·커밋한다.

**Cron 값** 은 `config/briefing.json` 의 `schedule.cron_utc` 에서 확인할 수 있고, Routines 등록 시 이 값을 Trigger → Schedule 에 입력한다.

## 실행 단계 — 정확히 이 순서로

### 1. 수집 (Bash)

```bash
python scripts/collect_naver.py
```

완료 후 `collected/naver.json` 이 생성됐는지 확인. 항목 0개면 네이버 HTML 구조 변경 가능성 → 텔레그램으로 실패 알림 후 **그 지점에서 멈춰라**.

> **M2 에서 추가**: `python scripts/collect_naver.py --keyword-search` (Open API 키워드 검색)

### 2. 중복 제거 (Bash)

```bash
python scripts/manage_seen.py filter
```

`collected/filtered.json` 생성 확인.

### 3. 요약 (너가 직접)

`collected/filtered.json` 을 읽는다. 구조는:

```json
{
  "sources": [
    {
      "source": "naver_ranking",
      "items": [ { "rank": 1, "title": "...", "url": "...", "press": "...", "lead": null, ... } ]
    }
  ]
}
```

각 `item` 에 대해 `config/prompts/news-summary.md` 의 규칙을 엄격히 적용해 2~3줄 한국어 요약을 생성한다.

그 결과를 아래 구조의 `collected/summarized.json` 으로 저장:

```json
{
  "summarized_at": "2026-04-17T08:02:15+09:00",
  "date": "2026-04-17",
  "sources": [
    {
      "source": "naver_ranking",
      "items": [
        {
          "rank": 1,
          "title": "...",
          "url": "...",
          "press": "...",
          "lead": null,
          "summary": "...",
          "category": "랭킹",
          "tags": ["경제", "랭킹"]
        }
      ]
    }
  ]
}
```

### 4. Daily 노트 렌더링 (너가 직접)

`Daily/{YYYY-MM-DD}.md` 파일을 생성한다. 오늘 날짜(KST)를 파일명으로 사용.

템플릿:

```markdown
---
date: {YYYY-MM-DD}
tags: [daily, briefing]
---

# 🌅 모닝 브리핑 — {YYYY년 M월 D일 (요일)}

> 수집 기간: 전일 08:00 ~ 오늘 08:00 KST
> 총 수집: 경제뉴스 N건

## 📈 경제뉴스

### 네이버 경제면 랭킹

1. **[제목](URL)** — 언론사
   - 🤖 요약문
   - (리드 있으면) 📄 *원문 리드...*

2. ...

---

## 💡 Keep

> 중요한 항목을 발견하면 그 항목 아래에 `#keep` 태그를 추가하세요.
> 예: `- 이 기사 중요 #keep #거시`
> `Keeps.md` 에 자동 집계됩니다.
```

### 5. 메시지 전송 (Bash) — 활성화된 채널 모두로

`config/briefing.json` 의 `output.channels` 중 `enabled: true` 인 채널에 대해서만 전송:

```bash
# Telegram 활성화 시
python scripts/send_telegram.py

# Slack 활성화 시
python scripts/send_slack.py
```

양쪽 다 활성화면 둘 다 실행. 실패해도 멈추지 말고 다음 단계로 — 전송 실패는 로그에 기록되지만 브리핑 커밋은 진행.

### 6. seen.json 갱신 (Bash)

```bash
python scripts/manage_seen.py update
```

### 7. 커밋 & 푸시 (너가 직접)

`Daily/` 의 신규 노트와 `data/seen.json` 변경분을 커밋한다.

```bash
git add Daily/ data/seen.json
git commit -m "brief: {YYYY-MM-DD} 모닝 브리핑 자동 생성"
git push origin main
```

## 원칙

- **Briefing 발송은 무조건 진행**: 요약/렌더 중 일부 항목이 실패해도 나머지는 출력
- **No Evidence = No Claim**: 요약에 추측·전망·출처 불명 주장 넣지 말 것
- **커밋 메시지는 `brief:` 접두어로 통일** (나중에 git log 필터링 편함)
- **수집 0건일 때는 텔레그램으로 에러 알림** 후 중단 (잘못된 빈 브리핑 발송 방지)

## 환경변수 (Routine 설정에서 주입)

- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` (M1 미사용, M2부터)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (Telegram 활성화 시)
- `SLACK_WEBHOOK_URL` (Slack 활성화 시)

> 로컬 테스트는 `python3 scripts/config_ui.py` 로 편집 UI를 열어 `.env` 에 주입. 프로덕션(Scheduled Agent)은 Claude Code Routines 환경 설정 UI에서 별도 주입.
