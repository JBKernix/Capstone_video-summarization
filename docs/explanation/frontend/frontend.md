# React 화면 (`frontend/`)

영상 업로드·분석 진행·결과 확인·저장된 요약·실행 이력 화면입니다. Vite + React + TypeScript로 만들었고, 데이터는 모두 [앱 API 서버](../app/app_api.md)(`/api/...`)에서 받습니다. 빌드 결과(`frontend/dist`)는 앱 API 서버가 같은 포트(기본 8501)에서 내보내므로 Cloudflare Tunnel 설정을 바꿀 필요가 없습니다.

기존 Streamlit 화면(`app/main.py`, `app/pages/`)은 예비로 남아 있으며 `start_all.bat -Streamlit`으로 같은 포트에 띄울 수 있습니다. 두 화면은 같은 실행 기록·저장 결과를 공유합니다.

## 구성

| 항목 | 버전 |
| --- | --- |
| Node.js | 24 LTS (`winget install OpenJS.NodeJS.LTS`) |
| React | 19 |
| React Router | 7 (`react-router-dom`) |
| Markdown | `react-markdown` 10 + `remark-gfm` 4 (요약 본문·표 렌더링) |
| 빌드 | Vite 6, TypeScript 5.8, ESLint 9 |

차트·표 라이브러리는 쓰지 않습니다. 실행 이력의 단계별 시간 막대는 CSS로 그립니다.

## 폴더 구조

```text
frontend/
├── index.html
├── vite.config.ts          # 개발 서버에서 /api를 앱 API 서버로 전달
├── package.json / package-lock.json
└── src/
    ├── main.tsx            # 진입점
    ├── App.tsx             # 로그인 확인, 상단 메뉴, 라우트
    ├── api.ts              # API 호출(fetch/XHR), 응답 타입
    ├── format.ts           # 한국 시간 표시
    ├── index.css           # 전체 스타일(기존 app/styles.py 색·모양을 옮김)
    ├── components/
    │   ├── SummaryView.tsx # 원본 영상 + 요약(타임라인 클릭 → 영상 이동)
    │   ├── StepTracker.tsx # 분석 7단계 원형 진행 표시
    │   └── Notice.tsx      # 안내 상자, 페이지 제목
    └── pages/
        ├── HomePage.tsx
        ├── LoginPage.tsx
        ├── UploadPage.tsx
        ├── ResultListPage.tsx
        ├── ResultPage.tsx
        ├── SavedPage.tsx
        └── HistoryPage.tsx
```

## 화면과 주소

| 주소 | 화면 | Streamlit에서 대응하는 페이지 |
| --- | --- | --- |
| `/` | 홈(업로드·저장된 요약·실행 이력 바로가기) | `app/main.py` |
| `/upload` | 영상 업로드(파일 끌어다 놓기/유튜브 링크), 분석 설정, 7단계 진행, 로그, 분석 중지 | `pages/1_upload.py` |
| `/upload?run=<실행 ID>` | 진행 중이거나 끝난 분석에 다시 연결 | 같은 페이지의 `?run=` |
| `/result` | 다시 열 수 있는 분석 결과 목록(보존 기간 안의 완료 실행) | 없음(새로 추가) |
| `/result/<실행 ID>` | 원본 영상과 최종 요약, "영상과 요약 결과 저장" | `pages/2_analysis_result.py` |
| `/saved?item=<폴더명>` | 저장된 요약 목록·확인·삭제(확인 단계 있음) | `pages/3_saved_summaries.py` |
| `/history?run=<실행 ID>` | 실행 이력 필터·지표·표, 결과 화면 링크, 상세 탭(단계별 시간·모델 로딩/처리량과 설정/원본 로그), CSV·로그·JSON 다운로드 | `pages/4_run_history.py` |

상단 메뉴는 **영상 업로드 · 분석 결과 · 저장된 요약 · 실행 이력**입니다. 결과 화면은 다음 세 곳에서 다시 열 수 있습니다.

- 상단 **분석 결과** 탭
- 실행 이력 표의 **결과 → 보기** 링크
- 실행 상세의 **📄 결과 화면 보기** 버튼

분석 산출물은 보존 기간(기본 72시간)이 지나면 정리되어 목록에서 사라집니다. 오래 볼 결과는 결과 화면에서 저장하세요.

## 동작

### 로그인

`App.tsx`가 시작할 때 `GET /api/session`을 확인합니다.

- `blocked`: 외부 접속인데 서버에 비밀번호가 없음 → 차단 안내만 표시
- `authenticated: false`: 로그인 화면
- API가 401을 돌려주면(세션 만료 등) `auth-required` 이벤트로 로그인 화면으로 돌아갑니다.
- 비밀번호가 설정된 경우에만 상단에 로그아웃 버튼이 보입니다.

### 업로드와 분석 진행 (`UploadPage.tsx`)

1. 파일은 브라우저에서 확장자·크기(`/api/options`의 한도)를 먼저 확인한 뒤 XHR로 올려 업로드 퍼센트를 표시합니다. 서버 검증(ffprobe)에 실패하면 서버 오류 문구를 그대로 보여줍니다.
2. 업로드 결과는 `sessionStorage`에 두어 새로고침해도 유지됩니다. 다른 영상을 올리면 이전 업로드를 서버에서 지웁니다(Streamlit과 같은 규칙).
3. 분석 방식·로컬 모델·Whisper 설정은 `localStorage`에 기억합니다. 저장된 값이 서버 목록에 없으면 기본값으로 돌아갑니다.
4. "영상 분석 시작" → `POST /api/runs` → 주소에 `?run=<실행 ID>`를 붙이고, 끝날 때까지 1초마다 `GET /api/runs/<ID>`를 조회합니다.
5. 성공하면 `/result/<ID>`로 이동합니다. 실패·중지는 마지막 로그와 함께 표시합니다.
6. 분석 중이 아닐 때는 5초마다 `GET /api/runs/active`로 다른 사용자의 분석 여부를 확인해, 실행 중이면 시작 버튼을 막습니다.

브라우저를 닫아도 서버의 분석은 계속됩니다. `?run=` 주소로 다시 들어오거나 **분석 결과**·**실행 이력**에서 찾을 수 있습니다.

### 요약 표시 (`SummaryView.tsx`)

서버가 해석해 준 블록을 그립니다([요약 결과 형식](../app/app_api.md#요약-결과-형식)).

- `markdown` 블록: `react-markdown`으로 렌더링(HTML 태그는 렌더링하지 않음)
- `items` 블록: 항목 카드 + `▶ 0:10 ~ 0:20` 타임라인 뱃지. 누르면 같은 화면의 `<video>`를 그 시각으로 옮겨 재생하고 영상이 보이도록 스크롤합니다(키보드 Enter도 가능)
- 표/차트 섹션: 카드 왼쪽에 해당 구간 프레임 이미지

Streamlit에서는 뱃지 클릭을 `st.html` + `<script>`로 우회했지만(React #231 오류 회피), React에서는 일반 `onClick`으로 처리합니다.

### 실행 이력 (`HistoryPage.tsx`)

필터(영상명·상태·Whisper 설정)와 지표 계산은 브라우저에서 합니다. CSV는 현재 필터 결과의 실행 ID 목록을 서버에 보내 받고, 상세 지표 JSON은 브라우저에서 바로 만듭니다. 시간은 한국 시간(`format.ts`)으로 표시합니다.

## 개발과 빌드

```bash
cd frontend
npm ci            # 처음 한 번(package-lock.json 기준 설치)
npm run dev       # 개발 서버(기본 5173). /api는 127.0.0.1:8501로 전달
npm run lint      # ESLint
npm run build     # 타입 검사 + frontend/dist 생성
```

- 개발 서버를 쓰려면 앱 API 서버가 8501에서 실행 중이어야 합니다. 다른 주소면 `API_TARGET=http://127.0.0.1:8601 npm run dev`처럼 지정합니다.
- 화면 코드를 고친 뒤 실제 서버(8501)에 반영하려면 `npm run build`만 다시 실행하면 됩니다. `index.html`은 캐시하지 않으므로 앱 API 서버를 재시작할 필요 없이 새로고침하면 적용됩니다. API(`app/api/`)를 고쳤을 때만 앱 API 서버를 재시작합니다.
- `start_all.bat`은 `frontend/dist`가 **없을 때만** 자동으로 빌드합니다(`node_modules`가 없으면 `npm ci`부터).
- `node_modules/`, `dist/`는 `frontend/.gitignore`로 Git에서 제외됩니다.
- npm 11은 설치 스크립트를 기본으로 막아 `esbuild` 설치 시 경고가 나오지만, 플랫폼별 바이너리 패키지로 동작하므로 빌드에는 문제가 없습니다.

## 새 화면 추가하기

1. `src/pages/<이름>Page.tsx` 작성
2. 필요한 API가 없으면 `app/api/server.py`에 엔드포인트를 추가하고 `tests/test_api_server.py`에 테스트 추가
3. 응답 타입을 `src/api.ts`에 추가하고 `api.get/post/delete`로 호출(POST·DELETE에는 CSRF 헤더가 자동으로 붙음)
4. `App.tsx`의 `<Routes>`와 필요하면 상단 메뉴(`<NavLink>`)에 등록
5. `npm run lint && npm run build`

## 확인한 범위

API 테스트(`tests/test_api_server.py`), 린트·빌드, 실제 데이터로 앱 API 서버 응답(목록·결과·영상 Range·프레임·라우트)을 확인했습니다. 화면 동작은 서버 PC 브라우저에서 업로드·분석·결과 이동까지 확인했습니다. 스마트폰과 외부(Cloudflare) 접속 확인은 [단일 서버 운영 가이드](../../single_server_deployment.md)의 체크리스트를 따르세요.
