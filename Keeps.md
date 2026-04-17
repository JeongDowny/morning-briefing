# 💎 Keep 아카이브

> `#keep` 태그가 붙은 Daily 노트가 자동으로 집계됩니다.
> 사용법: 중요한 항목 발견 시 Daily 노트 안에 `#keep` 태그 추가 → 저장 → 이 페이지에 자동 반영

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

### 🌐 거시 (금리·환율·물가)

```dataview
LIST
FROM #keep AND #거시
SORT file.mday DESC
```

### 💰 자산 (부동산·코스피)

```dataview
LIST
FROM #keep AND #자산
SORT file.mday DESC
```

### 🌍 글로벌 (연준·나스닥)

```dataview
LIST
FROM #keep AND #글로벌
SORT file.mday DESC
```
