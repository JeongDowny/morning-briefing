# 📂 아카이브

`#archive` 태그가 붙은 노트가 자동 집계됩니다. 텔레그램 브리핑의 📥 버튼으로 저장됩니다.

## 최근 30일

```dataview
TABLE source AS "출처", date AS "날짜"
FROM #archive
WHERE date >= date(today) - dur(30 days)
SORT date DESC
```

## 소스별

```dataview
TABLE rows.file.link AS "글", rows.date AS "날짜"
FROM #archive
GROUP BY source
```

## 전체 (최신순)

```dataview
TABLE source AS "출처", date AS "날짜"
FROM #archive
SORT date DESC
```
