#!/usr/bin/env python3
# 구글 트렌드(한국) 실시간 검색어를 받아 순위 변동을 계산하고 index.html 생성
# GitHub Actions에서 매시간 자동 실행됨
import json
import os
import sys
import html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

RSS = "https://trends.google.com/trending/rss?geo=KR"
HDRS = {"User-Agent": "Mozilla/5.0 (compatible; trends-updater/1.0)"}
HT = "{https://trends.google.com/trending/rss}"
KST = timezone(timedelta(hours=9))
MAX_ITEMS = 20          # 화면에 노출할 최대 개수
MAX_NEWS = 3            # 항목당 관련 뉴스 최대 개수


def fetch():
    req = urllib.request.Request(RSS, headers=HDRS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def txt(el):
    return el.text.strip() if el is not None and el.text else ""


def parse(xml_bytes):
    """RSS를 파싱해 [{keyword, traffic, image, news:[{title,url,source}]}] 반환"""
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
            "image": txt(it.find(HT + "picture")),
            "news": news,
        })
        if len(items) >= MAX_ITEMS:
            break
    return items


def load_prev():
    """직전 실행의 키워드→순위 맵 (1-based)"""
    if os.path.exists("prev.json"):
        try:
            return json.load(open("prev.json", encoding="utf-8"))
        except Exception:
            return {}
    return {}


def movement(keyword, rank, prev):
    """이전 순위 대비 변동 계산"""
    if keyword not in prev:
        return {"move": "new", "delta": 0}
    delta = prev[keyword] - rank          # +면 상승, -면 하락
    if delta > 0:
        return {"move": "up", "delta": delta}
    if delta < 0:
        return {"move": "down", "delta": -delta}
    return {"move": "same", "delta": 0}


def main():
    try:
        raw = fetch()
        items = parse(raw)
    except Exception as e:
        print(f"fetch/parse failed: {e}")
        # 실패 시 기존 index.html 유지하고 종료 (변경 없음 → Actions가 커밋 안 함)
        sys.exit(0)

    if not items:
        print("no items parsed; keep existing index.html")
        sys.exit(0)

    prev = load_prev()
    ranked = []
    for i, it in enumerate(items):
        rank = i + 1
        it = dict(it)
        it["rank"] = rank
        it.update(movement(it["keyword"], rank, prev))
        ranked.append(it)

    now = datetime.now(KST)
    data = {
        "updatedAt": now.strftime("%Y-%m-%d %H:%M"),
        "updatedAtISO": now.isoformat(),
        "count": len(ranked),
        "items": ranked,
    }

    tpl = open("template.html", encoding="utf-8").read()
    out = tpl.replace("__TRENDS_DATA__", json.dumps(data, ensure_ascii=False))
    open("index.html", "w", encoding="utf-8").write(out)

    # 다음 실행 비교용 스냅샷 저장
    json.dump({it["keyword"]: it["rank"] for it in ranked},
              open("prev.json", "w", encoding="utf-8"), ensure_ascii=False)

    print(f"index.html generated; {len(ranked)} keywords at {data['updatedAt']} KST")


if __name__ == "__main__":
    main()
