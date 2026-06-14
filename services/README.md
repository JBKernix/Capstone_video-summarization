# Services

API 계층과 모델 로더 사이에서 입력 정규화, 프롬프트 구성, 결과 파싱과 다중 단계 추론을 담당합니다.

`scripts/`는 HTTP와 작업 상태를 처리하고, `models/`는 실제 모델 실행만 담당합니다. 서비스 계층은 두 계층이 서로의 세부 구현에 직접 의존하지 않도록 연결합니다.

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `summary_service.py` | LLM/VLM 서비스 조립과 상위 호출 인터페이스 제공 |
| `llm_service.py` | STT 요약, 중요 구간 추출, 결과 파싱 |
| `vlm_service.py` | OCR 정규화, 이미지 매칭, 프레임별 시각 요약 |

## SummaryService

`SummaryService`는 서버가 사용하는 단일 진입점입니다.

```text
SummaryService
  +-- LLMService ----+
  |                  +-- shared generation Lock
  `-- VLMService ----+
```

LLM과 VLM에 같은 `Lock`을 전달하여 두 모델이 동시에 GPU 추론이나 해제를 수행하지 않게 합니다.

주요 메서드:

| 메서드 | 설명 |
| --- | --- |
| `summarize_stt()` | STT 전체 요약 |
| `get_important_segments_in_chunks()` | 긴 STT 구간을 나누어 중요 구간 추출 |
| `summarize_frame()` | 단일 프레임 분석 |
| `summarize_frames()` | OCR 결과와 여러 프레임 분석 |
| `unload_llm()` | LLM GPU 메모리 해제 |
| `unload_vlm()` | VLM GPU 메모리 해제 |

## LLMService

### STT 요약

`summarize_stt()`는 STT 원문을 받아 다음 내용을 요구하는 한국어 프롬프트를 구성합니다.

- 핵심 주제
- 주요 내용
- 전체 요약
- 반복 제거와 명백한 STT 오류 보정
- 원문에 없는 정보 생성 금지

기본 `max_new_tokens`는 `1024`, 최대값은 `2048`입니다.

### 중요 구간 추출

각 세그먼트는 토큰 사용량을 줄이기 위해 다음 행 형식으로 모델에 전달됩니다.

```text
segment_id|start|end|text
```

모델 출력 형식:

```text
segment_id|start|end|topic|reason
```

파서는 정수 `segment_id`, 실수 `start`, `end`를 검증하고 객체 배열로 변환합니다. 형식이 잘못된 행은 건너뛰며, 한 묶음에서 유효한 결과가 하나도 없으면 `ValueError`를 발생시킵니다.

### 세그먼트 분할

`split_segments()`는 세그먼트 내부를 자르지 않고 JSON 직렬화 길이를 기준으로 묶습니다. 기본 묶음 크기는 `12000`자입니다.

```text
전체 segments
  -> 문자 길이 기준 chunk 생성
  -> chunk별 LLM 호출
  -> 출력 파싱
  -> 결과 배열 병합
```

## VLMService

### 지원 이미지 입력

`VLMService`는 다음 입력을 PIL RGB 이미지로 정규화합니다.

- 문자열 파일 경로
- `Path`
- `bytes`, `bytearray`
- binary file object
- PIL `Image`

분석이 끝나면 서비스가 생성한 PIL 이미지를 `finally`에서 닫습니다.

### OCR 입력

`load_ocr_results()`가 지원하는 형식:

- JSON 파일 경로
- JSON 문자열
- 객체 배열
- `frames`, `results`, `ocr_results` 키로 감싼 객체

각 항목에 `frame_id`가 없으면 배열 인덱스를 사용합니다. 중복 `frame_id`는 허용하지 않습니다.

권장 OCR 항목:

```json
{
  "frame_id": 0,
  "timestamp": 12.5,
  "image_path": "frame_000001.jpg",
  "ocr_text": "화면에서 인식된 텍스트",
  "detected_language": "ko",
  "scene_type": "slide"
}
```

### 프레임 매칭

`summarize_frames()`의 `frames`가 sequence이면 OCR 항목과 이미지의 순서 및 개수가 같아야 합니다.

mapping이면 다음 키를 순서대로 확인합니다.

1. `frame_id`
2. 문자열로 변환한 `frame_id`
3. OCR의 전체 `image_path`
4. `image_path`의 파일명

매칭되지 않은 프레임이 있으면 추론을 시작하지 않고 오류를 반환합니다.

### VLM 결과

원래 OCR 항목을 유지하고 `vlm_summary`를 추가합니다.

```json
{
  "frame_id": 0,
  "timestamp": 12.5,
  "ocr_text": "...",
  "vlm_summary": "## 프레임 시각 요약\n..."
}
```

진행 콜백을 전달하면 프레임마다 다음 형태로 호출합니다.

```python
progress_callback("vlm_frames", current_index, total_frames)
```

## 동시성과 모델 해제

모든 모델 생성과 `unload()`는 공유 lock 내부에서 실행됩니다. 서비스 메서드에서 별도 스레드를 만들지 않으며, 비동기 작업 관리는 `scripts/inference_jobs.py`가 담당합니다.

```text
작업 실행기
  -> 서비스 메서드 호출
  -> shared lock 획득
  -> loader 추론
  -> shared lock 해제
  -> 작업 종료 시 unload
```

## 기능 확장 원칙

- 프롬프트와 출력 형식 변경: 해당 서비스에서 수정
- 모델 클래스나 전처리 변경: `models/`에서 수정
- HTTP 필드와 상태 응답 변경: `scripts/`에서 수정
- 새 모델이 기존 GPU를 공유한다면 `SummaryService`의 공용 lock 사용
- 긴 입력은 한 번에 모델에 전달하기보다 기존 chunk 패턴 사용
- 모델 출력은 가능한 한 명시적인 형식으로 제한하고 파서를 함께 작성
