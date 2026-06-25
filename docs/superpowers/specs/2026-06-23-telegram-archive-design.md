# 텔레그램 원탭 아카이브 → Obsidian 설계

- 날짜: 2026-06-23 (개정: 2026-06-25, 검토 반영)
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
  → [신규 스텝] id 부여 + data/manifest-{날짜}.json 생성 → commit + push  (※ 발송 전에 push)
  → 텔레그램 발송: 항목마다 번호(1·2·3…) + 메시지 하단 [📥 1][📥 2]… 인라인 버튼 (callback_data = id)
  → commit: Daily/ , data/seen.json

[사용자] 폰/PC 텔레그램에서 브리핑 읽음 → 원하는 항목 번호의 [📥 N] 탭
  → Vercel 함수가 즉시 처리, 해당 버튼이 [✅ N] 으로 바뀜

[열람] Obsidian 에서 Archive/ 폴더, #archive 태그, 전문검색, 또는 Archive.md 인덱스 노트로 조회
```

읽기는 텔레그램, 저장은 텔레그램 원탭, 보관·열람은 Obsidian. Obsidian 에서 별도 체크 동작 없음.

## 3. 아키텍처 / 컴포넌트

### 3.1 데이터 흐름

| 단계 | 위치 | 산출물 |
|---|---|---|
| 수집·요약 | GitHub Actions (기존) | `collected/summarized.json` |
| id 부여 + manifest + **push** | 발송 직전 신규 스텝 | `data/manifest-{YYYY-MM-DD}.json` (원격 반영 완료) |
| 발송 + 번호 버튼 | `scripts/send_telegram.py` (수정) | 텔레그램 메시지 + 인라인 버튼 |
| 버튼 탭 처리 | `api/telegram.py` (신규, Vercel) | `Archive/*.md` 커밋 |
| 열람 | Obsidian (vault = repo) | 폴더/태그/검색/Dataview |

### 3.2 id 와 manifest

- **url 해석**: 항목 url 은 `originallink or link or url` 폴백 체인으로 구한다
  (`send_telegram.py:86` 의 기존 로직과 동일). 셋 다 비면 그 항목은 **버튼 제외**(아카이브 불가).
- **id 형식**: `{YYYYMMDD}-{hash8}` — `YYYYMMDD` = 발송일(KST), `hash8` = `sha1(url)` 앞 8자.
  예 `20260623-3f9a2b1c`. callback_data 64바이트 한계 안에 충분.
  같은 url → 같은 hash → dedup 키.
- **날짜 포맷 주의**: id 안은 `YYYYMMDD`(하이픈 없음), manifest 파일명은 `manifest-YYYY-MM-DD.json`.
  웹훅은 id 의 앞 8자를 `YYYY-MM-DD` 로 변환해 manifest 파일을 찾는다.
- **manifest 파일**: `data/manifest-{YYYY-MM-DD}.json`
  ```json
  {
    "date": "2026-06-23",
    "items": {
      "20260623-3f9a2b1c": {
        "title": "...",
        "url": "https://news.hada.io/topic?id=30756",
        "summary": "요약 문장",
        "source": "GeekNews"
      }
    }
  }
  ```
  - `source` 값은 항목의 `source_name` 필드에서 가져온다 (summarized.json 실제 필드명).
- **보관 정책**: 최근 N=14일치만 유지. manifest 생성 스텝에서 14일 초과 파일 삭제.
  만료된 버튼을 누르면 함수가 manifest 를 못 찾아 "만료됨" 응답.

### 3.3 텔레그램 발송 + 번호 버튼 (`scripts/send_telegram.py` 수정)

- 기존 섹션 분할 발송(`build_section_messages`) 유지. 한 메시지에 항목 여러 개 묶임.
- **인라인 키보드는 메시지 본문 중간에 못 박는다 — 메시지 하단 버튼 블록으로만 붙는다.**
  따라서 매핑을 위해:
  1. 각 항목 본문 줄 앞에 번호 prefix 를 붙인다: `1. • [제목](url)`, `2. • …`
  2. 그 메시지의 인라인 키보드에 항목별 버튼: `[📥 1]`, `[📥 2]` … (각 `callback_data` = 해당 id)
  3. 한 줄에 버튼 여러 개(예 4개씩 wrap) 배치 가능.
- 번호는 **메시지 단위로 리셋**(1부터). 버튼 텍스트의 번호 = 본문 번호와 일치.
- 발송은 메시지별 1회 `sendMessage` 호출에 `reply_markup` 동봉.
- 한 메시지 버튼 수는 항목 수만큼(섹션 분할로 보통 ≤ 한 메시지 4000자 내 항목). 텔레그램
  인라인 키보드 한도(메시지당 약 100버튼) 내라 문제 없음.

### 3.4 manifest 생성 + push 스텝 (워크플로, 발송 전)

- **발송보다 먼저** manifest 를 만들고 커밋·push 한다 (레이스/먹통 방지).
- 구현 택1:
  - (a) 별도 스크립트 `scripts/build_manifest.py` → 워크플로에서 send_telegram **앞** 스텝으로
    실행 후 즉시 `git add data/manifest-*.json && git commit && git push`.
  - (b) send_telegram 진입부에서 manifest 작성 후 자체 commit·push, 그 다음 발송.
- 권장 (a): 책임 분리. send_telegram 은 manifest 를 읽어 id·번호만 사용.
- push 실패 시 발송 중단(또는 경고) — manifest 없는 버튼은 의미 없으므로.

### 3.5 Vercel 함수 `api/telegram.py`

- 런타임: Python (repo 단일 언어 유지). Vercel Python Serverless Function (`@vercel/python`).
- 엔드포인트: `POST /api/telegram` (텔레그램 webhook 대상).
- 처리 순서:
  1. **인증**: 헤더 `X-Telegram-Bot-Api-Secret-Token` == env `WEBHOOK_SECRET`. 불일치 → 401.
  2. 업데이트 파싱: `callback_query` 만 처리 (그 외 200 무시).
     - `callback_query` 안에 chat_id·message_id 가 들어오므로 editMessageReplyMarkup 에 그대로 사용
       (메시지 id 별도 저장 불필요).
  3. `callback_data` 형식 검증: 정규식 `^\d{8}-[0-9a-f]{8}$`. 불일치 → answerCallbackQuery("잘못된 요청").
  4. id 앞 8자 → `YYYY-MM-DD` 변환 → `data/manifest-{날짜}.json` 을 GitHub raw 로 읽어 항목 조회.
     - manifest 없음/항목 없음 → answerCallbackQuery("⏳ 만료된 항목") 후 종료.
  5. **dedup**: `Archive/{date}-{hash8}.md` 존재를 GitHub Contents API (GET) 로 확인.
     - 이미 있음 → answerCallbackQuery("이미 저장됨") + 버튼 [✅ N] 수정 후 종료.
  6. 노트 마크다운 생성 → GitHub Contents API (PUT) 로 커밋.
     - **PUT 409(이미 존재/sha 충돌, 동시 탭 레이스)** → "이미 저장됨" 으로 동일 처리(멱등).
  7. answerCallbackQuery("✅ 아카이브됨") + editMessageReplyMarkup 으로 해당 버튼을 [✅ N] 으로 변경.
- env 변수 (Vercel):
  - `TELEGRAM_BOT_TOKEN` — answerCallbackQuery / editMessageReplyMarkup 호출용.
  - `GITHUB_TOKEN` — fine-grained PAT, 대상 repo `contents:write` 만. Archive 커밋 + manifest 읽기.
  - `WEBHOOK_SECRET` — webhook 검증 토큰.
  - `GITHUB_REPO` — `owner/repo`.

### 3.6 Archive 노트 형식

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

- `tags`: 항상 `archive` + 소스 slug (예 `geeknews`, `openai`). 소스 slug 는 `source_name` 을
  소문자·하이픈화(기존 `collect_rss.slugify` 와 동일 규칙). Dataview 필터용.
- frontmatter `title` 은 `"` 이스케이프 처리(제목에 따옴표 포함 가능).

### 3.7 `Archive.md` 인덱스 노트 (신규, repo 루트)

`Keeps.md` 의 Dataview 패턴 재사용. 한 번 만들어 두면 Dataview 가 자동 갱신.

(아래 코드펜스는 예시. 실제 파일에서는 정상 dataview 펜스로 작성.)

```
# 📂 아카이브

`#archive` 태그가 붙은 노트가 자동 집계됩니다. 텔레그램 브리핑의 [📥] 버튼으로 저장됩니다.

## 최근 30일
( dataview: FROM #archive WHERE date >= today-30d  TABLE source, date  SORT date DESC )

## 소스별
( dataview: FROM #archive GROUP BY source  TABLE rows.file.link, rows.date )

## 전체 (최신순)
( dataview: FROM #archive  TABLE source, date  SORT date DESC )
```

## 4. 변경 대상 정리

| # | 파일 | 변경 |
|---|---|---|
| 1 | `scripts/build_manifest.py` | 신규 — id 부여, `data/manifest-{날짜}.json` 생성, 14일 정리 |
| 2 | `scripts/send_telegram.py` | manifest 읽어 항목 번호 + 하단 번호 버튼 인라인 키보드 |
| 3 | `api/telegram.py` | 신규 — Vercel webhook 함수 |
| 4 | `vercel.json` | 신규 — Python 함수 라우팅 설정 |
| 5 | `Archive.md` | 신규 — Dataview 인덱스 노트 |
| 6 | `.github/workflows/daily-brief.yml` | manifest 스텝(발송 전, 커밋·push 포함) 추가 |
| 7 | `Archive/` | 신규 폴더 (`.gitkeep`) |
| 8 | (1회 수동) | Vercel 배포, env 4종 설정, 텔레그램 setWebhook(secret_token) 등록 |

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
| manifest/항목 없음 (만료·미push) | answerCallbackQuery("⏳ 만료된 항목") |
| Archive 파일 이미 존재 (GET) | answerCallbackQuery("이미 저장됨") + 버튼 [✅ N] |
| PUT 409 (동시 탭 레이스) | "이미 저장됨" 으로 멱등 처리 |
| GitHub API 기타 실패 | answerCallbackQuery("저장 실패, 잠시 후 재시도") + 함수 로그 |
| manifest push 실패 (cron) | 발송 중단/경고 — 버튼 없는 브리핑보다 낫게 결정 |

## 7. 테스트

- `build_manifest.py` / `api/telegram.py` 의 순수 로직을 외부 호출과 분리해 `--self-check`(assert):
  - id = `YYYYMMDD-sha1(url)[:8]` → 형식 일치, 같은 url 재계산 시 동일 id (dedup 키 안정).
  - url 폴백 체인(`originallink→link→url`), 셋 다 빈 항목 → 버튼/manifest 제외.
  - id → manifest 파일명 날짜 변환(`YYYYMMDD`→`YYYY-MM-DD`) 정확.
  - 잘못된 secret → 401, 잘못된 callback_data → 거부.
  - manifest 항목 → Archive 마크다운 변환: frontmatter/H1/태그/링크 정확, 제목 따옴표 이스케이프.
- GitHub API·텔레그램 API 호출은 모킹하거나 self-check 범위 제외 (네트워크 비의존).

## 8. 미해결/후속

- 번호 버튼 방식에서 한 메시지 항목이 매우 많으면 버튼 그리드가 길어질 수 있음 — 섹션 분할
  4000자 한도로 자연히 제한되나, 구현 시 한 메시지 항목 상한(예 ≤ 20) 확인.
- manifest 보관 N=14일은 초기값. 실제 사용 패턴 보고 조정.
- 발송 전 manifest push 로 cron 1회에 git push 가 2번(manifest, Daily) 발생 — concurrency
  그룹(`daily-brief`) 내라 충돌 없음. push 사이 원격 변경 가능성 낮음.
