# STT Pipeline

이 문서는 `modules/stt` 모듈과 `scripts/run_stt.py`가 오디오 파일에서 음성 인식 결과를 생성하는 흐름을 설명한다. 현재 STT 파이프라인은 Whisper를 사용해 오디오를 텍스트로 변환하고, 프로젝트에서 사용하기 쉬운 JSON/TXT 형식으로 결과를 저장한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `scripts/run_stt.py` | STT 파이프라인 실행 진입점 |
| `modules/stt/whisper_stt.py` | Whisper 모델 로드와 STT 실행 |
| `modules/stt/stt_formatter.py` | Whisper 원본 결과를 프로젝트 공통 STT 형식으로 변환하고 저장 |
| `modules/stt/stt.py` | STT 관련 함수를 다시 export하는 호환 모듈 |
| `configs/stt_config.yaml` | STT 모델, 언어, chunk 설정 |
| `runs/audio/audio.wav` | STT 입력 오디오 기본 경로 |
| `runs/stt/` | STT 결과 JSON/TXT 저장 위치 |

## 전체 실행 흐름

```text
scripts/run_stt.py
    -> load_config()
    -> 명령줄 인자와 stt_config.yaml 병합
    -> chunked 설정 확인
        -> run_chunked_whisper_stt()
            -> Whisper 모델 로드
            -> 오디오 로드
            -> chunk 단위 transcribe()
            -> chunk별 원본 결과 반환
            -> format_chunked_stt_result()
        또는
        -> run_whisper_stt()
            -> Whisper 모델 로드
            -> 전체 오디오 transcribe()
            -> format_stt_result()
    -> save_stt_json()
    -> save_stt_text()
```

## 1. `scripts/run_stt.py`

`run_stt.py`는 오디오 파일을 입력으로 받아 STT 결과를 생성하는 스크립트다.

기본 입력과 출력 경로는 다음과 같다.

```python
audio = PROJECT_ROOT / "runs" / "audio" / "audio.wav"
output_json = PROJECT_ROOT / "runs" / "stt" / "stt_result.json"
output_text = PROJECT_ROOT / "runs" / "stt" / "stt_result.txt"
config = PROJECT_ROOT / "configs" / "stt_config.yaml"
```

명령줄 인자를 지정하지 않으면 `configs/stt_config.yaml` 값을 사용한다.

```yaml
model_size: small
language: ko
device:
chunked: true
chunk_seconds: 30
overlap_seconds: 2
```

| 설정 | 의미 |
| --- | --- |
| `model_size` | Whisper 모델 크기 |
| `language` | 음성 인식 언어 코드 |
| `device` | 실행 장치. 비어 있으면 Whisper 기본값 사용 |
| `chunked` | 긴 오디오를 chunk로 나누어 처리할지 여부 |
| `chunk_seconds` | chunk 하나의 길이 |
| `overlap_seconds` | 인접 chunk 사이에 겹치는 길이 |

## 2. `whisper_stt.py`

`whisper_stt.py`는 Whisper 모델 로드와 음성 인식을 담당한다.

### 모델 로드 방식

Whisper 모듈은 함수 호출 시점에 지연 import한다.

```python
def _load_whisper_module():
    import whisper
    return whisper
```

모델은 `lru_cache`로 캐시한다.

```python
@lru_cache(maxsize=4)
def _load_model(model_size: str, device: str | None):
    whisper = _load_whisper_module()
    return whisper.load_model(model_size, device=device)
```

같은 `model_size`, `device` 조합을 반복해서 사용할 때 모델을 다시 로드하지 않기 위한 구조다.

### `run_whisper_stt()`

하나의 오디오 파일 전체를 한 번에 Whisper로 처리한다.

```python
run_whisper_stt(
    audio_path="runs/audio/audio.wav",
    model_size="small",
    language="ko",
    device=None,
)
```

처리 순서는 다음과 같다.

1. 오디오 파일 경로를 검증한다.
2. Whisper 모델을 로드하거나 캐시에서 가져온다.
3. `language`, `verbose=False` 등 transcribe 옵션을 만든다.
4. `model.transcribe()`를 호출한다.
5. Whisper 원본 결과를 반환한다.

### `run_chunked_whisper_stt()`

긴 오디오를 일정 길이로 나누어 STT를 수행한다.

```python
run_chunked_whisper_stt(
    audio_path="runs/audio/audio.wav",
    model_size="small",
    language="ko",
    chunk_seconds=30,
    overlap_seconds=2,
    device=None,
)
```

chunk 처리는 다음 기준을 사용한다.

| 값 | 의미 |
| --- | --- |
| `WHISPER_SAMPLE_RATE` | Whisper 입력 오디오 샘플레이트. 현재 `16000` |
| `chunk_seconds` | 한 chunk 길이 |
| `overlap_seconds` | 다음 chunk와 겹칠 길이 |
| `step_size` | `chunk_size - overlap_size` |

반환 결과는 chunk별 원본 Whisper 결과를 담는다.

```json
{
  "audio_path": "runs/audio/audio.wav",
  "language": "ko",
  "model_size": "small",
  "duration_sec": 120.0,
  "chunk_config": {
    "chunk_seconds": 30,
    "overlap_seconds": 2
  },
  "chunks": [
    {
      "chunk_index": 0,
      "chunk_start": 0.0,
      "chunk_end": 30.0,
      "result": {}
    }
  ]
}
```

## 3. `stt_formatter.py`

`stt_formatter.py`는 Whisper 원본 결과를 프로젝트 공통 STT 형식으로 변환한다.

### `format_stt_result()`

Whisper 전체 오디오 결과를 다음 구조로 변환한다.

```json
{
  "language": "ko",
  "segment_count": 2,
  "segments": [
    {
      "segment_id": 0,
      "start": 0.0,
      "end": 3.2,
      "text": "첫 번째 문장"
    }
  ],
  "full_text": "첫 번째 문장 두 번째 문장"
}
```

비어 있는 텍스트 segment는 결과에서 제외한다.

### `format_chunked_stt_result()`

chunk 단위 결과는 각 segment 시간이 chunk 내부 기준으로 들어온다. 이 함수는 `chunk_start`를 더해 전체 오디오 기준 시간으로 변환한다.

```python
global_start = chunk_start + raw_segment["start"]
global_end = chunk_start + raw_segment["end"]
```

overlap 때문에 같은 문장이 중복될 수 있으므로 `(start, end, text)` 기반 key로 중복을 제거한다.

### 저장 함수

| 함수 | 역할 |
| --- | --- |
| `save_stt_json()` | 구조화된 STT 결과를 JSON으로 저장 |
| `save_stt_text()` | `full_text` 또는 timestamp 포함 텍스트를 TXT로 저장 |

timestamp를 포함하면 TXT는 다음 형식으로 저장된다.

```text
[0.00 - 3.20] 첫 번째 문장
[3.20 - 5.10] 두 번째 문장
```

## 입력 파일 형식

입력은 Whisper가 읽을 수 있는 오디오 파일이다.

```text
runs/audio/audio.wav
```

전처리 단계의 `extract_audio()` 기본 설정을 사용하면 16kHz mono WAV가 생성된다.

## 출력 파일 형식

기본 출력 위치는 다음과 같다.

```text
runs/stt/stt_result.json
runs/stt/stt_result.txt
```

JSON 결과는 후속 요약 단계에서 segment 단위 시간 정보와 전체 텍스트를 함께 사용할 수 있도록 구성되어 있다.

## 실패 처리

오디오 파일이 없으면 `FileNotFoundError`가 발생한다. 오디오 경로가 파일이 아니면 `ValueError`가 발생한다.

Whisper 패키지가 설치되어 있지 않으면 `_load_whisper_module()`에서 `ImportError`가 발생한다.

chunk 설정이 올바르지 않으면 `run_chunked_whisper_stt()`가 `ValueError`를 발생시킨다.

| 조건 | 오류 |
| --- | --- |
| `chunk_seconds <= 0` | chunk 길이는 0보다 커야 함 |
| `overlap_seconds < 0` | overlap은 0 이상이어야 함 |
| `chunk_seconds <= overlap_seconds` | chunk 길이는 overlap보다 커야 함 |

## 현재 한계

1. chunk overlap 중복 제거는 단순한 시간/텍스트 key 기반이다.
2. 긴 오디오에서 문장이 chunk 경계에 걸리면 일부 문맥이 자연스럽지 않을 수 있다.
3. Whisper 모델 로드와 추론 비용이 크므로 GPU/CPU 환경에 따라 실행 시간이 크게 달라진다.
4. PyTorch CUDA/cuDNN DLL은 PaddleOCR와 같은 프로세스에 로드되면 충돌할 수 있으므로 전체 파이프라인에서는 별도 프로세스 실행을 기본으로 사용한다.
