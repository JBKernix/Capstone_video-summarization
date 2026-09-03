# 설치 및 실행 가이드

이 문서는 로컬 환경에서 영상 요약 파이프라인을 실행하기 위한 준비 절차를 정리합니다.

## 권장 환경

| 항목 | 권장값 |
| --- | --- |
| OS | Windows |
| Python | 3.11 |
| 패키지 관리자 | conda 또는 venv + pip |
| 외부 도구 | FFmpeg, FFprobe |
| GPU | 선택 사항, Whisper/EasyOCR 속도 개선용 |
| UI | Streamlit |

## Python 환경 생성

```bash
conda create -n capstone_test python=3.11
conda activate capstone_test
pip install -r requirements.txt
```

`requirements.txt`에는 EasyOCR, OpenCV, PyTorch(cu130), Whisper(`openai-whisper`), requests, PyYAML 등이 포함되어 있습니다.
현재 UI 실행을 위해 `streamlit==1.58.0`도 포함되어 있고, 유튜브 링크 다운로드를 위해 `yt-dlp`도 포함되어 있습니다.

## FFmpeg 확인

전처리 단계는 `ffmpeg`와 `ffprobe`를 PATH에서 실행할 수 있어야 합니다.

```bash
ffmpeg -version
ffprobe -version
```

둘 중 하나라도 실행되지 않으면 오디오 추출, 영상 정보 조회, 프레임 샘플링이 실패합니다.

## 입력 영상 준비

기본 입력 경로는 `data/input/*.mp4`입니다.

```text
data/
  input/
    sample.mp4
```

기본값으로 실행할 때는 `data/input/`에 MP4 파일을 하나만 두는 것이 안전합니다. 여러 파일이 있으면 `--video` 옵션으로 분석할 파일을 직접 지정하세요.

Streamlit 앱에서는 파일 업로드 대신 유튜브 링크를 입력해 영상을 준비할 수도 있습니다. `modules/preprocess/youtube_downloader.py`의 `download_youtube_video()`가 `yt-dlp`로 다운로드해 `data/input/input.mp4`로 저장합니다. 업로드 용량 제한은 `.streamlit/config.toml`의 `maxUploadSize`(기본 500MB)로 설정되어 있습니다.

## STT 설정

STT 기본 설정은 `configs/stt_config.yaml`에서 관리합니다.

```yaml
model_size: small
language: ko
device:
temperature: 0.0
beam_size:
```

`device`가 비어 있으면 Whisper 기본 동작을 따릅니다. GPU를 명시하려면 실행 시 `--stt-device cuda` 또는 설정 파일 값을 사용합니다.

## GPU 서버 설정

LLM, VLM, 최종 요약 단계는 외부 GPU 서버를 호출합니다. 기본 서버 주소는 `modules/llm/__init__.py`에 있습니다.

```python
GPU_SERVER_URL = "http://10.10.4.27:8000"
```

세 클라이언트(`stt_summarizer_client.py`, `vlm_summarizer_client.py`, `final_summarizer_client.py`)는 모두 `modules/llm/gpu_job_client.py`의 `GPUJobClientMixin`을 상속해 HTTP 에러 처리와 비동기 job 폴링(`status_url`을 주기적으로 조회) 로직을 공유합니다.

서버는 다음 API를 제공해야 합니다.

| 엔드포인트 | 사용 위치 |
| --- | --- |
| `GET /health` | 클라이언트 상태 확인 |
| `POST /llm/summarize` | STT 요약 및 주요 구간 추출 |
| `POST /vlm/summarize` | 프레임 이미지 요약 |
| `POST /llm/final-summary` | STT/VLM 결과 통합 요약 |

## 전체 실행

Streamlit 앱:

```bat
run_app.bat
```

또는:

```bash
streamlit run app/main.py
```

CLI:

```bash
python scripts/run_pipeline.py --video data/input/sample.mp4 --run-dir runs
```

일부 단계를 건너뛸 수 있습니다.

```bash
python scripts/run_pipeline.py --skip-ocr
python scripts/run_pipeline.py --skip-vlm
```

`--skip-stt` 옵션은 `scripts/run_pipeline.py`에서 현재 주석 처리되어 비활성화되어 있습니다. STT는 항상 실행됩니다.

## 단계별 실행

```bash
python scripts/run_preprocess.py --video data/input/sample.mp4 --run-dir runs
python scripts/run_stt.py --audio runs/audio/audio.wav
python scripts/run_llm_summary.py --stt-json runs/stt/stt_result.json
python scripts/run_ocr.py
python scripts/run_vlm_summary.py --ocr-json runs/ocr/ocr_result.json
python scripts/run_final_summary.py
```

현재 `run_pipeline.py`는 최종 통합 요약까지 실행합니다. `run_final_summary.py`는 기존 STT/VLM 요약 파일을 바탕으로 최종 요약만 다시 생성할 때 사용합니다.

## 문제 해결

| 증상 | 확인할 것 |
| --- | --- |
| `ffmpeg` 또는 `ffprobe`를 찾을 수 없음 | FFmpeg 설치 및 PATH 등록 |
| Whisper 모델 다운로드가 오래 걸림 | 첫 실행에서는 모델 파일 다운로드가 필요함 |
| EasyOCR 초기화 실패 | `easyocr`, `torch` 설치 상태와 CUDA 호환성 |
| LLM/VLM 단계 연결 실패 | `GPU_SERVER_URL` 서버 접근 가능 여부 |
| 프레임 이미지 파일을 찾지 못함 | `runs/metadata/frame_metadata.json`의 `image_path`와 실제 `runs/frames/` 확인 |
| 앱에서 진행 상황이 보이지 않음 | `runs/app_pipeline.log` 생성 여부와 로그 안 `##PROGRESS##` 마커, 파이프라인 프로세스 상태 |
| 유튜브 영상 다운로드 실패 | 링크 형식(`is_youtube_url`), `yt-dlp` 설치 여부, 네트워크/영상 비공개 여부 |
