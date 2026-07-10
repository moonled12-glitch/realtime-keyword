#!/usr/bin/env python3
# 구글 트렌드(한국) + signal.bz 실시간 검색어를 받아 순위 변동을 계산하고 index.html 생성
# GitHub Actions에서 매시간 자동 실행됨
#
# 소스
#  - 구글: Google Trends 인기 급상승 검색어 RSS (geo=KR)
#  - 네이버(형): signal.bz 실시간 검색어 집계 API
#      (네이버는 2021년 공식 실검 폐지 → signal.bz가 사실상 대체 지표로 널리 쓰임)
import json
import os
import sys
import html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

GOOGLE_RSS = "https://trends.google.com/trending/rss?geo=KR"
SIGNAL_API = "https://api.signal.bz/news/realtime"
HDRS = {"User-Agent": "Mozilla/5.0 (compatible; trends-updater/1.0)"}
HT = "{https://trends.google.com/trending/rss}"
KST = timezone(timedelta(hours=9))
MAX_ITEMS = 20          # 화면에 노출할 최대 개수
MAX_NEWS = 3            # 항목당 관련 뉴스 최대 개수

# signal.bz state 코드 → 내부 이동값 (delta 없을 때의 기본 표시)
SIGNAL_STATE = {"n": "new", "+": "up", "-": "down", "s": "same"}


def get(url):
    req = urllib.request.Request(url, headers=HDRS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def txt(el):
    return el.text.strip() if el is not None and el.text else ""


def parse_google(xml_bytes):
    """구글 RSS → [{keyword, traffic, image, news:[{title,url,source}]}]"""
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        keyword = txt(it.find("title"))
        if not keyword:
            continue
        news = []
        for n in it.findall(HT + "news_item")[:MAX_NEWS]:
            title = txt(n.find(HT + "news_item_title"))
            url = txt(n.find(HT + "news_item_url"))
            if title and url:
                news.append({
                    "title": html.unescape(title),
                    "url": url,
                    "source": txt(n.find(HT + "news_item_source")),
                })
        items.append({
            "keyword": keyword,
            "traffic": txt(it.find(HT + "approx_traffic")),
            "news": news,
        })
        if len(items) >= MAX_ITEMS:
            break
    return items


def parse_signal(raw_bytes):
    """signal.bz JSON → [{keyword, summary, state}]"""
    obj = json.loads(raw_bytes)
    items = []
    for e in obj.get("top10", [])[:MAX_ITEMS]:
        kw = (e.get("keyword") or "").strip()
        if not kw:
            continue
        items.append({
            "keyword": kw,
            "summary": e.get("summary", ""),
            "state": e.get("state", ""),
        })
    return items


def load_prev():
    """직전 실행의 소스별 키워드→순위 맵. 구버전(평면) 포맷도 안전 처리."""
    if not os.path.exists("prev.json"):
        return {"google": {}, "naver": {}}
    try:
        data = json.load(open("prev.json", encoding="utf-8"))
    except Exception:
        return {"google": {}, "naver": {}}
    if isinstance(data, dict) and ("google" in data or "naver" in data):
        return {"google": data.get("google", {}), "naver": data.get("naver", {})}
    return {"google": {}, "naver": {}}   # 구버전 포맷은 무시하고 초기화


def movement(keyword, rank, prev_map, fallback_state=""):
    """이전 순위 대비 변동. 이전 스냅샷이 없으면 소스가 준 state로 대체."""
    if keyword in prev_map:
        delta = prev_map[keyword] - rank      # +면 상승, -면 하락
        if delta > 0:
            return {"move": "up", "delta": delta}
        if delta < 0:
            return {"move": "down", "delta": -delta}
        return {"move": "same", "delta": 0}
    if not prev_map and fallback_state in SIGNAL_STATE:
        return {"move": SIGNAL_STATE[fallback_state], "delta": 0}
    return {"move": "new", "delta": 0}


def rank_items(items, prev_map):
    out = []
    for i, it in enumerate(items):
        it = dict(it)
        it["rank"] = i + 1
        it.update(movement(it["keyword"], it["rank"], prev_map, it.get("state", "")))
        it.pop("state", None)
        out.append(it)
    return out


def main():
    prev = load_prev()

    # 구글
    google = []
    try:
        google = rank_items(parse_google(get(GOOGLE_RSS)), prev["google"])
    except Exception as e:
        print(f"google fetch/parse failed: {e}")

    # 네이버(형): signal.bz
    naver = []
    try:
        naver = rank_items(parse_signal(get(SIGNAL_API)), prev["naver"])
    except Exception as e:
        print(f"signal.bz fetch/parse failed: {e}")

    if not google and not naver:
        print("both sources failed; keep existing index.html")
        sys.exit(0)

    now = datetime.now(KST)
    data = {
        "updatedAt": now.strftime("%Y-%m-%d %H:%M"),
        "updatedAtISO": now.isoformat(),
        "google": google,
        "naver": naver,
    }

    tpl = open("template.html", encoding="utf-8").read()
    out = tpl.replace("__TRENDS_DATA__", json.dumps(data, ensure_ascii=False))
    open("index.html", "w", encoding="utf-8").write(out)

    # 다음 실행 비교용 스냅샷 저장 (수집 성공한 소스만 갱신)
    snap = {"google": prev["google"], "naver": prev["naver"]}
    if google:
        snap["google"] = {it["keyword"]: it["rank"] for it in google}
    if naver:
        snap["naver"] = {it["keyword"]: it["rank"] for it in naver}
    json.dump(snap, open("prev.json", "w", encoding="utf-8"), ensure_ascii=False)

    print(f"index.html generated at {data['updatedAt']} KST "
          f"(google={len(google)}, naver={len(naver)})")


if __name__ == "__main__":
    main()
