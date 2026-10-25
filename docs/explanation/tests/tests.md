# 테스트

`tests/` 폴더는 주요 모듈과 앱 보조 로직을 검증하는 테스트를 담고 있습니다.

## 테스트 파일

| 파일 | 대상 |
| --- | --- |
| `tests/test_audio_extractor.py` | 오디오 추출 |
| `tests/test_frame_sampler.py` | 프레임 샘플링(대표 프레임·장면 전환·고정 간격) |
| `tests/test_pipeline.py` | 파이프라인 보조 흐름 |
| `tests/test_stt.py` | STT 포맷팅/실행 관련 동작 |
| `tests/test_vlm_summary.py` | VLM 요약 클라이언트 |
| `tests/test_summary_result.py` | 앱 최종 요약 로더와 영상 경로 해석 |
| `tests/test_api_server.py` | React 화면용 앱 API 서버(`app/api/`): 로그인·잠금·CSRF, 개발자 모드, 사용자 화면 분석 방식, 업로드 검증, 분석 실행·진행 상황, 결과·프레임·영상, 강의노트 `outline`, 저장·삭제, 실행 이력·CSV, 결과 다시 열기(`has_result`), React 라우트 |
| `tests/test_run_registry.py` | 업로드·실행 폴더, 단일 실행 슬롯, 보존 기간 정리 |
| `tests/test_pipeline_process.py` | 파이프라인 실행·중지 |
| `tests/test_pipeline_history.py`, `tests/test_run_history.py`, `tests/test_model_load_history.py` | 실행 이력 기록(`metrics.json`)과 모델 로딩 지표 |
| `tests/test_history_ui.py` | Streamlit 실행 이력 화면 |
| `tests/test_auth.py`, `tests/test_analysis_options.py`, `tests/test_local_models.py` | Streamlit 로그인 게이트, 분석 설정 위젯, 로컬 모델 선택 |
| `tests/test_analysis_backends.py` | 로컬/Claude 분석 방식 설정과 오류 처리 |

`tests/conftest.py`는 모든 테스트에서 `app/run_registry.py`의 업로드·실행 폴더와 실행 슬롯 파일을 임시 폴더로 바꿔, 테스트가 실제 `runs/`·`data/`를 건드리지 않게 합니다.

## 실행

```bash
pytest
```

앱이 실행되는 `capstone` conda 환경(FastAPI·httpx·Streamlit 설치됨)에서 실행하세요. 앱 API 테스트(`test_api_server.py`)는 FastAPI `TestClient`(httpx)가 필요합니다.

```bash
%USERPROFILE%\anaconda3\envs\capstone\python.exe -m pytest
```

특정 파일만 실행:

```bash
pytest tests/test_summary_result.py
```

`python -m unittest discover`로도 실행할 수는 있지만, `tests/test_frame_sampler.py`와 `tests/test_vlm_summary.py`는 `unittest.TestCase`가 아닌 pytest 스타일 함수(`tmp_path`/`monkeypatch` fixture 사용)로 작성되어 있어 `unittest discover`는 이 파일들을 수집조차 하지 못하고 조용히 건너뜁니다. 그 결과 실제보다 적은 테스트 수가 통과한 것으로 보일 수 있으므로, 전체 테스트는 반드시 `pytest`로 실행해야 합니다.

## 오디오/프레임 샘플링 테스트: `run_ffmpeg_with_progress` 모킹

`extract_audio()`(오디오 추출)와 `sample_scene_change_frames()`(장면 전환 프레임 샘플링)가 기존 `run_ffmpeg()` 대신 스트리밍 진행률 콜백을 받는 `run_ffmpeg_with_progress()`를 호출하도록 바뀌면서, 관련 테스트도 함께 갱신되었습니다.

- `tests/test_audio_extractor.py::test_extract_audio_builds_ffmpeg_command`는 `audio_extractor.get_video_info`(영상 길이 조회)와 `audio_extractor.run_ffmpeg_with_progress`를 모킹하고, 호출 인자로 전달된 FFmpeg 명령어 리스트와 총 길이(`args[1]`)를 검증합니다.
- `tests/test_frame_sampler.py::test_scene_change_sampling_uses_important_ranges_and_showinfo_timestamps`도 동일하게 `frame_sampler.run_ffmpeg_with_progress`와 `frame_sampler.get_video_info`를 모킹합니다.
- `run_ffmpeg`를 직접 모킹해 "호출되면 안 된다"를 검증하던 기존 테스트(`test_empty_time_ranges_write_empty_metadata_without_running_ffmpeg`, `test_empty_scene_change_ranges_do_not_run_ffmpeg`)는 그대로 유지됩니다. 이 경로들은 중요 구간이 비어 있어 FFmpeg 실행 자체가 스킵되는 경우이므로 `run_ffmpeg_with_progress`로의 전환과 무관합니다.

## 대표 프레임 샘플링 테스트

프레임 샘플링의 기본 방식이 대표 프레임(`representative`)으로 바뀌면서 `tests/test_frame_sampler.py`에 다음 테스트가 추가되었습니다. 모두 `frame_sampler.run_ffmpeg`와 `get_video_info`를 모킹해 실제 FFmpeg 없이 실행됩니다.

- `test_select_evenly_keeps_first_and_last`: 후보가 한도보다 많으면 처음과 끝을 포함해 고르게 고르고, 적으면 그대로 둠
- `test_sample_frames_defaults_to_representative`: `sample_frames()`의 기본 방식이 `sample_representative_frames()`이며 구간당 최대 장수(`DEFAULT_MAX_FRAMES_PER_SEGMENT`)를 넘김
- `test_representative_sampling_caps_frames_per_segment`: 구간을 시간순으로 정렬하고 영상 길이를 넘는 끝을 자름, FFmpeg 필터에 `mpdecimate`(같은 화면 제거) 사용, 구간당 최대 장수 제한, 파일 이름·`sampling_method` 기록
- `test_representative_sampling_falls_back_to_middle_frame`: 후보가 하나도 없으면 구간 가운데 시각의 프레임 한 장을 뽑음

이에 맞춰 `tests/test_pipeline.py`의 파이프라인 인자에 `max_frames_per_segment`가 추가되었고, `tests/test_pipeline_history.py`는 `--interval-seconds` 없이 기본(대표 프레임) 방식으로 실행합니다. 테스트용 단색 영상은 화면이 바뀌지 않아 구간에서 1장만 남으므로 `frames_extracted`·`ocr_success`가 1이고, Claude 파이프라인 테스트의 VLM 응답도 1장 기준입니다.

## 앱 API 테스트: 개발자 모드와 강의노트

`tests/test_api_server.py`의 `client` fixture는 사용자 화면 분석 방식 파일(`USER_DEFAULTS_PATH`)을 임시 폴더로 바꾸고 `DEV_PASSWORD`를 지워 기본 개발자 비밀번호(`admin`)로 테스트합니다. 개발자 전용 API를 쓰는 테스트는 `enter_dev_mode()`로 먼저 `POST /api/dev/login`을 보냅니다.

- 로그인·개발자 모드
  - `test_without_password_local_and_tunnel_are_allowed`: 앱 비밀번호가 없으면 외부(Cloudflare) 접속도 통과(예전의 차단 테스트를 대체). 단, 실행 이력은 개발자 모드가 아니면 403
  - `test_developer_mode_needs_its_own_password`: 세션의 `developer` 값, 틀린 비밀번호 401, 개발자 로그인 후 실행 이력 접근, 개발자 로그아웃 후 다시 403
  - `test_developer_mode_still_needs_app_login`: 앱 비밀번호가 있으면 앱 로그인 전에는 개발자 로그인도 401, 앱 로그아웃은 개발자 모드도 끝냄
  - `test_dev_password_can_be_changed_by_env`: `DEV_PASSWORD` 환경 변수로 개발자 비밀번호 변경
- 분석 실행
  - `test_user_runs_use_backend_chosen_by_developer`: 일반 사용자가 보낸 분석 방식은 무시하고 기본값(로컬)을 씀. `PUT /api/dev/user-defaults`는 개발자만 가능하고, 지정한 뒤에는 일반 사용자 분석과 `/api/options`의 `user_defaults`에 반영됨
  - `test_run_status_reports_progress_and_filtered_logs`: 진행 상황의 `logs`는 일반 사용자에게 빈 목록, 개발자에게만 로그 표시
- 강의노트 `outline`
  - `test_result_outline_for_chapter_player`: 마크다운에서 제목·3줄 요약·키워드(따옴표 강조 용어 우선, 겹치는 중요 구간 주제 제외)·챕터(시작 시각순, 내용과 화면 분석 문장 분리, 썸네일)·표/차트 자료·결론을 만듦
  - `test_result_without_chapters_has_no_outline`: 타임라인 챕터가 없으면 `outline`이 `null`
  - `test_result_returns_every_distinct_frame_in_a_chapter`: 챕터 `frames`에 구간 안의 화면을 시간순으로 모두 담고 다음 구간 화면은 섞지 않음. 표/차트 자료는 표/차트로 분류된 화면만 담고 대표 화면은 그중 첫 장
  - `test_result_outline_from_lecture_note_json`: 결과 JSON에 `lecture_note`가 있으면 `outline`을 그 JSON으로 만듦(개발자 화면용 `blocks`는 계속 마크다운에서). 용어·공지, 빈 용어·제목 없는 챕터 제외, 시간 없는 챕터(`start: null`, "시간 정보 없음", 썸네일·`frames` 없음), 자료 유형(`kind`)·내용·의미 텍스트 확인

## 앱 결과 로더 테스트

`test_summary_result.py`는 다음 동작을 확인합니다.

- `final_summary_result.json`이 있으면 TXT보다 우선 사용
- JSON이 없으면 `final_summary.txt`로 fallback
- 결과 파일이 없으면 `FileNotFoundError`
- `summary`, `final_summary` 키에서 Markdown 요약 추출
- 구조화 요약 필드 감지
- 명시된 영상 경로가 존재하면 그 경로를 사용

## 알려진 실패 테스트

2026-10-19 기준 `capstone` 환경(Windows)에서 아래 9개가 실패합니다. React·앱 API 작업 전 코드에서도 이 9개가 실패했으며(기본 Anaconda 환경에서 작업 전후 비교), 원인은 아직 확인하지 않았습니다. 출력에 한글이 깨져 보이는 경우가 있어 Windows 콘솔 인코딩(cp949) 관련 가능성이 있습니다.

- `tests/test_analysis_backends.py::test_api_errors_do_not_log_credentials_or_response_body` (401·429·500, 3개)
- `tests/test_model_load_history.py::test_poll_snapshots_do_not_double_count_and_csv_preserves_missing`
- `tests/test_pipeline_history.py::test_claude_pipeline_archives_all_stage_outputs`
- `tests/test_pipeline_process.py::test_stop_waits_for_exit_before_recording_cancel`
- `tests/test_run_history.py::test_runs_keep_separate_logs_and_snapshots`
- `tests/test_run_history.py::test_failure_or_interrupt_preserves_partial_run` (failed·cancelled, 2개)

예전에 이 절에 있던 `tests/test_pipeline.py::PipelineVlmTests::test_main_requests_vlm_summary_after_ocr`는 현재 통과합니다.

## 주의 사항

- 일부 테스트는 FFmpeg/FFprobe 실행 가능 여부에 영향을 받을 수 있습니다.
- Whisper, EasyOCR, GPU 서버를 직접 사용하는 테스트는 환경에 따라 느리거나 실패할 수 있습니다.
- `.pytest_cache/`는 로컬 캐시이며 문서나 소스 코드 대상이 아닙니다.

## 테스트 작성 기준

새 기능을 추가할 때는 다음 중 하나 이상을 검증하는 테스트를 추가합니다.

- 입력 파일이 없을 때의 예외
- 출력 JSON 구조
- 기본 경로와 옵션 처리
- 외부 서버 응답 형식 처리
- 앱 결과 표시용 fallback 처리
- 일부 실패가 전체 결과에 미치는 영향
