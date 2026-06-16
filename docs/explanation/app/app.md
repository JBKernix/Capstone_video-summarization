# Streamlit App

`app/` 폴더는 영상 업로드, 분석 실행, 최종 요약 결과 확인을 제공하는 Streamlit UI입니다.

## 현재 파일

| 파일 | 역할 |
| --- | --- |
| `app/main.py` | Streamlit 앱 진입점, 업로드 페이지로 이동 |
| `app/pages/1_upload.py` | 영상 업로드, 파이프라인 백그라운드 실행, 로그 표시, 분석 중지 |
| `app/pages/2_analysis_result.py` | 원본 영상과 최종 요약 결과 표시 |
| `app/final_summary_view.py` | 최종 요약 표시 공통 렌더링 함수 |
| `app/summary_result.py` | `runs/final` 결과 파일 로더와 요약 데이터 판별 |
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

## 업로드 페이지

`app/pages/1_upload.py`는 다음 일을 처리합니다.

1. `mp4`, `mov`, `avi` 파일 업로드
2. 업로드 파일을 `data/input/input.mp4`로 저장
3. `scripts/run_pipeline.py --video data/input/input.mp4`를 `subprocess.Popen`으로 실행
4. stdout/stderr를 `runs/app_pipeline.log`에 저장
5. 로그에서 진행률 출력과 경로 출력 일부를 필터링해 UI에 표시
6. 분석 완료 시 `pages/2_analysis_result.py`로 이동
7. 분석 중지 버튼으로 프로세스 종료

Windows에서는 중지 시 `taskkill /PID <pid> /T /F`를 사용합니다.

## 결과 페이지

`app/pages/2_analysis_result.py`는 다음 데이터를 표시합니다.

| 영역 | 데이터 |
| --- | --- |
| 원본 영상 | 세션의 `video_path` 또는 `data/input/input.mp4` |
| 요약 결과 | `runs/final/final_summary_result.json` 우선, 없으면 `runs/final/final_summary.txt` |

요약 JSON이 구조화 필드(`title`, `main_topic`, `topics`, `conclusion`, `keywords`)를 가지고 있으면 UI 컴포넌트로 나누어 표시합니다. 그렇지 않으면 `summary` 또는 `final_summary` 값을 Markdown으로 표시합니다.

## 결과 로더

`app/summary_result.py`의 `load_final_summary(final_dir)`는 다음 순서로 파일을 찾습니다.

1. `final_summary_result.json`
2. `final_summary.txt`

JSON이 있으면 `mode="json"`으로, 텍스트 파일만 있으면 `mode="markdown"`으로 반환합니다. 둘 다 없으면 `FileNotFoundError`가 발생합니다.

## 세션 상태

앱에서 사용하는 주요 `st.session_state` 키는 다음과 같습니다.

| 키 | 의미 |
| --- | --- |
| `video_path` | 업로드 후 저장된 영상 경로 |
| `uploaded_filename` | 사용자가 업로드한 원본 파일명 |
| `analysis_process` | 실행 중인 파이프라인 프로세스 |
| `analysis_log_handle` | 로그 파일 핸들 |
| `analysis_done` | 분석 완료 여부 |
| `analysis_cancelled` | 분석 중지 여부 |
| `last_analysis_log` | 마지막 표시 로그 |

## 주의 사항

- 앱은 파이프라인을 별도 프로세스로 실행하므로 GPU 서버, FFmpeg, Whisper, EasyOCR 환경이 CLI 실행과 동일하게 준비되어야 합니다.
- 업로드 파일명과 관계없이 현재 저장 경로는 `data/input/input.mp4`입니다.
- 최종 결과 페이지는 `runs/final` 산출물이 있어야 정상 표시됩니다.
