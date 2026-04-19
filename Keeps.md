# Keep 아카이브

`#keep` 태그가 붙은 Daily 노트가 자동 집계됩니다. Daily 노트 안에서 중요한 항목 아래에 `#keep` 태그를 추가하면 됩니다.

## 이번 주 Keep

```dataview
LIST
FROM #keep
WHERE file.mday >= date(today) - dur(7 days)
SORT file.mday DESC
```

## 전체 Keep (최신순)

```dataview
TABLE WITHOUT ID
  file.link AS "출처 노트",
  file.mday AS "Keep 추가일"
FROM #keep
SORT file.mday DESC
```

## 카테고리별

### 거시 (금리·환율·물가)

```dataview
LIST
FROM #keep AND #거시
SORT file.mday DESC
```

### 자산 (부동산·코스피)

```dataview
LIST
FROM #keep AND #자산
SORT file.mday DESC
```

### 글로벌 (연준·나스닥)

```dataview
LIST
FROM #keep AND #글로벌
SORT file.mday DESC
```

### OpenAI

```dataview
LIST
FROM #keep AND #openai
SORT file.mday DESC
```

### Anthropic

```dataview
LIST
FROM #keep AND #anthropic
SORT file.mday DESC
```

### Threads

```dataview
LIST
FROM #keep AND #threads
SORT file.mday DESC
```

### 연구 · 논문

```dataview
LIST
FROM #keep AND #research
SORT file.mday DESC
```
