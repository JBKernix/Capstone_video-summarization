# Multimodal Video Summarization

영상에서 음성, 주요 프레임, OCR 텍스트를 추출하고 외부 GPU 서버의 LLM/VLM API를 사용해 최종 요약을 만드는 캡스톤 프로젝트입니다.

현재 저장소의 핵심 실행 흐름은 Streamlit UI가 아니라 `scripts/`의 CLI 스크립트입니다. `app/` 아래 UI 파일은 아직 비어 있으므로, 실행과 검증은 아래 CLI 명령을 기준으로 진행합니다.

## 주요 기능

- FFmpeg/FFprobe 기반 영상 정보 확인, 오디오 추출, MP4 변환
- 일정 간격 또는 장면 전환 기반 프레임 샘플링
- Whisper 기반 STT 결과 생성
- EasyOCR 기반 프레임 텍스트 추출
- STT 결과를 LLM 서버로 보내 주요 구간과 요약 생성
- OCR/프레임 결과를 VLM 서버로 보내 프레임별 요약 생성
- STT 요약과 VLM 요약을 결합한 최종 요약 생성

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
├── app/                  # Streamlit UI 예정 영역, 현재 파일은 비어 있음
├── configs/              # STT 등 설정 파일
├── data/input/           # 기본 입력 영상 위치
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
GPU_SERVER_URL = "http://10.30.2.224:8000"
```

서버가 접근 가능하지 않으면 `run_llm_summary.py`, `run_vlm_summary.py`, `run_final_summary.py` 및 전체 파이프라인의 관련 단계가 실패합니다.

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
  --stt-language ko
```

일부 단계를 건너뛸 수 있습니다.

```bash
python scripts/run_pipeline.py --skip-stt
python scripts/run_pipeline.py --skip-ocr
python scripts/run_pipeline.py --skip-vlm
```

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

참고로 `scripts/run_pipeline.py`는 VLM 프레임 요약까지 실행합니다. 최종 통합 요약 파일인 `runs/final/final_summary.txt`가 필요하면 `scripts/run_final_summary.py`를 이어서 실행하세요.

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
| `runs/final/final_summary_result.json` | 최종 통합 요약 구조화 결과 |

## 문서

- `docs/setup_guide.md`: 설치 및 실행 환경 안내
- `docs/data_format.md`: 주요 JSON 데이터 형식
- `docs/system_overvies.md`: 시스템 개요 문서
- `docs/explanation/README.md`: 모듈별 상세 설명 문서 색인
- `docs/explanation/scripts/scripts.md`: CLI 스크립트 설명
- `docs/explanation/app/app.md`: UI 예정 파일과 현재 상태
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
| Streamlit UI | 파일만 존재, 미구현 |

## 팀 역할

| 이름 | 담당 |
| --- | --- |
| 함도연 | STT 데이터, AI 모델 조사, VLM/LLM 환경 설정 |
| 김승민 | 영상 전처리, 프레임/오디오 분할, 입출력 UI |
| 정병두 | OCR 데이터, VLM/LLM 모듈 설계 |
| 조윤호 | 입출력 UI |
