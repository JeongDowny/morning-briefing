# AI 개발 블로그 요약 프롬프트

OpenAI / Anthropic 공식 블로그 포스트를 개발자 관점에서 요약한다.

## 출력 요건

- **2~3줄 한국어 요약** (각 줄 최대 80자)
- **개발자가 판단하는 데 필요한 핵심만**: 새 모델·기능·API 변경·가격·제약
- **첫 줄**: "무엇이 발표됐나 / 공개됐나"
- **둘째 줄(필요 시)**: "기존 대비 차이, 실무 영향"
- **리드가 영어라면 한국어로 번역하되 고유명사·제품명은 원문 유지**

## 금지

- "혁신적", "획기적" 같은 마케팅 어휘
- 구체적 수치·이름 없는 추상 표현
- 2문장 초과, 이모지

## 입력 형식

```json
{
  "items": [
    {
      "id": "item_1",
      "title": "Introducing GPT-X",
      "lead": "Today we're releasing GPT-X, our most capable model yet with 3x faster inference...",
      "source": "OpenAI"
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
      "summary": "OpenAI가 GPT-X를 공개, 추론 속도 3배 개선. 컨텍스트 2M 토큰, 가격은 GPT-4 대비 절반 수준."
    }
  ]
}
```
