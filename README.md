# morning-briefing

매일 아침 경제뉴스·AI 개발 동향·Threads 팔로잉 포스트를 자동 수집·요약해서 Obsidian vault 와 Slack/Telegram 으로 전달하는 개인용 자동화.

세 가지 프로필 중 골라서 사용합니다.

- **경제만** — 네이버 경제 전문지 랭킹 수집
- **개발만** — OpenAI · Anthropic 공식 블로그 + Threads 계정
- **전체** — 위 둘 다

수집 · 요약 · 전송은 GitHub Actions 가 정해진 시각에 실행합니다. 랩탑 상태와 무관하게 동작합니다.

## 동작 방식

1. `.github/workflows/daily-brief.yml` 의 cron 이 지정된 시각(UTC) 에 트리거됩니다.
2. `config/briefing.json` 의 `enabled` 플래그에 따라 활성화된 소스만 수집:
   - `scripts/collect_naver.py` — 네이버 "많이 본 뉴스" 랭킹 (경제 전문 언론사 whitelist 필터링)
   - `scripts/collect_openai.py` — OpenAI 공식 RSS
   - `scripts/collect_anthropic.py` — Anthropic `/news` HTML 스크래핑 (공식 RSS 없음)
   - `scripts/collect_threads.py` — RSSHub 경유 Threads 계정별 피드
3. `scripts/manage_seen.py filter` 가 지난 30일 이내 이미 노출된 항목 제거.
4. `scripts/summarize.py` 가 Google Gemini API 로 각 항목을 한국어 2~3줄로 요약 (기본 `gemini-2.0-flash`, 무료 티어).
5. `scripts/render_daily.py` 가 `Daily/YYYY-MM-DD.md` 생성.
6. `scripts/send_telegram.py` · `scripts/send_slack.py` 중 시크릿이 설정된 쪽이 섹션별 메시지로 전송.
7. 신규 노트와 `data/seen.json` 이 `main` 브랜치로 자동 커밋.

## 요구사항

- Python 3.11 이상 (로컬 테스트용, GitHub Actions 러너는 자동 준비)
- GitHub 계정 + public 레포 (Actions 2,000분/월 무료)
- [Google Gemini API Key](https://aistudio.google.com/apikey) (요약 단계용, **무료 티어** — 카드 등록 불필요)
- Telegram 봇 또는 Slack Incoming Webhook (발송 채널)
- (선택) 네이버 개발자 센터 Client ID / Secret — 경제 프로필의 키워드 검색(M2)에서 사용

## 설치

```bash
git clone https://github.com/jeongdowny/morning-briefing.git
cd morning-briefing
pip install feedparser requests beautifulsoup4 pytz
```

## 설정

레포 루트에서 설정 UI 를 실행합니다.

```bash
python3 scripts/config_ui.py
```

`http://localhost:8765` 이 자동으로 열립니다. 탭 구성:

| 탭 | 역할 |
|---|---|
| 채널 | 프로필 프리셋(경제만 / 개발만 / 전체) + Telegram·Slack 활성화 및 테스트 전송 |
| 시크릿 | `.env` 토큰 관리 (gitignore, 표시/숨김 토글) |
| 네이버 랭킹 | 수집 대상 언론사 화이트리스트, 상위 N 개 |
| 키워드 | Open API 검색 키워드 (M2) |
| 개발소식 | OpenAI / Anthropic 수집 활성화 |
| Threads | 팔로잉 계정 추가·삭제 |
| 기타 | 발송 시각(KST) 입력 시 UTC cron 자동 계산 |
| Routine 등록 | Routines UI 에 붙여넣을 값 복사 버튼 모음 |
| 발급 가이드 | Naver / Telegram / Slack / GitHub App / RSSHub 단계별 안내 |

**첫 사용자**: 채널 탭의 "프로필 프리셋" 버튼 하나로 관련 섹션들이 한 번에 활성화됩니다. 이후 개별 토글로 세부 조정 가능.

`auto-commit` 이 켜져 있으면 저장 시 `config/briefing.json` 변경사항을 `config: ...` 커밋 메시지로 자동 커밋합니다. `.env` 는 절대 커밋되지 않습니다.

## Obsidian 연동

레포 디렉토리 구조가 그대로 Obsidian vault 로 동작합니다.

1. Obsidian 에서 `Open folder as vault` → 이 레포 폴더 선택.
2. Community plugin 설치:
   - **Obsidian Git** — auto pull 15분.
   - **Dataview** — `Keeps.md` 집계용.
3. Routine 이 푸시한 `Daily/YYYY-MM-DD.md` 를 열고, 다시 볼 항목에 `#keep` 태그를 붙이면 `Keeps.md` 에 카테고리별로 자동 집계됩니다.

카테고리 태그는 자동 분류됩니다: `#거시`, `#자산`, `#글로벌` (경제), `#openai`, `#anthropic`, `#threads`, `#research` (개발).

## GitHub Actions 등록

자동 실행은 `.github/workflows/daily-brief.yml` 이 담당합니다. 셋업 UI 의 **"🚀 GitHub Actions 등록"** 탭에 복사 버튼이 준비되어 있습니다.

1. `python3 scripts/config_ui.py` → "🚀 GitHub Actions 등록" 탭.
2. **로컬 `.env`** 에 시크릿 저장:
   - `GEMINI_API_KEY` (요약용, 필수 · 무료)
   - `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` (Telegram 발송 시)
   - `SLACK_WEBHOOK_URL` (Slack 발송 시)
   - (선택) `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` — M2 키워드 검색용
3. UI 의 "Secrets 페이지 열기" 링크 → GitHub repo Settings → Secrets and variables → Actions.
4. UI 에서 각 키의 "값 복사" 버튼 → GitHub Secrets UI 에서 **New repository secret** 클릭 → 같은 Name 으로 paste.
5. 발송 시각(cron) 은 "⚙️ 기타" 탭에서 시간만 바꾸면 저장 시 워크플로 YAML 이 자동 동기화됩니다.
6. GitHub Actions 탭에서 "Daily Brief" 워크플로 → **Run workflow** 로 즉시 한 번 실행해 검증.

### 과거 Claude Code Routines 기반 셋업

초기 설계는 Claude Code Routines 로 돌렸으나 샌드박스 egress 네트워크 제한으로 수집 대상(naver·openai·anthropic·rsshub) 에 접근 불가하여 GitHub Actions 로 전환했습니다. 관련 문서는 `.claude/` 하위에 남아있지만 실제 실행에는 사용되지 않습니다.

## 로컬에서 파이프라인 수동 실행

의존성 설치:

```bash
pip install requests beautifulsoup4 feedparser pytz google-genai
```

`.env` 에 키 저장 후 (config UI 또는 직접 편집):

```bash
python3 scripts/collect_naver.py        # ranking 활성화 시
python3 scripts/collect_openai.py       # dev_news 활성화 시
python3 scripts/collect_anthropic.py    # dev_news 활성화 시
python3 scripts/collect_threads.py      # threads 활성화 시
python3 scripts/manage_seen.py filter
python3 scripts/summarize.py            # GEMINI_API_KEY 필요
python3 scripts/render_daily.py
python3 scripts/send_telegram.py        # 또는 send_slack.py
python3 scripts/manage_seen.py update
```

`.env` 의 값은 스크립트가 자동으로 읽지 않으므로 로컬 실행 시에는 `export` 하거나 `python-dotenv` 로 로드하세요. 예: `set -a; source .env; set +a; python3 scripts/summarize.py`.

## 알려진 제약

- **Anthropic HTML 스크래핑**: 공식 RSS 가 없어 `anthropic.com/news` 의 Next.js 렌더링 DOM 을 파싱합니다. 구조 변경 시 `scripts/collect_anthropic.py` 의 선택자 업데이트가 필요합니다.
- **RSSHub 공용 인스턴스**: `rsshub.app` 은 Rate limit 과 간헐적 장애가 있습니다. 안정성을 원한다면 RSSHub self-host 후 `config/briefing.json` 의 `threads.rsshub_base` 교체.
- **네이버 랭킹 필터링**: 네이버의 공식 섹션별 랭킹 URL 이 없어 "많이 본 뉴스" 중 경제 전문 언론사로 화이트리스트 필터링하는 우회 구조입니다. 일부 비경제 기사가 섞여 들어올 수 있습니다.

## 구현 현황

- [x] 프로필 프리셋 (경제 / 개발 / 전체)
- [x] 네이버 경제 전문지 랭킹 수집
- [x] OpenAI RSS · Anthropic HTML · Threads RSSHub
- [x] Telegram / Slack 섹션 분할 전송
- [x] Obsidian Daily 노트 + `#keep` 집계
- [x] 로컬 설정 편집 UI (시크릿 / Routine 등록 복사 버튼 포함)
- [ ] 네이버 Open API 키워드 검색 (M2)
- [ ] Hacker News · GitHub Trending (M2)
- [ ] 주간 리뷰 리포트 (M3)
- [ ] 가격 스냅샷 — KOSPI · USD/KRW · 금 · 유가 (M3)

설계 배경과 리스크 정리는 [`morning-briefing-plan.md`](./morning-briefing-plan.md) 참조.

## 라이선스

MIT.
