#!/usr/bin/env python3
# posts/*.md (published: true)만 읽어 blog/ 정적 페이지 + sitemap/rss 생성.
# posts/ 는 읽기 전용(사람이 편집·발행). drafts/ 는 절대 건드리지 않음(자동발행 방지).
import os
import re
import html
import glob
import markdown
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
POSTS_DIR = "posts"
OUT_DIR = "blog"

# 애드센스 퍼블리셔 ID — 승인 후 실제 값(ca-pub-…)으로 교체. 그전엔 광고가 안 뜸(정상).
ADSENSE_CLIENT = os.environ.get("ADSENSE_CLIENT", "").strip() or "ca-pub-XXXXXXXXXXXXXXXX"
SITE_NAME = "실시간 검색어 블로그"


def site_url():
    """origin만 반환. 하위경로는 PREFIX가 담당(이중 경로 방지)."""
    if os.path.exists("CNAME"):
        host = open("CNAME", encoding="utf-8").read().strip()
        if host:
            return f"https://{host}"
    return "https://moonled12-glitch.github.io"


BASE = site_url()
# 프로젝트 페이지(하위경로)면 blog 링크 접두사, 커스텀 도메인이면 루트
PREFIX = "" if os.path.exists("CNAME") else "/realtime-keyword"


def esc(s):
    return html.escape(s or "", quote=True)


# ---------- frontmatter 파싱 (pyyaml 의존성 없이 최소 구현) ----------
def parse_post(path):
    raw = open(path, encoding="utf-8").read()
    meta, body = {}, raw
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
    if m:
        head, body = m.group(1), m.group(2)
        for line in head.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    slug = os.path.splitext(os.path.basename(path))[0]
    tags = [t.strip() for t in re.split(r"[,，]", meta.get("tags", "")) if t.strip()]
    return {
        "slug": slug,
        "title": meta.get("title", slug),
        "date": meta.get("date", ""),
        "keyword": meta.get("keyword", ""),
        "description": meta.get("description", ""),
        "tags": tags,
        "published": str(meta.get("published", "")).lower() in ("true", "1", "yes"),
        "body_md": body.strip(),
    }


def ad_unit(slot_label):
    return (f'<div class="ad"><span class="ad-note">광고</span>'
            f'<ins class="adsbygoogle" style="display:block" '
            f'data-ad-client="{ADSENSE_CLIENT}" data-ad-slot="0000000000" '
            f'data-ad-format="auto" data-full-width-responsive="true" '
            f'data-label="{slot_label}"></ins>'
            f'<script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></div>')


ADSENSE_HEAD = (
    f'<script async '
    f'src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADSENSE_CLIENT}" '
    f'crossorigin="anonymous"></script>' if ADSENSE_CLIENT != "ca-pub-XXXXXXXXXXXXXXXX"
    else '<!-- 애드센스 승인 후 ADSENSE_CLIENT 설정 시 여기에 로더 스크립트가 삽입됩니다 -->'
)

CSS = """
:root{--bg:#0d1017;--card:#161b26;--line:#252c3a;--txt:#e8ecf3;--sub:#8b95a7;--accent:#ff5a3c;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--txt);line-height:1.5;
 font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo","Malgun Gothic",sans-serif;
 -webkit-font-smoothing:antialiased;}
a{color:var(--accent);}
.wrap{max-width:720px;margin:0 auto;padding:18px 16px 60px;}
.nav{display:flex;gap:16px;align-items:center;padding:14px 0;border-bottom:1px solid var(--line);
 font-size:14px;font-weight:600;}
.nav .brand{font-size:17px;font-weight:800;letter-spacing:-.3px;margin-right:auto;}
.nav .brand .dot{color:var(--accent);}
.nav a{color:var(--sub);text-decoration:none;}
.nav a:hover{color:var(--txt);}
.ad{margin:22px 0;padding:10px;border:1px dashed var(--line);border-radius:10px;
 text-align:center;min-height:60px;background:var(--card);}
.ad-note{display:block;font-size:10px;color:var(--sub);letter-spacing:.4px;margin-bottom:4px;}
article h1{font-size:26px;font-weight:800;letter-spacing:-.5px;line-height:1.3;
 text-wrap:balance;margin:20px 0 8px;}
.meta{font-size:12.5px;color:var(--sub);margin-bottom:6px;}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 4px;}
.tags a{font-size:11px;background:var(--card);border:1px solid var(--line);
 padding:3px 9px;border-radius:999px;text-decoration:none;color:var(--sub);}
.content{font-size:16px;line-height:1.75;margin-top:8px;}
.content h2{font-size:20px;font-weight:700;margin:26px 0 8px;}
.content h3{font-size:17px;font-weight:700;margin:20px 0 6px;}
.content p{margin:12px 0;}
.content ul,.content ol{margin:12px 0 12px 22px;}
.content li{margin:5px 0;}
.content img{max-width:100%;border-radius:10px;}
.content blockquote{border-left:3px solid var(--accent);margin:14px 0;padding:4px 14px;color:var(--sub);}
.content a{word-break:break-all;}
.postlist{list-style:none;display:flex;flex-direction:column;gap:14px;margin-top:18px;}
.postlist li{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px;}
.postlist a.t{font-size:18px;font-weight:700;text-decoration:none;color:var(--txt);display:block;}
.postlist .d{font-size:12px;color:var(--sub);margin:4px 0;}
.postlist .x{font-size:14px;color:var(--sub);line-height:1.5;
 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
footer{margin-top:34px;padding-top:16px;border-top:1px solid var(--line);
 font-size:12px;color:var(--sub);line-height:1.9;}
footer a{color:var(--sub);}
"""


def nav():
    return (f'<div class="nav">'
            f'<a class="brand" href="{PREFIX}/">실시간 검색<span class="dot">어</span></a>'
            f'<a href="{PREFIX}/">실시간</a>'
            f'<a href="{PREFIX}/blog/">블로그</a>'
            f'<a href="{PREFIX}/about.html">소개</a></div>')


def foot():
    return (f'<footer>© {SITE_NAME} · '
            f'<a href="{PREFIX}/privacy.html">개인정보처리방침</a> · '
            f'<a href="{PREFIX}/about.html">소개</a><br>'
            f'본 블로그는 실시간 인기 검색어를 소재로 직접 작성·편집한 글을 제공합니다.</footer>')


def page(title, desc, body, canonical):
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="article">
{ADSENSE_HEAD}
<style>{CSS}</style>
</head>
<body><div class="wrap">
{nav()}
{body}
{foot()}
</div></body>
</html>
"""


def render_article(p):
    body_html = markdown.markdown(p["body_md"], extensions=["extra", "sane_lists"])
    tags = "".join(f'<a href="{PREFIX}/blog/">#{esc(t)}</a>' for t in p["tags"])
    canonical = f'{BASE}{PREFIX}/blog/{p["slug"]}.html'
    inner = f"""<article>
  <h1>{esc(p["title"])}</h1>
  <div class="meta">{esc(p["date"])}{' · ' + esc(p["keyword"]) if p["keyword"] else ''}</div>
  {f'<div class="tags">{tags}</div>' if tags else ''}
  {ad_unit("top")}
  <div class="content">{body_html}</div>
  {ad_unit("bottom")}
  <p style="margin-top:20px"><a href="{PREFIX}/blog/">← 목록으로</a></p>
</article>"""
    # 본문 중간 광고: 문단 절반 지점에 삽입
    parts = inner.split("</p>")
    if len(parts) > 3:
        mid = len(parts) // 2
        parts[mid] = parts[mid] + "</p>" + ad_unit("middle")
        inner = "</p>".join(p_ if i == mid else p_ for i, p_ in enumerate(parts))
    return page(p["title"], p["description"] or p["title"], inner, canonical)


def render_index(posts):
    items = ""
    for p in posts:
        items += (f'<li><a class="t" href="{PREFIX}/blog/{p["slug"]}.html">{esc(p["title"])}</a>'
                  f'<div class="d">{esc(p["date"])}{" · " + esc(p["keyword"]) if p["keyword"] else ""}</div>'
                  f'<div class="x">{esc(p["description"])}</div></li>')
    body = f"""<h1 style="font-size:24px;font-weight:800;margin:18px 0 4px;">블로그</h1>
<p style="color:var(--sub);font-size:14px;">실시간 인기 검색어를 소재로 직접 쓴 글</p>
{ad_unit("list-top")}
<ul class="postlist">{items or '<li>아직 발행된 글이 없습니다.</li>'}</ul>"""
    return page(f"블로그 · {SITE_NAME}",
                "실시간 인기 검색어를 소재로 직접 작성한 블로그 글 모음",
                body, f"{BASE}{PREFIX}/blog/")


def build_sitemap(posts):
    urls = [f"{BASE}{PREFIX}/", f"{BASE}{PREFIX}/blog/",
            f"{BASE}{PREFIX}/about.html", f"{BASE}{PREFIX}/privacy.html"]
    urls += [f'{BASE}{PREFIX}/blog/{p["slug"]}.html' for p in posts]
    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f'{body}</urlset>')


def build_rss(posts):
    items = ""
    for p in posts[:20]:
        link = f'{BASE}{PREFIX}/blog/{p["slug"]}.html'
        items += (f"<item><title>{esc(p['title'])}</title><link>{link}</link>"
                  f"<guid>{link}</guid>"
                  f"<description>{esc(p['description'])}</description></item>")
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0"><channel>'
            f'<title>{SITE_NAME}</title><link>{BASE}{PREFIX}/blog/</link>'
            f'<description>실시간 인기 검색어 블로그</description>{items}'
            '</channel></rss>')


PRIVACY_MD = """## 개인정보처리방침

본 사이트(이하 '사이트')는 이용자의 개인정보를 중요하게 생각합니다.

### 1. 수집하는 정보
사이트는 회원가입 없이 이용 가능하며, 이름·이메일 등 개인정보를 직접 수집하지 않습니다.

### 2. 쿠키 및 광고
사이트는 Google AdSense 등 제3자 광고를 게재할 수 있습니다. Google을 포함한 제3자
공급업체는 쿠키를 사용해 이용자의 이전 방문 기록을 바탕으로 광고를 게재할 수 있습니다.
이용자는 [Google 광고 설정](https://www.google.com/settings/ads)에서 맞춤 광고를
비활성화할 수 있습니다.

### 3. 접속 분석
사이트는 트래픽 분석을 위해 접속 로그 등 익명 통계를 활용할 수 있습니다.

### 4. 문의
개인정보 관련 문의는 사이트 운영자에게 연락해 주세요.
"""

ABOUT_MD = """## 소개

이 사이트는 대한민국의 **실시간 인기 검색어**를 한눈에 보여주고, 그중 이슈가 되는
주제를 운영자가 직접 정리·편집해 블로그 글로 제공합니다.

- 실시간 검색어: 구글 트렌드 및 공개 집계 기반
- 블로그: 검색어를 소재로 운영자가 작성·편집한 글

정보의 정확성을 위해 노력하지만, 각 글은 발행 시점 기준이며 최신 사실과 다를 수 있습니다.
"""


def render_static(title, md):
    body = f'<article><div class="content">{markdown.markdown(md, extensions=["extra"])}</div></article>'
    slug = "privacy" if "개인정보" in title else "about"
    return page(f"{title} · {SITE_NAME}", title, body, f"{BASE}{PREFIX}/{slug}.html")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    posts = [parse_post(f) for f in glob.glob(os.path.join(POSTS_DIR, "*.md"))]
    posts = [p for p in posts if p["published"]]
    posts.sort(key=lambda p: p["date"], reverse=True)

    for p in posts:
        open(os.path.join(OUT_DIR, f'{p["slug"]}.html'), "w", encoding="utf-8").write(
            render_article(p))
    open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8").write(render_index(posts))
    open("privacy.html", "w", encoding="utf-8").write(render_static("개인정보처리방침", PRIVACY_MD))
    open("about.html", "w", encoding="utf-8").write(render_static("소개", ABOUT_MD))
    open("sitemap.xml", "w", encoding="utf-8").write(build_sitemap(posts))
    open("rss.xml", "w", encoding="utf-8").write(build_rss(posts))
    print(f"blog built: {len(posts)} post(s) → {OUT_DIR}/, +privacy/about, sitemap.xml, rss.xml "
          f"(base={BASE}{PREFIX})")


if __name__ == "__main__":
    main()
