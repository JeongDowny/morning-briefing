# 모닝 브리핑 자동화 시스템 — 개발 계획서 v2.1

> Claude Code Scheduled Agent 기반 | 매일 아침 08:00 KST 자동 실행
> 업데이트: 2026-04-17
>
> **v2 → v2.1 변경사항 (검증·설계결정 반영)**:
> - ✅ OpenAI RSS 검증 (`/news/rss.xml` 정상), Anthropic HTML 스크래핑으로 전환 (공식 RSS 없음)
> - ✅ 네이버 랭킹 URL 동작 확인 (`EUC-KR` 인코딩 주의)
> - ✅ Scheduled Agent 실행 모델 = **하이브리드** (Python 수집 + Claude 요약/렌더/커밋)
> - ✅ GitHub 인증 = **Claude GitHub App** (PAT 수동 설정 불필요)
> - ✅ 발송 시각 08:00 KST로 조정, 키워드 카테고리 구조 도입
> - ✅ Keep = 페이지 단위, 카테고리 태그는 `config/briefing.json` 값과 일치
> - ✅ 텔레그램 = 섹션별 독립 메시지 3개
> - ✅ URL 정규화 규칙(originallink 우선) 추가
>
> **v1 → v2**: 매크로 분석/트레이드 아이디어 제거, 네이버뉴스 전환, OpenAI/Anthropic 추가, Obsidian + 텔레그램 이중 채널, Keep 기능 도입

---

## 1. 프로젝트 개요

### 목적
매일 아침 출근 전(08:00 KST)에 세 가지 정보를 자동 수집·요약·배포한다.

1. **경제뉴스** — 네이버뉴스 경제면 랭킹 + 관심 키워드 검색
2. **AI/개발 소식** — OpenAI, Anthropic 공식 블로그
3. **Threads 하이라이트** — 팔로잉 계정 최신 포스트

### 읽기 UX (경로 1: 단순 구성)

| 역할 | 도구 | 용도 |
|---|---|---|
| 주 뷰어 | **Obsidian** (맥 데스크톱) | 출근 후 모니터에서 정독, `#keep` 태그로 북마크 |
| 보조 푸시 | **텔레그램 봇** | 핸드폰 푸시 알림 + 헤드라인 훑기 |
| 저장소 | **GitHub 레포 자체가 Obsidian vault** | Obsidian Git 플러그인으로 자동 pull |
| Keep | **Obsidian `#keep` 태그 + Dataview 자동 집계** | Keeps.md에서 누적 조회 |

### 명시적 제외 (v1 대비)
- ❌ 매크로 헤지펀드 분석 / 트레이드 아이디어
- ❌ YouTube 수집 (필요해지면 v2.1에서 검토)
- ❌ Slack 발송 (텔레그램으로 대체)

---

## 2. 시스템 아키텍처

### 실행 모델 — 하이브리드

| 단계 | 담당 | 이유 |
|---|---|---|
| **수집** (HTTP 요청·HTML/RSS 파싱) | **Python 스크립트** | 결정적, 테스트 가능, 유지보수 분리 |
| **중복 제거 / 상태 관리** | **Python 스크립트** | JSON 구조체 조작은 결정적 처리가 적합 |
| **요약** | **Claude 네이티브** | LLM 본연의 영역 |
| **Daily 노트 렌더링** | **Claude 네이티브** | 자유로운 MD 포맷팅, Python 템플릿 불필요 |
| **텔레그램 전송** | **Python 스크립트** | 단순 HTTP 호출, 결정적 포맷팅 |
| **git 커밋·push** | **Claude 네이티브** (Bash 도구) | Claude GitHub App 자격으로 자동 인증 |

### 흐름도

```
┌─ Claude Code Scheduled Agent (클라우드, 08:00 KST) ─┐
│                                                        │
│  Step 1: config/briefing.json 로드                     │
│                                                        │
│  Step 2: 경제뉴스 수집 [Python]                         │
│     ├─ 네이버뉴스 경제면 랭킹 TOP 10 (HTML 파싱)         │
│     └─ 네이버 오픈API 키워드 검색 (키워드×3건)           │
│                                                        │
│  Step 3: AI/개발 소식 수집 [Python]                     │
│     ├─ OpenAI RSS (feedparser)                         │
│     └─ Anthropic /news HTML (BeautifulSoup)            │
│                                                        │
│  Step 4: Threads 수집 [Python]                          │
│     └─ RSSHub 경유 계정별 RSS                           │
│                                                        │
│  Step 5: 중복 제거 [Python] (data/seen.json 대조)       │
│                                                        │
│  Step 6: Claude 요약 [Claude 네이티브]                  │
│     ├─ 리드 문단 있는 항목 → 요약 + 리드 병기            │
│     └─ 리드 문단 없는 항목 → 요약만                      │
│                                                        │
│  Step 7: 렌더링 [Claude 네이티브]                        │
│     └─ Daily/{date}.md 생성                             │
│                                                        │
│  Step 8: 텔레그램 전송 [Python]                         │
│     └─ 섹션별 메시지 3개 분할 전송                        │
│                                                        │
│  Step 9: 커밋 [Claude 네이티브]                          │
│     └─ Daily/, data/seen.json → main 푸시               │
│                                                        │
└────────────────────────────────────────────────────────┘
                        │
                        ▼
     ┌──────────────────┴──────────────────┐
     │                                      │
     ▼                                      ▼
┌─────────────────┐              ┌─────────────────┐
│ 맥 Obsidian     │              │ 아이폰 텔레그램  │
│ (Obsidian Git이 │              │ (푸시 알림 +     │
│  자동 pull)      │              │  헤드라인 훑기)  │
└─────────────────┘              └─────────────────┘
```

---

## 3. 레포지토리 구조

```
morning-briefing/                 ← GitHub 레포 = Obsidian vault (동일 폴더)
│
├── Daily/                        ← Scheduled Agent가 매일 새 파일 커밋
│   ├── 2026-04-17.md
│   ├── 2026-04-18.md
│   └── ...
│
├── Keeps.md                      ← Dataview 쿼리로 #keep 자동 집계
│
├── config/
│   ├── briefing.json             ← 수집 대상·키워드·계정 설정
│   └── prompts/
│       ├── news-summary.md       ← 경제뉴스 요약 프롬프트
│       ├── blog-summary.md       ← 개발 블로그 요약 프롬프트
│       └── threads-summary.md    ← Threads 포스트 요약 프롬프트
│
├── data/
│   └── seen.json                 ← 중복 방지 (Scheduled Agent가 자동 관리)
│
├── scripts/                      ← 수집/상태관리/전송만 담당 (요약·렌더링은 Claude 네이티브)
│   ├── collect_naver.py          ← 네이버 랭킹 + 키워드 검색
│   ├── collect_rss.py            ← OpenAI RSS + Anthropic HTML 스크래핑
│   ├── collect_threads.py        ← RSSHub 경유 Threads 수집
│   ├── manage_seen.py            ← seen.json 필터링·갱신
│   └── send_telegram.py          ← 섹션별 메시지 3개 전송
│
├── .claude/
│   └── routine-prompt.md         ← Scheduled Agent에 주입되는 실행 지시 프롬프트
│
├── .obsidian/                    ← Obsidian 설정 (플러그인 포함, workspace 제외)
│
├── .gitignore                    ← __pycache__, .DS_Store, .obsidian/workspace*.json 등
│
└── README.md
```

> **참고**: `Feeds/` (소스별 타임라인 누적 노트) 는 v3+ 에서 추가 예정 (Section 14 참조).

---

## 4. 설정 파일 명세

### 4-1. `config/briefing.json`

```json
{
  "naver_news": {
    "ranking": {
      "sections": ["economy"],
      "top_n": 10
    },
    "keyword_search": {
      "keywords": [
        { "term": "금리",    "category": "거시" },
        { "term": "환율",    "category": "거시" },
        { "term": "물가",    "category": "거시" },
        { "term": "부동산",  "category": "자산" },
        { "term": "코스피",  "category": "자산" },
        { "term": "연준",    "category": "글로벌" },
        { "term": "나스닥",  "category": "글로벌" }
      ],
      "per_keyword": 3,
      "sort": "date"
    }
  },
  "dev_news": {
    "sources": [
      {
        "name": "OpenAI",
        "url": "https://openai.com/news/rss.xml",
        "type": "rss"
      },
      {
        "name": "Anthropic",
        "url": "https://www.anthropic.com/news/rss.xml",
        "type": "rss"
      }
    ]
  },
  "threads": {
    "accounts": [
      { "handle": "swyx",          "label": "AI 엔지니어링" },
      { "handle": "yoheinakajima", "label": "에이전트 연구" },
      { "handle": "karpathy",      "label": "ML 대가" }
    ],
    "max_posts_per_account": 3,
    "fetch_method": "rsshub",
    "rsshub_base": "https://rsshub.app"
  },
  "window": {
    "from_hour": 8,
    "to_hour": 8,
    "timezone": "Asia/Seoul",
    "applies_to": ["keyword_search", "dev_news", "threads"]
  },
  "output": {
    "obsidian": {
      "daily_note_path": "Daily/{date}.md",
      "include_raw_lead": true
    },
    "telegram": {
      "enabled": true,
      "digest_mode": "by_section"
    }
  },
  "dedupe": {
    "retention_days": 30
  }
}
```

### 4-2. `config/prompts/*.md`

각 소스별 요약 프롬프트를 별도 MD 파일로 분리 — 품질 개선 시 파일만 수정.

공통 원칙:
- **2~3줄 한국어 요약**
- **사실 기반**, 추측/해석 금지
- **고유명사·수치 보존** (제목에서 생략된 실적치, 인물, 회사명)
- **첫 문장은 "무엇이 일어났는가"**, 두 번째는 "왜 중요한가" (필요 시)

---

## 5. 데이터 수집 상세

### 5-1. 네이버뉴스 경제면 랭킹

- **URL**: `https://news.naver.com/main/ranking/popularDay.naver?sectionId=101`
- **검증 결과 (2026-04-17)**: 200 응답, `EUC-KR` 인코딩, 로그인 불필요 ✅
- **방법**: `requests` + `BeautifulSoup`으로 HTML 파싱 (인코딩 디코딩 주의)
- **수집 필드**: 랭킹, 제목, URL, 언론사, 등록 시각
- **시간 필터**: **적용 안 함** — 랭킹은 이미 "오늘 많이 본" 기준이므로 `top_n` 개수만 따른다
- **주의**: 네이버는 User-Agent 검사함 → 브라우저 UA 설정 필수
- **실패 대비**: HTML 구조 변경 감지 시 에러 로그 → 텔레그램으로 관리자 알림

### 5-2. 네이버 뉴스 검색 API (키워드)

- **엔드포인트**: `https://openapi.naver.com/v1/search/news.json`
- **인증**: Client ID + Secret (네이버 개발자 센터)
- **파라미터**: `query` (= `term`), `display=3`, `sort=date`
- **쿼터**: 일 25,000회 (충분)
- **수집 필드**: `title`, `link` (네이버 뉴스), `originallink` (원본), `pubDate`, `description`
- **HTML 태그 정리**: `description`에서 `<b>`, `</b>` 등 제거
- **키워드 관리**:
  - `config/briefing.json`의 `keyword_search.keywords` 배열에 `{ "term": "...", "category": "..." }` 객체로 정의
  - 추가/삭제: 배열에 한 줄 넣거나 빼고 커밋하면 끝
  - `category` 값은 Obsidian Daily 노트·텔레그램 메시지에서 **섹션 헤더 그룹핑**에 사용 (같은 카테고리 키워드는 한 섹션 안에 묶여 노출)
  - 현재 카테고리: `거시` / `자산` / `글로벌` (자유롭게 확장 가능)

### 5-3. OpenAI / Anthropic 개발 소식 수집

**검증 결과 (2026-04-17)**

| 소스 | 공식 RSS | 확정 URL / 방식 |
|---|---|---|
| OpenAI | ✅ 있음 | `https://openai.com/news/rss.xml` (feedparser 파싱) |
| Anthropic | ❌ 없음 | `https://www.anthropic.com/news` **HTML 스크래핑** (BeautifulSoup) |

#### OpenAI 처리
- **도구**: `feedparser`
- **엔드포인트**: `https://openai.com/news/rss.xml` (Cloudflare 경유, 정상 200 응답)
- **수집 필드**: `title`, `link`, `description`, `pubDate`, `category`
- **시간 필터**: 직전 24시간

#### Anthropic 처리
- **방법**: `requests` + `BeautifulSoup`로 `https://www.anthropic.com/news` HTML 파싱
- **Next.js 앱** 특성: 서버 렌더링 HTML에 article 카드 정보 포함 → 카드 요소의 제목·링크·날짜·요약 추출
- **선택자**: 구축 단계에서 현재 DOM 구조 기반으로 확정 (설정 파일로 분리해 유지보수 용이하게)
- **리스크**: DOM 구조 변경 시 스크래핑 중단 → Section 13 리스크에 등재, 실패 시 텔레그램 관리자 알림
- **대체 경로 (fallback 후보)**:
  - RSSHub 커뮤니티 라우트 탐색 (`https://rsshub.app/anthropic/...`)
  - rss.app 등 서드파티 RSS 생성기
  - `https://www.anthropic.com/sitemap.xml` 파싱 후 최신 뉴스 URL 추출
- **시간 필터**: 직전 24시간

### 5-4. Threads 수집

- **1차 방법**: RSSHub 공용 인스턴스 (`https://rsshub.app/threads/{handle}`)
- **2차 방법 (fallback)**: 공개 프로필 HTML 파싱
- **RSSHub 공용 인스턴스 리스크**: Rate limit, 간헐적 다운
  - MVP에선 공용 사용
  - 안정성 문제 생기면 자체 Docker로 self-host (`DIYgod/RSSHub`)
- **계정 추가 방법**: `config/briefing.json`의 `threads.accounts` 배열에 항목 추가 후 커밋

---

## 6. 요약 로직

### 분기 원칙

| 원본 리드 문단 상태 | 출력 |
|---|---|
| **있음** (OpenAI/Anthropic 블로그, Threads 포스트, 일부 뉴스) | Claude 요약 (2~3줄) + 원문 리드 문단 병기 |
| **없음** (제목만 긁힌 뉴스 등) | Claude 요약만 |

### Claude 호출 전략

- **단일 호출로 배치 처리**: 모든 수집 항목을 하나의 프롬프트에 묶어서 요약 요청 → 토큰 비용 최소화
- **구조화 출력**: JSON 형식으로 요구 → 파싱 후 Daily 노트에 삽입
- **폴백**: Claude 호출 실패 시 제목 + 원문 리드 그대로 사용 (Briefing 발송은 무조건 진행)

---

## 7. Obsidian 출력 포맷

### 7-1. `Daily/2026-04-17.md` 예시

```markdown
---
date: 2026-04-17
tags: [daily, briefing]
---

# 🌅 모닝 브리핑 — 2026년 4월 17일 (금)

> 수집 기간: 2026-04-16 08:00 ~ 2026-04-17 08:00 KST
> 총 수집: 경제뉴스 22건 / 개발소식 4건 / Threads 7건

## 📈 경제뉴스

### 네이버 경제면 랭킹

1. **[원달러 환율 1,380원 돌파, 3개월 만에 최고](https://...)** — 한국경제
   - 🤖 미국 고용지표 호조로 달러 강세가 재개되며 환율이 1,380원을 뚫었다. 외국인 자금 유출 우려가 커지고 있다.
   - 📄 *17일 서울 외환시장에서 원달러 환율이 전일 대비 6.2원 오른 1,381.4원에 마감했다...*

2. **...**

### 키워드 검색

#### 🌐 거시 — 금리
- **[한국은행 기준금리 동결 유력](https://...)** — 매일경제
  - 🤖 4월 금통위에서 기준금리 3.50% 동결이 우세하다. 물가 둔화와 가계부채 우려가 맞물린 상태.

#### 🌐 거시 — 환율
- ...

#### 💰 자산 — 부동산
- ...

#### 🌍 글로벌 — 연준
- ...

## 🤖 AI / 개발 소식

### OpenAI
- **[Introducing GPT-X](https://openai.com/...)**
  - 🤖 OpenAI가 차세대 모델 GPT-X를 발표했다. 추론 속도 3배, 컨텍스트 2M 토큰.
  - 📄 *Today we're releasing GPT-X, our most capable model yet...*

### Anthropic
- **[...](...)**
  - 🤖 ...

## 🧵 Threads

### @swyx — AI 엔지니어링
- **[2026-04-16 14:23](https://threads.net/...)** 
  - 🤖 AI 에이전트 프레임워크 5개 비교. LangGraph vs Mastra vs CrewAI 등 실제 프로덕션 사용 소감 정리.
  - 📄 *Just finished benchmarking 5 agent frameworks...*

### @karpathy — ML 대가
- ...

---

## 💡 Keep

> 중요한 항목 아래에 `#keep` 태그를 붙이세요. Keeps.md에 자동으로 집계됩니다.
> 예: `- 중요한 이유 메모 #keep`
```

### 7-2. `Keeps.md` 구조

```markdown
# 💎 Keep 아카이브

> `#keep` 태그가 붙은 모든 항목이 자동으로 모입니다.

## 이번 주

\`\`\`dataview
LIST
FROM #keep
WHERE file.mday >= date(today) - dur(7 days)
SORT file.mday DESC
\`\`\`

## 전체 (최신순)

\`\`\`dataview
TABLE WITHOUT ID
  file.link AS "출처 노트",
  file.mday AS "태그 추가일"
FROM #keep
SORT file.mday DESC
\`\`\`

## 카테고리별

### 경제

\`\`\`dataview
LIST
FROM #keep AND #경제
\`\`\`

### AI/개발

\`\`\`dataview
LIST
FROM #keep AND #ai
\`\`\`
```

### 7-3. Keep 워크플로우

1. 출근 후 Obsidian에서 `Daily/2026-04-17.md` 열기
2. 중요한 항목 발견 → **그 항목이 속한 Daily 노트 어디에든 `#keep` 태그 추가** (예: 항목 밑 메모에 `#keep #거시`)
3. 저장 → `Keeps.md`의 Dataview 쿼리가 자동 반영
4. 주간/월간 리뷰 시 Keeps.md 에서 검토

### 7-4. Keep 단위 — **페이지 단위**

- `#keep` 태그가 어디 있든 **그 Daily 노트 전체**가 Keep 결과에 포함됨
- 즉 "2026-04-17에 뭔가 킵했다" → `Keeps.md`에선 그 날짜 노트가 한 줄로 뜸 → 클릭해서 들어가 세부 항목 확인
- 줄 단위로 발췌하지 않음 (Dataview 인라인 쿼리 복잡도 회피)

### 7-5. 태그 네이밍 규칙

| 태그 | 의미 | 사용 예 |
|---|---|---|
| `#keep` | 이 노트에 킵할 항목이 있음 (필수) | 모든 Keep에 붙임 |
| `#거시` | 금리·환율·물가 카테고리 | `briefing.json` 의 `category: "거시"` 와 일치 |
| `#자산` | 부동산·코스피 | 〃 |
| `#글로벌` | 연준·나스닥 | 〃 |
| `#ai` | OpenAI/Anthropic 개발 소식 | 자동 분류 |
| `#threads` | Threads 포스트 | 자동 분류 |

**원칙**: 카테고리 태그는 `config/briefing.json` 의 `category` 값과 **정확히 일치**시킴. 일관성 유지로 Dataview 쿼리 예측 가능성 확보.

**사용자는 `#keep` 만 붙이면 됨** — 카테고리 태그는 Scheduled Agent가 Daily 노트 생성 시 해당 항목 하단에 미리 기입해둠 (사용자가 직접 달 필요 없음).

---

## 8. 텔레그램 출력 포맷

### 메시지 전략 — **섹션별 독립 메시지 3개**

각 섹션을 **별도 메시지로 분할 전송**. 이유:
- 모바일 가독성: 한 메시지당 스크롤 짧음
- 관심 없는 섹션 빨리 지나침
- 4096자 제한 여유롭게 확보

```
메시지 1: 📈 경제뉴스 (랭킹 + 키워드 카테고리별)
메시지 2: 🤖 AI / 개발 소식 (OpenAI + Anthropic)
메시지 3: 🧵 Threads 하이라이트 (팔로잉 계정별)
```

- 섹션 내 콘텐츠가 4096자 초과 시 해당 섹션만 추가 분할
- **MarkdownV2 포맷** 사용 (볼드, 링크, 이모지)
- 이스케이프 주의: `- ( ) . ! +` 등 특수문자는 `\` 로 이스케이프 필수

### 메시지 예시

```
🌅 *모닝 브리핑 — 04/17 (금)*

📈 *경제뉴스 TOP 5*
1\. [원달러 환율 1,380 돌파](link) _한국경제_
   ▸ 미 고용 호조로 달러 강세 재개

2\. [한국은행 기준금리 동결 유력](link) _매일경제_
   ▸ 4월 금통위 3\.50% 동결 우세

...

━━━━━━━━━━━━━━
🤖 *AI/개발 소식*
• [GPT\-X 발표](link) _OpenAI_
  ▸ 추론 3배 빨라짐, 컨텍스트 2M

...

━━━━━━━━━━━━━━
🧵 *Threads 하이라이트*
• @swyx: [에이전트 프레임워크 비교](link)
  ▸ LangGraph vs Mastra vs CrewAI

...

━━━━━━━━━━━━━━
📖 자세히: Obsidian `Daily/2026-04-17`
```

---

## 9. 중복 방지

### `data/seen.json` 구조

```json
{
  "last_updated": "2026-04-17T08:00:00+09:00",
  "news": {
    "https://n.news.naver.com/article/...": "2026-04-17T06:30:00+09:00"
  },
  "dev_blog": {
    "https://openai.com/blog/gpt-x": "2026-04-17T02:10:00+09:00"
  },
  "threads": {
    "swyx": ["post-id-1", "post-id-2"],
    "karpathy": ["post-id-5"]
  }
}
```

### 정책
- **URL 또는 post ID 기준**으로 중복 체크
- **유지 기간**: 30일 (`dedupe.retention_days`)
- Scheduled Agent가 매 실행 후 오래된 항목 정리 + 새 항목 추가 → 커밋

### URL 정규화 규칙 (중요)

같은 기사가 여러 소스에서 다른 URL로 수집되는 문제 방지:

```
우선순위:
1. originallink (언론사 원본 URL)  ← 네이버 검색 API의 `originallink` 필드
2. link (네이버 뉴스 래퍼 URL)     ← 네이버 검색 API의 `link` 필드
3. 그 외 소스는 해당 소스의 기본 URL 필드 그대로
```

- `collect_naver.py` 는 수집 시 `originallink`가 있으면 그걸 식별자로 사용
- `manage_seen.py` 의 dedup 로직도 위 우선순위로 정규화된 URL 기준 비교
- **결과**: 랭킹에서 본 기사가 키워드 검색에도 뜨더라도 단일 항목으로 병합

---

## 10. Scheduled Agent 설정

Claude Code Routines (= Scheduled Agent) 기반. 클라우드 환경에서 cron에 따라 자동 실행.

### 기본 설정

| 항목 | 값 |
|---|---|
| 이름 | `morning-briefing` |
| Trigger | Schedule — Cron `0 23 * * *` (UTC) = **매일 08:00 KST** |
| Repository | `morning-briefing` (main 브랜치) |
| **커밋 권한** | **Allow unrestricted branch pushes = ON** (main에 `Daily/**`, `data/seen.json` 직접 커밋하기 위해) |
| GitHub 인증 | **Claude GitHub App** (레포 설치) 또는 `/web-setup` 으로 `gh` CLI 토큰 동기화 — **PAT 수동 설정 불필요** |
| Python 런타임 | 사전 설치 (Python 3.x, pip, poetry, uv) — 별도 설치 불필요 |
| Setup Script | `pip install feedparser requests beautifulsoup4 pytz` (출력 캐싱되어 세션 간 재사용) |
| Connector | 없음 (텔레그램은 Bot API HTTP 직접 호출) |

> **참고**: Routines는 현재 research preview 상태. 동작·제한·API가 변경될 수 있음.

### 실행 플로우 (하이브리드 모델)

Scheduled Agent에 주입되는 프롬프트가 아래 순서대로 Claude에게 지시:

```
1. [bash] python scripts/collect_naver.py      → collected/naver.json
2. [bash] python scripts/collect_rss.py        → collected/rss.json
3. [bash] python scripts/collect_threads.py    → collected/threads.json
4. [bash] python scripts/manage_seen.py filter → collected/filtered.json
5. [Claude 네이티브] filtered.json 읽어 각 항목 요약 → summarized.json
6. [Claude 네이티브] summarized.json → Daily/{date}.md 생성
7. [bash] python scripts/send_telegram.py --input summarized.json
8. [bash] python scripts/manage_seen.py update
9. [Claude 네이티브] git add + commit + push (Claude GitHub App 자격으로)
```

- **수집·상태관리·전송**(1~4, 7~8): Python 스크립트로 결정적 처리
- **요약·렌더링·커밋**(5~6, 9): Claude 네이티브 도구(LLM + 파일·bash·git)

### 환경변수

| 키 | 용도 | 발급처 |
|---|---|---|
| `NAVER_CLIENT_ID` | 네이버 뉴스 검색 API | 네이버 개발자 센터 |
| `NAVER_CLIENT_SECRET` | 〃 | 〃 |
| `TELEGRAM_BOT_TOKEN` | 텔레그램 봇 인증 | `@BotFather` |
| `TELEGRAM_CHAT_ID` | 본인 채팅 ID | `getUpdates` API |

---

## 11. 셋업 체크리스트

### 11-1. 외부 API / 계정

- [ ] **네이버 개발자 센터** (developers.naver.com) 접속 → 애플리케이션 등록 → "검색" API 선택 → Client ID/Secret 발급
- [ ] **Telegram**:
  - [ ] 텔레그램 앱에서 `@BotFather` 검색 → `/newbot` → 봇 이름·username 입력 → **Token** 획득
  - [ ] 만든 봇에게 아무 메시지 발송
  - [ ] 브라우저에서 `https://api.telegram.org/bot<TOKEN>/getUpdates` → `chat.id` 값 복사
- [ ] **GitHub**: `morning-briefing` 레포 생성 (private 권장)

### 11-2. 레포 초기 파일 구성

- [ ] `.gitignore` 생성 — 아래 내용 포함:
  ```
  # Python
  __pycache__/
  *.pyc
  .venv/
  
  # OS
  .DS_Store
  Thumbs.db
  
  # Obsidian — 기기별 상태 (커밋 시 충돌 유발)
  .obsidian/workspace*.json
  .obsidian/app.json
  .obsidian/appearance.json
  
  # 수집 중간 산출물 (임시)
  collected/
  ```
- [ ] `.obsidian/` 의 플러그인 설정만 커밋 (workspace·app·appearance는 위 gitignore로 제외)

### 11-3. 로컬 맥 Obsidian 셋업

- [ ] **Obsidian 설치**: https://obsidian.md → Download for macOS
- [ ] 레포 clone:
  ```bash
  cd ~/source
  git clone git@github.com:<본인>/morning-briefing.git
  ```
- [ ] Obsidian 실행 → "Open folder as vault" → `~/source/morning-briefing` 선택
- [ ] **플러그인 설치** (Settings → Community plugins):
  - [ ] "Obsidian Git" 설치 → Settings:
    - Vault backup interval: 15 min
    - Pull on startup: **ON**
    - Auto pull every N minutes: **15**
  - [ ] "Dataview" 설치 → Settings:
    - Enable JavaScript Queries: **OFF** (보안)
- [ ] `.obsidian/` 플러그인 설정 커밋 (위 gitignore 규칙 따름)
- [ ] 테스트: 레포에 `Daily/2026-04-17.md` 샘플 푸시 → Obsidian에서 자동 pull 확인

### 11-4. Claude Code Scheduled Agent

- [ ] **GitHub 인증 셋업** (둘 중 하나):
  - **권장**: `morning-briefing` 레포에 **Claude GitHub App 설치** (https://github.com/apps/claude)
  - **대안**: 로컬 CLI에서 `/web-setup` 실행 → `gh` CLI 토큰을 Claude에 동기화
- [ ] `claude` CLI에서 `/schedule` 실행 (또는 https://claude.ai/code/routines 웹 UI)
- [ ] 신규 Routine 등록:
  - 이름: `morning-briefing`
  - Trigger: Schedule, Cron `0 23 * * *` (UTC)
  - Repo: `morning-briefing`
  - **Allow unrestricted branch pushes**: **ON** (main 직접 커밋 허용)
  - Setup script: `pip install feedparser requests beautifulsoup4 pytz`
  - Prompt: `.claude/routine-prompt.md` 내용 복사 (구현 단계에서 작성)
- [ ] **환경변수 4개 주입** (환경 설정 UI):
  - `NAVER_CLIENT_ID`
  - `NAVER_CLIENT_SECRET`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
- [ ] **Run once** 로 테스트 실행 → Daily 노트 생성 & 텔레그램 수신 확인

---

## 12. 마일스톤 — MVP부터 점진 확장

| 단계 | 범위 | 확인 포인트 |
|---|---|---|
| **M1 — MVP (Week 1)** | 네이버뉴스 랭킹만 + Obsidian Daily 노트 + 텔레그램 전송 | 매일 자동 도착 확인, Obsidian 자동 pull 동작 |
| **M2 (Week 2)** | 키워드 검색 + OpenAI/Anthropic RSS 추가 | 요약 품질 점검, 리드 병기 포맷 확인 |
| **M3 (Week 3)** | Threads 추가 (RSSHub) | RSSHub 안정성 관찰 |
| **M4 (Week 4)** | `Keeps.md` + Dataview 쿼리 완성, 중복 방지 정제 | 한 달 누적 Keep 리뷰 |

---

## 13. 리스크와 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| 네이버 HTML 구조 변경 | 랭킹 수집 중단 | 선택자 설정 파일 분리, 실패 감지 시 텔레그램 관리자 알림 |
| RSSHub 공용 인스턴스 다운 | Threads 미수집 | 해당 섹션만 스킵, 다음 실행에서 재시도 |
| OpenAI/Anthropic RSS 경로 변경 | 개발소식 누락 | 구축 시 실제 URL 검증, 설정으로 분리 |
| Claude 요약 실패 | 요약 비어있음 | 제목 + 원문 리드만으로 폴백 (Briefing은 무조건 발송) |
| Scheduled Agent 실패 | 당일 브리핑 없음 | 실패 시 텔레그램 실패 알림, 다음날 정상 복귀 |
| 텔레그램 메시지 길이 초과 | 메시지 잘림 | 섹션별 분할 전송, 4000자마다 분할 |

---

## 14. 후속 고도화 (v3+)

### 단기
- 경제 캘린더 연동 — FOMC, 금통위, CPI 발표 전일엔 "내일 주목 포인트" 섹션 자동 추가
- 가격 스냅샷 — KOSPI, USD/KRW, S&P500, UST 10Y, WTI 전일 종가 vs 오늘 시가

### 중기
- 텔레그램 이모지 반응(⭐) 감지 → 해당 항목에 `#keep` 태그 자동 추가 (봇 webhook 추가 필요)
- 소스 품질 피드백 — Keep 비율이 낮은 소스/키워드 자동 디프라이오리티
- **`Feeds/` 디렉토리 누적 노트** — 소스별 장기 타임라인:
  ```
  Feeds/
  ├── OpenAI.md          ← OpenAI 공지 전체 타임라인 (append-only)
  ├── Anthropic.md       ← Anthropic 공지 전체 타임라인
  └── Threads-swyx.md    ← 계정별 포스트 타임라인
  ```
  Daily 노트가 당일 요약이라면 Feeds/ 는 소스별 역사 추적용

### 장기
- 주간 리뷰 (월요일 아침) — 지난 주 Keep 항목 요약 + 관심 테마 변화
- 검색 인터페이스 — Obsidian 외부에서도 브리핑 히스토리 조회 가능한 간단 웹뷰

---

*생성일: 2026-04-17*
*원본: `morning-briefing-plan-v1.md` (아카이브)*
