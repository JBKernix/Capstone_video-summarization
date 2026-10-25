# App

FastAPI 애플리케이션, HTTP 입력 검증, 비동기 작업 상태 관리와 서버 실행 설정을 담당하는 계층입니다.

모델별 프롬프트나 추론 구현은 이 폴더에 두지 않습니다. HTTP와 작업 실행에 필요한 조정만 수행하고 실제 처리 로직은 `services/`, 모델 로딩은 `models/`에 위임합니다.

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `server.py` | FastAPI 앱 생성, 의존 객체 조립, LLM/VLM 라우트 등록 |
| `api_models.py` | 요청, 작업 접수, 상태 조회, 결과 응답용 Pydantic 모델 |
| `inference_jobs.py` | 백그라운드 추론 실행, 진행률 갱신, 오류 처리, 모델 해제 |
| `job_store.py` | 작업 ID와 인메모리 상태 저장소 |
| `server_logging.py` | 콘솔 로그와 회전 파일 로그 설정 |
| `local_model_manager.py` | 요청별 `local_model`에 맞춰 단일 추론 실행기 슬롯을 전환·재사용 |
| `local_model_api.py` | `GET /models`, `POST /models/{model_id}/download` 라우트 |
| `claude_api.py` | `POST /claude/messages` 프록시 라우트 |
| `model_load_metrics.py` | 모델 로드 계측 데코레이터(`measure_model_load`, `collect_job_loads`) |

## 서버 조립

`server.py`는 서버 시작 시 다음 객체를 한 번 생성합니다.

```text
SummaryService
    +-- LLMService (LLM_BACKEND로 로컬/Claude 선택)
    `-- VLMService

JobStore
InferenceJobRunner (기본 실행기)
LocalModelManager(기본 실행기)
ThreadPoolExecutor(max_workers=1)
```

`ThreadPoolExecutor`의 worker를 하나로 유지하여 LLM과 VLM 작업이 동시에 GPU를 점유하지 않도록 합니다. `SummaryService` 내부에서도 두 서비스가 하나의 lock을 공유하므로 직접 서비스 메서드를 호출하는 경우에도 추론은 직렬화됩니다.

`app.include_router(claude_router)`와 `app.include_router(model_router)`로 `claude_api.py`, `local_model_api.py`의 라우트를 등록합니다. 세 라우트(`/llm/summarize`, `/vlm/summarize`, `/llm/final-summary`)는 이제 `job_executor.submit(job_runner.run_*, ...)` 대신 `job_executor.submit(model_manager.run, local_model, "run_*", ...)`로 제출되어, 요청의 `local_model` 값에 따라 실제로 어떤 실행기가 쓰일지 결정됩니다.

## 로컬 모델 전환 (LocalModelManager)

`LocalModelManager`는 기본 `InferenceJobRunner` 하나만 감싸는 게 아니라, 마지막으로 사용된 로컬 모델에 맞는 `InferenceJobRunner`를 하나 더 캐시합니다.

```text
run(model_id, method, job_id, *args)
  model_id is None
    -> 캐시된 로컬 모델 실행기가 있으면 GPU 메모리 해제 후 기본 실행기로 복귀
    -> 기본 실행기로 method 호출
  model_id == 캐시된 모델
    -> 캐시된 실행기 재사용 (재로딩 없음)
  model_id != 캐시된 모델
    -> 다운로드 여부 재확인 (configs/local_models.require_downloaded)
    -> 기존 실행기의 LLM/VLM GPU 메모리 해제
    -> model_id에 맞는 로더로 새 SummaryService/InferenceJobRunner 생성
       (legacy-qwen은 LLMLoader/VLMLoader, 그 외는 MultimodalLoader 또는 MiniCPMLoader)
    -> 새 실행기를 캐시하고 method 호출
```

전환 실패(다운로드 안 됨, 모델 로딩 오류 등)는 모두 잡아 작업을 `failed` 상태로 기록합니다. `run()`은 `job_executor`가 실행하는 단일 스레드 안에서만 호출되므로, 모델 전환 도중 다른 요청이 같은 GPU를 동시에 건드리지 않습니다. `legacy-qwen`이 아닌 로컬 모델은 `keep_llm_loaded=True`/`keep_vlm_loaded=True`로 실행되어, 같은 모델을 쓰는 다음 작업에서 재로딩 없이 재사용됩니다(모델을 바꿀 때만 명시적으로 해제).

## 로컬 모델 카탈로그 (local_model_api.py)

`configs/local_models.py`에 정의된 고정 모델 목록(`PROFILES`)을 조회·다운로드하는 라우트입니다.

- `GET /models`: 각 모델의 `profile_status()`(준비 상태, precision, runtime, commit revision, 체크포인트별 파일 검증 결과)와 현재 다운로드 진행 상태(`download`)를 함께 반환합니다.
- `POST /models/{model_id}/download`: 존재하지 않는 `model_id`면 `422`. 이미 큐에 있거나 다운로드 중이면 새로 시작하지 않고 현재 상태를 반환합니다. 그 외에는 별도의 단일 워커 `ThreadPoolExecutor`(추론 큐와는 별개)에 `download_profile()`을 제출하고 `202`로 접수만 응답합니다. 실제 다운로드 완료 여부는 다시 `GET /models`로 폴링해서 확인해야 합니다.

`server.py`의 `validate_local_model()`은 `/llm/summarize`, `/vlm/summarize`, `/llm/final-summary` 요청에 `local_model`이 있으면 `configs.local_models.require_downloaded()`로 다운로드 완료 여부를 먼저 검사하고, 준비되지 않았으면 작업을 큐에 넣지 않고 바로 `422`를 반환합니다.

## 모델 로딩 계측

`model_load_metrics.py`는 두 개의 데코레이터로 작업별 모델 로딩 이벤트를 `JobStore`에 연결합니다.

- `@collect_job_loads`: `InferenceJobRunner.run_summary`/`run_vlm`/`run_final`에 적용되어, 실행 동안 `ContextVar`에 "현재 job_id에 이벤트를 기록하는 콜백"을 심어 둡니다.
- `@measure_model_load(kind, companion)`: `LLMLoader.load()`, `VLMLoader.load()`, `MultimodalLoader.load_text()`/`load_vision()`에 적용되어, 호출 전후로 시간을 재고 `{kind, model, started_at, status, duration_seconds}` 이벤트를 만들어 `ContextVar`의 콜백으로 전달합니다. `status`는 이미 로드되어 있으면 `reused`(소요 시간 0초), 새로 로드했으면 `loaded`, 예외가 나면 `failed`입니다. GPU 로더는 `load()` 안에서 `torch.cuda.synchronize()`까지 기다린 뒤 측정을 마칩니다.

기록된 이벤트는 `JobStore.record_model_load()`가 작업의 `model_loads` 리스트에 쌓고, `JobStatusResponse.model_loads`로 응답에 노출됩니다. 실패한 작업이라도 그 시점까지의 로딩 이벤트는 남습니다. `ClaudeLLMLoader`(원격 API)는 이 데코레이터를 쓰지 않으므로 계측되지 않습니다.

## Claude API 프록시 (claude_api.py)

`POST /claude/messages`는 클라이언트가 Anthropic API 키를 직접 다루지 않도록 서버가 대신 호출해 주는 프록시입니다.

- 요청 스키마(`ClaudeRequest`)는 `model`(`claude-`로 시작), `max_tokens`(1~8192), `system`, `messages`(정확히 1개), `tools`(정확히 1개), `tool_choice`만 허용하고 `extra="forbid"`로 그 외 필드는 거부합니다.
- API 키는 요청 시점에 서버 환경변수 `ANTHROPIC_API_KEY`에서만 읽으며, 클라이언트가 보낸 값은 사용하지 않습니다. 키가 없으면 `503`입니다.
- Anthropic 응답이 실패하면 상태 코드만 `400/401/403/429`는 그대로, 그 외는 `502`로 변환해 돌려주고 원본 오류 본문은 그대로 노출하거나 로그에 남기지 않습니다(요청 데이터가 섞여 있을 수 있음).
- 성공 응답에서 `content`, `stop_reason`, `usage`만 추려 반환합니다.
- `LLM_BACKEND` 설정과 무관하게 항상 활성화되어 있으며, `GET /health`의 `claude_api_proxy`/`claude_api_configured`로 지원·설정 여부만 확인할 수 있습니다.

## HTTP 처리 흐름

### LLM

```text
POST /llm/summarize
  -> SummaryRequest 검증
  -> JobStore에 queued 작업 생성
  -> InferenceJobRunner.run_summary 제출
  -> STT 요약
  -> 중요 구간 추출
  -> completed 또는 failed 상태 저장
```

### VLM

```text
POST /vlm/summarize
  -> OCR JSON 크기 및 형식 검증
  -> JPG 파일명, 개수, 크기 검증
  -> OCR image_path와 업로드 파일명 매칭
  -> JobStore에 queued 작업 생성
  -> InferenceJobRunner.run_vlm 제출
  -> 프레임별 분석
  -> completed 또는 failed 상태 저장
```

### 최종 요약

```text
POST /llm/final-summary
  -> STT/VLM 요약 파일 검증
  -> JobStore에 queued 작업 생성
  -> InferenceJobRunner.run_final 제출
  -> SummaryService.summarize_final_note()
  -> JSON 읽기 실패 시도는 warning, 최종 format(json/markdown_fallback)은 info 로그
  -> FinalSummaryResponse(final_summary, lecture_note) 저장
```

`FinalSummaryResponse`의 `final_summary`는 마크다운 최종 요약이고, `lecture_note`는 강의 노트 JSON입니다. 모델 출력을 JSON으로 읽지 못해 마크다운 프롬프트로 대체한 경우 `lecture_note`는 `None`입니다. 강의 노트 구조와 대체 규칙은 [`services/README.md`](../services/README.md#최종-요약)를 참고하세요.

## 요약 레벨(summary_level)

`server.py`의 세 라우트(`/llm/summarize`, `/vlm/summarize`, `/llm/final-summary`)는 더 이상 `max_new_tokens`를 직접 입력받지 않습니다. 대신 `summary_level`(`simple`/`standard`/`detailed`) 값을 `configs/inference_config.py`의 `get_summary_level_preset()`으로 조회해 단계별 `max_new_tokens`와 청크 크기를 한 번에 결정합니다. `simple` 프리셋은 `extract_important_segments=False`이므로 `run_summary`가 중요 구간 추출 단계 자체를 건너뜁니다.

## 작업 상태

작업 상태는 다음 순서로 변경됩니다.

```text
queued -> running -> completed
                  `-> failed
```

`JobStore`는 프로세스 메모리에만 상태를 보관합니다. 서버가 재시작되면 기존 작업과 결과가 사라집니다. 여러 Uvicorn worker를 사용하면 worker마다 별도 저장소가 생기므로 운영 환경에서는 `--workers 1`을 사용해야 합니다.

`failed` 상태의 `message`는 실패 원인이 `ValueError`(입력 검증 실패, GPU 메모리 부족 등 사용자가 조치 가능한 오류)이면 해당 오류 메시지를 그대로 노출하고, 그 외 예외는 일반 실패 메시지로 감춥니다. `error` 필드에는 항상 원본 예외 메시지가 들어갑니다.

작업 상태 응답의 `model_loads`에는 그 작업 동안 실제로 발생한 모델 로딩/재사용/실패 이벤트가 쌓입니다(자세한 내용은 [모델 로딩 계측](#모델-로딩-계측) 참고).

작업 ID 형식:

```text
stt-summary-<12자리 식별자>
vlm-summary-<12자리 식별자>
```

## VLM 업로드 제한

파일 크기와 확장자는 `scripts/vlm_upload.py`, 프레임 개수는 `configs/inference_config.py`의 `VLM_INFERENCE_CONFIG.max_frame_count`가 제한합니다.

| 항목 | 제한 |
| --- | --- |
| OCR JSON | 10MB |
| 프레임 한 장 | 20MB |
| 요청당 프레임 | 8장 |
| 이미지 확장자 | `.jpg`, `.jpeg` |

OCR 결과에 `image_path`가 있으면 경로의 파일명과 업로드된 파일명을 대소문자 구분 없이 매칭합니다. `image_path`가 없으면 OCR 항목 수와 프레임 수가 같을 때만 입력 순서를 사용합니다.

## 모델 유지 설정

`InferenceJobRunner`는 성공과 실패 모두 `finally`에서 모델 해제를 시도합니다.

- `KEEP_LLM_LOADED=1`: LLM 유지
- `KEEP_VLM_LOADED=1`: VLM 유지

기본값은 모두 해제입니다. 유지 설정은 다음 요청의 로딩 시간을 줄이지만 GPU 메모리를 계속 점유합니다.

## 로깅

`server_logging.py`는 같은 로그를 콘솔과 `logs/server.log`에 기록합니다.

- 로그 파일 최대 크기: 10MB
- 백업 파일: 최대 5개
- 긴 추론 단계: 10초마다 경과 시간 기록
- `NO_COLOR` 설정 시 콘솔 컬러 비활성화

## 라우트 추가 원칙

새 API를 추가할 때는 다음 순서를 권장합니다.

1. `api_models.py`에 요청과 응답 모델 정의
2. `server.py`에서 HTTP 입력 검증 및 작업 접수
3. 오래 걸리는 처리는 `InferenceJobRunner`에 구현
4. 모델별 비즈니스 로직은 `services/`에 구현
5. 실제 모델 초기화와 추론은 `models/`에 구현

라우트에서 GPU 추론을 직접 실행하면 HTTP 요청이 장시간 블로킹되므로 작업 실행기를 통해 처리해야 합니다.
