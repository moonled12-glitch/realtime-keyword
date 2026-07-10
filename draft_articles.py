#!/usr/bin/env python3
# 트렌드 키워드로 Gemini에게 '편집용 블로그 초안'을 받아 drafts/<slug>.md 로 저장.
# - 이미 drafts/ 또는 posts/ 에 있는 slug는 스킵(사용자 편집물 보호)
# - 실행당 상한(MAX_DRAFTS)으로 비용 억제
# - GEMINI_API_KEY 없으면 아무것도 안 함
# 발행은 사람이: drafts/ 에서 골라 편집 → posts/ 로 옮기고 published: true → 커밋
import os
import re
import json
import html
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import generate as g   # get(), GEMINI_KEY, SUMMARY_MODEL, txt() 재사용

KST = timezone(timedelta(hours=9))
DRAFTS_DIR = "drafts"
POSTS_DIR = "posts"
MAX_DRAFTS = 10         # 실행 1회당 신규 초안 상한
POOL_TOP_N = 10         # 소스별 상위 N개 키워드를 후보로

DRAFT_SYSTEM = (
    "너는 한국어 블로그 작가다. 주어진 실시간 검색어와 관련 뉴스 헤드라인을 바탕으로 "
    "블로그 글 '초안'을 Markdown으로 써라. 규칙: "
    "1) 첫 줄에 '# 제목'(클릭하고 싶은 자연스러운 한국어 제목). "
    "2) 도입 1문단 + '## 소제목' 2~3개로 구성, 각 소제목 아래 2~4문장. "
    "3) 헤드라인에 근거하되 사실을 지어내지 말 것. 모르면 '확인이 필요하다'고 쓸 것. "
    "4) 광고성·과장 표현 금지, 정보 전달 중심. "
    "5) 마지막에 한 줄로 '※ 이 글은 초안입니다 — 직접 사실 확인 후 보완하세요.'를 넣어라. "
    "제목과 본문만 출력(설명 금지)."
)


def slugify(keyword):
    s = keyword.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^0-9a-z가-힣\-]", "", s)  # 한글/영숫자/하이픈만
    return re.sub(r"-{2,}", "-", s).strip("-") or "post"


def keyword_pool():
    """prev.json(google/naver 순위)에서 상위 키워드 후보 목록."""
    if not os.path.exists("prev.json"):
        return []
    try:
        d = json.load(open("prev.json", encoding="utf-8"))
    except Exception:
        return []
    pool = []
    for src in ("google", "naver"):
        ranked = sorted(d.get(src, {}).items(), key=lambda kv: kv[1])[:POOL_TOP_N]
        for kw, _ in ranked:
            if kw not in pool:
                pool.append(kw)
    return pool


def google_news_items(keyword, limit=5):
    url = g.GNEWS_RSS.format(urllib.parse.quote(keyword))
    root = ET.fromstring(g.get(url))
    items = []
    for it in root.iter("item"):
        t = g.txt(it.find("title"))
        link = g.txt(it.find("link"))
        if t and link:
            items.append({"title": html.unescape(t), "link": link})
        if len(items) >= limit:
            break
    return items


def existing_slugs():
    slugs = set()
    for d in (DRAFTS_DIR, POSTS_DIR):
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".md"):
                    slugs.add(os.path.splitext(f)[0])
    return slugs


def make_draft(client, keyword, news):
    from google.genai import types
    heads = "\n".join(f"- {n['title']}" for n in news)
    resp = client.models.generate_content(
        model=g.SUMMARY_MODEL,
        contents=f'실시간 검색어: "{keyword}"\n\n관련 뉴스 헤드라인:\n{heads}',
        config=types.GenerateContentConfig(
            system_instruction=DRAFT_SYSTEM, max_output_tokens=1200, temperature=0.6),
    )
    return (resp.text or "").strip()


def main():
    if not g.GEMINI_KEY:
        print("GEMINI_API_KEY 없음 - 초안 생성 건너뜀")
        return
    os.makedirs(DRAFTS_DIR, exist_ok=True)
    try:
        from google import genai
        client = genai.Client(api_key=g.GEMINI_KEY)
    except Exception as e:
        print(f"gemini init failed ({e})")
        return

    have = existing_slugs()
    now = datetime.now(KST)
    made = 0
    for kw in keyword_pool():
        slug = slugify(kw)
        if slug in have or made >= MAX_DRAFTS:
            continue
        try:
            news = google_news_items(kw)
            if not news:
                continue
            article = make_draft(client, kw, news)
            if not article:
                continue
            # 본문에서 제목(# ...) 추출
            mt = re.search(r"^#\s+(.+)$", article, re.M)
            title = mt.group(1).strip() if mt else kw
            body = re.sub(r"^#\s+.+$", "", article, count=1, flags=re.M).strip()
            # 이미지 자리(교체용) — 첫 소제목 앞에 삽입
            ph = (f'<figure class="ph">여기에 "{kw}" 관련 이미지를 넣으세요'
                  f'<br>(라이선스 확인 후 사용)</figure>')
            if "\n## " in body:
                body = body.replace("\n## ", "\n\n" + ph + "\n\n## ", 1)
            else:
                body = ph + "\n\n" + body
            sources = "\n".join(f"- [{html.escape(n['title'])}]({n['link']})" for n in news)
            fm = (f"---\n"
                  f'title: "{title.replace(chr(34), "")}"\n'
                  f"date: {now.strftime('%Y-%m-%d')}\n"
                  f'keyword: "{kw}"\n'
                  f"tags: 실시간검색어, {kw}\n"
                  f'description: "{kw} 관련 이슈 정리"\n'
                  f"published: false\n"
                  f"---\n\n")
            content = fm + body + "\n\n## 관련 뉴스\n" + sources + "\n"
            open(os.path.join(DRAFTS_DIR, f"{slug}.md"), "w", encoding="utf-8").write(content)
            have.add(slug)
            made += 1
        except Exception as e:
            print(f"draft failed for {kw!r}: {e}")
    print(f"drafts created: {made} (model {g.SUMMARY_MODEL})")


if __name__ == "__main__":
    main()
