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

## 서버 조립

`server.py`는 서버 시작 시 다음 객체를 한 번 생성합니다.

```text
SummaryService
    +-- LLMService
    `-- VLMService

JobStore
InferenceJobRunner
ThreadPoolExecutor(max_workers=1)
```

`ThreadPoolExecutor`의 worker를 하나로 유지하여 LLM과 VLM 작업이 동시에 GPU를 점유하지 않도록 합니다. `SummaryService` 내부에서도 두 서비스가 하나의 lock을 공유하므로 직접 서비스 메서드를 호출하는 경우에도 추론은 직렬화됩니다.

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

## 작업 상태

작업 상태는 다음 순서로 변경됩니다.

```text
queued -> running -> completed
                  `-> failed
```

`JobStore`는 프로세스 메모리에만 상태를 보관합니다. 서버가 재시작되면 기존 작업과 결과가 사라집니다. 여러 Uvicorn worker를 사용하면 worker마다 별도 저장소가 생기므로 운영 환경에서는 `--workers 1`을 사용해야 합니다.

작업 ID 형식:

```text
stt-summary-<12자리 식별자>
vlm-summary-<12자리 식별자>
```

## VLM 업로드 제한

`scripts/vlm_upload.py`의 기본 제한은 다음과 같습니다.

| 항목 | 제한 |
| --- | --- |
| OCR JSON | 10MB |
| 프레임 한 장 | 20MB |
| 요청당 프레임 | 32장 |
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
