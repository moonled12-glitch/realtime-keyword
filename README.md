# 실시간 검색어

지금 대한민국에서 가장 많이 검색되는 **실시간 인기 검색어 순위** 사이트입니다.
**구글 실시간**과 **네이버 실시간**을 탭으로 나눠서 제공합니다. (loword.co.kr 벤치마킹)

- 데이터 소스
  - **구글**: Google Trends 인기 급상승 검색어 RSS (geo=KR) — 키 불필요, 검색량·관련 뉴스 포함
  - **네이버**: 두 방식 중 자동 선택
    - **(A) 네이버 데이터랩 API** — `NAVER_CLIENT_ID/SECRET` 시크릿이 있으면 사용.
      구글 트렌드 키워드를 후보로, 네이버 검색비중 순으로 재정렬한 순위.
    - **(B) [signal.bz](https://signal.bz) 실시간 검색어 집계** — 키가 없으면 자동 폴백.
    > 네이버는 2021년 공식 실시간 검색어를 폐지했습니다. 두 방식 모두 네이버 공식 실검이 아닙니다.
    > 데이터랩은 "지정 키워드의 상대 추이"만 제공하므로, 뜨는 키워드 발견은 구글 후보에 의존합니다.
- 순위 변동 표시: `NEW` / `▲상승` / `▼하락` / `–유지` (직전 스냅샷과 비교, 소스별 계산)

## 네이버 데이터랩 API 연결 (선택)

키를 등록하면 네이버 탭이 signal.bz → 데이터랩 기준으로 자동 전환됩니다.

1. [developers.naver.com](https://developers.naver.com/apps) → 애플리케이션 등록 →
   사용 API에 **데이터랩(검색어트렌드)** 추가 → **Client ID / Client Secret** 발급
2. 저장소 **Settings → Secrets and variables → Actions → New repository secret** 에서 등록
   - `NAVER_CLIENT_ID`
   - `NAVER_CLIENT_SECRET`
3. Actions에서 워크플로 실행 → 네이버 탭이 "네이버 데이터랩 기준"으로 표시됨
   (키가 없거나 호출 실패 시 자동으로 signal.bz로 폴백)
- 약 10분마다 **GitHub Actions**가 자동으로 데이터를 받아 페이지를 다시 생성
- 백엔드 서버 없는 **정적 사이트** (GitHub Pages 배포 가능)

## 구조

| 파일 | 역할 |
|------|------|
| `generate.py` | 구글 트렌드 RSS + signal.bz 수집 → 순위 변동 계산 → `index.html` 생성 |
| `template.html` | UI 템플릿 (`__TRENDS_DATA__` 자리에 데이터 주입) |
| `index.html` | 생성된 결과물 (배포되는 페이지) |
| `prev.json` | 직전 순위 스냅샷 (변동 계산용) |
| `.github/workflows/update.yml` | 약 10분마다 자동 갱신 워크플로 |

## 로컬 실행

```bash
python generate.py       # index.html 생성
# 브라우저로 index.html 열기, 또는:
python -m http.server 8000   # http://localhost:8000
```

## 배포 (GitHub Pages)

1. 이 폴더를 GitHub 새 저장소에 push
2. 저장소 **Settings → Pages** → Source를 `main` 브랜치 `/ (root)`로 설정
3. Actions 탭에서 **Update trends data** 워크플로가 약 10분마다 실행됨
   (수동 실행: Actions → 워크플로 선택 → *Run workflow*)

> 참고: GitHub Actions cron은 부하 시 지연·건너뜀이 있어 실제 간격은 10~20분으로 들쭉날쭉할 수 있습니다.
