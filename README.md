# morning-briefing-economy

네이버 경제뉴스를 매일 아침 자동 수집·요약해서 Obsidian vault 와 Slack/Telegram 으로 전달하는 개인용 자동화.

경제 학습 목적으로 설계되었으며 투자 자문 도구가 아니다. 수집은 "많이 본 뉴스" 랭킹 중 경제 전문 언론사로 화이트리스트 필터링하고, 요약은 Claude Code Routine 이 담당한다.

## 동작 방식

1. Claude Code Routine 이 사용자가 지정한 시각(KST)에 클라우드에서 실행된다. 로컬 머신은 켜져 있지 않아도 된다.
2. `scripts/collect_naver.py` 가 네이버 랭킹 페이지를 파싱해 `collected/naver.json` 에 저장한다.
3. `scripts/manage_seen.py filter` 가 `data/seen.json` 과 대조해 지난 30일 이내 이미 노출된 항목을 제거한다.
4. Routine 안의 Claude 가 각 항목을 한국어 2~3줄로 요약하고 `Daily/YYYY-MM-DD.md` 를 생성한다.
5. `scripts/send_telegram.py` · `scripts/send_slack.py` 중 활성화된 쪽이 섹션별 메시지로 전송한다.
6. 신규 노트와 `data/seen.json` 변경분이 `main` 브랜치로 커밋된다.

## 요구사항

- Python 3.11 이상
- Claude Code (Routines 사용 가능한 플랜)
- Telegram 봇 또는 Slack Incoming Webhook (발송 채널)
- (선택) 네이버 개발자 센터 Client ID / Secret — 키워드 검색(M2) 에서 사용

## 설치

```bash
git clone https://github.com/jeongdowny/morning-briefing-economy.git
cd morning-briefing-economy
pip install requests beautifulsoup4 pytz
```

## 설정

레포 루트에서 설정 UI 를 실행한다.

```bash
python3 scripts/config_ui.py
```

`http://localhost:8765` 이 자동으로 열린다. 탭은 다음과 같다.

| 탭 | 역할 |
|---|---|
| 채널 | Telegram / Slack 활성화, 각 채널 테스트 전송 |
| 시크릿 | `.env` 에 저장되는 API 토큰 (gitignore 됨) |
| 네이버 랭킹 | 수집 대상 언론사 화이트리스트, 상위 N 개 |
| 키워드 | Open API 검색 키워드 (M2 에서 활성화) |
| 기타 | 발송 시각(KST) 입력 시 UTC cron 을 자동 계산 |
| 발급 가이드 | Naver / Telegram / Slack / GitHub App 단계별 안내 |

`auto-commit` 을 켜면 저장 시 `config/briefing.json` 변경분이 자동으로 커밋된다. `.env` 값은 절대 커밋되지 않는다.

## Obsidian 연동

레포 디렉토리 구조가 그대로 Obsidian vault 로 동작한다.

1. Obsidian 에서 `Open folder as vault` → 이 레포 폴더 선택.
2. Community plugin 설치:
   - **Obsidian Git** — auto pull 15분.
   - **Dataview** — `Keeps.md` 집계용.
3. Routine 이 푸시한 `Daily/YYYY-MM-DD.md` 를 열고, 다시 볼 항목에 `#keep` 태그를 붙이면 `Keeps.md` 에 자동 집계된다.

## Claude Code Routine 등록

1. [github.com/apps/claude](https://github.com/apps/claude) 에서 이 레포에 Claude GitHub App 설치.
2. `claude` CLI 에서 `/schedule` 실행 (또는 [claude.ai/code/routines](https://claude.ai/code/routines)).
3. 새 Routine 을 아래와 같이 구성한다.
   - Trigger — Schedule, cron 은 설정 UI "기타" 탭의 값 사용
   - Repository — 이 레포
   - Allow unrestricted branch pushes — on
   - Setup script — `pip install requests beautifulsoup4 pytz`
   - Prompt — `.claude/routine-prompt.md` 내용 복사
4. `.env` 와 동일한 키를 환경변수에 주입한다.
5. `Run once` 로 첫 실행을 검증한다.

## 로컬 파이프라인 수동 실행

요약과 Daily 노트 생성은 Routine 안의 Claude 가 담당하지만, 수집·전송 단계는 로컬에서 단독 실행할 수 있다.

```bash
python3 scripts/collect_naver.py
python3 scripts/manage_seen.py filter
python3 scripts/send_telegram.py          # 또는 send_slack.py
python3 scripts/manage_seen.py update
```

## 구현 현황

- [x] 네이버 경제 전문지 랭킹 수집
- [x] Telegram / Slack 섹션 분할 전송
- [x] Obsidian Daily 노트 + `#keep` 집계
- [x] 로컬 설정 편집 UI
- [ ] 네이버 Open API 키워드 검색 (M2)
- [ ] 월요일 주간 리뷰 (M3)
- [ ] 가격 스냅샷 — KOSPI, USD/KRW, 금, 유가 (M4)

설계 배경과 리스크 정리는 [`morning-briefing-plan.md`](./morning-briefing-plan.md) 참조.

## 관련 프로젝트

[morning-briefing-dev](https://github.com/jeongdowny/morning-briefing-dev) — 같은 파이프라인 구조로 OpenAI · Anthropic · Threads 를 수집하는 개발자 버전.

## 라이선스

MIT.
