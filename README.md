# 실시간 검색어

지금 대한민국에서 가장 많이 검색되는 **실시간 인기 검색어 순위** 사이트입니다.
**구글 실시간**과 **네이버 실시간**을 탭으로 나눠서 제공합니다. (loword.co.kr 벤치마킹)

- 데이터 소스 (둘 다 API 키 불필요)
  - **구글**: Google Trends 인기 급상승 검색어 RSS (geo=KR) — 검색량·관련 뉴스 포함
  - **네이버**: [signal.bz](https://signal.bz) 실시간 검색어 집계
    > 네이버는 2021년 공식 실시간 검색어를 폐지했습니다. "네이버 실시간"은 signal.bz의
    > 집계값이며 네이버 공식 순위가 아닙니다.
- 순위 변동 표시: `NEW` / `▲상승` / `▼하락` / `–유지` (직전 스냅샷과 비교, 소스별 계산)
- 매시간 **GitHub Actions**가 자동으로 데이터를 받아 페이지를 다시 생성
- 백엔드 서버 없는 **정적 사이트** (GitHub Pages 배포 가능)

## 구조

| 파일 | 역할 |
|------|------|
| `generate.py` | 구글 트렌드 RSS + signal.bz 수집 → 순위 변동 계산 → `index.html` 생성 |
| `template.html` | UI 템플릿 (`__TRENDS_DATA__` 자리에 데이터 주입) |
| `index.html` | 생성된 결과물 (배포되는 페이지) |
| `prev.json` | 직전 순위 스냅샷 (변동 계산용) |
| `.github/workflows/update.yml` | 매시간 자동 갱신 워크플로 |

## 로컬 실행

```bash
python generate.py       # index.html 생성
# 브라우저로 index.html 열기, 또는:
python -m http.server 8000   # http://localhost:8000
```

## 배포 (GitHub Pages)

1. 이 폴더를 GitHub 새 저장소에 push
2. 저장소 **Settings → Pages** → Source를 `main` 브랜치 `/ (root)`로 설정
3. Actions 탭에서 **Update trends data** 워크플로가 매시간 실행됨
   (수동 실행: Actions → 워크플로 선택 → *Run workflow*)

> 참고: GitHub Actions cron은 지연될 수 있어 "매시간"은 근사값입니다.
