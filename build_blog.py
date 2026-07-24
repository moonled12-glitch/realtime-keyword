#!/usr/bin/env python3
# posts/*.md (published: true)만 읽어 blog/ 정적 페이지 + sitemap/rss 생성.
# posts/ 는 읽기 전용(사람이 편집·발행). drafts/ 는 절대 건드리지 않음(자동발행 방지).
# 디자인은 홈(index)과 동일 테마(라이트 기본 + 다크 토글, Noto Sans KR, 초록 accent).
import os
import re
import html
import glob
import json
import urllib.parse
import markdown
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
POSTS_DIR = "posts"
OUT_DIR = "blog"

ADSENSE_CLIENT = os.environ.get("ADSENSE_CLIENT", "").strip() or "ca-pub-XXXXXXXXXXXXXXXX"
SITE_NAME = "키워드픽"


def site_url():
    if os.path.exists("CNAME"):
        host = open("CNAME", encoding="utf-8").read().strip()
        if host:
            return f"https://{host}"
    return "https://moonled12-glitch.github.io"


BASE = site_url()
PREFIX = "" if os.path.exists("CNAME") else "/realtime-keyword"


def esc(s):
    return html.escape(s or "", quote=True)


# ---------- frontmatter 파싱 ----------
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
    body = body.strip()
    return {
        "slug": slug,
        "title": meta.get("title", slug),
        "date": meta.get("date", ""),
        "keyword": meta.get("keyword", ""),
        "description": meta.get("description", ""),
        "tags": tags,
        "category": (meta.get("category") or "기타").strip() or "기타",
        "published": str(meta.get("published", "")).lower() in ("true", "1", "yes"),
        "body_md": body,
        "thumb": first_image(body),  # 목록 썸네일용 첫 이미지
    }


def first_image(body):
    """본문에서 첫 이미지 URL 추출(썸네일용). placeholder(figure.ph)는 img가 없어 자동 제외."""
    m = re.search(r'<img[^>]+src="([^"]+)"', body)
    if m:
        return m.group(1)
    m = re.search(r'!\[[^\]]*\]\(([^)\s]+)', body)  # 마크다운 이미지 ![](url)
    return m.group(1) if m else ""


# ---------- 광고 (자리표시자 + 자동광고 로더) ----------
def adbox():
    return '<div class="ad">광고 · 반응형</div>'


ADSENSE_HEAD = (
    f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
    f'?client={ADSENSE_CLIENT}" crossorigin="anonymous"></script>' if ADSENSE_CLIENT != "ca-pub-XXXXXXXXXXXXXXXX"
    else '<!-- 애드센스 승인 후 ADSENSE_CLIENT 설정 시 로더/자동광고 스크립트 삽입 -->'
)

THEME_INIT = ("<script>(function(){try{var t=localStorage.getItem('theme');"
              "if(t)document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>")
THEME_JS = ("<script>(function(){var b=document.getElementById('themeBtn');if(!b)return;"
            "function cur(){return document.documentElement.getAttribute('data-theme')||'light';}"
            "function ap(t){document.documentElement.setAttribute('data-theme',t);"
            "try{localStorage.setItem('theme',t);}catch(e){}b.textContent=(t==='dark')?'\\u2600\\ufe0f':'\\ud83c\\udf19';}"
            "b.textContent=(cur()==='dark')?'\\u2600\\ufe0f':'\\ud83c\\udf19';"
            "b.addEventListener('click',function(){ap(cur()==='dark'?'light':'dark');});})();</script>")

CSS = """
:root{--bg:#f1f3f4;--surface:#fff;--text:#191c1f;--muted:#767b80;--border:#e5e8ea;
 --accent:#0b7d63;--accent-soft:#e6f4ef;--adbg:#f0f2f3;--shadow:0 1px 3px rgba(20,30,40,.06);}
html[data-theme="dark"]{--bg:#12151a;--surface:#1a1e25;--text:#e9ebee;--muted:#8b9299;
 --border:#2a2f38;--accent:#2fbf8f;--accent-soft:#12281f;--adbg:#181b21;--shadow:0 1px 3px rgba(0,0,0,.3);}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--text);font-family:'Noto Sans KR',system-ui,sans-serif;
 -webkit-font-smoothing:antialiased;transition:background .25s,color .25s;}
a{color:inherit;}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px;}
.content-wrap{max-width:720px;margin:0 auto;padding:0 20px;}
/* 2단 레이아웃(본문 + 우측 사이드바) */
.layout{display:flex;gap:28px;align-items:flex-start;}
.content-col{flex:1;min-width:0;max-width:720px;}
.sidebar{flex:0 0 300px;position:sticky;top:72px;}
@media(max-width:940px){.layout{flex-direction:column;}.sidebar{flex:auto;width:100%;position:static;}.content-col{max-width:none;}}
.side-card{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:15px 16px;margin-bottom:16px;box-shadow:var(--shadow);}
.side-h{font-size:15px;font-weight:800;margin:0 0 8px;}
.rank-list{list-style:none;margin:0;padding:0;}
.rank-list a{display:flex;align-items:center;gap:10px;padding:7px 4px;text-decoration:none;color:var(--text);font-size:14px;border-radius:6px;}
.rank-list a:hover{background:var(--bg);color:var(--accent);}
.rank-list .rk{flex:0 0 20px;text-align:center;font-weight:800;color:var(--accent);font-size:13px;}
.rank-list .rkw{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
/* 실시간 검색어 보드(홈과 동일 구조: 순위·AI요약·관련뉴스, 자동 fetch) */
.side-rt-head{display:flex;align-items:baseline;justify-content:space-between;gap:6px;margin-bottom:6px;}
.side-rt-head .side-h{margin:0;}
.rt-time{font-size:11px;color:var(--muted);white-space:nowrap;}
.rt-item{border-bottom:1px solid var(--border);}
.rt-item:last-child{border-bottom:0;}
.rt-row{width:100%;display:flex;align-items:center;gap:9px;padding:8px 2px;background:none;border:0;cursor:pointer;text-align:left;color:var(--text);font-size:14px;font-family:inherit;}
.rt-row:hover{color:var(--accent);}
.rt-rk{flex:0 0 18px;text-align:center;font-weight:800;color:var(--accent);font-size:13px;}
.rt-kw{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600;}
.rt-b{flex:0 0 auto;font-size:10px;font-weight:800;}
.rt-b.up{color:#e5484d;} .rt-b.down{color:#3b82f6;} .rt-b.new{color:var(--accent);} .rt-b.same{color:var(--muted);}
.rt-panel{display:none;padding:2px 2px 12px 29px;}
.rt-item.open .rt-panel{display:block;}
.rt-sum{font-size:12.5px;line-height:1.6;color:var(--text);background:var(--accent-soft);border-radius:8px;padding:9px 11px;margin-bottom:8px;}
.rt-news{display:flex;flex-direction:column;gap:5px;}
.rt-news a{font-size:12px;color:var(--muted);text-decoration:none;line-height:1.4;}
.rt-news a:hover{color:var(--accent);}
.side-posts{list-style:none;margin:0;padding:0;}
.side-posts a{display:flex;gap:10px;align-items:center;padding:6px 4px;text-decoration:none;color:var(--text);border-radius:8px;}
.side-posts a:hover{background:var(--bg);}
.sp-thumb{flex:0 0 54px;width:54px;height:40px;border-radius:6px;overflow:hidden;background:var(--bg);display:block;}
.sp-thumb img{width:100%;height:100%;object-fit:cover;}
.sp-noimg{background:var(--border);}
.sp-t{font-size:13px;line-height:1.4;font-weight:600;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
/* 글 본문 카드: 페이지 배경과 구분되도록 면 처리 */
.post{background:var(--surface);border:1px solid var(--border);border-radius:16px;
 padding:28px 32px;margin:0 0 8px;box-shadow:0 1px 3px rgba(0,0,0,.04);}
@media(max-width:640px){.post{padding:22px 18px;border-radius:12px;}}
.ad-top{width:100%;display:flex;justify-content:center;padding:8px 20px 0;}
.ad-top>div{width:100%;max-width:970px;height:56px;background:var(--adbg);border:1px dashed var(--border);
 border-radius:8px;display:flex;align-items:center;justify-content:center;color:var(--muted);
 font-size:11px;letter-spacing:.14em;font-family:ui-monospace,monospace;}
.ad{margin:22px 0;height:90px;background:var(--adbg);border:1px dashed var(--border);border-radius:10px;
 display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:11px;
 letter-spacing:.14em;font-family:ui-monospace,monospace;}
header{position:sticky;top:0;z-index:20;background:var(--surface);border-bottom:1px solid var(--border);}
header .wrap{display:flex;align-items:center;gap:20px;padding-top:11px;padding-bottom:11px;}
.logo{text-decoration:none;display:flex;align-items:center;gap:8px;flex-shrink:0;}
.logo .mark{width:26px;height:26px;border-radius:8px;background:var(--accent);color:#fff;
 font-weight:900;font-size:15px;display:flex;align-items:center;justify-content:center;}
.logo .name{font-weight:900;font-size:19px;letter-spacing:-.02em;}
nav.main{display:flex;gap:2px;margin-left:6px;}
nav.main a{text-decoration:none;font-size:14px;font-weight:500;color:var(--muted);padding:7px 12px;border-radius:8px;}
nav.main a:hover{background:var(--bg);}
nav.main a.active{color:var(--accent);font-weight:700;background:var(--accent-soft);}
.theme-btn{margin-left:auto;width:36px;height:36px;border-radius:9px;border:1px solid var(--border);
 background:var(--surface);color:var(--text);cursor:pointer;font-size:15px;display:flex;
 align-items:center;justify-content:center;}
.theme-btn:hover{background:var(--bg);}
main{padding:26px 0 50px;}
article h1{font-size:28px;font-weight:900;letter-spacing:-.02em;line-height:1.32;margin:4px 0 8px;text-wrap:balance;}
.meta{font-size:13px;color:var(--muted);margin-bottom:4px;}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0;}
.tags a{font-size:11px;background:var(--surface);border:1px solid var(--border);padding:3px 9px;
 border-radius:999px;text-decoration:none;color:var(--muted);}
.article-body{font-size:16px;line-height:1.85;}
.article-body h2{font-size:20px;font-weight:800;margin:28px 0 8px;letter-spacing:-.01em;}
.article-body h3{font-size:17px;font-weight:700;margin:20px 0 6px;}
.article-body p{margin:13px 0;}
.article-body ul,.article-body ol{margin:13px 0 13px 22px;}
.article-body li{margin:5px 0;}
.article-body a{color:var(--accent);word-break:break-all;}
.article-body blockquote{border-left:3px solid var(--accent);margin:14px 0;padding:4px 14px;color:var(--muted);}
.article-body img{max-width:100%;height:auto;border-radius:10px;display:block;}
.article-body figure{margin:20px auto;text-align:center;}
.article-body figure img{max-width:100%;height:auto;border-radius:10px;display:inline-block;}
/* 이미지 크기 옵션: figure class 로 조절 (기본=중간) */
.article-body figure.small{max-width:340px;}
.article-body figure.medium{max-width:560px;}
.article-body figure.large{max-width:100%;}
.article-body figcaption{font-size:12px;color:var(--muted);text-align:center;margin-top:6px;}
.article-body figure.ph{background:var(--surface);border:1px dashed var(--border);border-radius:10px;
 min-height:200px;display:flex;align-items:center;justify-content:center;text-align:center;padding:20px;
 color:var(--muted);font-size:13px;line-height:1.6;}
.ai-notice{margin-top:22px;padding:11px 14px;background:var(--bg);border:1px solid var(--border);
 border-radius:8px;font-size:12.5px;color:var(--muted);line-height:1.5;}
.backlink{display:inline-block;margin-top:24px;color:var(--accent);text-decoration:none;font-weight:700;font-size:14px;}
.page-h1{font-size:26px;font-weight:900;letter-spacing:-.02em;margin:0 0 3px;}
.page-sub{font-size:14px;color:var(--muted);margin:0 0 18px;}
/* 카테고리 필터 바 */
.catbar{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px;}
.catbtn{font-size:13px;font-weight:700;padding:7px 14px;border-radius:999px;cursor:pointer;
 border:1px solid var(--border);background:var(--surface);color:var(--muted);}
.catbtn:hover{color:var(--text);}
.catbtn.on{background:var(--accent);border-color:var(--accent);color:#fff;}
/* 목록 카테고리 뱃지 */
.cat-badge{display:inline-block;font-size:11px;font-weight:700;color:var(--accent);
 background:var(--accent-soft);padding:2px 8px;border-radius:999px;margin-bottom:5px;}
/* 페이지네이션 */
.pager{display:flex;flex-wrap:wrap;justify-content:center;gap:6px;margin:26px 0 6px;}
.pg{min-width:36px;height:36px;padding:0 10px;border-radius:8px;cursor:pointer;font-size:14px;font-weight:700;
 border:1px solid var(--border);background:var(--surface);color:var(--text);}
.pg:hover{border-color:var(--accent);color:var(--accent);}
.pg.on{background:var(--accent);border-color:var(--accent);color:#fff;}
.postlist{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:14px;}
.postlist li{background:var(--surface);border:1px solid var(--border);border-radius:14px;
 box-shadow:var(--shadow);overflow:hidden;}
.pl-link{display:flex;gap:14px;align-items:center;padding:14px 16px;text-decoration:none;color:inherit;}
.pl-thumb{flex:0 0 auto;width:132px;height:90px;border-radius:10px;overflow:hidden;background:var(--bg);}
.pl-thumb img{width:100%;height:100%;object-fit:cover;display:block;}
.pl-text{min-width:0;}
.postlist .t{font-size:18px;font-weight:800;color:var(--text);display:block;letter-spacing:-.01em;}
.pl-link:hover .t{color:var(--accent);}
.postlist .d{font-size:12px;color:var(--muted);margin:4px 0;}
.postlist .x{font-size:14px;color:var(--muted);line-height:1.5;display:-webkit-box;
 -webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
@media(max-width:520px){.pl-thumb{width:100px;height:74px;}.pl-link{gap:11px;padding:12px 13px;}.postlist .t{font-size:16px;}}
.static-body{font-size:15.5px;line-height:1.85;}
.static-body h2{font-size:22px;font-weight:900;margin:6px 0 12px;letter-spacing:-.02em;}
.static-body h3{font-size:16px;font-weight:800;margin:20px 0 6px;}
.static-body p{margin:12px 0;} .static-body a{color:var(--accent);}
.static-body ul{margin:12px 0 12px 20px;} .static-body li{margin:5px 0;}
footer{border-top:1px solid var(--border);background:var(--surface);margin-top:40px;}
footer .wrap{padding-top:24px;padding-bottom:24px;display:flex;flex-wrap:wrap;gap:12px 24px;
 align-items:center;justify-content:space-between;}
.foot-brand{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted);}
.foot-brand b{font-weight:900;color:var(--text);}
footer nav{display:flex;gap:18px;font-size:13px;}
footer nav a{color:var(--muted);text-decoration:none;}
footer nav a:hover{color:var(--text);}
"""


def header(active):
    def link(name, href):
        cls = ' class="active"' if name == active else ''
        return f'<a{cls} href="{href}">{name}</a>'
    return (f'<div class="ad-top"><div>광고 · 728 × 90</div></div>'
            f'<header><div class="wrap">'
            f'<a class="logo" href="{PREFIX}/"><span class="mark">K</span><span class="name">키워드픽</span></a>'
            f'<nav class="main">{link("실시간", PREFIX+"/")}{link("블로그", PREFIX+"/blog/")}'
            f'{link("소개", PREFIX+"/about.html")}</nav>'
            f'<button class="theme-btn" id="themeBtn" aria-label="다크/라이트 모드 전환">🌙</button>'
            f'</div></header>')


def foot():
    return (f'<footer><div class="wrap">'
            f'<div class="foot-brand"><b>키워드픽</b><span>데이터 출처: 구글 트렌드 · signal.bz</span></div>'
            f'<nav><a href="{PREFIX}/about.html">소개</a><a href="{PREFIX}/blog/">블로그</a>'
            f'<a href="{PREFIX}/privacy.html">개인정보처리방침</a></nav>'
            f'</div></footer>')


def load_trends():
    """prev.json에서 현재 구글 실시간 검색어 상위 10개."""
    try:
        d = json.load(open("prev.json", encoding="utf-8"))
        g = sorted(d.get("google", {}).items(), key=lambda x: x[1])
        return [k for k, _ in g][:10]
    except Exception:
        return []


RT_SCRIPT = """<script>
(function(){
  var PREFIX="__PREFIX__";
  function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  function badge(m,d){
    if(m==='up')return '<span class="rt-b up">\\u25B2'+d+'</span>';
    if(m==='down')return '<span class="rt-b down">\\u25BC'+d+'</span>';
    if(m==='new')return '<span class="rt-b new">NEW</span>';
    return '<span class="rt-b same">\\u2013</span>';
  }
  fetch(PREFIX+'/trends.json?_='+Date.now()).then(function(r){return r.json();}).then(function(d){
    var t=document.getElementById('rtTime'); if(t&&d.updatedAt)t.textContent=d.updatedAt+' 기준';
    var board=document.getElementById('rtBoard'); if(!board)return;
    var items=(d.naver&&d.naver.length?d.naver:d.google)||[];
    items=items.slice(0,10);
    if(!items.length)return;
    board.innerHTML=items.map(function(it,i){
      var sum=it.aiSummary||it.summary||'';
      var news=(it.news||[]).slice(0,3).map(function(n){
        return '<a href="'+n.url+'" target="_blank" rel="noopener">'+esc(n.title)+'</a>';}).join('');
      var panel=(sum?'<div class="rt-sum">\\uD83E\\uDD16 '+esc(sum)+'</div>':'')+(news?'<div class="rt-news">'+news+'</div>':'');
      return '<div class="rt-item">'
        +'<button type="button" class="rt-row" aria-expanded="false">'
        +'<span class="rt-rk">'+(i+1)+'</span><span class="rt-kw">'+esc(it.keyword)+'</span>'+badge(it.move,it.delta)+'</button>'
        +(panel?'<div class="rt-panel">'+panel+'</div>':'')+'</div>';
    }).join('');
    board.querySelectorAll('.rt-row').forEach(function(b){
      b.addEventListener('click',function(){
        var it=b.parentNode; it.classList.toggle('open');
        b.setAttribute('aria-expanded', it.classList.contains('open')?'true':'false');
      });
    });
  }).catch(function(){});
})();
</script>"""


def build_sidebar(posts, current_slug=None):
    trends = load_trends()
    # JS/JSON 실패 시 폴백용 기본 목록(서버 렌더)
    fb = ""
    for i, kw in enumerate(trends, 1):
        url = "https://news.google.com/search?q=" + urllib.parse.quote(kw) + "&hl=ko&gl=KR&ceid=KR:ko"
        fb += (f'<li><a href="{url}" target="_blank" rel="noopener">'
               f'<span class="rk">{i}</span><span class="rkw">{esc(kw)}</span></a></li>')
    trend_card = (
        '<div class="side-card">'
        '<div class="side-rt-head"><h3 class="side-h">🔥 실시간 검색어</h3>'
        '<span class="rt-time" id="rtTime"></span></div>'
        f'<div id="rtBoard"><ol class="rank-list">{fb}</ol></div>'
        '</div>' + RT_SCRIPT.replace("__PREFIX__", PREFIX)
    )
    feat = [p for p in posts if p["slug"] != current_slug][:6]
    post_items = ""
    for p in feat:
        thumb = (f'<span class="sp-thumb"><img src="{esc(p["thumb"])}" alt="" loading="lazy"></span>'
                 if p.get("thumb") else '<span class="sp-thumb sp-noimg"></span>')
        post_items += (f'<li><a href="{PREFIX}/blog/{p["slug"]}.html">{thumb}'
                       f'<span class="sp-t">{esc(p["title"])}</span></a></li>')
    posts_card = (f'<div class="side-card"><h3 class="side-h">📝 블로그 인기 글</h3>'
                  f'<ul class="side-posts">{post_items}</ul></div>') if post_items else ""
    return trend_card + posts_card


def page(title, desc, canonical, body, active, sidebar=""):
    if sidebar:
        main = (f'<main class="wrap layout"><div class="content-col">{body}</div>'
                f'<aside class="sidebar">{sidebar}</aside></main>')
    else:
        main = f'<main><div class="content-wrap">{body}</div></main>'
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
<meta property="og:type" content="website">
{THEME_INIT}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
{ADSENSE_HEAD}
<style>{CSS}</style>
</head>
<body>
{header(active)}
{main}
{foot()}
{THEME_JS}
</body>
</html>
"""


def content_with_mid_ad(body_html):
    sections = re.split(r"(?=<h2)", body_html)
    if len(sections) <= 2:
        return body_html
    mid = len(sections) // 2
    return "".join((adbox() + sec) if i == mid else sec for i, sec in enumerate(sections))


def render_article(p, posts):
    body_html = markdown.markdown(p["body_md"], extensions=["extra", "sane_lists"])
    tags = "".join(f'<a href="{PREFIX}/blog/">#{esc(t)}</a>' for t in p["tags"])
    canonical = f'{BASE}{PREFIX}/blog/{p["slug"]}.html'
    inner = f"""<article class="post">
  <span class="cat-badge">{esc(p.get("category") or "기타")}</span>
  <h1>{esc(p["title"])}</h1>
  <div class="meta">{esc(p["date"])}{' · ' + esc(p["keyword"]) if p["keyword"] else ''}</div>
  {f'<div class="tags">{tags}</div>' if tags else ''}
  {adbox()}
  <div class="article-body">{content_with_mid_ad(body_html)}</div>
  {adbox()}
  <div class="ai-notice">이 블로그 포스팅은 AI로 수집된 내용을 기반으로 작성되었습니다.</div>
  <a class="backlink" href="{PREFIX}/blog/">← 목록으로</a>
</article>"""
    return page(p["title"], p["description"] or p["title"], canonical, inner, "블로그",
                sidebar=build_sidebar(posts, current_slug=p["slug"]))


# 카테고리 표시 순서(존재하는 것만 노출)
CATEGORY_ORDER = ["시사", "경제", "사회", "연예", "IT·과학", "게임", "스포츠", "생활", "기타"]


def render_index(posts):
    items = ""
    for p in posts:
        cat = p.get("category") or "기타"
        thumb = (f'<div class="pl-thumb"><img src="{esc(p["thumb"])}" alt="" loading="lazy"></div>'
                 if p.get("thumb") else "")
        items += (f'<li data-cat="{esc(cat)}"><a class="pl-link" href="{PREFIX}/blog/{p["slug"]}.html">'
                  f'{thumb}'
                  f'<div class="pl-text">'
                  f'<span class="cat-badge">{esc(cat)}</span>'
                  f'<span class="t">{esc(p["title"])}</span>'
                  f'<div class="d">{esc(p["date"])}{" · " + esc(p["keyword"]) if p["keyword"] else ""}</div>'
                  f'<div class="x">{esc(p["description"])}</div>'
                  f'</div></a></li>')
    # 존재하는 카테고리만, 지정 순서로 필터 버튼 생성
    present = {p.get("category") or "기타" for p in posts}
    cats = [c for c in CATEGORY_ORDER if c in present] + sorted(present - set(CATEGORY_ORDER))
    catbar_html = ('<div class="catbar"><button class="catbtn on" data-cat="전체">전체</button>'
                   + "".join(f'<button class="catbtn" data-cat="{esc(c)}">{esc(c)}</button>' for c in cats)
                   + '</div>')
    body = (f'<h1 class="page-h1">블로그</h1>'
            f'<p class="page-sub">실시간 인기 검색어를 소재로 직접 쓴 글</p>'
            f'{catbar_html}'
            f'{adbox()}'
            f'<ul class="postlist" id="postlist">{items or "<li>아직 발행된 글이 없습니다.</li>"}</ul>'
            f'<div class="pager" id="pager"></div>'
            f'{INDEX_JS}')
    return page(f"블로그 · {SITE_NAME}",
                "실시간 인기 검색어를 소재로 직접 작성한 블로그 글 모음",
                f"{BASE}{PREFIX}/blog/", body, "블로그", sidebar=build_sidebar(posts))


INDEX_JS = """<script>
(function(){
  var PER=10, cat='전체', page=1;
  var list=document.getElementById('postlist');
  if(!list) return;
  var items=[].slice.call(list.querySelectorAll('li'));
  var pager=document.getElementById('pager');
  function filtered(){ return cat==='전체'?items:items.filter(function(li){return li.getAttribute('data-cat')===cat;}); }
  function render(){
    var f=filtered(), pages=Math.max(1,Math.ceil(f.length/PER));
    if(page>pages)page=pages;
    items.forEach(function(li){li.style.display='none';});
    f.slice((page-1)*PER, page*PER).forEach(function(li){li.style.display='';});
    var h='';
    if(pages>1){ for(var p=1;p<=pages;p++){ h+='<button class="pg'+(p===page?' on':'')+'" data-p="'+p+'">'+p+'</button>'; } }
    pager.innerHTML=h;
  }
  document.querySelectorAll('.catbtn').forEach(function(b){
    b.addEventListener('click',function(){
      document.querySelectorAll('.catbtn').forEach(function(x){x.classList.remove('on');});
      b.classList.add('on'); cat=b.getAttribute('data-cat'); page=1; render();
    });
  });
  pager.addEventListener('click',function(e){
    if(e.target && e.target.className.indexOf('pg')>-1){ page=parseInt(e.target.getAttribute('data-p'),10); render(); window.scrollTo(0,0); }
  });
  render();
})();
</script>"""


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
    body = f'<article class="post static-body">{markdown.markdown(md, extensions=["extra"])}</article>'
    slug = "privacy" if "개인정보" in title else "about"
    active = "소개" if slug == "about" else ""
    return page(f"{title} · {SITE_NAME}", title, f"{BASE}{PREFIX}/{slug}.html", body, active)


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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    posts = [parse_post(f) for f in glob.glob(os.path.join(POSTS_DIR, "*.md"))]
    posts = [p for p in posts if p["published"]]
    posts.sort(key=lambda p: p["date"], reverse=True)

    for p in posts:
        open(os.path.join(OUT_DIR, f'{p["slug"]}.html'), "w", encoding="utf-8").write(render_article(p, posts))
    open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8").write(render_index(posts))
    open("privacy.html", "w", encoding="utf-8").write(render_static("개인정보처리방침", PRIVACY_MD))
    open("about.html", "w", encoding="utf-8").write(render_static("소개", ABOUT_MD))
    open("sitemap.xml", "w", encoding="utf-8").write(build_sitemap(posts))
    open("rss.xml", "w", encoding="utf-8").write(build_rss(posts))
    print(f"blog built: {len(posts)} post(s) → {OUT_DIR}/, +privacy/about, sitemap.xml, rss.xml "
          f"(base={BASE}{PREFIX})")


if __name__ == "__main__":
    main()
