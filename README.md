# Video Summarization AI Server

영상의 STT 결과를 요약하고, OCR/VLM 분석에 사용할 중요 구간을 추출하는 FastAPI 서버입니다.

현재 HTTP API는 STT 요약과 중요 구간 추출을 제공합니다. VLM 프레임 분석 기능은
`VLMService`로 구현되어 있지만 별도의 HTTP 엔드포인트는 아직 제공하지 않습니다.

## 주요 기능

- Qwen3-8B를 사용한 한국어 STT 요약
- STT 타임스탬프 기반 중요 영상 구간 추출
- Qwen2.5-VL-7B-Instruct를 사용한 프레임 및 OCR 내용 요약
- 단일 작업 실행기와 공용 lock을 사용한 GPU 추론 직렬화
- 작업 ID 기반 비동기 처리와 진행 상태 조회

## 사용 모델

| 용도 | 모델 | 로컬 경로 |
| --- | --- | --- |
| STT 요약 및 구간 추출 | `Qwen/Qwen3-8B` | `models/hf_cache/Qwen3-8B` |
| 프레임 분석 | `Qwen/Qwen2.5-VL-7B-Instruct` | `models/hf_cache/Qwen2.5-VL-7B-Instruct` |

## 요구 사항

- Python 3.10 이상
- CUDA를 지원하는 NVIDIA GPU
- 설치된 CUDA 환경과 호환되는 PyTorch
- 모델 저장 공간 약 35GB 이상

현재 모델 설정은 `device="cuda"`, `torch_dtype="float16"`을 사용합니다.

## 설치

가상 환경을 생성하고 패키지를 설치합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

CUDA 버전에 맞는 PyTorch 설치가 필요한 경우 [PyTorch 설치 안내](https://pytorch.org/get-started/locally/)에 따라 먼저 설치한 뒤 나머지 패키지를 설치합니다.

## 모델 다운로드

다음 명령은 Hugging Face에서 두 모델을 `models/hf_cache` 아래에 다운로드합니다.

```powershell
python scripts\download_models.py
```

모델 파일은 `.gitignore`에 의해 Git에서 제외됩니다.

## 서버 실행

Windows 탐색기에서 `scripts/start_server.bat`를 더블클릭하면 서버가 실행됩니다. 이 파일은 `video_summarization` Conda 환경의 Python을 사용합니다.
기본 서버 주소는 `http://10.30.2.224:8000`이며, 환경 경로나 서버 주소가 다르면 배치 파일의 `PYTHON_EXE`, `SERVER_HOST`, `SERVER_PORT` 값을 수정해야 합니다.

`scripts/server.py`를 직접 실행할 수 있습니다.

```powershell
python scripts\server.py
```

또는 PowerShell 실행 스크립트를 사용합니다.

```powershell
.\scripts\start_server.ps1
```

PowerShell 스크립트의 기본 호스트와 포트는 `10.30.2.224:8000`입니다.

호스트와 포트를 변경하려면 다음과 같이 실행합니다.

```powershell
.\scripts\start_server.ps1 -HostAddress "127.0.0.1" -Port 8080
```

Uvicorn 명령을 직접 사용해도 됩니다.

```powershell
python -m uvicorn scripts.server:app --host 0.0.0.0 --port 8000 --workers 1
```

개발 중 자동 재시작이 필요하면 다음 명령을 사용합니다.

```powershell
python -m uvicorn scripts.server:app --reload --port 8000
```

GPU 모델과 작업 상태가 프로세스 메모리에 유지되므로 운영 시에는 반드시
`--workers 1`을 사용합니다. `--reload`는 개발 환경에서만 사용합니다.

기본적으로 각 작업이 끝나면 LLM을 GPU 메모리에서 내립니다. 다음 요청의 모델
재로딩 시간을 줄이려면 서버 실행 전에 환경 변수를 설정합니다.

```powershell
$env:KEEP_LLM_LOADED = "1"
.\scripts\start_server.ps1
```

`scripts/server.py`를 직접 실행할 때는 `SERVER_HOST`, `SERVER_PORT` 환경 변수로
주소를 변경할 수 있습니다.

```powershell
$env:SERVER_HOST = "127.0.0.1"
$env:SERVER_PORT = "8080"
python scripts\server.py
```

서버 실행 후 API 문서를 확인할 수 있습니다.

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- 상태 확인: `http://localhost:8000/health`

`GET /health` 응답 예시는 다음과 같습니다.

```json
{
  "status": "ok",
  "active_jobs": 1
}
```

## STT 요청 형식

`POST /llm/summarize`는 STT JSON을 요청 본문으로 받고 HTTP `202 Accepted`와
작업 ID를 즉시 반환합니다. 추론 중에는 작업 상태 API를 주기적으로 조회합니다.

작업 ID는 `stt-summary-a1b2c3d4e5f6` 형식입니다. 작업 종류와 고유 식별자가 포함되어 서버 로그에서 작업을 쉽게 구분할 수 있습니다. 생성 시각은 각 로그 줄에 별도로 기록됩니다.

```json
{
  "language": "ko",
  "segments": [
    {
      "segment_id": 0,
      "start": 0.0,
      "end": 3.4,
      "text": "첫 번째 발화 내용입니다."
    },
    {
      "segment_id": 1,
      "start": 3.4,
      "end": 7.0,
      "text": "두 번째 발화 내용입니다."
    }
  ],
  "full_text": "첫 번째 발화 내용입니다. 두 번째 발화 내용입니다.",
  "max_new_tokens": 1024
}
```

`full_text`가 비어 있으면 서버가 `segments[].text`를 연결하여 요약합니다. `max_new_tokens`는 `1`부터 `2048`까지 지정할 수 있습니다.

프로젝트의 샘플 STT 결과로 작업을 생성하려면 다음 명령을 실행합니다.

```powershell
$job = Invoke-RestMethod `
  -Uri "http://localhost:8000/llm/summarize" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -InFile "test\stt_result.json"

$job
```

작업 생성 응답은 다음과 같습니다.

```json
{
  "job_id": "작업 ID",
  "status": "queued",
  "message": "요청을 접수했습니다. status_url을 조회해 진행 상태를 확인하세요.",
  "status_url": "/llm/jobs/작업 ID"
}
```

진행 상태를 확인합니다.

```powershell
$statusUrl = "http://localhost:8000$($job.status_url)"

do {
  $status = Invoke-RestMethod -Uri $statusUrl
  Write-Host "[$($status.status)] $($status.message)"
  if ($status.status -in @("queued", "running")) {
    Start-Sleep -Seconds 5
  }
} while ($status.status -in @("queued", "running"))

$status.result
```

상태 값은 `queued`, `running`, `completed`, `failed` 중 하나입니다. 추론 중에는 `message`, `current_step`, `total_steps`로 진행 상황을 확인할 수 있습니다.

상태 응답에는 `created_at`, `updated_at`, `elapsed_seconds`가 항상 포함됩니다.
실패한 작업은 `error`에 오류 메시지가 기록되며, 완료 전에는 `result`가 `null`입니다.

작업 대기열과 상태는 서버 프로세스의 메모리에만 저장됩니다. 서버를 재시작하면
기존 작업 ID와 결과는 사라지며, 여러 worker를 실행하면 worker별로 상태가 분리됩니다.

서버 진행 로그는 콘솔과 `logs/server.log`에 함께 기록됩니다. 긴 추론 단계에서는 10초마다 단계별 및 전체 경과 시간이 기록되며, 상태 API의 `elapsed_seconds`에서도 전체 경과 시간을 확인할 수 있습니다.
로그 파일은 최대 10MB 단위로 회전하며 이전 로그를 최대 5개까지 보관합니다.

## 완료 응답 형식

작업 상태가 `completed`이면 `result`에 다음 결과가 포함됩니다.

```json
{
  "job_id": "작업 ID",
  "status": "completed",
  "message": "요약과 중요 구간 추출이 완료되었습니다.",
  "result": {
    "summary": "## STT 요약\n...",
    "important_segments": [
      {
        "segment_id": 0,
        "start": 0.0,
        "end": 7.0,
        "topic": "주제",
        "reason": "선택 이유"
      }
    ]
  }
}
```

- `summary`: STT 전체 내용의 Markdown 요약
- `important_segments`: 중요 구간 객체 배열
- `segments`가 없으면 `important_segments`는 빈 배열 `[]`입니다.

`segment_id`, `start`, `end`를 사용해 후속 프레임 추출 범위를 결정할 수 있습니다.

## 프로젝트 구조

```text
.
|-- models/
|   |-- llm_loader.py
|   |-- vlm_loader.py
|   `-- hf_cache/             # 다운로드한 로컬 모델
|-- scripts/
|   |-- __init__.py
|   |-- download_models.py
|   |-- server.py
|   |-- start_server.bat
|   `-- start_server.ps1
|-- services/
|   |-- llm_service.py
|   |-- summary_service.py
|   `-- vlm_service.py
|-- test/
|   |-- stt_result.json
|   |-- llm_service_result.json
|   `-- test_llm_service.py
|-- logs/
|   `-- server.log           # 실행 중 생성, Git 제외
|-- README.md
`-- requirements.txt
```

## LLM 서비스 직접 실행

API 서버를 거치지 않고 샘플 STT 파일로 LLM 서비스를 실행할 수 있습니다.

```powershell
python test\test_llm_service.py `
  --input test\stt_result.json `
  --output test\llm_service_result.json `
  --max-new-tokens 256 `
  --important-max-new-tokens 192 `
  --segment-chunk-chars 12000
```

이 명령은 실제 Qwen3-8B 모델을 로드하므로 CUDA GPU와 다운로드된 모델이 필요하며
실행 시간이 오래 걸릴 수 있습니다.

## 처리 흐름

1. `scripts/server.py`가 STT JSON을 검증합니다.
2. `full_text`를 LLM에 전달하여 전체 요약을 생성합니다.
3. 타임스탬프가 있는 `segments`와 요약을 LLM에 전달합니다.
4. LLM이 입력에 존재하는 `start`, `end`, `segment_id`를 기준으로 중요 구간을 선택합니다.
5. 후속 처리에서 선택된 시간대의 프레임과 OCR 결과를 `VLMService`로 분석할 수 있습니다.

## 주의 사항

- 모델은 첫 추론 요청 시 메모리에 로드되므로 첫 응답이 오래 걸릴 수 있습니다.
- 두 모델은 크기가 크므로 GPU VRAM과 시스템 메모리를 충분히 확보해야 합니다.
- `/health`는 서버 프로세스 상태만 확인하며 CUDA 및 모델 로딩 성공 여부까지 검사하지 않습니다.
- LLM 작업이 끝나면 기본적으로 모델을 GPU에서 내립니다. 다음 요청의 재로딩 시간을 줄이려면 서버 실행 전에 `KEEP_LLM_LOADED=1`을 설정합니다.
- 중요 구간은 LLM의 구분자 형식 출력을 파싱합니다. 형식이 잘못된 묶음은 건너뛰므로 결과 개수가 입력이나 예상과 다를 수 있습니다.
- 현재 작업 취소, 결과 영속화, 만료된 작업 정리 기능은 구현되어 있지 않습니다.
