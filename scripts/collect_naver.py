"""네이버뉴스 경제 언론사 랭킹 수집 (M1).

config/briefing.json 의 naver_news.ranking 설정을 읽어,
네이버 "많이 본 뉴스" 페이지(언론사별 구조)에서 경제 중심 언론사(press_whitelist)의
TOP 5 항목만 모아 상위 top_n 건을 collected/naver.json 으로 저장한다.

설계 배경:
  네이버 랭킹 페이지(popularDay.naver)는 공식적으로 "섹션별 랭킹" URL을 제공하지 않고,
  80+개 언론사별 TOP 5 리스트로 구성된다. 따라서 경제 뉴스를 모으려면
  "경제 전문 언론사"를 화이트리스트로 지정해 그 블록들만 추출하는 전략이 가장 안정적이다.

출력 스키마:
{
  "source": "naver_ranking",
  "collected_at": "2026-04-17T08:00:00+09:00",
  "items": [
    {
      "rank": 1,
      "title": "...",
      "url": "https://n.news.naver.com/article/...",
      "press": "한국경제",
      "lead": null,
      "category": "랭킹"
    }
  ]
}
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "briefing.json"
OUTPUT_DIR = ROOT / "collected"
OUTPUT_PATH = OUTPUT_DIR / "naver.json"

NAVER_RANKING_URL = "https://news.naver.com/main/ranking/popularDay.naver"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def fetch_ranking_html() -> str:
    # 네이버 뉴스는 EUC-KR 응답. requests가 헤더 기반으로 자동 감지하지만 강제 지정해 안정화.
    resp = requests.get(
        NAVER_RANKING_URL,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    resp.encoding = "euc-kr"
    return resp.text


def extract_press_name(header_text: str) -> str:
    """박스 헤더 텍스트에서 언론사명만 깔끔하게 추출.

    네이버 헤더에는 '조선일보랭킹 결과를 더 볼 수 있어요.' 같이 안내문구가 붙는 경우가 있어 정리 필요.
    """
    if not header_text:
        return ""
    return header_text.split("랭킹")[0].strip()


def parse_ranking(html: str, press_whitelist: list[str], top_n: int) -> list[dict[str, Any]]:
    """언론사별 랭킹 박스를 순회하며 화이트리스트 언론사의 TOP 5만 추출, 상위 top_n건 반환.

    박스 구조:
      div.rankingnews_box
        └ strong.rankingnews_name / a.rankingnews_name   (언론사명)
        └ ul.rankingnews_list
            └ li (기사 하나씩)
                └ a (제목 + URL)
    """
    soup = BeautifulSoup(html, "html.parser")
    boxes = soup.select("div.rankingnews_box")

    # 화이트리스트 정규화 (공백·대소문자 완화)
    whitelist_set = {p.strip() for p in press_whitelist}

    collected: list[dict[str, Any]] = []
    rank = 0

    for box in boxes:
        press_el = box.select_one(".rankingnews_name, strong.rankingnews_name, a.rankingnews_name")
        press = extract_press_name(press_el.get_text(strip=True) if press_el else "")
        if press not in whitelist_set:
            continue

        list_items = box.select("ul.rankingnews_list li")
        for li in list_items:
            a_el = li.select_one("a.list_title, a[href*='n.news.naver.com']")
            if not a_el:
                continue
            title = a_el.get_text(strip=True)
            url = a_el.get("href", "")
            if not title or not url:
                continue
            rank += 1
            collected.append(
                {
                    "rank": rank,
                    "title": title,
                    "url": url,
                    "press": press,
                    "lead": None,
                    "category": "랭킹",
                }
            )
            if rank >= top_n:
                return collected

    return collected


def collect() -> dict[str, Any]:
    config = load_config()
    ranking_cfg = config.get("naver_news", {}).get("ranking", {})

    if not ranking_cfg.get("enabled", False):
        print("[collect_naver] ranking.enabled=false → 스킵", file=sys.stderr)
        return {"source": "naver_ranking", "items": []}

    top_n = ranking_cfg.get("top_n", 10)
    whitelist = ranking_cfg.get("press_whitelist", [])
    if not whitelist:
        print("[collect_naver] press_whitelist 비어있음 → 중단", file=sys.stderr)
        return {"source": "naver_ranking", "items": []}

    now_kst = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")

    try:
        html = fetch_ranking_html()
        items = parse_ranking(html, whitelist, top_n)
        print(
            f"[collect_naver] 화이트리스트 {len(whitelist)}개 언론사 → {len(items)}건 수집",
            file=sys.stderr,
        )
    except Exception as e:
        print(f"[collect_naver] 수집 실패: {e}", file=sys.stderr)
        items = []

    return {
        "source": "naver_ranking",
        "collected_at": now_kst,
        "items": items,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(exist_ok=True)
    result = collect()
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(
        f"[collect_naver] 저장 완료: {OUTPUT_PATH.relative_to(ROOT)} (총 {len(result['items'])}건)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
