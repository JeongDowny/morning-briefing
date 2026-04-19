# morning-briefing

> 매일 아침 경제뉴스·AI 개발 동향을 자동 수집·요약해서 Obsidian vault 와 Telegram/Slack 으로 전달하는 GitHub Actions 기반 파이프라인

출근 전 20분에 필요한 정보만 모아 Claude 가 아닌 Gemini (무료) 가 한국어로 2~3줄 요약해준다. 레포 폴더 자체가 Obsidian vault 로 동작해서 중요한 항목은 `#keep` 태그로 바로 북마크할 수 있고, 랩탑이 꺼져 있어도 GitHub Actions 가 정해진 시각에 알아서 돌려준다.

## 만들게 된 이유

매일 아침 20분, 커피 마시면서 뉴스·블로그를 대충 훑고 출근하고 싶은데 막상 열어보면 —

- 경제뉴스 사이트는 **연예·사회 기사가 앞에 섞여 있어서** 거르느라 시간이 가고
- AI 랩·블로그 (OpenAI · Anthropic · DeepMind · Hugging Face · 개인 블로그...) 는 **사이트 10군데 돌아다니기 귀찮고**
- 원문이 영어면 **아침에 머리 풀 가동** 되는 게 피곤하고

그래서 매일 아침 8시에 알아서 수집·요약·전송해주는 파이프라인을 얹었다. 개인용이지만 필요한 사람 fork 해서 쓰라고 OSS 로 공개.

## 주요 기능

- **경제뉴스 수집** — 네이버 오픈 API 로 관심 키워드 (금리·환율·물가·부동산·코스피·연준·나스닥 등) 기반 최근 24h 기사
- **AI 랩·블로그 RSS** — OpenAI · Anthropic · Google DeepMind · Hugging Face · GitHub Blog + 개인 블로그 (Simon Willison · swyx · Karpathy · Lilian Weng · Nathan Lambert). 새 소스는 `config/briefing.json` 에 한 줄만 추가
- **Gemini 요약** — 소스별 배치 호출로 한국어 2~3줄, 영문 제목은 한국어 번역 병기. 무료 티어로 월 0원
- **Obsidian vault** — 레포 = vault, `Daily/YYYY-MM-DD.md` 자동 커밋, `#keep` 태그 → `Keeps.md` Dataview 집계
- **Telegram / Slack** — 섹션별 분할 메시지, 활성화된 채널만 전송
- **로컬 편집 UI** — `python3 scripts/config_ui.py` 로 브라우저에서 키워드·소스·시크릿 편집

## 동작 예시

매일 08:00 KST 에 이런 Daily 노트가 자동으로 레포에 커밋된다.

```markdown
# 🌅 모닝 브리핑 — 2026년 04월 19일 (일)

> 수집 기간: 전일 08:00 ~ 오늘 08:00 KST · 총 23건

## 📈 경제뉴스
### 네이버 경제 뉴스
- **[원달러 환율 1,380 돌파](URL)** — 한국경제
  - 🤖 원달러 환율이 전일 대비 6.2원 오른 1,381.4원에 마감, 3개월 만에 최고치.
    미 고용지표 호조로 달러 강세가 재개된 영향. 외국인 자금 유출 우려 확대.

## 🤖 AI / 개발 소식
### Anthropic
- **[Introducing Claude Opus 4.7](URL)** — Anthropic
  - ▸ *Claude Opus 4.7 공개*
  - 🤖 Anthropic 이 Opus 4.7 을 4/16 공개. 코딩·에이전트·비전·다단계 작업 성능이
    향상되고 이전 Opus 대비 정확도·일관성에서 개선을 보였다고 밝혔다.

### Simon Willison
- **[Changes in the system prompt between Claude Opus 4.6 and 4.7](URL)** — Simon Willison
  - ▸ *Claude Opus 4.6 ↔ 4.7 시스템 프롬프트 변경 사항*
  - 🤖 Anthropic 의 시스템 프롬프트 아카이브에서 Opus 4.7 업데이트 내역 분석.
    Simon 이 Claude Code 로 Git 타임라인화해서 diff 확인 가능하게 만듦.
```

Telegram 으로는 섹션별 3개 메시지 푸시 알림. 핸드폰에서 빠르게 훑고, 출근해서 모니터로 Obsidian 열어 깊이 읽는 흐름.

## 요구사항

- GitHub 계정 (public 레포 Actions 월 2,000분 무료)
- Python 3.11 이상 (로컬 편집 UI · 수동 실행용)
- [Google Gemini API Key](https://aistudio.google.com/apikey) — 무료 티어, 카드 등록 불필요
- Telegram Bot 또는 Slack Incoming Webhook (발송 채널)
- (선택) 네이버 개발자 Client ID/Secret — 경제 키워드 검색 쓸 때

## 설치

### 1. Fork & clone

```bash
git clone https://github.com/<your-username>/morning-briefing.git
cd morning-briefing
pip install requests beautifulsoup4 feedparser pytz google-genai
```

### 2. 설정 UI

```bash
python3 scripts/config_ui.py
```

브라우저 `http://localhost:8765` 자동 오픈. 탭:

- **채널** — Telegram / Slack 활성화 + 테스트 전송
- **시크릿** — `.env` 에 토큰 저장 (gitignore, 표시/숨김 토글)
- **네이버 랭킹** — 경제지 화이트리스트
- **경제 키워드** — 수집 키워드 추가/삭제
- **개발소식** — dev_news.sources 확인 (직접 편집은 `config/briefing.json`)
- **기타** — 발송 시각 (KST) → UTC cron 자동 계산 + 워크플로 YAML 동기화
- **GitHub Actions 등록** — Secrets 페이지 링크 + 각 값 복사 버튼
- **발급 가이드** — Gemini · Telegram · Slack · GitHub App 단계별 안내

### 3. GitHub Secrets 등록

UI 의 **GitHub Actions 등록** 탭 → 각 시크릿 "값 복사" 버튼 → GitHub 레포 Settings → Secrets and variables → Actions → New repository secret:

- `GEMINI_API_KEY` (필수)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (Telegram 쓸 때)
- `SLACK_WEBHOOK_URL` (Slack 쓸 때)
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` (경제 키워드 검색 쓸 때)

### 4. 첫 실행 확인

`.github/workflows/daily-brief.yml` 이 매일 08:00 KST 에 자동 실행. 첫 검증은 Actions 탭 → **Daily Brief** → **Run workflow** 버튼.

## 로컬 수동 실행

CI 없이 직접 돌려보고 싶을 때:

```bash
set -a; source .env; set +a

python3 scripts/collect_naver.py       # 경제뉴스
python3 scripts/collect_rss.py         # 모든 RSS 소스 (10+ 개)
python3 scripts/collect_anthropic.py   # Anthropic HTML
python3 scripts/manage_seen.py filter  # 지난 30일 중복 제거
python3 scripts/summarize.py           # Gemini 요약
python3 scripts/render_daily.py        # Daily/YYYY-MM-DD.md 생성
python3 scripts/send_telegram.py       # 전송
python3 scripts/manage_seen.py update  # seen.json 갱신
```

## 저장 구조

```
.
├── Daily/                      ← 일일 브리핑 노트 (자동 커밋)
│   ├── 2026-04-18.md
│   └── 2026-04-19.md
│
├── Keeps.md                    ← #keep 태그 Dataview 집계
│
├── config/
│   ├── briefing.json           ← 모든 설정 (UI 가 편집)
│   └── prompts/
│       ├── news-summary.md     ← 경제뉴스 요약 규칙
│       ├── blog-summary.md     ← AI 블로그 요약 규칙
│       └── threads-summary.md
│
├── scripts/
│   ├── config_ui.py            ← 로컬 편집 UI (stdlib http.server)
│   ├── collect_naver.py        ← 네이버 키워드 검색 + 랭킹
│   ├── collect_rss.py          ← 범용 RSS (10+ 소스 자동 순회)
│   ├── collect_anthropic.py    ← Anthropic /news HTML 스크래핑
│   ├── collect_threads.py      ← Threads (RSSHub 차단, 비활성)
│   ├── manage_seen.py          ← 중복 제거 + seen.json 관리
│   ├── summarize.py            ← Gemini 호출 (소스별 배치)
│   ├── render_daily.py         ← Daily MD 생성
│   ├── send_telegram.py
│   └── send_slack.py
│
├── data/seen.json              ← 중복 방지 상태 (30일 유지)
├── .github/workflows/daily-brief.yml   ← GitHub Actions 파이프라인
└── .claude/                    ← Claude Code CLI 설정 (로컬 개발용)
```

### Daily 노트

파일명: `Daily/YYYY-MM-DD.md`. 섹션 — **📈 경제뉴스 · 🤖 AI / 개발 소식 · 🧵 Threads (현재 비활성)**. 중요 항목 아래에 `#keep` 태그를 붙이면 `Keeps.md` 에 카테고리별 (`#거시`, `#자산`, `#글로벌`, `#openai`, `#anthropic` 등) 로 자동 집계.

### Obsidian 연동

레포 폴더를 그대로 vault 로 열면 `Daily/` · `Keeps.md` 가 바로 보인다.

1. [Obsidian](https://obsidian.md) 설치 → "Open folder as vault" → 이 레포 폴더
2. Community plugin:
   - **Obsidian Git** — 15분 interval auto pull (Actions 가 push 한 최신 브리핑 자동 반영)
   - **Dataview** — `Keeps.md` 집계
3. 출근해서 `Daily/오늘날짜.md` 열고 읽으며 `#keep` 태그 추가

## 알려진 제약

- **Anthropic 은 공식 RSS 가 없어** `/news` 페이지 Next.js DOM 을 파싱한다. 사이트 구조가 바뀌면 `scripts/collect_anthropic.py` 의 선택자 업데이트가 필요하다.
- **Threads 수집 불가** — RSSHub 공용 인스턴스(`rsshub.app`) 가 2026-04 부로 production 접근을 차단했다. Self-host 전에는 안 돈다. 대체로 각 인물의 블로그 RSS (Simon Willison · Karpathy bearblog · Latent Space · Interconnects · Lilian Weng) 를 `dev_news.sources` 에 추가해 커버한다.
- **Gemini 2.5-flash 무료 티어 한도는 일 20회** 요청이다. 프로덕션 (일 3~4회) 엔 충분하지만 로컬 테스트를 여러 번 돌리면 금방 소진된다. 다음날 자동 리셋.

## 개발

설정 UI 는 외부 의존성 없는 순수 stdlib `http.server` 위에서 동작한다. HTML/CSS/JS 는 `config_ui.py` 에 인라인.

```bash
pip install requests beautifulsoup4 feedparser pytz google-genai

# 각 수집기·요약기·전송기 독립 실행 가능
python3 scripts/collect_rss.py         # 10+ RSS 소스 한 번에
python3 scripts/config_ui.py           # UI 서버 → http://localhost:8765
```

새 RSS 소스 추가는 `config/briefing.json` 의 `dev_news.sources` 배열에 한 줄 추가하면 끝. 코드 수정 불필요.

설계·리팩터 히스토리는 [`morning-briefing-plan.md`](./morning-briefing-plan.md) 참조 (v1: 매크로 분석 → v2: 단일 레포 + 프로필 → v3: Routines → GitHub Actions · Claude API → Gemini).

## 라이선스

MIT.
