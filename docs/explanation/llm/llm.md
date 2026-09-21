# LLM/VLM 요약 클라이언트

`modules/llm`은 로컬 모델을 직접 실행하지 않고 외부 GPU 서버 API를 호출해 STT 요약, 프레임 VLM 요약, 최종 통합 요약을 생성합니다. 세 클라이언트(`GPULLMClient`, `GPUVLMClient`, `GPUFinalSummaryClient`)는 공통 로직을 `GPUJobClientMixin`으로 공유합니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/llm/__init__.py` | `GPU_SERVER_URL` 기본값 |
| `modules/llm/summary_levels.py` | 요약 크기/속도 프리셋 상수(`SUMMARY_LEVELS`, `DEFAULT_SUMMARY_LEVEL`) 및 UI 라벨/설명 |
| `modules/llm/gpu_job_client.py` | `GPUJobClientMixin` - HTTP 에러 처리 및 비동기 job 폴링 공통 로직 |
| `modules/llm/stt_summarizer_client.py` | STT 결과 요약 및 주요 구간 추출 |
| `modules/llm/vlm_summarizer_client.py` | OCR 결과와 프레임 이미지를 VLM 서버로 전송 |
| `modules/llm/final_summarizer_client.py` | STT/VLM 요약 파일을 결합해 최종 요약 요청 |
| `scripts/run_llm_summary.py` | STT 요약 단독 실행 |
| `scripts/run_vlm_summary.py` | VLM 요약 단독 실행 |
| `scripts/run_final_summary.py` | 최종 요약 단독 실행 |

## 서버 설정

기본 서버 주소:

```python
GPU_SERVER_URL = "http://100.124.136.28:8000"
```

세 클라이언트는 기본 timeout, poll interval, job timeout 값을 사용합니다.

| 설정 | 기본값 |
| --- | --- |
| `timeout` | `600`초 |
| `poll_interval` | `10`초 |
| `job_timeout` | `3600`초 |

## 요약 레벨 (`modules/llm/summary_levels.py`)

세 요청(`/llm/summarize`, `/vlm/summarize`, `/llm/final-summary`) 모두 `summary_level` 값을 폼 데이터로 함께 보냅니다.

| 값 | 라벨 | 설명 |
| --- | --- | --- |
| `simple` | 간단요약 | 핵심만 간략히, 속도 빠름 |
| `standard` (기본값) | 기본요약 | 균형 잡힌 요약 |
| `detailed` | 상세요약 | 자세히 요약, 속도 느림 |

> `SUMMARY_LEVELS`의 값은 GPU 서버(`gpu-server` 브랜치)의 `configs/inference_config.py::SUMMARY_LEVEL_PRESETS` 키와 반드시 동일해야 합니다. 실제 토큰 수/속도는 서버가 프리셋에 따라 결정하며, 클라이언트는 값만 전달합니다.
>
> `simple`은 `standard`/`detailed`와 달리 영상(VLM) 분석 자체를 생략합니다. `scripts/run_pipeline.py`가 `simple`일 때 프레임 추출/OCR/VLM 단계를 아예 건너뛰고 STT 요약만 최종 요약으로 사용하기 때문입니다(아래 "최종 요약" 및 `pipeline.md` 참고). `SUMMARY_LEVEL_CAPTIONS`(업로드 페이지 안내 문구)도 이를 반영해 "영상 분석 생략"을 명시합니다.

## STT 요약

클라이언트: `GPULLMClient` (`GPUJobClientMixin` 상속, `job_label = "LLM"`, `progress_step = STEP_STT_SUMMARY`)

공개 메서드:

| 메서드 | 반환 |
| --- | --- |
| `summarize_stt_file(stt_json_path=None, summary_level=DEFAULT_SUMMARY_LEVEL)` | 요약 문자열 |
| `summarize_stt_file_result(stt_json_path=None, summary_level=DEFAULT_SUMMARY_LEVEL)` | `summary`/`important_segments`를 포함한 dict |

엔드포인트:

```text
POST /llm/summarize
```

입력:

```text
runs/stt/stt_result.json
```

출력:

```text
runs/llm/stt_summary.txt
runs/llm/stt_summary_result.json
```

`stt_result.json`을 `modules.common.load_json()`으로 읽어 `segments`에서 `full_text`를 만듭니다. **무음 영상(음성 텍스트가 비어 있는 경우)은 예외가 아니라 정상 케이스**로 취급하여 GPU 서버를 호출하지 않고 다음 결과를 즉시 반환합니다.

```json
{
  "summary": "음성이 감지되지 않았습니다.",
  "important_segments": [],
  "no_speech": true
}
```

텍스트가 있는 경우에만 서버에 요청을 보냅니다(요청 payload에 `summary_level`도 함께 포함). 서버 응답에는 `summary`가 반드시 있어야 하며, `important_segments`는 문자열 JSON이어도 파싱을 시도합니다.

## VLM 프레임 요약

클라이언트: `GPUVLMClient` (`GPUJobClientMixin` 상속, `job_label = "VLM"`, `progress_step = STEP_VLM_SUMMARY`)

엔드포인트:

```text
POST /vlm/summarize
```

입력:

```text
runs/ocr/ocr_result.json
runs/frames/*.jpg
```

출력:

```text
runs/vlm/vlm_summary.txt
runs/vlm/vlm_summary_result.json
```

특징:

- OCR JSON은 `modules.common.load_json()`으로 읽고, `image_path`로 실제 프레임 파일을 찾습니다.
- 프레임은 JPG/JPEG만 허용합니다.
- 한 번에 최대 8개 프레임씩(`MAX_FRAME_COUNT`) 서버에 전송합니다.
- `summarize_ocr_file(ocr_json_path=None, summary_level=DEFAULT_SUMMARY_LEVEL)`은 `summary_level`이 `SUMMARY_LEVELS`(`simple`/`standard`/`detailed`)에 없으면 `ValueError`를 발생시킵니다. 과거에는 프레임당 최대 생성 토큰 수(`max_new_tokens`, 1~384)를 직접 지정했지만, 요약 레벨 프리셋으로 대체되었습니다.
- 배치마다 시작/완료 시점에 `report_progress()`로 진행률을 보고합니다. 메시지는 `"VLM 배치 처리 중 (N/M)"` / `"VLM 배치 처리 완료 (N/M)"` 형태이며, 배치 수 기준 퍼센트(`(batch_index - 1) / total_batches * 100`, `batch_index / total_batches * 100`)도 함께 전달됩니다.

## 최종 요약

클라이언트: `GPUFinalSummaryClient` (`GPUJobClientMixin` 상속, `job_label = "Final summary"`, `progress_step = STEP_FINAL_SUMMARY`)

엔드포인트:

```text
POST /llm/final-summary
```

입력:

```text
runs/llm/stt_summary_result.json
runs/vlm/vlm_summary_result.json
```

출력:

```text
runs/final/final_summary.txt
runs/final/final_summary_result.json
```

최종 요약 클라이언트는 STT/VLM 요약 JSON(`modules.common.load_json()`로 읽음) 안의 `summary`(STT)/`results`(VLM)가 비어 있지 않은지 먼저 검증합니다. 과거에는 `stt_summary.txt`/`vlm_summary.txt`도 함께 전송했지만, 두 텍스트 파일 내용이 각 JSON 안에 이미 들어있는 중복 데이터였기 때문에 JSON 2개만 보내도록 변경했습니다. `summarize_files_result(stt_summary_json_path, vlm_summary_json_path, summary_level=DEFAULT_SUMMARY_LEVEL)`은 `summary_level`도 폼 데이터로 함께 전송합니다.

### VLM 요약이 없을 때 (`write_stt_only_final_summary_step`)

`scripts/run_final_summary.py`에는 서버를 호출하지 않는 `write_stt_only_final_summary_step(stt_summary_json_path, output_path, output_json_path=None)`도 있습니다. `scripts/run_pipeline.py`는 VLM 요약이 없으면(`--summary-level simple`이라 VLM 단계를 건너뛰었거나 `--skip-vlm`을 지정한 경우) 이 함수로 최종 통합 요약 API 호출 없이 STT 요약을 그대로 최종 요약으로 사용합니다. 이 경우 결과 JSON은 일반 경로와 필드 구성이 다릅니다.

```json
{
  "source": {
    "stt_summary_json_path": "runs/llm/stt_summary_result.json",
    "vlm_summary_json_path": null,
    "mode": "stt_only"
  },
  "summary": "STT 기반 요약 텍스트"
}
```

`final_summary` 키가 없고 `source.mode`가 `"stt_only"`라는 점이 일반 경로(`run_final_summary_step`, 아래 데이터 형식 참고)와 다릅니다. STT 요약 자체가 비어 있으면(`summary` 필드가 빈 문자열) `ValueError`가 발생합니다.

## 비동기 job 응답

서버가 바로 결과를 주지 않고 다음 형태를 반환할 수 있습니다.

```json
{
  "job_id": "abc",
  "status_url": "/jobs/abc"
}
```

세 클라이언트 모두 이 판별과 폴링을 직접 구현하지 않고 `GPUJobClientMixin`이 공통 처리합니다.

- `job_id is None or not status_url`이면 예상치 못한 응답으로 보고 `ValueError`를 발생시킵니다 (falsy 체크가 아니라 `is None` 체크이므로 `job_id`가 `0`이어도 유효한 값으로 인정됩니다).
- 그 외에는 `_wait_for_job(status_url)`을 호출해 `status_url`을 `poll_interval`마다 조회합니다. `status_url`이 절대 URL이 아니면 `config.server_url`을 붙여 요청합니다.
- 상태 메시지가 바뀔 때마다 콘솔에 `"{job_label} job status: {status} - {message}"`를 출력하고, `progress_step`이 설정된 클라이언트는 `report_progress(progress_step, f"{job_label} 처리 중: {message}")`로도 보고합니다 (비동기 작업이라 전체 진행률(퍼센트)은 알 수 없으므로 퍼센트 없이 메시지만 보고합니다).
- HTTP 에러는 `_raise_for_status()`가 처리하며, 에러 발생 시 응답 본문을 포함해 `requests.HTTPError`를 다시 발생시킵니다.

| 상태 | 동작 |
| --- | --- |
| `completed` | `result`를 읽고 반환 |
| `failed` | `RuntimeError` |
| timeout 초과 (`job_timeout`) | `TimeoutError` |

## CLI

```bash
python scripts/run_llm_summary.py --stt-json runs/stt/stt_result.json --summary-level standard
python scripts/run_vlm_summary.py --ocr-json runs/ocr/ocr_result.json --summary-level standard
python scripts/run_final_summary.py --summary-level standard
```

## 주의 사항

- 전체 파이프라인은 최종 통합 요약까지 자동 실행합니다. 최종 요약만 다시 생성할 때는 `run_final_summary.py`를 별도로 실행합니다.
- GPU 서버 응답 형식이 예상과 다르면 `ValueError`가 발생합니다.
- VLM 단계는 OCR JSON의 프레임 파일 경로가 실제로 존재해야 합니다.
- 무음 영상은 오류가 아니라 `no_speech: true`가 포함된 정상 결과로 처리되므로, 후속 단계(최종 요약 등)에서 이 플래그를 확인해야 합니다.
- `--summary-level`(`simple`/`standard`/`detailed`, 기본값 `standard`)은 세 스크립트와 `run_pipeline.py`가 모두 지원하며, 클라이언트 쪽 값은 GPU 서버의 프리셋 키와 반드시 일치해야 합니다.
