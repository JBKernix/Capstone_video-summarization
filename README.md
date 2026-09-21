# Multimodal Video Summarization

영상에서 음성, 주요 프레임, OCR 텍스트를 추출하고 외부 GPU 서버의 LLM/VLM API를 사용해 최종 요약을 만드는 캡스톤 프로젝트입니다.

현재 저장소는 `scripts/` CLI 파이프라인과 Streamlit 기반 `app/` UI를 함께 제공합니다. UI는 영상 업로드, 파이프라인 실행, 원본 영상과 최종 요약 결과 확인을 담당합니다.

## 주요 기능

- FFmpeg/FFprobe 기반 영상 정보 확인, 오디오 추출, MP4 변환
- 일정 간격 또는 장면 전환 기반 프레임 샘플링
- Whisper 기반 STT 결과 생성
- EasyOCR 기반 프레임 텍스트 추출
- STT 결과를 LLM 서버로 보내 주요 구간과 요약 생성
- OCR/프레임 결과를 VLM 서버로 보내 프레임별 요약 생성
- STT 요약과 VLM 요약을 결합한 최종 요약 생성
- 파일 업로드 또는 유튜브 링크로 분석할 영상 지정 (`yt-dlp` 기반 다운로드)
- 요약 크기/속도 프리셋(간단요약/기본요약/상세요약) 선택
- 분석 진행 중 7단계 진행 상황을 원형 아이콘/퍼센트로 실시간 표시, 실패 시 오류 표시
- 분석 완료 후 영상과 요약 결과를 `data/saved/`에 함께 저장
- 저장된 요약 결과를 다시 불러와 확인/삭제
- 요약 결과의 타임라인을 분:초 뱃지로 표시하고 클릭 시 영상 재생 위치 이동
- 비밀번호 로그인 게이트와 Cloudflare Tunnel을 이용한 외부 공개(둘 다 선택 사항)

## 처리 흐름

```text
입력 영상
  -> 오디오 추출
  -> Whisper STT
  -> LLM 기반 STT 요약 및 주요 구간 추출
  -> 주요 구간 프레임 샘플링
  -> EasyOCR 분석
  -> VLM 기반 프레임 요약
  -> 최종 LLM 요약
```

## 폴더 구조

```text
Capstone_video-summarization/
├── app/                  # Streamlit UI
├── configs/              # STT 등 설정 파일
├── data/input/           # 기본 입력 영상 위치
├── data/saved/           # 분석 결과 저장 위치 (영상 + 요약본)
├── docs/                 # 설계 및 모듈 설명 문서
├── modules/              # 전처리, STT, OCR, LLM/VLM 클라이언트
├── runs/                 # 기본 실행 결과 출력 위치
├── scripts/              # CLI 실행 스크립트
├── tests/                # 테스트 코드
├── requirements.txt
└── README.md
```

## 설치

Python 3.11 환경을 권장합니다.

```bash
git clone https://github.com/JBKernix/Capstone_video-summarization.git
cd Capstone_video-summarization

conda create -n capstone_test python=3.11
conda activate capstone_test

pip install -r requirements.txt
```

`requirements.txt`에는 EasyOCR, OpenCV, PyTorch(cu130), Whisper(`openai-whisper`), Streamlit(1.58.0), 유튜브 다운로드용 `yt-dlp`, requests, PyYAML 등이 포함되어 있습니다.

FFmpeg와 FFprobe가 시스템 PATH에서 실행 가능해야 합니다.

```bash
ffmpeg -version
ffprobe -version
```

## 실행 전 준비

기본 입력 경로는 `data/input/*.mp4`입니다. 기본값으로 실행하려면 `data/input/`에 MP4 파일을 하나만 두세요.

STT 기본 설정은 `configs/stt_config.yaml`에 있습니다.

```yaml
model_size: small
language: ko
device:
temperature: 0.0
beam_size:
```

LLM/VLM/최종 요약 단계는 외부 GPU 서버를 호출합니다. 기본 서버 주소는 `modules/llm/__init__.py`의 `GPU_SERVER_URL` 값입니다.

```python
GPU_SERVER_URL = "http://100.124.136.28:8000"
```

서버가 접근 가능하지 않으면 `run_llm_summary.py`, `run_vlm_summary.py`, `run_final_summary.py` 및 전체 파이프라인의 관련 단계가 실패합니다.

## Streamlit 앱 실행

Windows에서는 배치 파일로 실행할 수 있습니다.

```bat
run_app.bat
```

직접 실행할 수도 있습니다.

```bash
streamlit run app/main.py
```

앱(`app/pages/1_upload.py`)은 두 가지 방식으로 분석할 영상을 지정할 수 있습니다.

- 파일 업로드: `data/input/input.<확장자>` (mp4/mov/avi)로 저장
- 유튜브 링크: `modules/preprocess/youtube_downloader.py`의 `download_youtube_video()`가 `yt-dlp`로 다운로드해 `data/input/input.mp4`로 저장

업로드 화면에는 요약 크기/속도 프리셋을 고르는 "요약 옵션"도 함께 있습니다 (`modules/llm/summary_levels.py`).

| 프리셋 | 설명 |
| --- | --- |
| 간단요약 (`simple`) | 속도 우선. 프레임 추출/OCR/VLM 단계를 건너뛰고 STT 요약만으로 최종 요약을 만듭니다 |
| 기본요약 (`standard`, 기본값) | 음성과 영상을 균형 있게 요약 |
| 상세요약 (`detailed`) | 음성과 영상을 자세히 요약하지만 속도가 느림 |

영상이 준비되면 `scripts/run_pipeline.py --summary-level <선택값>`을 백그라운드 프로세스로 실행합니다. 실행 로그는 `runs/app_pipeline.log`에 저장되며, 파이프라인이 `modules/common/progress.py`의 `report_progress()`로 남기는 `##PROGRESS##` 마커를 앱이 폴링해 7단계 진행 상황을 원형 아이콘과 퍼센트로 보여줍니다. 파이프라인 프로세스가 오류로 종료되면 진행 중이던 단계가 빨간 오류 아이콘으로 표시됩니다.

분석이 끝나면 `pages/2_analysis_result.py`에서 원본 영상과 최종 요약을 함께 확인할 수 있고, "영상과 요약 결과 저장" 버튼(`app/result_export.py`)으로 `data/saved/[영상 제목] - 년월일시분초/` 폴더에 영상과 요약 파일을 복사해 보관할 수 있습니다. 요약 화면의 타임라인은 `분:초` 형식의 클릭 가능한 뱃지로 표시되며, 클릭하면 영상이 해당 지점으로 이동합니다. `pages/3_saved_summaries.py`에서는 저장된 결과 목록을 다시 불러와 확인하거나 삭제할 수 있습니다.

## 로그인 보호 및 외부 공개 (선택)

앱을 로컬에서만 쓸 때는 아래 설정이 필요 없습니다. Cloudflare Tunnel 등으로 외부에 공개할 때만 설정하세요.

- **로그인 게이트**: `.streamlit/secrets.toml`에 `APP_PASSWORD`를 설정하면 모든 페이지 진입 전에 비밀번호 입력 화면이 표시됩니다(`app/auth.py`의 `require_login()`). `APP_PASSWORD`가 없으면 로그인 화면 없이 그대로 통과합니다.
- **Cloudflare Tunnel**: `start_tunnel.bat`(Windows) 또는 `start_tunnel.ps1`을 실행하면 `cloudflared`가 로컬 8501 포트(Streamlit 기본 포트)를 외부 URL로 연결하고, 발급된 URL을 `tunnel_url.txt`에 저장합니다. `cloudflared`가 PATH에 설치되어 있어야 합니다.

## 전체 파이프라인 실행

```bash
python scripts/run_pipeline.py --video data/input/sample.mp4 --run-dir runs
```

자주 쓰는 옵션은 다음과 같습니다.

```bash
python scripts/run_pipeline.py \
  --video data/input/sample.mp4 \
  --run-dir runs \
  --method interval \
  --interval-seconds 5 \
  --stt-model-size small \
  --stt-language ko \
  --summary-level standard
```

`--summary-level`은 `simple`/`standard`(기본값)/`detailed` 중 하나이며, `simple`을 선택하면 프레임 추출/OCR/VLM 단계가 건너뛰어지고 STT 요약이 최종 요약으로 그대로 사용됩니다.

일부 단계를 건너뛸 수 있습니다.

```bash
python scripts/run_pipeline.py --skip-ocr
python scripts/run_pipeline.py --skip-vlm
```

`--skip-vlm`을 사용하거나 `--summary-level simple`이어서 VLM 요약이 없으면, 최종 통합 요약 단계는 서버에 병합 요청을 보내지 않고 STT 요약을 그대로 최종 요약으로 저장합니다.

`--skip-stt` 옵션은 현재 비활성화되어 있습니다(`scripts/run_pipeline.py`에서 주석 처리). STT를 건너뛰면 이후 요약/프레임/OCR/VLM/최종요약 단계가 모두 연쇄적으로 건너뛰어져 옵션 설명과 실제 동작이 달라 혼란을 줄 수 있기 때문입니다. STT는 항상 실행됩니다.

## 단계별 실행

전처리와 프레임 샘플링:

```bash
python scripts/run_preprocess.py --video data/input/sample.mp4 --run-dir runs
```

STT:

```bash
python scripts/run_stt.py --audio runs/audio/audio.wav
```

STT 요약:

```bash
python scripts/run_llm_summary.py --stt-json runs/stt/stt_result.json
```

OCR:

```bash
python scripts/run_ocr.py
```

VLM 프레임 요약:

```bash
python scripts/run_vlm_summary.py --ocr-json runs/ocr/ocr_result.json
```

최종 요약:

```bash
python scripts/run_final_summary.py
```

참고로 `scripts/run_pipeline.py`는 최종 통합 요약까지 실행합니다. 개별 단계만 다시 실행해야 할 때는 `scripts/run_final_summary.py`를 별도로 사용할 수 있습니다.

## 주요 출력 파일

기본 출력 루트는 `runs/`입니다.

| 경로 | 설명 |
| --- | --- |
| `runs/audio/audio.wav` | 영상에서 추출한 오디오 |
| `runs/stt/stt_result.json` | Whisper STT 구조화 결과 |
| `runs/stt/stt_result.txt` | STT 텍스트 결과 |
| `runs/llm/stt_summary.txt` | STT 기반 LLM 요약 |
| `runs/llm/stt_summary_result.json` | 주요 구간을 포함한 STT 요약 결과 |
| `runs/metadata/frame_metadata.json` | 샘플링된 프레임 메타데이터 |
| `runs/ocr/ocr_result.json` | 프레임별 OCR 결과 |
| `runs/vlm/vlm_summary.txt` | 프레임별 VLM 요약 |
| `runs/vlm/vlm_summary_result.json` | VLM 요약 구조화 결과 |
| `runs/final/final_summary.txt` | 최종 통합 요약 |
| `runs/final/final_summary_result.json` | 최종 통합 요약 결과 (`source`/`final_summary`/`summary` 3개 키만 있으며, 실제 요약 내용은 `summary` 안에 마크다운 텍스트로 들어있음. VLM 요약이 없을 때는 `final_summary` 키 없이 `source`/`summary`만 있고 `source.mode`가 `"stt_only"`) |

## 문서

- `docs/setup_guide.md`: 설치 및 실행 환경 안내
- `docs/data_format.md`: 주요 JSON 데이터 형식
- `docs/system_overvies.md`: 시스템 개요 문서
- `docs/explanation/README.md`: 모듈별 상세 설명 문서 색인
- `docs/explanation/scripts/scripts.md`: CLI 스크립트 설명
- `docs/explanation/app/app.md`: Streamlit UI 구조와 실행 흐름
- `docs/explanation/configs/configs.md`: 설정 파일 설명
- `docs/explanation/tests/tests.md`: 테스트 구성 설명

## 현재 구현 상태

| 영역 | 상태 |
| --- | --- |
| 영상 전처리 | 구현됨 |
| 프레임 샘플링 | 구현됨 |
| 오디오 추출 | 구현됨 |
| Whisper STT | 구현됨 |
| EasyOCR | 구현됨 |
| STT 요약 LLM 클라이언트 | 구현됨, GPU 서버 필요 |
| VLM 요약 클라이언트 | 구현됨, GPU 서버 필요 |
| 최종 요약 클라이언트 | 구현됨, GPU 서버 필요 |
| Streamlit UI | 구현됨 |

## 팀 역할

| 이름 | 담당 |
| --- | --- |
| 함도연 | STT 데이터, AI 모델 조사, VLM/LLM 환경 설정 |
| 김승민 | 영상 전처리, 프레임/오디오 분할, 입출력 UI |
| 정병두 | OCR 데이터, AI 모델 조사, VLM/LLM 모듈 설계 |
| 조윤호 | 입출력 UI |
