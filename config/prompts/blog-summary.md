# AI 개발 블로그 요약 프롬프트

OpenAI / Anthropic 공식 블로그 포스트를 개발자 관점에서 요약. 영문 원본이므로 한국어 번역 제목(`title_ko`)과 핵심 요약(`summary`)을 함께 제공.

## 반드시 포함할 필드

각 항목에 대해 JSON 으로 반환:

- `id`: 입력과 동일
- `title_ko`: 원문 제목의 한국어 번역
  - 제품명·회사명·인명 고유명사는 원문 유지 (예: `Claude Opus 4.7`, `Anthropic`, `OpenAI`, `Broadcom`, `Mozilla`)
  - 자연스러운 한국어 어순으로. 영어 문장 그대로 직역 금지.
- `summary`: 2~3줄 한국어 요약

## summary 작성 규칙 — 엄격히 준수

### 원칙 1: 제목 재진술 금지

❌ 나쁨 (제목 번역에 불과):
> Anthropic 이 Claude Opus 4.7 을 공개했다.

✅ 좋음 (lead 의 구체 내용 반영):
> Claude Opus 4.7 공개. 코딩·에이전트·비전·다단계 작업 성능이 강화됐다. Anthropic 은 이전 Opus 대비 정확도와 일관성이 개선됐다고 밝혔다.

### 원칙 2: lead 에서 수치·고유명사·기능명 반드시 추출

lead 문단에 다음이 있으면 **무조건** summary 에 포함:
- 수치: `3x faster` → `추론 속도 3배`, `$10M` → `1,000만 달러`, `2M tokens` → `2M 토큰`
- 기능명: `computer use`, `in-app browsing` 같은 신기능 이름은 원문 유지 + 괄호로 한국어 설명 선택
- 날짜: `Apr 16, 2026` → 맥락에 맞게 `4/16 발표`
- 대상: `for enterprises` → `기업용`, `for developers` → `개발자용`
- 파트너·기관명: Google, Broadcom, Mozilla 등 원문 유지

### 원칙 3: lead 가 비어있거나 짧을 때

- 제목이 담은 정보를 풀어서 서술 (예: `MOU for AI safety` → `AI 안전성 협력 MOU 체결` + 맥락이 제목에 있으면 당사자 포함)
- 추측·가정 금지. 모르는 건 쓰지 말 것.

### 원칙 4: 금지 어휘

다음 형용사는 **구체 수치가 뒷받침될 때만** 허용 — 아니면 제거:
- `혁신적`, `획기적`, `놀라운`, `강력한`, `차세대` (수치 없이 쓰면 삭제)
- `~할 예정이다`, `~할 것으로 보인다` (추측 표현)

### 원칙 5: 길이

- 1줄 요약: 60~100자
- 2줄 요약: 총 120~160자
- 3줄: lead 가 정보 풍부할 때만

## 입력 형식

```json
{
  "items": [
    {
      "id": "item_0",
      "title": "Introducing Claude Opus 4.7",
      "lead": "ProductApr 16, 2026Our latest Opus model brings stronger performance across coding, agents, vision, and multi-step tasks, with greater thoroughness and consistency...",
      "source": "Anthropic"
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
      "title_ko": "Claude Opus 4.7 공개",
      "summary": "Anthropic 이 Opus 4.7 을 4/16 공개. 코딩·에이전트·비전·다단계 작업 성능이 향상되고, 이전 Opus 대비 정확도와 일관성에서 개선을 보였다고 밝혔다."
    }
  ]
}
```
