# LLM/VLM 요약 클라이언트

`modules/llm`은 로컬 모델을 직접 실행하지 않고 외부 GPU 서버 API를 호출해 STT 요약, 프레임 VLM 요약, 최종 통합 요약을 생성합니다. 세 클라이언트(`GPULLMClient`, `GPUVLMClient`, `GPUFinalSummaryClient`)는 공통 로직을 `GPUJobClientMixin`으로 공유합니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/llm/__init__.py` | `GPU_SERVER_URL` 기본값 |
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
GPU_SERVER_URL = "http://10.10.4.27:8000"
```

세 클라이언트는 기본 timeout, poll interval, job timeout 값을 사용합니다.

| 설정 | 기본값 |
| --- | --- |
| `timeout` | `600`초 |
| `poll_interval` | `10`초 |
| `job_timeout` | `3600`초 |

## STT 요약

클라이언트: `GPULLMClient` (`GPUJobClientMixin` 상속, `job_label = "LLM"`, `progress_step = STEP_STT_SUMMARY`)

공개 메서드:

| 메서드 | 반환 |
| --- | --- |
| `summarize_stt_file(stt_json_path=None)` | 요약 문자열 |
| `summarize_stt_file_result(stt_json_path=None)` | `summary`/`important_segments`를 포함한 dict |

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

텍스트가 있는 경우에만 서버에 요청을 보냅니다. 서버 응답에는 `summary`가 반드시 있어야 하며, `important_segments`는 문자열 JSON이어도 파싱을 시도합니다.

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
- `max_new_tokens`는 1에서 384 사이여야 합니다.
- 배치마다 시작/완료 시점에 `report_progress()`로 진행률을 보고합니다. 메시지는 `"VLM 배치 처리 중 (N/M)"` / `"VLM 배치 처리 완료 (N/M)"` 형태이며, 배치 수 기준 퍼센트(`(batch_index - 1) / total_batches * 100`, `batch_index / total_batches * 100`)도 함께 전달됩니다.

## 최종 요약

클라이언트: `GPUFinalSummaryClient` (`GPUJobClientMixin` 상속, `job_label = "Final summary"`, `progress_step = STEP_FINAL_SUMMARY`)

엔드포인트:

```text
POST /llm/final-summary
```

입력:

```text
runs/llm/stt_summary.txt
runs/llm/stt_summary_result.json
runs/vlm/vlm_summary.txt
runs/vlm/vlm_summary_result.json
```

출력:

```text
runs/final/final_summary.txt
runs/final/final_summary_result.json
```

최종 요약 클라이언트는 입력 텍스트 파일이 비어 있지 않은지, JSON 파일(`modules.common.load_json()`로 읽음)이 객체인지 먼저 검증합니다.

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
python scripts/run_llm_summary.py --stt-json runs/stt/stt_result.json
python scripts/run_vlm_summary.py --ocr-json runs/ocr/ocr_result.json --max-new-tokens 384
python scripts/run_final_summary.py
```

## 주의 사항

- 전체 파이프라인은 최종 통합 요약까지 자동 실행합니다. 최종 요약만 다시 생성할 때는 `run_final_summary.py`를 별도로 실행합니다.
- GPU 서버 응답 형식이 예상과 다르면 `ValueError`가 발생합니다.
- VLM 단계는 OCR JSON의 프레임 파일 경로가 실제로 존재해야 합니다.
- 무음 영상은 오류가 아니라 `no_speech: true`가 포함된 정상 결과로 처리되므로, 후속 단계(최종 요약 등)에서 이 플래그를 확인해야 합니다.
