# Streamlit App

`app/` 폴더는 영상 업로드(파일 업로드 또는 유튜브 링크), 분석 파이프라인 실행, 최종 요약 결과 확인/저장을 제공하는 Streamlit UI입니다.

## 현재 파일

| 파일 | 역할 |
| --- | --- |
| `app/main.py` | Streamlit 앱 진입점, 업로드 페이지로 이동 |
| `app/pages/1_upload.py` | 영상 업로드(파일/유튜브), 파이프라인 백그라운드 실행, 실시간 진행률 표시, 분석 중지 |
| `app/pages/2_analysis_result.py` | 원본 영상과 최종 요약 결과 표시, 결과 저장 버튼 |
| `app/final_summary_view.py` | 영상+요약을 나란히 표시하는 공통 렌더링 함수, 자체 테스트 페이지 |
| `app/summary_result.py` | `runs/final` 결과 파일 로더와 요약 데이터 판별 |
| `app/summary_timeline.py` | 최종 요약 텍스트의 타임라인 표기를 파싱해 클릭 가능한 뱃지/카드로 렌더링 |
| `app/result_export.py` | 영상 + 최종 요약 결과를 `data/saved/`에 복사해 저장 |
| `app/styles.py` | Streamlit 공통 CSS |
| `app/__init__.py` | app 패키지 표시 |

`app/pages/3_settings.py`는 현재 존재하지 않습니다.

## 실행

Windows 배치 파일:

```bat
run_app.bat
```

직접 실행:

```bash
streamlit run app/main.py
```

`run_app.bat`는 `capstone` conda 환경 활성화를 시도한 뒤 `streamlit run app\main.py`를 실행합니다.

`.streamlit/config.toml`에는 업로드 용량 제한만 설정되어 있습니다.

```toml
[server]
maxUploadSize = 500
```

> 한때 `st.video()` 대신 정적 파일 서빙(`enableStaticServing`)을 검토했지만, Streamlit에 하드코딩된 200MB 파일 크기 제한 때문에 폐기했습니다. 영상 표시는 항상 `st.video()`를 사용합니다.

## 업로드 페이지

`app/pages/1_upload.py`는 다음 일을 처리합니다.

1. 라디오 버튼(`파일 업로드` / `유튜브 링크`)으로 업로드 방식 선택
2. **파일 업로드**: `mp4`, `mov`, `avi` 파일을 원본 확장자를 유지한 채 `data/input/input{확장자}` (예: `data/input/input.mov`)로 저장
   - 예전에는 무조건 `data/input/input.mp4`로 저장해서 MOV/AVI 파일이 mp4로 위장되고, 파이프라인이 실제 변환이 필요한데도 이를 건너뛰는 버그가 있었습니다. 확장자를 유지하도록 고쳐 이 문제를 해결했습니다.
   - 저장 후 파일 크기를 검증하고 불일치하면 에러 후 `st.stop()`
   - 영상 제목은 파일명(확장자 제외)으로 `st.session_state["video_title"]`에 저장
3. **유튜브 링크**: `modules/preprocess/youtube_downloader.py`의 `download_youtube_video(url, output_path)`로 다운로드
   - 내부적으로 `yt-dlp` 사용, 확장자와 무관하게 항상 `.mp4`로 저장(기존 파일이 있으면 삭제 후 재다운로드)
   - 반환값은 `(저장 경로, 영상 제목)` 튜플이며 영상 제목은 유튜브 메타데이터의 실제 제목
   - `is_youtube_url(url)`로 링크 형식을 먼저 검증
4. `scripts/run_pipeline.py --video <저장된 경로>`를 `subprocess.Popen`으로 실행 (`--skip-stt` 옵션은 비활성화되어 있어 STT는 항상 실행됨)
5. stdout/stderr를 `runs/app_pipeline.log`에 저장 (UTF-8 강제: `PYTHONIOENCODING`/`PYTHONUTF8` 환경변수 설정)
6. 로그에서 `##PROGRESS##` 마커(JSON)와 Whisper STT의 tqdm 퍼센트 표시줄을 파싱해 "분석 절차" 영역의 7개 단계별 원형 아이콘을 실시간으로 갱신
7. 사람이 보는 로그 영역은 진행률 마커/tqdm 진행바/산출물 경로 줄을 필터링해서 표시
8. 분석 완료(returncode 0) 시 `pages/2_analysis_result.py`로 이동
9. 분석 중지 버튼으로 프로세스 종료

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

파이프라인은 `report_progress(step, message, percent)`로 `##PROGRESS## {"step": ..., "message": ..., "percent": ...}` 형태의 JSON 줄을 표준 출력에 남기고, 업로드 페이지가 이를 파싱해 단계별 원형 아이콘 상태를 계산합니다(`parse_progress_state`, `describe_step_status`).

| 상태 | 조건 | 표시 |
| --- | --- | --- |
| 대기중 (`pending`) | 현재 진행 중인 단계보다 뒤 | 회색 원에 단계 숫자 |
| 진행중·퍼센트 있음 (`active-percent`) | 현재 단계이고 percent 값이 있음(주로 STT tqdm) | 원이 conic-gradient로 퍼센트만큼 차오르고, 원 안에 `NN%` 텍스트 |
| 진행중·퍼센트 모름 (`active-indeterminate`) | 현재 단계이고 percent 값이 없음 | 원이 스피너 애니메이션으로 회전, 아래에 현재 메시지 텍스트 |
| 완료 (`done`) | 현재 진행 중인 단계보다 앞 | 원이 파란색으로 채워지고 체크마크(`✓`) 표시 |

같은 단계에서 퍼센트 없는 메시지가 나중에 도착해도 이전 퍼센트 값은 유지됩니다(sticky).

> `get_analysis_process()` 함수는 두 분기가 항상 같은 값을 반환해 `poll()` 체크가 의미 없는 죽은 로직이었기 때문에 주석 처리되었습니다. 호출부는 `st.session_state.get("analysis_process")`를 직접 사용합니다.

## 결과 페이지

`app/pages/2_analysis_result.py`는 `app/final_summary_view.py`의 `render_video_and_summary()`를 다음 옵션으로 호출해 원본 영상과 요약 결과를 나란히 표시합니다.

| 파라미터 | 값 |
| --- | --- |
| `column_ratio` | `(0.85, 1.15)` |
| `column_gap` | `"medium"` |
| `show_captions` | `False` (파일 경로 캡션 숨김) |
| `summary_container_height` | `600` |

| 영역 | 데이터 |
| --- | --- |
| 원본 영상 | `resolve_video_path(st.session_state.get("video_path"))` — 없거나 존재하지 않으면 `data/input/input.mp4`로 폴백, 그마저 없으면 경고 표시 |
| 요약 결과 | `runs/final/final_summary_result.json` 우선, 없으면 `runs/final/final_summary.txt` (`load_final_summary`) |

요약을 찾거나 읽지 못하면 경고와 함께 "영상 업로드로 이동" 버튼을 표시하고 페이지를 중단합니다.

### 결과 저장

"💾 영상과 요약 결과 저장" 버튼을 누르면 `app/result_export.py`의 `save_analysis_result()`가 실행되어 현재 영상 파일과 `runs/final/`의 `final_summary.txt`/`final_summary_result.json`을 `data/saved/[영상 제목] - YYYYMMDD-HHMMSS/` 폴더에 복사합니다. 제목이 없으면 날짜시각(`YYYYMMDD-HHMMSS`)만으로 폴더명을 만들고, 폴더명에 쓸 수 없는 Windows 금지 문자(`\ / : * ? " < > |`)는 제거됩니다. 영상과 요약 결과가 모두 없으면 `FileNotFoundError`가 발생해 화면에 에러로 표시됩니다.

## 요약 렌더링

`app/final_summary_view.py`의 `render_summary_data(summary_data)`는 구조화된 필드(`title`/`main_topic`/`topics`/`conclusion`/`keywords`)가 있으면 그것을 UI 컴포넌트(제목, 핵심 주제 박스, 키워드 뱃지, 주제별 expander, 종합 결론 박스)로 나누어 표시합니다.

> **주의**: 실제로는 GPU 서버가 이 구조화된 필드들을 절대 반환하지 않기 때문에 이 분기는 사실상 죽은 코드입니다(향후 호환을 위해 남겨둠). 실제 렌더링 경로는 항상 `get_summary_markdown()`으로 얻은 자유 텍스트를 `render_summary_with_timeline()`으로 표시하는 쪽입니다.

## 타임라인 렌더링 (`app/summary_timeline.py`)

최종 요약 텍스트(마크다운 문자열)에는 `(타임라인: 66.0 ~ 813.0)` 같은 초 단위 표기가 곳곳에 들어 있습니다. `render_summary_with_timeline(markdown_text, ocr_result_path, project_root)`는 이 텍스트를 `##` 단위 섹션으로 나누어 다음과 같이 처리합니다.

| 섹션 유형 | 판별 조건 | 렌더링 |
| --- | --- | --- |
| 번호 매겨진 항목 섹션 | 본문에 `### N. 제목 (타임라인: 시작 ~ 끝)` 형태가 있음 (`HAS_NUMBERED_ITEM_PATTERN`) | 항목별로 테두리 박스(`st.container(border=True)`) 카드 렌더링, 각 카드에 분:초 형식(`1:06 ~ 13:33`) 클릭 가능한 타임라인 뱃지 부착 |
| 표/차트 섹션 | 위 조건을 만족하면서 제목에 "표" 또는 "차트"가 포함 | 위 카드에 더해, `runs/ocr/ocr_result.json`에서 해당 타임라인 구간(±1초)에 매칭되는 프레임 스크린샷도 함께 표시 (`scene_type == "chart_or_table"`인 프레임 우선, 없으면 구간 내 아무 프레임) |
| 그 외 일반 섹션 | 위 조건에 해당하지 않음 (핵심 주제, 종합 결론 등) | 마크다운 그대로 표시하되 `(타임라인: ...)` 표기만 분:초 형식의 일반 텍스트로 변환(클릭 불가) |

타임라인 뱃지를 클릭하면 자바스크립트가 `document.querySelector('video')`로 페이지의 `<video>` 엘리먼트를 찾아 `currentTime`을 이동시키고 재생합니다. 페이지 새로고침은 없습니다.

> **중요 구현 디테일**: 이 뱃지는 `st.markdown(unsafe_allow_html=True)`가 아니라 **`st.html(..., unsafe_allow_javascript=True)`**로 렌더링합니다(`_render_timeline_badge` 함수). `st.markdown`으로 `onclick` 속성이 있는 HTML을 넣으면 Streamlit이 이를 React 엘리먼트로 변환하는 과정에서 `onclick`이 문자열로 취급되어 런타임 에러(React #231)가 발생합니다. `st.html`은 iframe 없이 문서에 HTML을 그대로 삽입하고 내부 자바스크립트를 실제로 실행하므로 이 문제가 없습니다. 추후 실수로 `st.markdown`으로 되돌리지 않도록 주의해야 합니다.

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
| `analysis_process` | 실행 중인 파이프라인 `subprocess.Popen` 프로세스 |
| `analysis_log_handle` | 로그 파일 핸들 |
| `analysis_done` | 분석 완료 여부 |
| `analysis_cancelled` | 분석 중지 여부 |
| `last_analysis_log` | 마지막 표시 로그 |

## 주의 사항

- 앱은 파이프라인을 별도 프로세스로 실행하므로 GPU 서버, FFmpeg, Whisper, EasyOCR 환경이 CLI 실행과 동일하게 준비되어야 합니다.
- 유튜브 링크 다운로드를 사용하려면 `yt-dlp` 패키지가 설치되어 있어야 합니다.
- 업로드 파일은 원본 확장자를 유지해 `data/input/input{확장자}`로 저장됩니다(유튜브 다운로드는 항상 `.mp4`).
- `--skip-stt` 옵션은 현재 비활성화되어 있어 STT 단계는 항상 실행됩니다.
- 최종 결과 페이지는 `runs/final` 산출물이 있어야 정상 표시되며, 표/차트 구간 스크린샷을 보려면 `runs/ocr/ocr_result.json`도 필요합니다.
