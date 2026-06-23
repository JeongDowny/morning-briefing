# 텔레그램 원탭 아카이브 → Obsidian 설계

- 날짜: 2026-06-23
- 상태: 설계 확정 (구현 전)

## 1. 목적

매일 모닝 브리핑을 텔레그램으로 받는다. 그중 보관하고 싶은 항목을 **텔레그램에서 버튼 한 번**으로
아카이브하면, repo(= Obsidian vault) 의 `Archive/` 폴더에 **개별 Obsidian 노트 1개**로 영구 저장된다.
나중에 Obsidian 에서 폴더·태그·검색·Dataview 인덱스로 꺼내본다.

핵심 제약: 현재 시스템은 GitHub Actions cron 배치라 상시 서버가 없다. 텔레그램 인라인 버튼 콜백을
받으려면 상시 HTTP 엔드포인트가 필요하므로, **Vercel 서버리스 함수 1개**를 webhook 으로 둔다.
별도 DB 는 두지 않는다 — **repo 자체가 저장소**다 (GitHub Contents API 로 노트를 커밋).

## 2. 사용자 흐름 (UX)

```
[매일 08:00 KST] GitHub Actions cron
  collect → filter → summarize
  → 각 항목에 id 부여 + data/manifest-{날짜}.json 생성 (id → 제목·url·요약·소스·날짜)
  → 텔레그램 발송: 각 항목 아래 [📥 아카이브] 인라인 버튼 (callback_data = id)
  → commit: Daily/ , data/seen.json , data/manifest-*.json

[사용자] 폰/PC 텔레그램에서 브리핑 읽음 → 원하는 항목 [📥 아카이브] 탭
  → Vercel 함수가 즉시 처리, 버튼이 [✅ 저장됨] 으로 바뀜

[열람] Obsidian 에서 Archive/ 폴더, #archive 태그, 전문검색, 또는 Archive.md 인덱스 노트로 조회
```

읽기는 텔레그램, 저장은 텔레그램 원탭, 보관·열람은 Obsidian. Obsidian 에서 별도 체크 동작 없음.

## 3. 아키텍처 / 컴포넌트

### 3.1 데이터 흐름

| 단계 | 위치 | 산출물 |
|---|---|---|
| 수집·요약 | GitHub Actions (기존) | `collected/summarized.json` |
| id 부여 + manifest | 발송 직전 (신규 로직) | `data/manifest-{YYYY-MM-DD}.json` |
| 발송 + 버튼 | `scripts/send_telegram.py` (수정) | 텔레그램 메시지 + 인라인 버튼 |
| 버튼 탭 처리 | `api/telegram.py` (신규, Vercel) | `Archive/*.md` 커밋 |
| 열람 | Obsidian (vault = repo) | 폴더/태그/검색/Dataview |

### 3.2 id 와 manifest

- **id 형식**: `{YYYYMMDD}-{hash8}` — `hash8` = `sha1(url)` 앞 8자. 예 `20260623-3f9a2b1c`.
  - callback_data 64바이트 한계 안에 충분히 들어감.
  - 같은 url → 같은 id → 자연스러운 dedup 키.
- **manifest 파일**: `data/manifest-{YYYY-MM-DD}.json`
  ```json
  {
    "date": "2026-06-23",
    "items": {
      "20260623-3f9a2b1c": {
        "title": "...",
        "url": "https://news.hada.io/topic?id=30756",
        "summary": "🤖 요약 문장",
        "source": "GeekNews",
        "date": "2026-06-23"
      }
    }
  }
  ```
- **보관 정책**: 최근 N=14일치만 유지. 발송 단계에서 14일 초과 manifest 파일 삭제. 만료된 버튼을
  누르면 함수가 manifest 를 못 찾아 "만료됨" 응답.

### 3.3 Vercel 함수 `api/telegram.py`

- 런타임: Python (repo 단일 언어 유지). Vercel Python Serverless Function.
- 엔드포인트: `POST /api/telegram` (텔레그램 webhook 대상).
- 처리 순서:
  1. **인증**: 요청 헤더 `X-Telegram-Bot-Api-Secret-Token` == env `WEBHOOK_SECRET` 검증. 불일치 → 401.
  2. 업데이트 파싱: `callback_query` 만 처리 (그 외 200 무시).
  3. `callback_data` = id → 날짜 추출 → `data/manifest-{날짜}.json` 을 GitHub raw 로 읽어 항목 조회.
     - manifest 없음/항목 없음 → answerCallbackQuery("⏳ 만료된 항목") 후 종료.
  4. **dedup**: `Archive/{date}-{hash8}.md` 존재 여부를 GitHub Contents API (GET) 로 확인.
     - 이미 있음 → answerCallbackQuery("이미 저장됨") + 버튼 [✅ 저장됨] 으로 수정 후 종료.
  5. 노트 마크다운 생성 → GitHub Contents API (PUT) 로 커밋.
  6. answerCallbackQuery("✅ 아카이브됨") + editMessageReplyMarkup 으로 해당 버튼을 [✅ 저장됨] 으로 변경.
- env 변수 (Vercel):
  - `TELEGRAM_BOT_TOKEN` — answerCallbackQuery / editMessageReplyMarkup 호출용.
  - `GITHUB_TOKEN` — fine-grained PAT, 대상 repo `contents:write` 만. Archive 커밋 + manifest 읽기.
  - `WEBHOOK_SECRET` — webhook 검증 토큰.
  - `GITHUB_REPO` — `owner/repo`.

### 3.4 `scripts/send_telegram.py` 수정

- 발송 직전: summarized 항목마다 id 계산 → `data/manifest-{날짜}.json` 작성 → 오래된 manifest 정리.
- 메시지의 각 항목 아래 인라인 키보드 1행: `[{"text": "📥 아카이브", "callback_data": id}]`.
  - 현재 split_by_section 발송 유지. 한 메시지에 여러 항목 → 항목마다 버튼 행 추가.
  - 텔레그램 인라인 키보드는 메시지 단위라, 메시지 본문 항목 순서와 버튼 행 순서를 일치시킨다.
- 발송 실패해도 manifest 는 이미 커밋됨 (재발송 시 동일 id 유지).

### 3.5 Archive 노트 형식

파일: `Archive/{YYYY-MM-DD}-{hash8}.md` (한글 제목 파일명 회피, 제목은 frontmatter + H1 에 보존)

```markdown
---
title: "Flock 기반 경찰서장들의 여성 스토킹 사례가 영장 필요성을 보여줌"
date: 2026-06-23
source: GeekNews
url: https://news.hada.io/topic?id=30756
tags: [archive, geeknews]
---

# Flock 기반 경찰서장들의 여성 스토킹 사례가 영장 필요성을 보여줌

> 📂 GeekNews · 2026-06-23 아카이브

🤖 <요약>

🔗 [원문 보기](https://news.hada.io/topic?id=30756)
```

- `tags`: 항상 `archive` + 소스 slug (예 `geeknews`, `openai`). Dataview 필터용.
- frontmatter `date`/`source`/`url`/`title` 가 인덱스·정렬·중복판단의 기준.

### 3.6 `Archive.md` 인덱스 노트 (신규, repo 루트)

`Keeps.md` 의 Dataview 패턴 재사용. 한 번 만들어 두면 Dataview 가 자동 갱신 — 관리 불필요.

```markdown
# 📂 아카이브

`#archive` 태그가 붙은 노트가 자동 집계됩니다. 텔레그램 브리핑에서 [📥 아카이브] 버튼으로 저장됩니다.

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
```

(이 spec 안의 dataview 코드펜스는 예시. 실제 파일에서는 정상 ```dataview 펜스로 작성.)

## 4. 변경 대상 정리

| # | 파일 | 변경 |
|---|---|---|
| 1 | `scripts/send_telegram.py` | id 부여, manifest 생성/정리, 항목별 인라인 버튼 |
| 2 | `api/telegram.py` | 신규 — Vercel webhook 함수 |
| 3 | `vercel.json` | 신규 — Python 함수 라우팅 설정 |
| 4 | `Archive.md` | 신규 — Dataview 인덱스 노트 |
| 5 | `.github/workflows/daily-brief.yml` | commit 경로에 `data/manifest-*.json` 추가 |
| 6 | `Archive/` | 신규 폴더 (`.gitkeep` 또는 첫 노트 생성 시) |
| 7 | (1회 수동) | Vercel 배포, env 4종 설정, 텔레그램 setWebhook 등록 |

폐기: Obsidian 체크박스 / render_daily 체크박스화 — 사용 안 함 (브리핑은 Obsidian 안 거침).

## 5. 보안

- **webhook 검증**: 모든 요청에서 `X-Telegram-Bot-Api-Secret-Token` 헤더를 `WEBHOOK_SECRET` 과 비교.
  불일치 시 401. setWebhook 시 `secret_token` 파라미터로 등록.
- **최소권한 토큰**: `GITHUB_TOKEN` 은 대상 repo 한 곳, `contents` 읽기/쓰기만 가진 fine-grained PAT.
- **시크릿 보관**: Vercel 환경변수에만. repo·코드에 하드코딩 금지.
- **입력 검증**: callback_data 형식(`^\d{8}-[0-9a-f]{8}$`) 정규식 검증 후 사용. 경로 조작 차단.

## 6. 에러 처리

| 상황 | 처리 |
|---|---|
| webhook secret 불일치 | 401, 본문 없음 |
| callback_data 형식 불량 | answerCallbackQuery("잘못된 요청") |
| manifest/항목 없음 (만료) | answerCallbackQuery("⏳ 만료된 항목") |
| Archive 파일 이미 존재 | answerCallbackQuery("이미 저장됨") + 버튼 [✅] |
| GitHub API 실패 | answerCallbackQuery("저장 실패, 잠시 후 재시도") + 함수 로그 |
| 텔레그램 발송 실패 (cron) | continue-on-error 유지, manifest 는 이미 커밋됨 |

## 7. 테스트

- `api/telegram.py` 의 순수 로직(인증·callback_data 검증·노트 마크다운 생성·id 계산)을 외부 호출과
  분리해 `--self-check`(assert 기반)으로 검증:
  - id = sha1(url) 앞8 + 날짜 → 형식 일치, 같은 url 재계산 시 동일 id (dedup 키 안정성).
  - 잘못된 secret → 401 경로.
  - 잘못된 callback_data 형식 → 거부.
  - manifest 항목 → Archive 마크다운 변환: frontmatter/H1/태그/링크 정확.
- GitHub API·텔레그램 API 호출은 모킹하거나 self-check 범위에서 제외 (네트워크 비의존).

## 8. 미해결/후속

- 텔레그램 인라인 키보드는 메시지당 버튼 수 제한이 있으므로, split_by_section 발송에서 한 메시지에
  항목이 너무 많으면 메시지를 더 잘게 쪼갠다 (구현 시 항목 수 상한 확인).
- manifest 보관 N=14일은 초기값. 실제 사용 패턴 보고 조정.
