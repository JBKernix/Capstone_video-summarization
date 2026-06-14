# Video Summarization AI Server

영상의 STT 결과를 요약하고 중요한 구간을 추출하며, 해당 구간의 프레임과 OCR 결과를 VLM으로 분석하는 FastAPI 서버입니다.

## 주요 기능

- Qwen3-8B 기반 한국어 STT 요약
- STT 타임스탬프 기반 중요 영상 구간 추출
- Qwen2.5-VL-7B-Instruct 기반 프레임 및 OCR 분석
- 작업 ID 기반 비동기 요청과 진행 상태 조회
- 단일 작업 큐와 공용 lock을 통한 GPU 추론 직렬화
- 작업 완료 후 LLM/VLM GPU 메모리 자동 해제
- 콘솔 및 회전 로그 파일 기록

## 사용 모델

| 용도 | Hugging Face 모델 | 로컬 저장 경로 |
| --- | --- | --- |
| STT 요약 및 중요 구간 추출 | `Qwen/Qwen3-8B` | `models/hf_cache/Qwen3-8B` |
| 프레임 및 OCR 분석 | `Qwen/Qwen2.5-VL-7B-Instruct` | `models/hf_cache/Qwen2.5-VL-7B-Instruct` |

모델 가중치와 Hugging Face 캐시는 용량이 크므로 GitHub에 포함되지 않습니다.

## 요구 사항

- Python 3.10 이상
- CUDA를 지원하는 NVIDIA GPU
- 설치된 CUDA 환경과 호환되는 PyTorch
- 모델 저장 공간 약 35GB 이상

기본 모델 설정은 `device="cuda"`, `torch_dtype="float16"`입니다.

## 설치

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

CUDA 환경에 맞는 PyTorch가 별도로 필요하다면 [PyTorch 설치 안내](https://pytorch.org/get-started/locally/)에 따라 설치합니다.

## 모델 다운로드

```powershell
python scripts\download_models.py
```

다운로드된 파일은 `models/hf_cache/`에 저장되며 `.gitignore`에 의해 Git에서 제외됩니다.

## 서버 실행

Windows에서는 배치 파일을 실행할 수 있습니다.

```powershell
.\scripts\start_server.bat
```

배치 파일은 기본적으로 다음 값을 사용합니다.

- Conda 환경: `video_summarization`
- 서버 주소: `10.30.2.224:8000`
- Uvicorn worker: `1`

환경 경로나 서버 주소가 다르면 `scripts/start_server.bat`의 `PYTHON_EXE`, `SERVER_HOST`, `SERVER_PORT`를 수정합니다.

Python 또는 Uvicorn으로 직접 실행할 수도 있습니다.

```powershell
python scripts\server.py
```

```powershell
python -m uvicorn scripts.server:app --host 0.0.0.0 --port 8000 --workers 1
```

GPU 모델과 작업 상태가 프로세스 메모리에 저장되므로 운영 환경에서는 `--workers 1`을 사용해야 합니다.

## 환경 변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `SERVER_HOST` | `0.0.0.0` | `server.py` 직접 실행 시 호스트 주소 |
| `SERVER_PORT` | `8000` | `server.py` 직접 실행 시 포트 |
| `KEEP_LLM_LOADED` | `0` | `1`이면 LLM 작업 후 모델을 GPU에 유지 |
| `KEEP_VLM_LOADED` | `0` | `1`이면 VLM 작업 후 모델을 GPU에 유지 |
| `NO_COLOR` | 미설정 | 설정하면 콘솔 컬러 로그 비활성화 |

기본 설정에서는 각 작업이 끝날 때 모델 참조와 CUDA 캐시를 해제합니다.

## API

서버 실행 후 다음 문서를 사용할 수 있습니다.

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- 상태 확인: `GET /health`

### STT 요약 요청

`POST /llm/summarize`는 JSON 요청을 받고 `202 Accepted`와 작업 ID를 반환합니다.

```json
{
  "language": "ko",
  "segments": [
    {
      "segment_id": 0,
      "start": 0.0,
      "end": 3.4,
      "text": "첫 번째 발화 내용입니다."
    }
  ],
  "full_text": "첫 번째 발화 내용입니다.",
  "max_new_tokens": 1024
}
```

`full_text`가 비어 있으면 `segments[].text`를 연결하여 사용합니다. `max_new_tokens`는 `1`부터 `2048`까지 지정할 수 있습니다.

### VLM 프레임 분석 요청

`POST /vlm/summarize`는 `multipart/form-data` 요청을 받습니다.

| 필드 | 형식 | 설명 |
| --- | --- | --- |
| `ocr_result` | JSON 파일 1개 | 프레임별 OCR 결과 배열 |
| `frames` | JPG 파일 여러 개 | OCR의 `image_path` 파일명과 매칭할 프레임 |
| `max_new_tokens` | 정수 | 기본값 `512`, 최대 `2048` |

PowerShell 요청 예시:

```powershell
curl.exe -X POST "http://localhost:8000/vlm/summarize" `
  -F "ocr_result=@C:\path\to\ocr_result.json;type=application/json" `
  -F "frames=@C:\path\to\frame_000001.jpg;type=image/jpeg" `
  -F "frames=@C:\path\to\frame_000002.jpg;type=image/jpeg" `
  -F "max_new_tokens=512"
```

프레임은 최대 32장, 파일당 최대 20MB까지 받을 수 있습니다. OCR JSON은 최대 10MB입니다.

### 작업 상태 조회

- LLM: `GET /llm/jobs/{job_id}`
- VLM: `GET /vlm/jobs/{job_id}`

작업 상태는 `queued`, `running`, `completed`, `failed` 중 하나입니다.

```json
{
  "job_id": "vlm-summary-a1b2c3d4e5f6",
  "status": "running",
  "message": "프레임을 분석하고 있습니다. (1/3)",
  "current_step": 1,
  "total_steps": 3,
  "result": null,
  "error": null,
  "created_at": "2026-06-14T00:00:00+00:00",
  "updated_at": "2026-06-14T00:00:05+00:00",
  "elapsed_seconds": 5.0
}
```

작업과 결과는 서버 메모리에만 저장되므로 서버를 재시작하면 사라집니다.

## 프로젝트 구조

아래 구조는 `.gitignore`에 의해 제외되는 테스트 파일, 모델 가중치, 입력·출력 데이터, 실행 결과 및 로그를 제외한 GitHub 업로드 대상입니다.

```text
.
|-- models/
|   |-- __init__.py
|   |-- llm_loader.py
|   `-- vlm_loader.py
|-- scripts/
|   |-- __init__.py
|   |-- api_models.py
|   |-- download_models.py
|   |-- inference_jobs.py
|   |-- job_store.py
|   |-- server.py
|   |-- server_logging.py
|   |-- start_server.bat
|   `-- vlm_upload.py
|-- services/
|   |-- __init__.py
|   |-- llm_service.py
|   |-- summary_service.py
|   `-- vlm_service.py
|-- .gitignore
|-- README.md
`-- requirements.txt
```

## Scripts 폴더

FastAPI 서버 실행, HTTP 요청 처리, 비동기 작업 관리와 운영 설정을 담당합니다.

상세 설명: [`scripts/README.md`](scripts/README.md)

| 파일 | 역할 |
| --- | --- |
| `server.py` | FastAPI 앱 생성, LLM/VLM 라우트 등록, 서비스와 작업 실행기 조립 |
| `api_models.py` | STT 요청, 작업 접수, 작업 상태와 결과에 사용하는 Pydantic 모델 정의 |
| `inference_jobs.py` | LLM/VLM 백그라운드 추론, 진행률 갱신, 오류 처리, GPU 모델 해제 |
| `job_store.py` | 작업 ID 생성과 인메모리 작업 상태 저장 및 조회 |
| `server_logging.py` | 콘솔 컬러 로그와 회전 파일 로그 설정 |
| `vlm_upload.py` | OCR JSON과 JPG 업로드 크기 검증, 파일명 기반 OCR-프레임 매칭 |
| `download_models.py` | 필요한 Hugging Face 모델을 로컬 캐시에 다운로드 |
| `start_server.bat` | Windows Conda 환경에서 Uvicorn 서버 실행 |

## Models 폴더

Hugging Face 모델의 로딩, 추론과 GPU 메모리 해제를 담당합니다. Python 로더 코드는 GitHub에 포함되지만 `models/hf_cache/`의 실제 모델 파일은 제외됩니다.

상세 설명: [`models/README.md`](models/README.md)

| 파일 | 역할 |
| --- | --- |
| `llm_loader.py` | Qwen3-8B 토크나이저와 모델 로드, 텍스트 생성, 모델 해제 |
| `vlm_loader.py` | Qwen2.5-VL 모델과 프로세서 로드, 이미지 분석, 모델 해제 |

두 로더 모두 모델을 지연 로딩하며, `unload()` 호출 시 참조 제거와 CUDA 캐시 정리를 수행합니다.

## Services 폴더

모델 로더와 API 계층 사이의 비즈니스 로직을 담당합니다.

상세 설명: [`services/README.md`](services/README.md)

| 파일 | 역할 |
| --- | --- |
| `llm_service.py` | STT 요약 프롬프트, 중요 구간 추출, 세그먼트 분할과 결과 파싱 |
| `vlm_service.py` | OCR 결과 파싱, 다중 프레임 매칭, 프레임별 VLM 프롬프트와 결과 구성 |
| `summary_service.py` | LLM/VLM 서비스 생성, 공용 GPU lock 공유, 상위 호출 인터페이스 제공 |

## GitHub 제외 항목

`.gitignore`에 따라 다음 내용은 저장소에 포함되지 않습니다.

| 경로 또는 패턴 | 내용 |
| --- | --- |
| `models/hf_cache/` | 다운로드된 모델 설정과 가중치 |
| `*.pt`, `*.pth`, `*.bin`, `*.safetensors` | 모델 및 체크포인트 파일 |
| `data/input/`, `data/output/` | 입력 및 출력 데이터 |
| `runs/` | 프레임 추출 등 실행 결과 |
| `logs/` | 서버 실행 로그 |
| `test/` | 로컬 테스트 코드와 샘플 데이터 |
| `.env` | 환경 변수와 비밀 설정 |
| `__pycache__/` | Python 바이트코드 캐시 |

## 처리 흐름

1. `scripts/server.py`가 요청을 검증하고 작업을 생성합니다.
2. `JobStore`가 작업 상태와 진행률을 메모리에 저장합니다.
3. 단일 `ThreadPoolExecutor`가 GPU 추론 작업을 순서대로 실행합니다.
4. `InferenceJobRunner`가 `SummaryService`를 통해 LLM 또는 VLM 서비스를 호출합니다.
5. 서비스가 입력을 정규화하고 프롬프트를 구성한 뒤 모델 로더에 전달합니다.
6. 작업 완료 후 결과를 저장하고 기본 설정에서는 GPU 모델을 해제합니다.

## 주의 사항

- 첫 요청에서는 로컬 모델을 GPU에 로드하므로 응답 시간이 오래 걸릴 수 있습니다.
- `/health`는 서버 프로세스 상태만 확인하며 CUDA와 모델 로딩까지 검사하지 않습니다.
- 작업 취소, 결과 영속화, 만료 작업 정리 기능은 현재 제공하지 않습니다.
- `KEEP_LLM_LOADED=1` 또는 `KEEP_VLM_LOADED=1`은 재로딩 시간을 줄이지만 GPU 메모리를 계속 점유합니다.
