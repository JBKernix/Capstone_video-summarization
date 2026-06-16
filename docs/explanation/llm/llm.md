# LLM/VLM 요약 클라이언트

`modules/llm`은 로컬 모델을 직접 실행하지 않고 외부 GPU 서버 API를 호출해 STT 요약, 프레임 VLM 요약, 최종 통합 요약을 생성합니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/llm/__init__.py` | `GPU_SERVER_URL` 기본값 |
| `modules/llm/stt_summarizer_client.py` | STT 결과 요약 및 주요 구간 추출 |
| `modules/llm/vlm_summarizer_client.py` | OCR 결과와 프레임 이미지를 VLM 서버로 전송 |
| `modules/llm/final_summarizer_client.py` | STT/VLM 요약 파일을 결합해 최종 요약 요청 |
| `scripts/run_llm_summary.py` | STT 요약 단독 실행 |
| `scripts/run_vlm_summary.py` | VLM 요약 단독 실행 |
| `scripts/run_final_summary.py` | 최종 요약 단독 실행 |
| `modules/llm/receive.py` | 비어 있음 |

## 서버 설정

기본 서버 주소:

```python
GPU_SERVER_URL = "http://10.30.2.224:8000"
```

세 클라이언트는 기본 timeout, poll interval, job timeout 값을 사용합니다.

| 설정 | 기본값 |
| --- | --- |
| `timeout` | `600`초 |
| `poll_interval` | `10`초 |
| `job_timeout` | `3600`초 |

## STT 요약

클라이언트: `GPULLMClient`

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

`stt_result.json`의 `segments`를 읽어 `full_text`를 만들고 서버에 전달합니다. 서버 응답에는 `summary`가 반드시 있어야 하며, `important_segments`는 문자열 JSON이어도 파싱을 시도합니다.

## VLM 프레임 요약

클라이언트: `GPUVLMClient`

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

- OCR JSON에서 `image_path`를 읽어 실제 프레임 파일을 찾습니다.
- 프레임은 JPG/JPEG만 허용합니다.
- 한 번에 최대 8개 프레임씩 서버에 전송합니다.
- `max_new_tokens`는 1에서 384 사이여야 합니다.

## 최종 요약

클라이언트: `GPUFinalSummaryClient`

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

최종 요약 클라이언트는 입력 텍스트 파일이 비어 있지 않은지, JSON 파일이 객체인지 먼저 검증합니다.

## 비동기 job 응답

서버가 바로 결과를 주지 않고 다음 형태를 반환할 수 있습니다.

```json
{
  "job_id": "abc",
  "status_url": "/jobs/abc"
}
```

이 경우 클라이언트는 `status_url`을 주기적으로 조회합니다.

| 상태 | 동작 |
| --- | --- |
| `completed` | `result`를 읽고 반환 |
| `failed` | `RuntimeError` |
| timeout 초과 | `TimeoutError` |

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
