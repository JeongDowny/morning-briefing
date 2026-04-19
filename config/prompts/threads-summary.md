# Threads 포스트 요약 프롬프트

팔로잉 계정의 최근 포스트를 한 줄 요약한다.

## 출력 요건

- **1~2줄 한국어 요약** (최대 120자)
- **내용 핵심만**: 주장·정보·링크 공유 의도
- **스레드(연속 포스트)일 경우**: 전체 주제를 한 문장으로
- **영어 포스트**는 요지만 한국어로 옮김
- **맥락 부족한 반응·리트윗**은 "(맥락 참조)"로 표시

## 금지

- 원문 그대로 번역 — 요지 추출이 목적
- 추측·해석 추가
- 이모지 (원문의 것도 제거)

## 입력 형식

```json
{
  "items": [
    {
      "id": "item_1",
      "handle": "swyx",
      "label": "AI 엔지니어링",
      "content": "Just finished benchmarking 5 agent frameworks. LangGraph vs Mastra vs CrewAI...",
      "posted_at": "2026-04-16T14:23:00"
    }
  ]
}
```

## 출력 형식 (JSON)

```json
{
  "summaries": [
    {
      "id": "item_1",
      "summary": "에이전트 프레임워크 5개 벤치마크. Durability는 Mastra, 유연성은 LangGraph 추천."
    }
  ]
}
```
