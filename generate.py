#!/usr/bin/env python3
# 구글 트렌드(한국) + 네이버 실시간 검색어를 받아 순위 변동을 계산하고 index.html 생성
# GitHub Actions에서 매시간 자동 실행됨
#
# 소스
#  - 구글: Google Trends 인기 급상승 검색어 RSS (geo=KR)
#  - 네이버:
#      (A) 네이버 데이터랩 검색어트렌드 API  ← NAVER_CLIENT_ID/SECRET 환경변수가 있으면 사용
#          · 데이터랩은 "발견"이 아니라 "지정 키워드의 상대 추이"만 주므로,
#            구글 트렌드 키워드를 후보로 삼아 네이버 검색비중 순으로 재정렬한다.
#          · 요청당 최대 5개 그룹만 상호 비교되어, 공통 앵커("날씨")로 배치 간 정규화한다.
#      (B) signal.bz 실시간 검색어 집계     ← 키가 없으면 자동 폴백 (네이버는 2021년 공식 실검 폐지)
import json
import os
import sys
import time
import html
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

GOOGLE_RSS = "https://trends.google.com/trending/rss?geo=KR"
SIGNAL_API = "https://api.signal.bz/news/realtime"
DATALAB_API = "https://openapi.naver.com/v1/datalab/search"
GNEWS_RSS = "https://news.google.com/rss/search?q={}&hl=ko&gl=KR&ceid=KR:ko"
HDRS = {"User-Agent": "Mozilla/5.0 (compatible; trends-updater/1.0)"}
HT = "{https://trends.google.com/trending/rss}"
KST = timezone(timedelta(hours=9))
MAX_ITEMS = 20          # 화면에 노출할 최대 개수
MAX_NEWS = 3            # 항목당 관련 뉴스 최대 개수

NAVER_ID = os.environ.get("NAVER_CLIENT_ID", "").strip()
NAVER_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
DATALAB_ANCHOR = "날씨"   # 배치 간 정규화용 기준 검색어 (항상 검색량이 큰 일반어)

# AI 요약 (Google Gemini, 무료 API) — 키가 있으면 새 키워드만 요약해 캐시
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "").strip() or "gemini-flash-lite-latest"
SUMMARIES_FILE = "summaries.json"
SUMMARY_TOP_N = 10      # 소스별 상위 N개만 요약 대상
MAX_NEW_SUMMARIES = 12  # 실행 1회당 신규 요약 상한 (비용 캡)
SUMMARY_CACHE_MAX = 120 # 캐시 보존 상한 (회전 대비, 재생성/할당량 절약)
GEMINI_SLEEP = 4.5      # 호출 간격(초) — Gemini 무료 분당 한도(RPM) 회피

SIGNAL_STATE = {"n": "new", "+": "up", "-": "down", "s": "same"}

# 홈(실시간 보드) 애드센스 — 승인 후 ADSENSE_CLIENT(ca-pub-…) 설정 시 활성화. 자동광고도 이 로더로 동작.
ADSENSE_CLIENT = os.environ.get("ADSENSE_CLIENT", "").strip() or "ca-pub-XXXXXXXXXXXXXXXX"
_ADS_ON = ADSENSE_CLIENT != "ca-pub-XXXXXXXXXXXXXXXX"
ADSENSE_HEAD = (
    f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    f'?client={ADSENSE_CLIENT}" crossorigin="anonymous"></script>' if _ADS_ON
    else '<!-- 애드센스 승인 후 ADSENSE_CLIENT 설정 시 로더/자동광고 스크립트가 삽입됩니다 -->')


def ad_html(label):
    return ('<div class="ad"><span class="ad-note">광고</span>'
            f'<ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_CLIENT}" '
            f'data-ad-slot="0000000000" data-ad-format="auto" data-full-width-responsive="true" '
            f'data-label="{label}"></ins>'
            '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>')


def rail_html(label):
    return (f'<div class="rail rail-{label}"><span class="ad-note">광고</span>'
            f'<ins class="adsbygoogle" data-ad-client="{ADSENSE_CLIENT}" '
            f'data-ad-slot="0000000000" data-label="home-{label}"></ins>'
            '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>')


def get(url):
    req = urllib.request.Request(url, headers=HDRS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def post_json(url, body, headers):
    data = json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json", **headers}
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def txt(el):
    return el.text.strip() if el is not None and el.text else ""


# ---------- 구글 ----------
def parse_google(xml_bytes):
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
                    "image": txt(n.find(HT + "news_item_picture")),
                })
        items.append({"keyword": keyword,
                      "traffic": txt(it.find(HT + "approx_traffic")),
                      "image": txt(it.find(HT + "picture")),
                      "news": news})
        if len(items) >= MAX_ITEMS:
            break
    return items


# ---------- 네이버 (B) signal.bz ----------
def parse_signal(raw_bytes):
    obj = json.loads(raw_bytes)
    items = []
    for e in obj.get("top10", [])[:MAX_ITEMS]:
        kw = (e.get("keyword") or "").strip()
        if not kw:
            continue
        items.append({"keyword": kw, "summary": e.get("summary", ""),
                      "state": e.get("state", "")})
    return items


# ---------- 네이버 (A) 데이터랩 ----------
def datalab_ratio(keywords):
    """키워드별 '최근일 검색비중(앵커=날씨 기준 정규화)'을 dict로 반환."""
    end = datetime.now(KST).date()
    start = end - timedelta(days=7)
    headers = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
    scores = {}
    batch = [k for k in keywords if k and k != DATALAB_ANCHOR][:MAX_ITEMS]
    # 4개 후보 + 앵커 1개 = 5그룹씩
    for i in range(0, len(batch), 4):
        chunk = batch[i:i + 4]
        groups = [{"groupName": DATALAB_ANCHOR, "keywords": [DATALAB_ANCHOR]}]
        groups += [{"groupName": k, "keywords": [k]} for k in chunk]
        body = {"startDate": start.isoformat(), "endDate": end.isoformat(),
                "timeUnit": "date", "keywordGroups": groups}
        res = post_json(DATALAB_API, body, headers)
        latest = {}
        for g in res.get("results", []):
            pts = g.get("data", [])
            latest[g.get("title")] = pts[-1]["ratio"] if pts else 0.0
        anchor = latest.get(DATALAB_ANCHOR, 0.0)
        for k in chunk:
            raw = latest.get(k, 0.0)
            scores[k] = raw if anchor <= 0 else raw / anchor * 100.0
    return scores


def build_naver_datalab(google_keywords):
    """구글 후보를 네이버 검색비중 순으로 재정렬. 실패/빈약하면 None 반환(→폴백)."""
    scores = datalab_ratio(google_keywords)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    ranked = [(k, s) for k, s in ranked if s > 0]
    if len(ranked) < 3:
        return None
    top = ranked[0][1]
    items = []
    for k, s in ranked[:MAX_ITEMS]:
        idx = round(s / top * 100) if top > 0 else 0     # 1위=100으로 환산
        items.append({"keyword": k, "metric": f"네이버 검색비중 {idx}"})
    return items


# ---------- AI 요약 ----------
def load_summaries():
    if os.path.exists(SUMMARIES_FILE):
        try:
            return json.load(open(SUMMARIES_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def news_for(keyword, limit=3):
    """구글 뉴스 RSS에서 키워드 관련 기사 [{title,url,source}] (네이버 탭 관련기사용)."""
    root = ET.fromstring(get(GNEWS_RSS.format(urllib.parse.quote(keyword))))
    out = []
    for it in root.iter("item"):
        t = txt(it.find("title"))
        link = txt(it.find("link"))
        s = it.find("source")
        if t and link:
            out.append({"title": html.unescape(t), "url": link,
                        "source": (s.text or "").strip() if s is not None else ""})
        if len(out) >= limit:
            break
    return out


def google_news_titles(keyword, limit=5):
    """구글 뉴스 RSS에서 키워드 관련 최신 헤드라인 제목만 추출."""
    raw = get(GNEWS_RSS.format(urllib.parse.quote(keyword)))
    root = ET.fromstring(raw)
    titles = []
    for it in root.iter("item"):
        t = txt(it.find("title"))
        if t:
            titles.append(html.unescape(t))
        if len(titles) >= limit:
            break
    return titles


SUMMARY_SYSTEM = ("너는 실시간 검색어 큐레이터다. 아래 뉴스 헤드라인만 근거로 "
                  "이 키워드가 지금 왜 화제인지 한국어로 2~3문장으로 중립적이게 요약해라. "
                  "추측·과장 금지, 헤드라인에 없는 사실 추가 금지. 요약 본문만 출력.")


def ai_summary(client, keyword, headlines):
    from google.genai import types
    joined = "\n".join(f"- {h}" for h in headlines)
    resp = client.models.generate_content(
        model=SUMMARY_MODEL,
        contents=f'키워드: "{keyword}"\n\n관련 뉴스:\n{joined}',
        config=types.GenerateContentConfig(
            system_instruction=SUMMARY_SYSTEM,
            max_output_tokens=400,
            temperature=0.3,
        ),
    )
    return (resp.text or "").strip()


def build_summaries(google, naver, cache):
    """새 키워드만 요약해 캐시 갱신. 표시는 캐시만 있으면 되므로 키 없이도 유지."""
    wanted = []
    for it in google[:SUMMARY_TOP_N] + naver[:SUMMARY_TOP_N]:
        kw = it["keyword"]
        if kw not in wanted:
            wanted.append(kw)

    if GEMINI_KEY:
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_KEY)
        except Exception as e:
            print(f"gemini init failed ({e}); skip summary generation")
            client = None
        if client:
            made = 0
            for kw in wanted:
                if kw in cache:
                    continue
                if made >= MAX_NEW_SUMMARIES:
                    print(f"summary cap reached ({MAX_NEW_SUMMARIES}); rest next run")
                    break
                try:
                    titles = google_news_titles(kw)
                    if not titles:
                        continue
                    cache[kw] = ai_summary(client, kw, titles)
                    made += 1
                    time.sleep(GEMINI_SLEEP)   # RPM 회피
                except Exception as e:
                    print(f"summary failed for {kw!r}: {e}")
            print(f"AI summaries: {made} new via {SUMMARY_MODEL}")

    # 회전 대비: 현재 키워드 우선 보존 + 기존 캐시도 최대치까지 유지(재생성/할당량 절약)
    keep = {kw: cache[kw] for kw in wanted if kw in cache}
    for kw, v in cache.items():
        if len(keep) >= SUMMARY_CACHE_MAX:
            break
        keep.setdefault(kw, v)
    for it in google + naver:
        if it["keyword"] in keep:
            it["aiSummary"] = keep[it["keyword"]]
    return keep


# ---------- 공통 ----------
def load_prev():
    if not os.path.exists("prev.json"):
        return {"google": {}, "naver": {}}
    try:
        data = json.load(open("prev.json", encoding="utf-8"))
    except Exception:
        return {"google": {}, "naver": {}}
    if isinstance(data, dict) and ("google" in data or "naver" in data):
        return {"google": data.get("google", {}), "naver": data.get("naver", {})}
    return {"google": {}, "naver": {}}


def movement(keyword, rank, prev_map, fallback_state=""):
    if keyword in prev_map:
        delta = prev_map[keyword] - rank
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

    # 네이버: 데이터랩(키 있음) 우선, 실패 시 signal.bz 폴백
    naver, naver_source = [], "signal"
    google_kws = [it["keyword"] for it in google]
    if NAVER_ID and NAVER_SECRET and google_kws:
        try:
            dl = build_naver_datalab(google_kws)
            if dl:
                naver, naver_source = rank_items(dl, prev["naver"]), "datalab"
            else:
                print("datalab returned too few results; falling back to signal.bz")
        except Exception as e:
            print(f"datalab failed ({e}); falling back to signal.bz")
    if not naver:
        try:
            naver = rank_items(parse_signal(get(SIGNAL_API)), prev["naver"])
            naver_source = "signal"
        except Exception as e:
            print(f"signal.bz fetch/parse failed: {e}")

    if not google and not naver:
        print("both sources failed; keep existing index.html")
        sys.exit(0)

    # 네이버 항목에 관련 기사 붙이기(구글 뉴스 RSS) — 구글 탭처럼 패널에 노출
    if naver_source == "signal":
        for it in naver:
            try:
                it["news"] = news_for(it["keyword"])
            except Exception:
                it["news"] = []

    # AI 요약(캐시 기반, 새 키워드만 생성) — 항목에 aiSummary 부착
    summaries = build_summaries(google, naver, load_summaries())
    json.dump(summaries, open(SUMMARIES_FILE, "w", encoding="utf-8"),
              ensure_ascii=False)

    now = datetime.now(KST)
    data = {
        "updatedAt": now.strftime("%Y-%m-%d %H:%M"),
        "updatedAtISO": now.isoformat(),
        "google": google,
        "naver": naver,
        "naverSource": naver_source,
    }

    tpl = open("template.html", encoding="utf-8").read()
    out = (tpl.replace("__TRENDS_DATA__", json.dumps(data, ensure_ascii=False))
              .replace("__ADSENSE_HEAD__", ADSENSE_HEAD)
              .replace("__AD_TOP__", ad_html("home-top"))
              .replace("__AD_BOTTOM__", ad_html("home-bottom"))
              .replace("__AD_LEFT__", rail_html("left"))
              .replace("__AD_RIGHT__", rail_html("right")))
    open("index.html", "w", encoding="utf-8").write(out)

    snap = {"google": prev["google"], "naver": prev["naver"]}
    if google:
        snap["google"] = {it["keyword"]: it["rank"] for it in google}
    if naver:
        snap["naver"] = {it["keyword"]: it["rank"] for it in naver}
    json.dump(snap, open("prev.json", "w", encoding="utf-8"), ensure_ascii=False)

    print(f"index.html generated at {data['updatedAt']} KST "
          f"(google={len(google)}, naver={len(naver)} via {naver_source})")


if __name__ == "__main__":
    main()
