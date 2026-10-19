# 시스템 개요

이 프로젝트는 영상의 음성 정보와 화면 정보를 함께 사용해 요약을 생성하는 멀티모달 영상 요약 파이프라인입니다.

파일명은 현재 저장소의 기존 이름인 `system_overvies.md`를 유지합니다.

## 전체 구조

```text
입력 영상
  -> MP4 확인/변환
  -> 오디오 추출
  -> Whisper STT
  -> LLM STT 요약 및 주요 구간 추출
  -> 주요 구간 프레임 샘플링
  -> EasyOCR 화면 텍스트 추출
  -> VLM 프레임 요약
  -> 최종 LLM 통합 요약
```

간단·기본·상세(`simple`/`standard`/`detailed`) 설정은 Whisper 모델 크기(small/medium/large)만 바꾸며, 세 설정 모두 프레임 샘플링/OCR/VLM을 실행합니다. OCR·VLM은 CLI의 `--skip-ocr`/`--skip-vlm`으로만 건너뜁니다. 자세한 내용은 `docs/explanation/pipeline/pipeline.md`의 "건너뛰기 동작"을 참고하세요.

## 주요 컴포넌트

| 영역 | 위치 | 역할 |
| --- | --- | --- |
| 실행 스크립트 | `scripts/` | 단계별 CLI와 전체 파이프라인 진입점 |
| 전처리 | `modules/preprocess/` | 영상 정보 조회, MP4 변환, 오디오 추출, 프레임 샘플링, 유튜브 다운로드(`youtube_downloader.py`) |
| STT | `modules/stt/` | Whisper 실행 및 STT 결과 포맷팅 |
| OCR | `modules/ocr/` | EasyOCR 실행, 화면 유형 추정, OCR 결과 저장 |
| LLM/VLM | `modules/llm/` | 외부 GPU 서버 API 클라이언트, 공통 HTTP/폴링 로직(`gpu_job_client.py`), 요약 크기/속도 프리셋(`summary_levels.py`) |
| 공통 유틸리티 | `modules/common/` | 기본 경로, JSON/YAML 유틸리티, 경로 탐색(`file_utils.py`), 진행률 보고(`progress.py`) |
| UI | `frontend/`, `app/` | React 화면(`frontend/`)과 이를 내보내는 FastAPI 앱 서버(`app/api/`)가 기본 UI. 업로드(유튜브 링크 포함)와 분석 설정, 분석 진행률/오류 표시, 결과 확인·다시 열기, 결과 저장(`result_export.py`), 저장된 요약 다시보기, 실행 이력, 선택적 로그인 게이트. 기존 Streamlit 화면(`app/main.py`)은 예비 |

## 기본 실행 진입점

| 목적 | 명령 |
| --- | --- |
| 서버 PC 통합 실행(추론 서버 + React 앱) | `start_all.bat` ([단일 서버 운영](single_server_deployment.md)) |
| React 앱 서버만 | `python -m uvicorn app.api.server:app --host 127.0.0.1 --port 8501` (`frontend/dist` 빌드 필요) |
| Streamlit 앱(예비) | `streamlit run app/main.py`, `run_app.bat` 또는 `start_all.bat -Streamlit` |
| 전체 파이프라인 | `python scripts/run_pipeline.py` |
| 전처리만 실행 | `python scripts/run_preprocess.py` |
| STT만 실행 | `python scripts/run_stt.py` |
| OCR만 실행 | `python scripts/run_ocr.py` |
| STT 요약 | `python scripts/run_llm_summary.py` |
| VLM 요약 | `python scripts/run_vlm_summary.py` |
| 최종 요약 | `python scripts/run_final_summary.py` |

## 외부 의존성

| 의존성 | 사용 단계 |
| --- | --- |
| FFmpeg | MP4 변환, 오디오 추출, 프레임 추출 |
| FFprobe | 영상 길이, 해상도, FPS 조회 |
| Whisper | STT |
| EasyOCR | OCR |
| PyTorch | Whisper/EasyOCR 실행 |
| FastAPI·uvicorn | 앱 API 서버(React 화면) |
| Node.js | React 화면 빌드 |
| GPU 서버 | LLM 요약, VLM 요약, 최종 요약 |

## 실행 결과 위치

기본 결과 루트는 `runs/`입니다.

```text
runs/
  audio/
  stt/
  llm/
  frames/
  metadata/
  ocr/
  vlm/
  final/
```

앱에서 실행한 분석은 실행마다 `runs/jobs/<실행 ID>/` 아래에 같은 구조(audio, stt, llm, frames, ocr, vlm, final)로 저장되고, 보존 기간(`JOB_RETENTION_HOURS`, 기본 72시간)이 지나면 정리됩니다. 실행 이력은 `runs/history/<실행 ID>/`에 계속 남습니다.

앱에서 "영상과 요약 결과 저장" 버튼을 누르면 `data/saved/[영상 제목] - 년월일시분초/` 폴더에 원본 영상과 실행 폴더 `final/`의 요약 파일이 복사되어 남습니다. OCR 결과(`ocr/ocr_result.json`)가 있으면(`--skip-ocr`로 실행하지 않았으면) 표/차트 스크린샷 복원을 위해 프레임 이미지(`frames/`)와 OCR 결과 사본도 함께 저장됩니다. (`app/result_export.py`)

## 현재 상태

| 항목 | 상태 |
| --- | --- |
| CLI 파이프라인 | 구현됨 |
| 전처리/STT/OCR | 구현됨 |
| LLM/VLM 서버 클라이언트 | 구현됨 |
| 유튜브 링크 다운로드 | 구현됨 (`yt-dlp`) |
| React UI + 앱 API 서버 | 구현됨, 기본 UI (업로드, 분석 설정, 진행률/오류 표시, 결과 확인/저장/다시 열기, 저장된 요약, 실행 이력) |
| Streamlit UI | 구현됨, 예비 (같은 기능, `start_all.bat -Streamlit`) |
| 로그인 보호 | 구현됨, 선택 사항 (`APP_PASSWORD` 설정 시 동작. 미설정 시 Cloudflare 경유 외부 접속은 차단) |
| 외부 공개 | 구현됨, 선택 사항 (`start_all.bat -Tunnel` 또는 `start_tunnel.bat`/`.ps1`로 Cloudflare Tunnel 실행) |
| 설정 파일 | `stt_config.yaml`만 값이 있음, 나머지(`app_config.yaml`, `ffmpeg_config.yaml`, `llm_config.yaml`)는 비어 있음 |

## 참고 문서

- `docs/setup_guide.md`: 설치와 실행 준비
- `docs/data_format.md`: JSON/TXT 산출물 구조
- `docs/explanation/README.md`: 모듈별 상세 문서 색인
- `docs/single_server_deployment.md`: 단일 서버 실행과 Cloudflare 외부 접속
- `docs/explanation/frontend/frontend.md`: React 화면
- `docs/explanation/app/app_api.md`: 앱 API 서버
