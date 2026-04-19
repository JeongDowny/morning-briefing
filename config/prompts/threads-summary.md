# Threads 포스트 요약 프롬프트

팔로잉 계정의 최근 포스트를 한 줄 요약. 원문이 영어일 수 있으므로 필요 시 한국어 주제(title_ko)도 함께.

## 반드시 포함할 필드

각 항목에 대해 JSON 으로 반환:

- `id`: 입력과 동일
- `title_ko`: 포스트 내용이 영어라면 핵심 주제를 한국어 한 문장으로. 이미 한국어면 빈 문자열 `""`.
- `summary`: 1~2줄 한국어 요약

## summary 작성 규칙

### 원칙 1: 요지 추출, 통째 번역 아님

❌ 나쁨 (원문 그대로 번역):
> 나는 5개의 에이전트 프레임워크를 벤치마크했다. LangGraph, Mastra, CrewAI, ...

✅ 좋음 (주장·정보 요지):
> 에이전트 프레임워크 5개 벤치마크. Durability 중심이면 Mastra, 유연성이 필요하면 LangGraph 추천.

### 원칙 2: 구체 정보 보존

- 도구·회사·모델명은 원문 유지 (LangGraph, Mastra, Claude, GPT-5, Anthropic 등)
- 수치·비교 결과 필수 포함 (`3x faster`, `50% cheaper` 등)
- 스레드(연속 포스트) 는 여러 포스트를 하나의 주제로 묶어 요약

### 원칙 3: 맥락 부족 대응

- 리트윗·짧은 반응으로 맥락 불명 → `summary: "(맥락 참조 — 원문 링크 확인)"` 로 표시
- 추측·해석 추가 금지

### 원칙 4: 금지

- 원문 통째 번역 — 요지 추출이 목적
- 이모지 (원문의 것도 제거)
- `대단하다`, `흥미롭다` 같은 감정 표현

## 입력 형식

```json
{
  "items": [
    {
      "id": "item_0",
      "title": "",
      "lead": "Just finished benchmarking 5 agent frameworks. LangGraph vs Mastra vs CrewAI... tldr: use Mastra if you need durability, LangGraph for flexibility.",
      "source": "swyx"
    }
  ]
}
```

## 출력 형식 (JSON 만, 다른 설명 금지)

```json
{
  "summaries": [
    {
      "id": "item_0",
      "title_ko": "에이전트 프레임워크 5개 벤치마크",
      "summary": "LangGraph · Mastra · CrewAI 등 5개를 비교. Durability 중심이면 Mastra, 유연성이 필요하면 LangGraph 추천."
    }
  ]
}
```
