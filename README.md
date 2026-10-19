# Multimodal Video Summarization

영상에서 음성, 주요 프레임, OCR 텍스트를 추출하고 로컬 모델 서버 또는 Claude Haiku API를 사용해 최종 요약을 만드는 캡스톤 프로젝트입니다.

현재 저장소는 `scripts/` CLI 파이프라인과 웹 UI를 함께 제공합니다. 웹 UI는 React 화면(`frontend/`)과 이를 내보내는 FastAPI 앱 서버(`app/api/`)가 기본이며, 기존 Streamlit 화면(`app/main.py`)도 예비로 남아 있습니다. UI는 영상 업로드, 파이프라인 실행, 원본 영상과 최종 요약 결과 확인을 담당합니다.

## 주요 기능

- FFmpeg/FFprobe 기반 영상 정보 확인, 오디오 추출, MP4 변환
- 일정 간격 또는 장면 전환 기반 프레임 샘플링
- Whisper 기반 STT 결과 생성
- EasyOCR 기반 프레임 텍스트 추출
- STT 결과를 LLM 서버로 보내 주요 구간과 요약 생성
- OCR/프레임 결과를 VLM 서버로 보내 프레임별 요약 생성
- STT 요약과 VLM 요약을 결합한 최종 요약 생성
- 파일 업로드 또는 유튜브 링크로 분석할 영상 지정 (`yt-dlp` 기반 다운로드)
- 로컬 모델 서버 / Claude API 분석 방식 선택
- Whisper 크기 선택: 간단(small) / 기본(medium) / 상세(large)
- 분석 진행 중 7단계 진행 상황을 원형 아이콘/퍼센트로 실시간 표시, 실패 시 오류 표시
- 분석 완료 후 영상과 요약 결과를 `data/saved/`에 함께 저장
- 저장된 요약 결과를 다시 불러와 확인/삭제
- 완료된 분석 결과를 "분석 결과" 탭·실행 이력에서 다시 열기
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
├── app/                  # 앱 서버(app/api, React용 FastAPI)와 예비 Streamlit UI
├── frontend/             # React 화면 (Vite + TypeScript)
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

`requirements.txt`에는 EasyOCR, OpenCV, PyTorch(cu130), Whisper(`openai-whisper`), 앱 서버용 FastAPI(0.118.0)·uvicorn·python-multipart, Streamlit(1.58.0), 유튜브 다운로드용 `yt-dlp`, requests, PyYAML 등이 포함되어 있습니다. FastAPI가 쓰는 pydantic 2.14 때문에 `typing-extensions`는 4.16.0으로 고정되어 있습니다.

React 화면을 빌드하려면 [Node.js LTS](https://nodejs.org/)가 필요합니다(Windows: `winget install OpenJS.NodeJS.LTS`). `start_all.bat`은 빌드 결과가 없을 때 자동으로 빌드합니다.

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

LLM/VLM/최종 요약은 `--analysis-backend local|claude`로 선택합니다. 로컬 모드는 `gpu-server`의 Qwen 모델 서버를, API 모드는 같은 분석 서버를 거쳐 Claude Haiku를 사용합니다. 키는 서버 컴퓨터의 `ANTHROPIC_API_KEY` 환경변수에서만 읽습니다. 서버 업데이트 방법은 [분석 방식 설정](docs/analysis_backends.md)을 참고하세요.

## React 앱 실행 (기본)

화면은 React(`frontend/`), 화면이 호출하는 API는 FastAPI 앱 서버(`app/api/server.py`)입니다. 앱 서버가 React 빌드 결과(`frontend/dist`)도 함께 제공하므로 포트 하나(기본 8501)만 열면 됩니다. LLM/VLM 추론 서버(`GPU_SERVER_URL`, 기본 8000)와는 별개의 서버입니다.

`start_all.bat`은 기본으로 React 앱 서버를 띄우고, `frontend/dist`가 없으면 먼저 빌드합니다(Node.js LTS 필요). 직접 실행하는 방법은 아래와 같습니다.

```bash
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn app.api.server:app --host 127.0.0.1 --port 8501
```

화면 코드를 고친 뒤에는 `npm run build`를 다시 실행하세요. 개발 중에는 앱 서버를 8501에 띄운 상태에서 `frontend`에서 `npm run dev`를 실행하면 `/api` 요청이 8501로 전달됩니다.

| 경로 | 화면 |
| --- | --- |
| `/upload` | 영상 업로드·분석 설정·진행 상황 (`?run=<실행 ID>`로 새로고침 후 다시 연결) |
| `/result/<실행 ID>` | 원본 영상과 최종 요약, 결과 저장 |
| `/saved` | 저장된 요약 목록·확인·삭제 |
| `/history` | 실행 이력과 성능 지표 |

- 로그인 비밀번호는 `APP_PASSWORD` 환경변수 또는 기존 `.streamlit/secrets.toml`의 `APP_PASSWORD`를 씁니다. 규칙은 Streamlit과 같습니다(비밀번호가 없으면 로컬만 허용, Cloudflare Tunnel 경유 접속은 차단).
- 로그인 세션은 서버를 재시작하면 풀립니다. 유지하려면 `APP_SESSION_SECRET`을 고정값으로 설정하세요(유효 시간 `APP_SESSION_HOURS`, 기본 12시간).
- 업로드 한도는 `MAX_UPLOAD_MB`(기본 500MB), 외부 접속은 `EXTERNAL_UPLOAD_LIMIT_MB`(기본 100MB)입니다.
- 기존 Streamlit 화면이 필요하면 `start_all.bat -Streamlit`(또는 `APP_UI=streamlit`)으로 같은 포트에 띄울 수 있습니다. 두 화면은 같은 실행 기록·저장 결과를 공유하지만 같은 포트를 쓰므로 하나만 실행하세요.

## Streamlit 앱 실행 (예비)

Windows에서는 배치 파일로 실행할 수 있습니다.

```bat
run_app.bat
```

직접 실행할 수도 있습니다.

```bash
streamlit run app/main.py
```

앱(React `/upload`, Streamlit `app/pages/1_upload.py`)은 두 가지 방식으로 분석할 영상을 지정할 수 있습니다. 업로드마다 고유 폴더를 만들어 여러 사용자의 파일이 섞이지 않습니다.

- 파일 업로드: `data/input/uploads/<업로드 ID>/input.<확장자>` (mp4/mov/avi)로 저장
- 유튜브 링크: `modules/preprocess/youtube_downloader.py`의 `download_youtube_video()`가 `yt-dlp`로 다운로드해 `data/input/uploads/<업로드 ID>/input.mp4`로 저장

업로드 화면에는 **분석 방식**과 **Whisper 음성 인식**을 독립적으로 선택하는 설정이 있습니다.

| Whisper 설정 | 모델 | 화면 분석 |
| --- | --- | --- |
| 간단 (`simple`) | small | OCR·VLM 실행 |
| 기본 (`standard`, 기본값) | medium | OCR·VLM 실행 |
| 상세 (`detailed`) | large | OCR·VLM 실행 |

세 설정은 Whisper 크기만 변경하며 요약 생성 정책은 동일합니다.

영상이 준비되면 `scripts/run_pipeline.py --summary-level <선택값>`을 백그라운드 프로세스로 실행합니다. 실행 로그는 `runs/history/<실행 ID>/process.log`에 저장되며, 파이프라인이 `modules/common/progress.py`의 `report_progress()`로 남기는 `##PROGRESS##` 마커를 앱이 폴링해 7단계 진행 상황을 원형 아이콘과 퍼센트로 보여줍니다. 파이프라인 프로세스가 오류로 종료되면 진행 중이던 단계가 빨간 오류 아이콘으로 표시됩니다.

분석이 끝나면 `pages/2_analysis_result.py`에서 원본 영상과 최종 요약을 함께 확인할 수 있고, "영상과 요약 결과 저장" 버튼(`app/result_export.py`)으로 `data/saved/[영상 제목] - 년월일시분초/` 폴더에 영상과 요약 파일을 복사해 보관할 수 있습니다(표/차트 스크린샷 복원용 프레임/OCR 결과도 있으면 함께 저장). 요약 화면의 타임라인은 `분:초` 형식의 클릭 가능한 뱃지로 표시되며, 클릭하면 영상이 해당 지점으로 이동합니다. `pages/3_saved_summaries.py`에서는 저장된 결과 목록을 다시 불러와 확인하거나 삭제할 수 있습니다.

## 로그인 보호 및 외부 공개 (선택)

앱을 로컬에서만 쓸 때는 아래 설정이 필요 없습니다. Cloudflare Tunnel 등으로 외부에 공개할 때만 설정하세요.

- **로그인 게이트**: `.streamlit/secrets.toml`(React 앱 서버는 `APP_PASSWORD` 환경변수도 가능)에 `APP_PASSWORD`를 설정하면 모든 화면 진입 전에 비밀번호 입력 화면이 표시됩니다(React: `app/api/auth.py`, Streamlit: `app/auth.py`의 `require_login()`). `APP_PASSWORD`가 없으면 로컬 접속은 그대로 통과하고, Cloudflare를 거친 외부 접속은 차단됩니다.
- **Cloudflare Tunnel**: `start_tunnel.bat`(Windows) 또는 `start_tunnel.ps1`을 실행하면 `cloudflared`가 로컬 8501 포트(앱 서버 기본 포트)를 외부 URL로 연결하고, 발급된 URL을 `tunnel_url.txt`에 저장합니다. `cloudflared`가 PATH에 설치되어 있어야 합니다.

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

`--summary-level`은 Whisper 모델만 선택합니다: `simple=small`, `standard=medium`, `detailed=large`. 모든 선택에서 전체 분석 단계를 수행합니다.

일부 단계를 건너뛸 수 있습니다.

```bash
python scripts/run_pipeline.py --skip-ocr
python scripts/run_pipeline.py --skip-vlm
```

명시적으로 `--skip-ocr` 또는 `--skip-vlm`을 사용해 VLM 요약이 없으면, 최종 통합 요약 단계는 서버에 병합 요청을 보내지 않고 STT 요약을 그대로 최종 요약으로 저장합니다.

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
- `docs/single_server_deployment.md`: 단일 서버 실행(`start_all`)과 Cloudflare 외부 접속
- `docs/explanation/app/app.md`: 앱 공통 모듈과 Streamlit UI 구조
- `docs/explanation/app/app_api.md`: React 화면용 앱 API 서버(엔드포인트, 로그인·보안)
- `docs/explanation/frontend/frontend.md`: React 화면 구조, 개발·빌드 방법
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
| React 화면 + 앱 API 서버 | 구현됨 (기본 UI) |
| Streamlit UI | 구현됨 (예비) |

## 팀 역할

| 이름 | 담당 |
| --- | --- |
| 함도연 | STT 데이터, AI 모델 조사, VLM/LLM 환경 설정 |
| 김승민 | 영상 전처리, 프레임/오디오 분할, 입출력 UI |
| 정병두 | OCR 데이터, AI 모델 조사, VLM/LLM 모듈 설계 |
| 조윤호 | 입출력 UI |

## 실행 이력과 성능 분석

실행별 소요 시간, 프레임 수, OCR/VLM 처리량과 원본 로그가 `runs/history/<실행 ID>/`에 자동 보관됩니다. 앱의 **실행 이력** 화면(React·Streamlit 모두)에서 조회·필터링하고 CSV/JSON/로그를 다운로드할 수 있습니다. [자세한 사용법](docs/run_history.md)을 참고하세요.
