# 앱 API 서버 (`app/api/`)

React 화면(`frontend/`)이 호출하는 FastAPI 서버입니다. 기존 Streamlit 페이지가 하던 일(업로드 저장, 파이프라인 실행·중지, 진행 상황 해석, 결과·저장본·실행 이력 조회)을 JSON API로 제공하고, React 빌드 결과(`frontend/dist`)도 같은 포트에서 내보냅니다.

LLM/VLM 추론 서버(`gpu-server` 브랜치, `GPU_SERVER_URL`, 기본 `127.0.0.1:8000`)와는 **별개의 서버**입니다. 이 서버는 모델을 직접 실행하지 않고, 기존과 같이 `scripts/run_pipeline.py`를 자식 프로세스로 띄웁니다.

```text
브라우저 ──> 앱 API 서버 127.0.0.1:8501 (app.api.server:app)
               ├─ /api/...   JSON API
               └─ 그 외 경로  frontend/dist (React)
                     │ run_pipeline.py 실행
                     ▼
             추론 서버 127.0.0.1:8000 (gpu-server, LLM/VLM)
```

## 파일

| 파일 | 역할 |
| --- | --- |
| `app/api/server.py` | FastAPI 앱, 모든 엔드포인트, CSRF·업로드 크기 미들웨어, React 정적 파일 제공 |
| `app/api/auth.py` | 비밀번호 로그인, 개발자 모드 로그인(`DEV_PASSWORD`), 서명된 세션 쿠키, 외부 접속(Cloudflare) 판별 |
| `app/api/summary.py` | 최종 요약을 화면용 JSON(`blocks`/`structured`/`raw`)과 사용자용 강의노트 구조(`outline`)로 변환, 프레임 이미지 경로 해석 |

Streamlit 페이지와 API가 함께 쓰도록 페이지 안에 있던 로직을 UI와 무관한 모듈로 옮겼습니다. 동작은 그대로입니다.

| 모듈 | 옮겨 온 곳 | 내용 |
| --- | --- | --- |
| `app/pipeline_log.py` | `app/pages/1_upload.py` | `process.log` 읽기, `##PROGRESS##`·Whisper tqdm 파싱(`parse_progress_state`), 단계 상태 계산(`describe_step_status`), 화면용 로그 필터 |
| `app/summary_parse.py` | `app/summary_timeline.py` | 타임라인 표기 파싱(`parse_summary_markdown`), 분:초 변환, 표/차트 구간 프레임 찾기 |
| `app/saved_results.py` | `app/pages/3_saved_summaries.py` | `data/saved/` 목록·폴더명 해석·영상 찾기, 폴더 이름 검증(`saved_folder`) |
| `app/login_throttle.py` | `app/auth.py` | 같은 IP 5회 연속 실패 시 60초 잠금 |

업로드 저장·실행 슬롯·보존 기간 정리(`app/run_registry.py`), 파이프라인 실행·중지(`app/pipeline_process.py`), 결과 저장(`app/result_export.py`), 결과 로더(`app/summary_result.py`)는 Streamlit과 같은 함수를 그대로 사용합니다.

## 실행

```bash
python -m uvicorn app.api.server:app --host 127.0.0.1 --port 8501
```

보통은 `start_all.bat`이 실행합니다([단일 서버 운영 가이드](../../single_server_deployment.md)). `frontend/dist`가 없으면 `/api` 외 경로는 503과 함께 빌드 안내를 돌려줍니다.

## 엔드포인트

모든 `/api` 경로는 로그인이 필요합니다(`/api/session`, `/api/login`, `/api/logout`, `/api/dev/logout` 제외). `APP_PASSWORD`가 없으면 모든 접속이 로그인된 것으로 처리됩니다.

아래 표에서 **개발자 전용**으로 표시한 경로는 개발자 모드 쿠키(`vs_dev`)가 없으면 403입니다(`auth.require_developer`). 일반 사용자 화면은 이 API를 쓰지 않습니다.

### 로그인

| 메서드·경로 | 설명 |
| --- | --- |
| `GET /api/session` | `{required, authenticated, developer}` — 비밀번호 필요 여부, 로그인 여부, 개발자 모드 여부 |
| `POST /api/login` | `{password}` 확인 후 세션 쿠키 발급. 틀리면 401, 잠금 중이면 429 |
| `POST /api/logout` | 세션 쿠키와 개발자 쿠키 모두 삭제 |
| `POST /api/dev/login` | `{password}`를 `DEV_PASSWORD`(기본 `admin`)와 비교해 개발자 쿠키 `vs_dev` 발급. 로그인돼 있어야 하며, 틀리면 401, 잠금 중이면 429(일반 로그인과 실패 횟수를 따로 셈) |
| `POST /api/dev/logout` | 개발자 쿠키만 삭제 |

### 설정·업로드

| 메서드·경로 | 설명 |
| --- | --- |
| `GET /api/options` | Whisper 설정(간단/기본/상세와 모델), 분석 방식, 로컬 모델 목록, 사용자 화면용 분석 방식(`user_defaults`), 7단계 이름, 업로드 한도(외부 접속이면 낮춘 값) |
| `GET /api/models` | **개발자 전용.** 추론 서버 `/models`를 대신 조회(모델 설치 상태) |
| `PUT /api/dev/user-defaults` | **개발자 전용.** `{analysis_backend, local_model}` — 사용자 화면에서 시작한 분석에 쓸 분석 방식을 `runs/user_defaults.json`에 저장하고 저장된 값을 반환 |
| `POST /api/uploads` | multipart `file` 업로드. 확장자(MP4/MOV/AVI)·크기·디스크 여유·ffprobe 검증 후 `data/input/uploads/<업로드 ID>/input.<확장자>`에 저장. `{upload_id, filename, title, source_key}` 반환 |
| `POST /api/uploads/youtube` | `{url}` — 서버가 `yt-dlp`로 직접 내려받아 같은 형식으로 반환 |
| `DELETE /api/uploads/{upload_id}` | 다른 영상으로 바꿀 때 이전 업로드 삭제(실행 중인 작업의 영상은 보존) |

`user_defaults`는 `runs/user_defaults.json`에서 읽으며, 파일이 없거나 값이 잘못됐으면 `{analysis_backend: "local", local_model: <기본 로컬 모델>}`입니다. 일반 사용자가 유료 API 사용 여부 등을 고르지 못하게 하려는 것입니다.

업로드 정보(파일명·제목)는 업로드 폴더의 `upload.json`에 남겨, 분석 시작 시 실행 기록의 영상 제목으로 씁니다.

### 분석 실행

| 메서드·경로 | 설명 |
| --- | --- |
| `GET /api/runs/active` | 서버 전체에서 실행 중인 분석의 `run_id`(없으면 `null`) |
| `POST /api/runs` | `{upload_id, summary_level, analysis_backend, local_model}`로 파이프라인 시작, `{run_id}` 반환. 다른 분석이 실행 중이면 409. 개발자 모드가 아니면 보낸 `analysis_backend`·`local_model`을 무시하고 `user_defaults`를 씀 |
| `GET /api/runs/{run_id}` | 진행 상황. `state`(`running`/`success`/`failed`/`cancelled`/`interrupted`), 7단계별 상태·퍼센트·메시지, 현재 단계, 필터링한 최근 로그 40줄(개발자 모드가 아니면 `logs`는 빈 목록) |
| `POST /api/runs/{run_id}/cancel` | 분석 중지(프로세스 트리 종료 후 `cancelled` 기록) |

React 화면은 실행 중인 동안 `GET /api/runs/{run_id}`를 1초마다 호출합니다. 프로세스가 정상 종료 기록 없이 끝났으면(강제 종료·서버 재시작 등) 이 조회 시점에 `interrupted`로 기록합니다(Streamlit과 같은 규칙).

### 결과

| 메서드·경로 | 설명 |
| --- | --- |
| `GET /api/runs/{run_id}/result` | 요약 결과와 `video_url`. 요약 파일이 없으면 404 |
| `GET /api/runs/{run_id}/video` | 원본 영상(Range 요청 지원 → 브라우저에서 구간 이동 가능) |
| `GET /api/runs/{run_id}/frames/{index}` | OCR 결과 `index`번째 항목의 프레임 이미지 |
| `POST /api/runs/{run_id}/save` | `data/saved/[제목] - YYYYMMDD-HHMMSS/`에 영상·요약·프레임 저장, 폴더명만 반환 |

결과는 실행 산출물 폴더(`runs/jobs/<run_id>/`)에서 읽으므로 보존 기간(`JOB_RETENTION_HOURS`, 기본 72시간)이 지나면 404가 됩니다. 계속 보려면 저장해야 합니다.

### 저장된 요약

| 메서드·경로 | 설명 |
| --- | --- |
| `GET /api/saved` | 저장 폴더 목록 `{name, title, saved_at}` (최신순) |
| `GET /api/saved/{name}` | 저장본의 요약 결과, `title`·`saved_at`(폴더명에서 해석), `video_url` |
| `GET /api/saved/{name}/video`, `/frames/{index}` | 저장본의 영상과 프레임 |
| `DELETE /api/saved/{name}` | 저장 폴더 삭제(되돌릴 수 없음) |

`name`은 `data/saved/` 바로 아래 폴더 이름만 허용합니다(`..`·경로 구분자 거부).

### 실행 이력 (개발자 전용)

| 메서드·경로 | 설명 |
| --- | --- |
| `GET /api/history` | `runs/history/*/metrics.json` 목록(최신순). 각 기록에 결과 화면을 열 수 있는지(`has_result`) 추가 |
| `GET /api/history/{run_id}` | 기록 전체, 모델 로딩 행, 로그 마지막 100KB |
| `GET /api/history/{run_id}/log` | 원본 로그 파일 다운로드 |
| `POST /api/history/csv` | `{run_ids}`에 해당하는 기록을 CSV로 반환(`records_csv`, 수식 주입 방지 포함) |

## 요약 결과 형식

`GET .../result`와 `GET /api/saved/{name}`은 아래 셋 중 하나의 `mode`를 돌려줍니다.

| `mode` | 언제 | 내용 |
| --- | --- | --- |
| `blocks` | 마크다운 요약, 또는 결과 JSON에 강의 노트(`lecture_note`)가 있음 | `parse_summary_markdown()` 결과. `markdown` 블록(타임라인 표기를 분:초로 바꾼 텍스트)과 `items` 블록(`### N. 제목 (타임라인: …)` 항목 카드) |
| `structured` | JSON에 `title`/`main_topic`/`topics`/`conclusion`/`keywords`가 있음 | 해당 필드 그대로(문자열 주제는 `{content}`로 감쌈) |
| `raw` | 위 둘 다 아님 | JSON 원본 |

`blocks` 형태에는 사용자용 강의노트(챕터 플레이어) 화면을 위한 `outline`도 함께 들어갑니다. 만드는 방법은 두 가지입니다.

1. **강의 노트 JSON** — gpu-server 최종 요약 결과에 챕터가 있는 `lecture_note`가 있으면(`is_lecture_note`) 마크다운 파싱 없이 그 JSON으로 만듭니다(`_lecture_note_outline`). 이때 `structured` 판정보다 먼저 확인합니다. 시간이 없는 챕터·자료도 버리지 않고 `start: null`, `label: "시간 정보 없음"`으로 넘깁니다(화면은 재생 버튼만 숨김). `terms`·`notices`가 채워지고, 키워드는 `terms`의 용어를 먼저 쓴 뒤 아래 방식으로 채웁니다.
2. **마크다운 파싱** — 그 외에는 `_outline`이 아래 규칙으로 마크다운 블록에서 만듭니다. 번호 매긴 타임라인 챕터가 하나도 없으면 `null`이고, `terms`·`notices`는 항상 빈 목록입니다.

| 필드 | 만드는 방법 |
| --- | --- |
| `title` | `# 제목` 줄 |
| `key_points` | 제목에 "핵심"이 들어간 섹션(`## 핵심 주제`)의 목록. 없으면 결론 앞 3개 |
| `keywords` | 요약에서 따옴표로 강조한 용어('스타실드' 등) + 음성 요약의 중요 구간 주제(`runs/jobs/<run_id>/llm/stt_summary_result.json`, 실행 결과에만 있음). 2~15자, 서로 겹치는 표현 제외, 최대 6개 |
| `chapters` | 표/차트가 아닌 `items` 블록 항목. `{index, title, start, end, label, points, screen_notes, thumb_url, frames}`. "VLM 요약 자료에서는 …"으로 시작하는 항목은 접두어를 떼어 `screen_notes`로 분리. `thumb_url`은 챕터 구간의 대표 프레임(구간 안에 없으면 ±1초, 그래도 없으면 `null`), `frames`는 구간 안의 서로 다른 화면 목록 |
| `visuals` | 표/차트 섹션 항목(`items` 항목 + `section`). 강의 노트 JSON에서 만들면 `kind`(표·그래프·수식·코드·도식)도 있고, `text`는 `content` 목록과 "강의에서의 의미" |
| `terms` | `{term, definition}` 목록(강의 노트 JSON에만 있음) |
| `notices` | 과제·시험·공지 목록(강의 노트 JSON에만 있음) |
| `conclusion` | 제목에 "결론"이 들어간 섹션의 목록 |
| `extras` | 위에 들지 않은 마크다운 |

이 규칙은 gpu-server 최종 요약 프롬프트의 출력 형식(`## 핵심 주제`, `## 주요 내용`, `### N. 제목 (타임라인: …)`, `## 종합 결론`)에 맞춘 것입니다. 형식이 바뀌면 여기를 함께 고쳐야 합니다. 저장된 요약(`/api/saved/{name}`)에는 음성 요약 파일이 없어 키워드가 따옴표 강조 용어만으로 만들어집니다.

`items` 블록의 항목은 `{index, title, start, end, label, text, image_url, frames}`입니다. `start`(초)는 화면에서 영상 이동에 쓰고, `label`은 `0:10 ~ 0:20` 같은 표시용 문자열입니다. 제목에 "표"·"차트"가 있는 섹션만 `image_url`과 `frames`를 채웁니다.

`frames`는 `{url, time, label}` 목록으로, 타임라인 구간 안의 서로 다른 화면을 시간순으로 최대 4장 담습니다(`app/summary_parse.py`의 `find_matching_frames`, `MAX_FRAMES_PER_ITEM`). 구간 안에 프레임이 없을 때만 앞뒤 1초까지 넓혀 찾고, 4장을 넘으면 시간상 고르게 줄입니다. 표/차트 항목은 `chart_or_table` 화면이 있으면 그것만 씁니다. 프레임 추출 단계(representative 방식)에서 같은 화면을 이미 하나로 묶었기 때문에 여기 나오는 프레임은 서로 다른 화면입니다. 이미지 주소는 서버 절대경로 대신 OCR 결과 항목 번호(`/frames/{index}`)로 만들어, 서버 경로를 노출하지 않고 임의 파일을 읽을 수도 없습니다.

## 로그인과 보안

| 항목 | 동작 |
| --- | --- |
| 비밀번호 | `APP_PASSWORD` 환경변수 → 없으면 `.streamlit/secrets.toml`의 `APP_PASSWORD`. 파일이 깨져 있으면 로그인을 건너뛰지 않고 오류 |
| 비밀번호 미설정 | 로컬·Cloudflare 경유 외부 접속 모두 로그인 없이 통과(사용자 화면 공개). 개발자 전용 API는 여전히 개발자 비밀번호 필요 |
| 개발자 모드 | `DEV_PASSWORD`(기본 `admin`)로 `/api/dev/login`. 쿠키 `vs_dev`는 일반 세션과 같은 형식이지만 서명에 `dev:` 범위를 넣어 일반 세션 쿠키를 개발자 쿠키로 쓸 수 없음. 개발자 비밀번호를 바꾸면 기존 개발자 세션이 무효 |
| 세션 | HttpOnly·SameSite=Lax 쿠키 `vs_session`(외부·HTTPS 접속이면 Secure). 만료 시각과 HMAC 서명만 담고, 서명에 비밀번호 해시를 넣어 비밀번호를 바꾸면 기존 세션이 모두 무효 |
| 세션 키 | `APP_SESSION_SECRET`(없으면 서버 시작 시 무작위 → 재시작하면 다시 로그인), 유효 시간 `APP_SESSION_HOURS`(기본 12) |
| 무차별 대입 | 같은 IP 5회 연속 실패 시 60초 잠금(`app/login_throttle.py`, Streamlit과 공유) |
| CSRF | `/api`의 GET 외 요청은 `X-Requested-With: XMLHttpRequest` 헤더가 없으면 403. CORS는 열지 않아 다른 사이트가 이 헤더를 붙일 수 없음 |
| 업로드 크기 | 본문을 받기 전에 `Content-Length`로 확인. 한도 `MAX_UPLOAD_MB`(500), 외부 접속은 `EXTERNAL_UPLOAD_LIMIT_MB`(100, Cloudflare 요청 한도) |
| 경로 | 업로드 ID·실행 ID·저장 폴더명은 형식 검증 후 정해진 폴더 안에서만 찾음 |
| 노출 정보 | 응답에 서버 절대경로를 넣지 않음. API 문서 화면(`/docs`, `/openapi.json`)은 끔 |

## 환경변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `APP_PASSWORD` | 없음 | 로그인 비밀번호(없으면 `.streamlit/secrets.toml`). 둘 다 없으면 로그인 없이 공개 |
| `DEV_PASSWORD` | `admin` | 개발자 화면(`/dev`)·개발자 전용 API 비밀번호. 외부 공개 시 반드시 변경 권장 |
| `APP_SESSION_SECRET` | 시작 시 무작위 | 세션 서명 키. 고정하면 재시작 후에도 로그인 유지 |
| `APP_SESSION_HOURS` | `12` | 로그인 유지 시간 |
| `MAX_UPLOAD_MB` | `500` | 업로드 한도 |
| `EXTERNAL_UPLOAD_LIMIT_MB` | `100` | Cloudflare 경유 업로드 한도 |
| `FRONTEND_DIST` | `frontend/dist` | React 빌드 결과 위치 |
| `GPU_SERVER_URL` | `http://127.0.0.1:8000` | 추론 서버 주소(파이프라인에 전달) |
| `JOB_RETENTION_HOURS`, `MIN_FREE_DISK_GB` | `72`, `5` | `run_registry`와 동일 |

## 테스트

`tests/test_api_server.py`가 FastAPI `TestClient`로 로그인·잠금·CSRF, 개발자 모드(별도 비밀번호·`DEV_PASSWORD` 변경, 앱 로그인 선행 필요, 사용자 실행에 개발자가 지정한 분석 방식 적용, 비개발자에게 분석 로그 숨김), 업로드 검증·크기 제한·경로 탐색 차단, 실행 시작·중복 실행 거부·진행 상황 해석·중단 기록, 결과 블록·`outline`(마크다운·강의 노트 JSON)·구간별 프레임 목록·영상, 저장·삭제, 실행 이력·CSV, React 라우트 대체를 확인합니다. 실제 파이프라인과 추론 서버는 호출하지 않습니다.
