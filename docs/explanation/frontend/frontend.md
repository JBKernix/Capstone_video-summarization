# React 화면 (`frontend/`)

서비스 이름은 **핵심만PLZ**입니다. 화면은 두 가지입니다.

- **사용자 화면**(`/` 아래 전체, `src/user/`): 유튜브 링크·영상 파일로 요약을 시작하고, 쉬운 말로 된 진행 상황을 보고, 강의노트(챕터 플레이어)를 저장·다시 보기
- **개발자 화면**(`/dev` 아래, `src/dev/`·`src/pages/`): 영상 업로드·분석 설정·로그, 분석 결과, 저장된 요약, 실행 이력. 개발자 비밀번호로 들어갑니다([로그인과 개발자 모드](#로그인과-개발자-모드)).

Vite + React + TypeScript로 만들었고, 데이터는 모두 [앱 API 서버](../app/app_api.md)(`/api/...`)에서 받습니다. 빌드 결과(`frontend/dist`)는 앱 API 서버가 같은 포트(기본 8501)에서 내보내므로 Cloudflare Tunnel 설정을 바꿀 필요가 없습니다.

기존 Streamlit 화면(`app/main.py`, `app/pages/`)은 예비로 남아 있으며 `start_all.bat -Streamlit`으로 같은 포트에 띄울 수 있습니다. 두 화면은 같은 실행 기록·저장 결과를 공유합니다.

## 구성

| 항목 | 버전 |
| --- | --- |
| Node.js | 24 LTS (`winget install OpenJS.NodeJS.LTS`) |
| React | 19 |
| React Router | 7 (`react-router-dom`) |
| Markdown | `react-markdown` 10 + `remark-gfm` 4 (요약 본문·표 렌더링) |
| 빌드 | Vite 6, TypeScript 5.8, ESLint 9 |
| 글꼴 | Pretendard(`index.html`에서 jsDelivr CDN으로 불러옴) |

차트·표 라이브러리는 쓰지 않습니다. 실행 이력의 단계별 시간 막대는 CSS로 그립니다.

## 폴더 구조

```text
frontend/
├── index.html              # 제목·설명·아이콘(핵심만PLZ), Pretendard 글꼴
├── vite.config.ts          # 개발 서버에서 /api를 앱 API 서버로 전달
├── package.json / package-lock.json
└── src/
    ├── main.tsx            # 진입점
    ├── App.tsx             # 로그인 확인, /dev/* → DevApp, 그 외 → UserApp
    ├── api.ts              # API 호출(fetch/XHR, get/post/put/delete), 응답 타입
    ├── format.ts           # 한국 시간 표시
    ├── index.css           # 개발자 화면 스타일(기존 app/styles.py 색·모양을 옮김), 프레임 갤러리
    ├── components/
    │   ├── SummaryView.tsx     # 원본 영상 + 요약(타임라인 클릭 → 영상 이동), 본문만 그리는 SummaryBody
    │   ├── FrameGallery.tsx    # FrameGallery(구간 화면 여러 장), FrameStrip(챕터 화면 썸네일 줄)
    │   ├── DevPasswordForm.tsx # 개발자 비밀번호 입력(POST /api/dev/login)
    │   ├── StepTracker.tsx     # 분석 7단계 원형 진행 표시
    │   └── Notice.tsx          # 안내 상자, 페이지 제목
    ├── user/                   # 사용자 화면
    │   ├── UserApp.tsx         # 상단 메뉴(요약하기·내 강의노트), 라우트, 개발자 모드 팝업
    │   ├── HomeView.tsx        # 소개 + 유튜브 링크/영상 파일 입력, 요약 방식 선택
    │   ├── ProgressView.tsx    # 쉬운 말로 된 7단계 진행률, 요약 취소
    │   ├── NoteView.tsx        # 강의노트(저장·인쇄·삭제)
    │   ├── ChapterNote.tsx     # 챕터 플레이어
    │   ├── LibraryView.tsx     # 저장한 강의노트 목록·검색
    │   ├── labels.ts           # 사용자용 단계·요약 방식 이름, 시각·날짜 표시
    │   └── user.css            # 사용자 화면 스타일(u-* 클래스), 인쇄 규칙
    ├── dev/
    │   └── DevApp.tsx          # 개발자 화면: 개발자 인증 확인, 상단 메뉴, 라우트(basename /dev)
    └── pages/                  # 개발자 화면의 페이지
        ├── HomePage.tsx
        ├── LoginPage.tsx
        ├── UploadPage.tsx
        ├── ResultListPage.tsx
        ├── ResultPage.tsx
        ├── SavedPage.tsx
        └── HistoryPage.tsx
```

## 화면과 주소

`App.tsx`는 주소가 `/dev` 또는 `/dev/...`이면 `DevApp`, 그 밖의 모든 주소는 `UserApp`을 그립니다. 서버는 `/api`가 아닌 주소에 `index.html`을 돌려주므로 두 화면 모두 새로고침해도 유지됩니다.

### 사용자 화면 (`user/UserApp.tsx`)

| 주소 | 화면 |
| --- | --- |
| `/` | 소개 + 입력 카드(▶ 유튜브 링크 / 📁 영상 파일 탭), 요약 방식(빠르게·표준·꼼꼼하게) 선택, "✨ 핵심만 뽑아주세요" |
| `/summarize/<실행 ID>` | 요약 진행 상황(전체 %, 경과 시간, 7단계), 요약 취소. 성공하면 강의노트로 자동 이동 |
| `/note/run/<실행 ID>` | 방금 끝난 요약의 강의노트, "📌 내 강의노트에 저장", "🖨️ 인쇄 · PDF" |
| `/note/saved/<폴더명>` | 저장한 강의노트(저장 시각 표시, 인쇄, 삭제 확인) |
| `/library` | 저장한 강의노트 목록, 제목 검색 |

그 밖의 주소는 `/`로 돌아갑니다. 상단 메뉴는 **요약하기 · 내 강의노트**이고, 오른쪽 **🛠️ 개발자** 버튼은 이미 개발자 모드면 `/dev`로 이동하고 아니면 개발자 비밀번호 팝업(`DevPasswordForm`)을 띄웁니다.

### 개발자 화면 (`dev/DevApp.tsx`, 주소 앞에 `/dev`)

| 주소 | 화면 | Streamlit에서 대응하는 페이지 |
| --- | --- | --- |
| `/dev` | 홈(업로드·저장된 요약·실행 이력 바로가기) | `app/main.py` |
| `/dev/upload` | 영상 업로드(파일 끌어다 놓기/유튜브 링크), 분석 설정, 사용자 화면 분석 방식 지정, 7단계 진행, 로그, 분석 중지 | `pages/1_upload.py` |
| `/dev/upload?run=<실행 ID>` | 진행 중이거나 끝난 분석에 다시 연결 | 같은 페이지의 `?run=` |
| `/dev/result` | 다시 열 수 있는 분석 결과 목록(보존 기간 안의 완료 실행) | 없음(새로 추가) |
| `/dev/result/<실행 ID>` | 원본 영상과 최종 요약, "영상과 요약 결과 저장" | `pages/2_analysis_result.py` |
| `/dev/saved?item=<폴더명>` | 저장된 요약 목록·확인·삭제(확인 단계 있음) | `pages/3_saved_summaries.py` |
| `/dev/history?run=<실행 ID>` | 실행 이력 필터·지표·표, 결과 화면 링크, 상세 탭(단계별 시간·모델 로딩/처리량과 설정/원본 로그), CSV·로그·JSON 다운로드 | `pages/4_run_history.py` |

`BrowserRouter basename="/dev"`를 쓰므로 `pages/` 안의 링크(`to="/upload"` 등)는 그대로 `/dev/upload`가 됩니다. 상단에는 "개발자 모드" 표시와 **영상 업로드 · 분석 결과 · 저장된 요약 · 실행 이력** 메뉴, **사용자 화면**·**개발자 모드 종료**(`POST /api/dev/logout`)·로그아웃 버튼이 있습니다. 결과 화면은 다음 세 곳에서 다시 열 수 있습니다.

- 상단 **분석 결과** 탭
- 실행 이력 표의 **결과 → 보기** 링크
- 실행 상세의 **📄 결과 화면 보기** 버튼

분석 산출물은 보존 기간(기본 72시간)이 지나면 정리되어 목록에서 사라집니다. 오래 볼 결과는 결과 화면에서 저장하세요.

## 동작

### 로그인과 개발자 모드

`App.tsx`가 시작할 때 `GET /api/session`(`required`·`authenticated`·`developer`)을 확인합니다.

- 앱 비밀번호(`APP_PASSWORD`)가 없으면 로컬·외부 접속 모두 로그인 없이 들어옵니다(예전의 외부 접속 차단 상태 `blocked`는 없어졌습니다).
- `authenticated: false`: 로그인 화면(`LoginPage.tsx`, "핵심만PLZ 로그인")
- API가 401을 돌려주면(세션 만료 등) `auth-required` 이벤트로 로그인 화면으로 돌아갑니다.
- 비밀번호가 설정된 경우에만 상단에 로그아웃 버튼이 보입니다. 로그아웃하면 개발자 모드도 함께 끝납니다.

개발자 모드는 앱 로그인과 별개인 개발자 비밀번호(`DEV_PASSWORD`, 기본 `admin`)로 들어가며, 서버는 별도 쿠키(`vs_dev`)로 구분합니다.

- `DevPasswordForm`이 `POST /api/dev/login`을 보내고, 성공하면 세션을 다시 읽습니다(사용자 화면 팝업에서는 `/dev`로 이동). 사용자 화면의 🛠️ 팝업과 `/dev` 입구 화면이 같은 폼을 씁니다.
- `/dev`에 들어왔는데 `developer: false`이면 개발자 비밀번호 입력 화면만 보입니다.
- 실행 이력·모델 상태 API는 개발자 전용입니다. 개발자 쿠키가 만료되어 API가 "개발자 모드" 403을 돌려주면 `api.ts`가 `dev-required` 이벤트를 보내고, `DevApp`은 다시 비밀번호를 묻습니다.
- 분석 진행 상황(`GET /api/runs/<ID>`)의 `logs`는 개발자가 아니면 빈 목록입니다. 그래서 사용자 화면은 단계와 진행률만 보여 줍니다.

### 업로드와 분석 진행 (`UploadPage.tsx`)

1. 파일은 브라우저에서 확장자·크기(`/api/options`의 한도)를 먼저 확인한 뒤 XHR로 올려 업로드 퍼센트를 표시합니다. 서버 검증(ffprobe)에 실패하면 서버 오류 문구를 그대로 보여줍니다.
2. 업로드 결과는 `sessionStorage`에 두어 새로고침해도 유지됩니다. 다른 영상을 올리면 이전 업로드를 서버에서 지웁니다(Streamlit과 같은 규칙).
3. 분석 방식·로컬 모델·Whisper 설정은 `localStorage`에 기억합니다. 저장된 값이 서버 목록에 없으면 기본값으로 돌아갑니다.
4. "영상 분석 시작" → `POST /api/runs` → 주소에 `?run=<실행 ID>`를 붙이고, 끝날 때까지 1초마다 `GET /api/runs/<ID>`를 조회합니다.
5. 성공하면 `/result/<ID>`로 이동합니다. 실패·중지는 마지막 로그와 함께 표시합니다.
6. 분석 중이 아닐 때는 5초마다 `GET /api/runs/active`로 다른 사용자의 분석 여부를 확인해, 실행 중이면 시작 버튼을 막습니다.
7. 분석 설정 아래 **사용자 화면 분석 방식**에 지금 사용자 화면이 쓰는 방식(`/api/options`의 `user_defaults`)을 보여 줍니다. "위에서 고른 분석 방식을 사용자 화면에 적용"을 누르면 위에서 고른 분석 방식·로컬 모델을 `PUT /api/dev/user-defaults`로 저장합니다(이미 같으면 버튼이 꺼짐). 일반 사용자는 분석 방식을 고를 수 없고, 서버가 이 값으로 분석합니다.

브라우저를 닫아도 서버의 분석은 계속됩니다. `?run=` 주소로 다시 들어오거나 **분석 결과**·**실행 이력**에서 찾을 수 있습니다.

### 요약 표시 (`SummaryView.tsx`)

서버가 해석해 준 블록을 그립니다([요약 결과 형식](../app/app_api.md#요약-결과-형식)).

- `markdown` 블록: `react-markdown`으로 렌더링(HTML 태그는 렌더링하지 않음)
- `items` 블록: 항목 카드 + `▶ 0:10 ~ 0:20` 타임라인 뱃지. 누르면 같은 화면의 `<video>`를 그 시각으로 옮겨 재생하고 영상이 보이도록 스크롤합니다(키보드 Enter도 가능)
- 표/차트 섹션: 카드 왼쪽에 해당 구간 화면(`FrameGallery`). 항목의 `frames`(구간 안의 서로 다른 화면, 시간순)가 여러 장이면 큰 화면 아래에 썸네일 줄과 "화면 1/3"·`▶ 0:14` 버튼이 붙어, 썸네일로 큰 화면을 바꾸고 시각 버튼으로 영상을 그 시점으로 옮깁니다. `frames`가 비면 대표 화면(`image_url`) 한 장만 보입니다.

Streamlit에서는 뱃지 클릭을 `st.html` + `<script>`로 우회했지만(React #231 오류 회피), React에서는 일반 `onClick`으로 처리합니다.

### 사용자용 강의노트: 챕터 플레이어 (`user/ChapterNote.tsx`)

사용자용 강의노트 화면(`user/NoteView.tsx`, `/note/run/<실행 ID>`·`/note/saved/<폴더명>`)은 결과에 `outline`(타임라인 챕터)이 있으면 챕터 플레이어로, 없으면(`outline: null`) 영상 + 위의 블록 화면(`SummaryBody`)으로 보여 줍니다. 개발자 화면은 계속 블록 화면을 씁니다.

`outline`은 서버가 만듭니다. 최종 요약 결과에 gpu-server의 강의 노트 JSON(`lecture_note`)이 있으면 그 JSON으로, 없으면 최종 요약 마크다운을 해석해 만듭니다([요약 결과 형식](../app/app_api.md#요약-결과-형식)). 핵심 용어(`terms`)와 공지(`notices`)는 강의 노트 JSON에서만 채워지고, 그 JSON에서는 시간을 모르는 챕터·자료의 `start`가 `null`일 수 있습니다.

| 영역 | 내용 |
| --- | --- |
| 맨 위 | **📢 공지**(`outline.notices`, 있을 때만) |
| 요약 카드 | **3줄 요약**(`outline.key_points` 앞 3개, 노란 번호)과 **키워드** 칩(`outline.keywords`) |
| 왼쪽(휴대폰은 위) | 영상 + 챕터 막대. 막대 한 칸이 챕터 하나(다음 챕터 시작까지)이며 재생 위치만큼 채워지고, 누르면 그 챕터로 이동. 시간을 모르는 챕터는 막대에 넣지 않음. 아래에 지금 챕터 이름과 재생 중/일시정지 표시. 화면에 붙어 있어(sticky) 스크롤해도 보임 |
| 오른쪽(휴대폰은 아래) | 챕터 카드 목록(시작 시각순, 시간을 모르는 챕터는 원래 순서대로 맨 뒤): 썸네일(`thumb_url`, 없으면 번호), `▶ 0:36 ~ 0:54`, 제목, 화면 썸네일 줄(`FrameStrip`), 내용 목록, **📺 화면에서 확인**(화면 분석 내용). 카드 머리를 누르면 그 장면부터 재생. 시간을 모르는 챕터는 "시간 정보 없음"으로 표시하고 재생 버튼이 아님. 재생 중인 챕터는 파란 테두리로 강조(재생 전에는 강조 없음) |
| 아래 | **📊 화면 속 자료**(`outline.visuals`: `FrameGallery` + 내용, 자료 유형(`kind`, 예: 수식) 표시, 시간 버튼으로 이동. 시간을 모르면 버튼 없이 표시), **📘 핵심 용어**(`outline.terms`, 용어와 정의), **✅ 정리**(종합 결론), 분류되지 않은 나머지 마크다운(`extras`) |

`FrameStrip`은 챕터의 `frames`(챕터 구간 안의 서로 다른 화면, 시간순)가 2장 이상일 때만 작은 썸네일과 시각을 줄지어 보여 주고, 누르면 그 화면 시점부터 재생합니다(1장이면 챕터 썸네일과 같으므로 생략).

인쇄·PDF에서는 영상과 재생 표시를 숨기고 공지·요약·챕터·자료·용어·정리만 남깁니다. 스타일은 `user/user.css`의 `u-cn-*` 규칙입니다.

### 사용자 화면의 요약 시작·진행 (`user/HomeView.tsx`, `user/ProgressView.tsx`)

- 유튜브 링크는 주소 형식(youtube.com/youtu.be)을 확인한 뒤 `POST /api/uploads/youtube`, 영상 파일은 확장자·크기를 확인한 뒤 XHR로 올립니다. 이어서 `POST /api/runs`에 업로드 ID와 요약 방식만 보내고 `/summarize/<실행 ID>`로 이동합니다. 분석 방식은 보내지 않으며, 서버가 개발자가 지정한 값(`user_defaults`)을 씁니다. 요약을 시작하지 못하면 받은 영상을 지웁니다.
- 요약 방식·단계 이름은 서버 이름 대신 `labels.ts`의 쉬운 표현(빠르게·표준·꼼꼼하게, "받아쓰기"·"판서·자막 읽기" 등)으로 보여 줍니다.
- 5초마다 `GET /api/runs/active`로 다른 요약이 진행 중인지 확인해 시작 버튼을 막고 "진행 상황 보기" 링크를 보여 줍니다. 요약 서버가 준비되지 않았으면(`backend_ready: false`) 안내를 띄웁니다.
- 진행 화면은 1.5초마다 `GET /api/runs/<ID>`를 조회해, 끝난 단계 + 현재 단계 진행분으로 전체 %(완료 전 최대 99%)를 계산합니다. 실패·취소면 안내와 "다시 요약하기"를 보여 주고, 성공하면 `/note/run/<ID>`로 이동합니다.

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

1. 개발자 화면은 `src/pages/<이름>Page.tsx`, 사용자 화면은 `src/user/<이름>View.tsx` 작성
2. 필요한 API가 없으면 `app/api/server.py`에 엔드포인트를 추가하고(개발자 전용이면 `developer_only` 의존성) `tests/test_api_server.py`에 테스트 추가
3. 응답 타입을 `src/api.ts`에 추가하고 `api.get/post/put/delete`로 호출(CSRF 헤더가 자동으로 붙음)
4. `dev/DevApp.tsx` 또는 `user/UserApp.tsx`의 `<Routes>`와 필요하면 상단 메뉴(`<NavLink>`)에 등록
5. `npm run lint && npm run build`

## 확인한 범위

API 테스트(`tests/test_api_server.py`), 린트·빌드, 실제 데이터로 앱 API 서버 응답(목록·결과·영상 Range·프레임·라우트)을 확인했습니다. 화면 동작은 서버 PC 브라우저에서 업로드·분석·결과 이동까지 확인했습니다. 스마트폰과 외부(Cloudflare) 접속 확인은 [단일 서버 운영 가이드](../../single_server_deployment.md)의 체크리스트를 따르세요.
