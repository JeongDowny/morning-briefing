# morning-briefing-economy

> 매일 아침 경제뉴스를 자동 수집·요약·배포하는 개인용 브리핑 파이프라인
> **경제 공부 목적** — 랭킹·키워드 기반 네이버뉴스 수집, Obsidian + Slack/Telegram

자매 프로젝트: [`morning-briefing-dev`](https://github.com/jeongdowny/morning-briefing-dev) — AI·개발 동향 버전

---

## 특징

- ⏰ **매일 원하는 시각 발송** — `config_ui` 에서 시간 설정, cron 자동 계산
- 📈 **경제 전문 언론사 필터** — 매경·한경·머니투데이 등 9개 화이트리스트
- 🔍 **키워드 검색** (M2) — 금리·환율·물가·부동산·코스피·연준·나스닥 커스터마이징 가능
- 📝 **Obsidian 주 뷰어** — GitHub 레포 자체가 Obsidian vault, `#keep` 태그로 북마크
- 📲 **Slack / Telegram** 양쪽 지원 — 체크박스로 선택
- ☁️ **Claude Code Routines** — 랩탑 꺼져 있어도 클라우드 자동 실행
- 🎛️ **브라우저 UI** — 코드 없이 키워드·언론사·시각·시크릿 편집

---

## 5분 셋업

### 1. 클론 + 의존성

```bash
git clone https://github.com/jeongdowny/morning-briefing-economy.git
cd morning-briefing-economy
pip install requests beautifulsoup4 pytz
```

### 2. 설정 UI 실행

```bash
python3 scripts/config_ui.py
# → http://localhost:8765 자동 오픈
```

### 3. UI 에서 아래 단계대로

1. **📖 발급 가이드** 탭 — Naver API / Telegram Bot / Slack Webhook 단계별 발급 링크 제공
2. **🔑 시크릿** — 발급받은 키들 입력
3. **📡 채널** — Telegram 또는 Slack 활성화 + **테스트 전송** 버튼으로 확인
4. **📈 네이버 랭킹** — 원하는 언론사만 남기기
5. **⚙️ 기타** — 발송 시각(기본 08:00 KST) 조정 → 자동 계산된 Cron 복사
6. **💾 전체 저장** (auto-commit 켜두면 커밋까지 자동)

### 4. Claude Code Routines 등록

1. [github.com/apps/claude](https://github.com/apps/claude) → 이 레포에 Claude GitHub App 설치
2. `claude` CLI 에서 `/schedule` 실행 또는 [claude.ai/code/routines](https://claude.ai/code/routines) 접속
3. 새 Routine:
   - Name: `morning-briefing-economy`
   - Trigger: Schedule, **Cron = UI에서 복사한 값**
   - Repo: `morning-briefing-economy`
   - **Allow unrestricted branch pushes: ON**
   - Setup script: `pip install requests beautifulsoup4 pytz`
   - Prompt: `.claude/routine-prompt.md` 내용 복사 붙여넣기
4. 환경변수 주입 (UI 시크릿 탭과 동일 키)
5. **Run once** 로 테스트 실행

---

## 레포 구조

```
.
├── Daily/                    # 일일 브리핑 노트 (자동 생성, Obsidian vault)
├── Keeps.md                  # Dataview #keep 집계
├── config/
│   ├── briefing.json         # 모든 설정 (UI 가 관리)
│   └── prompts/              # 요약 프롬프트
├── data/seen.json            # 중복 방지 상태
├── scripts/
│   ├── config_ui.py          # ⭐ 로컬 편집 UI
│   ├── collect_naver.py      # 네이버 랭킹 수집
│   ├── manage_seen.py        # 중복 제거
│   ├── send_telegram.py
│   └── send_slack.py
└── .claude/routine-prompt.md # Scheduled Agent 실행 지시
```

---

## Obsidian 연동

이 레포 자체를 Obsidian vault 로 엽니다:

1. [Obsidian 설치](https://obsidian.md) → `Open folder as vault` → 이 레포 폴더 선택
2. Community plugins 설치:
   - **Obsidian Git** — 15분마다 자동 pull (Scheduled Agent 가 푸시한 최신 브리핑 수신)
   - **Dataview** — `Keeps.md` 의 `#keep` 자동 집계
3. 출근 후 `Daily/{날짜}.md` 열어 읽고, 중요한 항목 끝에 `#keep` 태그 추가
4. `Keeps.md` 에서 누적 키프 확인

---

## 로컬 파이프라인 수동 테스트

```bash
python3 scripts/collect_naver.py         # 수집 → collected/naver.json
python3 scripts/manage_seen.py filter    # 중복 제거 → collected/filtered.json
# (Claude 가 요약 + Daily 노트 생성 — Routines 가 자동으로 수행)
python3 scripts/send_telegram.py         # 전송 (.env 에 토큰 필요)
python3 scripts/manage_seen.py update    # seen.json 갱신
```

---

## 로드맵

- [x] **M1 MVP** — 네이버 랭킹 + Obsidian + Telegram/Slack
- [ ] **M2** — 네이버 Open API 키워드 검색 (금리·환율 등 정밀 필터)
- [ ] **M3** — Keep 주간 리뷰 (월요일 아침 지난 주 요약)
- [ ] **M4** — 가격 스냅샷 (KOSPI·USD/KRW·금·유가)

자세한 설계는 [`morning-briefing-plan.md`](./morning-briefing-plan.md) 참조.

---

## 라이선스 / 기여

MIT. 이슈·PR 환영합니다.

피드백: `@jeongdowny`
