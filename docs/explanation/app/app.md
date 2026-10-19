# 앱 (`app/`)

`app/` 폴더는 영상 업로드(파일 업로드 또는 유튜브 링크), 분석 파이프라인 실행, 최종 요약 결과 확인/저장을 담당합니다. 화면은 두 가지입니다.

| 화면 | 진입점 | 상태 |
| --- | --- | --- |
| React 화면 + 앱 API 서버 | `frontend/` + `app/api/server.py` | **기본**. `start_all.bat`이 실행 → [앱 API 서버](app_api.md), [React 화면](../frontend/frontend.md) |
| Streamlit 화면 | `app/main.py`, `app/pages/` | 예비. `start_all.bat -Streamlit` 또는 `run_app.bat` |

두 화면은 아래 공통 모듈(업로드 저장, 파이프라인 실행, 로그 해석, 결과 저장)을 함께 쓰므로 실행 기록·저장 결과·동작 규칙이 같습니다. 같은 포트(8501)를 쓰므로 하나만 실행합니다. 이 문서의 나머지는 공통 모듈과 Streamlit 화면을 설명합니다.

## 현재 파일

공통 모듈 (UI 라이브러리에 의존하지 않음)

| 파일 | 역할 |
| --- | --- |
| `app/api/` | React 화면용 FastAPI 앱 API 서버 ([app_api.md](app_api.md)) |
| `app/run_registry.py` | 업로드 폴더·실행 폴더(`runs/jobs/<run_id>`), 서버 전체 단일 실행 슬롯, 디스크 확인, 보존 기간 정리 |
| `app/pipeline_process.py` | `scripts/run_pipeline.py` 실행(`launch_pipeline`)과 중지(`stop_pipeline`) |
| `app/pipeline_log.py` | `process.log` 읽기, `##PROGRESS##`·Whisper tqdm 파싱, 단계 상태 계산, 화면용 로그 필터 (예전에는 `1_upload.py` 안에 있었음) |
| `app/summary_parse.py` | 최종 요약의 타임라인 표기를 블록 구조로 해석, 분:초 변환, 표/차트 구간 프레임 찾기 (예전에는 `summary_timeline.py` 안에 있었음) |
| `app/saved_results.py` | `data/saved/` 목록·폴더명 해석·영상 찾기·폴더명 검증 (예전에는 `3_saved_summaries.py` 안에 있었음) |
| `app/login_throttle.py` | 같은 IP 연속 실패 시 로그인 잠금 (예전에는 `auth.py` 안에 있었음) |
| `app/summary_result.py` | 결과 파일 로더와 요약 데이터 판별 |
| `app/result_export.py` | 영상 + 최종 요약 결과를 `data/saved/`에 복사해 저장 |
| `app/app_logging.py` | 접속 기록 로거 |
| `app/__init__.py` | app 패키지 표시 |

Streamlit 화면

| 파일 | 역할 |
| --- | --- |
| `app/main.py` | Streamlit 앱 진입점, 업로드 페이지로 이동 |
| `app/auth.py` | `require_login()` — `st.secrets["APP_PASSWORD"]`가 설정된 경우에만 비밀번호 로그인 화면을 띄우는 선택적 게이트 |
| `app/analysis_options.py` | 분석 방식·로컬 모델·Whisper 설정 위젯, 모델 설치 상태 |
| `app/pages/1_upload.py` | 영상 업로드(파일/유튜브), 분석 설정, 파이프라인 백그라운드 실행, 실시간 진행률/오류 표시, 분석 중지 |
| `app/pages/2_analysis_result.py` | 원본 영상과 최종 요약 결과 표시, 결과 저장 버튼 |
| `app/pages/3_saved_summaries.py` | `data/saved/`에 저장된 결과 목록을 불러와 다시 확인하거나 삭제 |
| `app/pages/4_run_history.py` | 실행 이력과 성능 지표 ([run_history.md](../../run_history.md)) |
| `app/final_summary_view.py` | 영상+요약을 나란히 표시하는 공통 렌더링 함수, 자체 테스트 페이지 |
| `app/summary_timeline.py` | `summary_parse.py`가 해석한 블록을 클릭 가능한 뱃지/카드로 렌더링 |
| `app/styles.py` | Streamlit 공통 CSS (React 화면은 `frontend/src/index.css`에 같은 색·모양을 옮김) |

네 페이지(`1_upload.py` ~ `4_run_history.py`)와 `main.py`는 모두 `st.set_page_config()` 직후 `require_login()`을 호출합니다.

## 실행 (Streamlit 화면)

React 화면 실행은 [React 화면](../frontend/frontend.md)과 [단일 서버 운영 가이드](../../single_server_deployment.md)를 참고하세요. Streamlit 화면은 추론 서버와 함께 다음과 같이 실행합니다.

```bat
start_all.bat -Streamlit
```

Streamlit만 단독 실행(Windows 배치 파일):

```bat
run_app.bat
```

직접 실행:

```bash
streamlit run app/main.py
```

`run_app.bat`는 `capstone` conda 환경 활성화를 시도한 뒤 `streamlit run app\main.py`를 실행합니다.

`.streamlit/config.toml`에는 업로드 용량 제한(`maxUploadSize = 500`), XSRF 보호, 외부 사용자용 메뉴·오류 상세 숨김 설정이 있습니다. React 화면의 업로드 한도는 앱 API 서버의 `MAX_UPLOAD_MB`(기본 500)입니다.

> 한때 `st.video()` 대신 정적 파일 서빙(`enableStaticServing`)을 검토했지만, Streamlit에 하드코딩된 200MB 파일 크기 제한 때문에 폐기했습니다. 영상 표시는 항상 `st.video()`를 사용합니다.

## 로그인 게이트 (`app/auth.py`)

`require_login()`은 `st.secrets.get("APP_PASSWORD")`가 비어 있으면 아무 일도 하지 않고 그대로 통과시킵니다(로컬 전용 실행 등). 값이 설정되어 있으면 비밀번호 입력 화면을 띄우고, 맞는 비밀번호를 입력해 `st.session_state["authenticated"] = True`가 될 때까지 `st.stop()`으로 이후 렌더링을 막습니다. Cloudflare Tunnel(`start_tunnel.ps1`) 등으로 앱을 외부에 노출할 때 사용하기 위한 것으로, `app/main.py`와 모든 페이지가 `apply_global_styles()`보다 먼저 호출합니다. 비밀번호가 없는데 Cloudflare를 거친 접속(`Cf-Connecting-Ip` 헤더)이면 차단합니다. 연속 실패 잠금은 `app/login_throttle.py`에 있으며 React 화면의 로그인(`app/api/auth.py`)과 같은 규칙을 씁니다.

## 업로드 페이지

`app/pages/1_upload.py`는 다음 일을 처리합니다.

1. 라디오 버튼(`파일 업로드` / `유튜브 링크`)으로 업로드 방식 선택
2. **파일 업로드**: `mp4`, `mov`, `avi` 파일을 원본 확장자를 유지한 채 업로드마다 고유한 폴더 `data/input/uploads/<시각-무작위ID>/input{확장자}`에 저장 (`app/run_registry.py`의 `new_upload_dir()`)
   - 원본 확장자를 유지해야 MOV/AVI가 mp4로 위장되어 변환이 건너뛰어지는 문제가 생기지 않습니다.
   - 디스크 여유 공간 확인, 저장 후 파일 크기 검증, ffprobe로 실제 영상인지 확인. 실패하면 폴더를 지우고 오류 표시
   - 영상 제목은 파일명(확장자 제외)으로 `st.session_state["video_title"]`에 저장
3. **유튜브 링크**: `modules/preprocess/youtube_downloader.py`의 `download_youtube_video(url, output_path)`로 다운로드
   - 내부적으로 `yt-dlp` 사용, 확장자와 무관하게 항상 `.mp4`로 저장(기존 파일이 있으면 삭제 후 재다운로드)
   - 반환값은 `(저장 경로, 영상 제목)` 튜플이며 영상 제목은 유튜브 메타데이터의 실제 제목
   - `is_youtube_url(url)`로 링크 형식을 먼저 검증
4. 업로드 박스 옆 "⚙️ 분석 설정" 박스에서 분석 방식(로컬 모델 서버/Claude API), 로컬 모델, Whisper 음성 인식(간단 small / 기본 medium / 상세 large)을 선택 (`app/analysis_options.py`, 기본값 `standard`). 세 Whisper 설정 모두 OCR·VLM을 실행하며 Whisper 크기만 다릅니다. 분석 진행 중에는 비활성화됩니다. 자세한 내용은 [분석 방식 설정](../../analysis_backends.md)을 참고하세요.
5. `app/pipeline_process.py`의 `launch_pipeline()`이 `scripts/run_pipeline.py --video <저장된 경로> --summary-level <선택값> --run-dir runs/jobs/<run_id> ...`을 `subprocess.Popen`으로 실행. 서버 전체에서 한 번에 하나만 실행하며(`run_registry.start_job`), 다른 분석이 진행 중이면 시작 버튼이 비활성화됩니다 (`--skip-stt` 옵션은 비활성화되어 있어 STT는 항상 실행됨)
6. stdout/stderr를 `runs/history/<run_id>/process.log`에 저장 (UTF-8 강제: `PYTHONIOENCODING`/`PYTHONUTF8` 환경변수 설정)
7. `app/pipeline_log.py`가 로그에서 `##PROGRESS##` 마커(JSON)와 Whisper STT의 tqdm 퍼센트 표시줄을 파싱해 "분석 절차" 영역의 7개 단계별 원형 아이콘을 실시간으로 갱신
8. 사람이 보는 로그 영역은 진행률 마커/tqdm 진행바/산출물 경로 줄을 필터링해서 표시 (`read_pipeline_logs`)
9. 분석 완료(returncode 0) 시 `pages/2_analysis_result.py?run=<run_id>`로 이동. 새로고침해도 주소의 `?run=` 값으로 진행 중인 작업이나 결과에 다시 연결됩니다. 프로세스가 0이 아닌 코드로 끝나고 사용자가 직접 중지한 것이 아니면(`analysis_cancelled`가 아님) 진행 중이던 단계가 오류 상태로 표시됨
10. 분석 중지 버튼으로 프로세스 종료

Windows에서는 중지 시 `taskkill /PID <pid> /T /F`를 사용합니다.

### 분석 절차 진행률 표시

7단계는 `modules/common/progress.py`의 `STEP_LABELS`에 정의되어 있으며, 업로드 페이지와 `scripts/run_pipeline.py`가 이 번호 체계를 공유합니다. "영상 업로드"는 이 7단계에 포함되지 않는 별도 사전 단계입니다.

| 단계 번호 | 이름 | 설명 |
| --- | --- | --- |
| 1 | 오디오 추출 | 영상에서 음성 분리 |
| 2 | STT 분석 | 음성을 텍스트로 변환 |
| 3 | STT 요약 | 핵심 내용 및 중요 구간 요약 |
| 4 | 프레임 추출 | 중요 구간 프레임 선택 |
| 5 | OCR 분석 | 화면 텍스트 및 시각 정보 이해 |
| 6 | VLM 요약 생성 | 프레임별 시각 요약 생성 |
| 7 | 최종 요약 생성 | 음성/시각 요약 통합 |

파이프라인은 `report_progress(step, message, percent)`로 `##PROGRESS## {"step": ..., "message": ..., "percent": ...}` 형태의 JSON 줄을 표준 출력에 남기고, `app/pipeline_log.py`의 `parse_progress_state`, `describe_step_status`가 이를 파싱해 단계별 원형 아이콘 상태를 계산합니다. React 화면은 같은 계산 결과를 앱 API(`GET /api/runs/{run_id}`)로 받아 그립니다.

| 상태 | 조건 | 표시 |
| --- | --- | --- |
| 대기중 (`pending`) | 현재 진행 중인 단계보다 뒤 | 회색 원에 단계 숫자 |
| 진행중·퍼센트 있음 (`active-percent`) | 현재 단계이고 percent 값이 있음(주로 STT tqdm) | 원이 conic-gradient로 퍼센트만큼 차오르고, 원 안에 `NN%` 텍스트 |
| 진행중·퍼센트 모름 (`active-indeterminate`) | 현재 단계이고 percent 값이 없음 | 원이 스피너 애니메이션으로 회전, 아래에 현재 메시지 텍스트 |
| 완료 (`done`) | 현재 진행 중인 단계보다 앞 | 원이 파란색으로 채워지고 체크마크(`✓`) 표시 |
| 오류 (`error`) | 파이프라인 프로세스가 0이 아닌 코드로 종료되고 사용자가 중지한 것이 아님 | 현재 진행 중이던 단계 원이 빨간색(`step-error`)으로 바뀌고 `✕` 표시, 설명 텍스트도 빨간색(`step-error-text`)으로 표시 |

같은 단계에서 퍼센트 없는 메시지가 나중에 도착해도 이전 퍼센트 값은 유지됩니다(sticky).

> `get_analysis_process()` 함수는 두 분기가 항상 같은 값을 반환해 `poll()` 체크가 의미 없는 죽은 로직이었기 때문에 주석 처리되었습니다. 호출부는 `st.session_state.get("analysis_process")`를 직접 사용합니다.

## 결과 페이지

`app/pages/2_analysis_result.py`는 주소의 `?run=<run_id>`(없으면 세션의 마지막 실행)로 실행 폴더 `runs/jobs/<run_id>/`를 찾고, `app/final_summary_view.py`의 `render_video_and_summary()`를 다음 옵션으로 호출해 원본 영상과 요약 결과를 나란히 표시합니다.

| 파라미터 | 값 |
| --- | --- |
| `column_ratio` | `(0.85, 1.15)` |
| `column_gap` | `"medium"` |
| `show_captions` | `False` (파일 경로 캡션 숨김) |
| `summary_container_height` | `600` |
| `ocr_result_path` | `runs/jobs/<run_id>/ocr/ocr_result.json` — 표/차트 스크린샷 조회에 사용 (실행 ID가 없으면 예전 경로 `runs/ocr/ocr_result.json`) |

| 영역 | 데이터 |
| --- | --- |
| 원본 영상 | 실행 정보(`job.json`)의 업로드 영상 경로 — 없거나 존재하지 않으면 `data/input/input.mp4`로 폴백, 그마저 없으면 경고 표시 |
| 요약 결과 | `runs/jobs/<run_id>/final/final_summary_result.json` 우선, 없으면 같은 폴더의 `final_summary.txt` (`load_final_summary`) |

실행 폴더는 보존 기간(`JOB_RETENTION_HOURS`, 기본 72시간)이 지나면 정리되므로, 오래 볼 결과는 저장해야 합니다.

요약을 찾거나 읽지 못하면 경고와 함께 "영상 업로드로 이동" 버튼을 표시하고 페이지를 중단합니다.

### 결과 저장

"💾 영상과 요약 결과 저장" 버튼을 누르면 `app/result_export.py`의 `save_analysis_result()`가 실행되어 현재 영상 파일과 실행 폴더 `final/`의 `final_summary.txt`/`final_summary_result.json`을 `data/saved/[영상 제목] - YYYYMMDD-HHMMSS/` 폴더에 복사합니다. 제목이 없으면 날짜시각(`YYYYMMDD-HHMMSS`)만으로 폴더명을 만들고, 폴더명에 쓸 수 없는 Windows 금지 문자(`\ / : * ? " < > |`)는 제거됩니다. 영상과 요약 결과가 모두 없으면 `FileNotFoundError`가 발생해 화면에 에러로 표시됩니다.

실행 폴더의 `ocr/ocr_result.json`이 있으면 함께 저장됩니다. `_copy_ocr_result_with_frames()`가 OCR 결과 안의 `image_path`가 가리키는 프레임 이미지를 저장 폴더의 `frames/`로 복사하고, JSON의 `image_path`도 그 복사본을 가리키는 `frames/<파일명>` 상대경로로 고쳐서 `data/saved/.../ocr_result.json`에 저장합니다. 실행 폴더의 원본 이미지는 보존 기간이 지나면 정리되므로, 복사해두지 않으면 나중에 저장 결과를 열었을 때 표/차트 스크린샷이 다른 영상의 프레임으로 바뀌어 보이는 문제가 있었기 때문입니다.

## 저장된 요약 페이지 (`app/pages/3_saved_summaries.py`)

`data/saved/` 아래 폴더들을 스캔해 저장된 결과 목록을 보여줍니다. 목록·폴더명 해석·영상 찾기 함수는 `app/saved_results.py`에 있으며 앱 API(`/api/saved`)도 같은 함수를 씁니다.

1. `list_saved_items()`가 `data/saved/`의 하위 폴더를 모두 순회하고, `parse_saved_folder_name()`으로 폴더명 `[제목] - YYYYMMDD-HHMMSS`에서 제목과 저장 시각을 추출해 시각 역순으로 정렬 (패턴에 맞지 않으면 폴더명 전체를 제목으로 사용하고 시각은 `None`)
2. 라디오 버튼으로 항목을 고르면 `find_saved_video()`가 폴더 안에서 `.mp4`/`.mov`/`.avi` 중 먼저 찾은 파일을 영상으로 사용
3. `load_final_summary(selected_folder)`로 요약을 읽어 `render_video_and_summary()`로 2번 페이지와 동일한 레이아웃(`column_ratio=(0.85, 1.15)`, `summary_container_height=600`)으로 표시. `ocr_result_path=selected_folder / "ocr_result.json"`을 넘겨 저장 당시 함께 복사된 프레임(`frames/`)으로 표/차트 스크린샷도 복원(저장 시점에 OCR 결과가 없었으면 이 파일 자체가 없어 스크린샷 없이 표시). 읽기 실패 시 경고만 표시하고 중단
4. "🗑️ 이 저장 결과 삭제" 버튼은 `st.session_state["confirm_delete_folder"]`로 확인 단계를 거친 뒤 `shutil.rmtree()`로 폴더 전체를 삭제 (되돌릴 수 없음)

저장된 항목이 하나도 없으면 안내 메시지와 함께 업로드 페이지로 이동하는 버튼을 표시합니다.

## 요약 렌더링

`app/final_summary_view.py`의 `render_summary_data(summary_data)`는 구조화된 필드(`title`/`main_topic`/`topics`/`conclusion`/`keywords`)가 있으면 그것을 UI 컴포넌트(제목, 핵심 주제 박스, 키워드 뱃지, 주제별 expander, 종합 결론 박스)로 나누어 표시합니다.

> **주의**: 실제로는 GPU 서버가 이 구조화된 필드들을 절대 반환하지 않기 때문에 이 분기는 사실상 죽은 코드입니다(향후 호환을 위해 남겨둠). 실제 렌더링 경로는 항상 `get_summary_markdown()`으로 얻은 자유 텍스트를 `render_summary_with_timeline()`으로 표시하는 쪽입니다.

## 타임라인 렌더링 (`app/summary_parse.py` → `app/summary_timeline.py`)

최종 요약 텍스트(마크다운 문자열)에는 `(타임라인: 66.0 ~ 813.0)` 같은 초 단위 표기가 곳곳에 들어 있습니다. 해석은 `app/summary_parse.py`의 `parse_summary_markdown(markdown_text, ocr_result_path, project_root)`가 맡아 `##` 단위 섹션을 `markdown` 블록과 `items` 블록(항목 번호·제목·시작/끝 초·분:초 표시·본문·프레임 경로)으로 나눕니다. Streamlit의 `render_summary_with_timeline()`과 React 화면(앱 API의 `blocks`)이 같은 결과를 그립니다.

| 섹션 유형 | 판별 조건 | 렌더링 |
| --- | --- | --- |
| 번호 매겨진 항목 섹션 | 본문에 `### N. 제목 (타임라인: 시작 ~ 끝)` 형태가 있음 (`HAS_NUMBERED_ITEM_PATTERN`) | 항목별로 테두리 박스(`st.container(border=True)`) 카드 렌더링, 각 카드에 분:초 형식(`1:06 ~ 13:33`) 클릭 가능한 타임라인 뱃지 부착 |
| 표/차트 섹션 | 위 조건을 만족하면서 제목에 "표" 또는 "차트"가 포함 | 위 카드에 더해, OCR 결과(`ocr_result.json`)에서 해당 타임라인 구간(±1초)에 매칭되는 프레임 스크린샷도 함께 표시 (`scene_type == "chart_or_table"`인 프레임 우선, 없으면 구간 내 아무 프레임) |
| 그 외 일반 섹션 | 위 조건에 해당하지 않음 (핵심 주제, 종합 결론 등) | 마크다운 그대로 표시하되 `(타임라인: ...)` 표기만 분:초 형식의 일반 텍스트로 변환(클릭 불가) |

타임라인 뱃지를 클릭하면 자바스크립트가 `document.querySelector('video')`로 페이지의 `<video>` 엘리먼트를 찾아 `currentTime`을 이동시키고 재생합니다. 페이지 새로고침은 없습니다.

> **중요 구현 디테일**: 이 뱃지는 `st.markdown(unsafe_allow_html=True)`가 아니라 **`st.html(..., unsafe_allow_javascript=True)`**로 렌더링합니다(`_render_timeline_badge` 함수). `st.markdown`으로 `onclick` 속성이 있는 HTML을 넣으면 Streamlit이 이를 React 엘리먼트로 변환하는 과정에서 `onclick`이 문자열로 취급되어 런타임 에러(React #231)가 발생합니다. `st.html`은 iframe 없이 문서에 HTML을 그대로 삽입하고 내부 자바스크립트를 실제로 실행하므로 이 문제가 없습니다. 추후 실수로 `st.markdown`으로 되돌리지 않도록 주의해야 합니다. React 화면은 이 우회 없이 일반 클릭 이벤트로 처리합니다.

## 결과 로더

`app/summary_result.py`의 `load_final_summary(final_dir)`는 다음 순서로 파일을 찾습니다.

1. `final_summary_result.json`
2. `final_summary.txt`

JSON이 있으면 `mode="json"`으로, 텍스트 파일만 있으면 `mode="markdown"`으로 `FinalSummary(mode, content, source_path)`를 반환합니다. 둘 다 없으면 `FileNotFoundError`가 발생합니다.

- `get_summary_markdown(summary_data)`: JSON 안의 `summary` 또는 `final_summary` 키에서 자유 텍스트를 찾아 반환합니다.
- `has_structured_summary(summary_data)`: `title`/`main_topic`/`topics`/`conclusion`/`keywords` 중 하나라도 값이 있으면 `True`를 반환합니다(실제로는 항상 `False`).

## 세션 상태

앱에서 사용하는 주요 `st.session_state` 키는 다음과 같습니다.

| 키 | 의미 |
| --- | --- |
| `video_path` | 업로드/다운로드 후 저장된 영상 경로 |
| `uploaded_filename` | 표시용 파일명(파일 업로드는 원본 파일명, 유튜브는 저장된 파일명) |
| `uploaded_file_key` | 같은 파일/링크의 중복 처리를 막기 위한 키 — 파일은 `"{파일명}_{크기}"`, 유튜브는 `"youtube_{url}"` |
| `video_title` | 영상 제목 — 파일 업로드는 파일명(확장자 제외), 유튜브는 실제 영상 제목. 결과 저장 폴더명에 사용 |
| `summary_level` | 선택된 요약 프리셋(`simple`/`standard`/`detailed`), 기본값 `standard` |
| `analysis_process` | 실행 중인 파이프라인 `subprocess.Popen` 프로세스 |
| `analysis_log_handle` | 로그 파일 핸들 |
| `analysis_run_id` / `attached_run_id` | 현재 연결된 실행 ID (주소의 `?run=`과 함께 새로고침 후 복원에 사용) |
| `analysis_run_dir` / `analysis_history_dir` / `analysis_log_path` | 실행 산출물 폴더, 실행 이력 폴더, `process.log` 경로 |
| `analysis_done` | 분석 완료 여부 |
| `analysis_cancelled` | 분석 중지 여부 |
| `last_analysis_log` | 마지막 표시 로그 |
| `authenticated` | `require_login()`이 로그인 성공 시 설정 (`APP_PASSWORD` 미설정 시 사용 안 함) |
| `confirm_delete_folder` | 저장된 요약 페이지에서 삭제 확인 중인 폴더 경로 |

## 주의 사항

- 앱은 파이프라인을 별도 프로세스로 실행하므로 GPU 서버, FFmpeg, Whisper, EasyOCR 환경이 CLI 실행과 동일하게 준비되어야 합니다.
- 유튜브 링크 다운로드를 사용하려면 `yt-dlp` 패키지가 설치되어 있어야 합니다.
- 업로드 파일은 원본 확장자를 유지해 `data/input/uploads/<업로드 ID>/input{확장자}`로 저장됩니다(유튜브 다운로드는 항상 `.mp4`).
- `--skip-stt` 옵션은 현재 비활성화되어 있어 STT 단계는 항상 실행됩니다.
- 최종 결과 페이지는 실행 폴더(`runs/jobs/<run_id>/final`) 산출물이 있어야 정상 표시되며, 표/차트 구간 스크린샷을 보려면 같은 폴더의 `ocr/ocr_result.json`도 필요합니다.
- 간단·기본·상세 모두 OCR·VLM을 실행합니다(Whisper 크기만 다름). 수동 `--skip-ocr`로 OCR을 건너뛴 실행만 스크린샷이 없습니다. 결과 저장 시 프레임과 OCR 결과도 `data/saved/.../frames/`, `data/saved/.../ocr_result.json`으로 함께 복사되므로, 실행 폴더가 정리된 뒤에도 저장된 요약의 스크린샷은 그대로 유지됩니다.
- `require_login()`은 `.streamlit/secrets.toml`에 `APP_PASSWORD`가 설정된 경우에만 동작하며, 로컬 전용 실행에는 영향이 없습니다. React 화면은 `APP_PASSWORD` 환경변수도 읽습니다([app_api.md](app_api.md#로그인과-보안)).
