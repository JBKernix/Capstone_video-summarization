# STT Pipeline

## 개요

`modules/stt`는 추출된 오디오 파일을 Whisper로 음성 인식하고, 프로젝트에서 사용하기 쉬운 JSON/TXT 결과로 저장한다.

기본 입력은 전처리 단계가 만든 `runs/audio/audio.wav`다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `scripts/run_stt.py` | STT 단독 실행 스크립트 |
| `modules/stt/whisper_stt.py` | Whisper 모델 로딩과 STT 실행 |
| `modules/stt/stt_formatter.py` | Whisper 원본 결과를 공통 STT 형식으로 변환하고 저장 |
| `modules/stt/stt.py` | STT 관련 함수 re-export |
| `configs/stt_config.yaml` | STT 기본 설정 |

## 실행 흐름

```text
run_stt.py 또는 run_pipeline.py
  -> STT 설정 로드
  -> run_whisper_stt()
  -> format_stt_result()
  -> save_stt_json()
  -> save_stt_text()
```

## 설정

기본 설정 파일:

```text
configs/stt_config.yaml
```

현재 값:

```yaml
model_size: small
language: ko
device:
temperature: 0.0
beam_size:
```

코드의 fallback 기본값은 `modules/stt/whisper_stt.py`의 상수로 관리한다. 기본 설정 파일에 값이 있으면 설정 파일 값이 우선한다.

| 상수 | fallback 값 |
| --- | --- |
| `DEFAULT_STT_MODEL_SIZE` | `medium` |
| `DEFAULT_STT_LANGUAGE` | `ko` |
| `DEFAULT_STT_DEVICE` | `None` |
| `DEFAULT_STT_TEMPERATURE` | `0.0` |
| `DEFAULT_STT_BEAM_SIZE` | `None` |

| 설정 | 설명 |
| --- | --- |
| `model_size` | Whisper 모델 크기 |
| `language` | 인식 언어 코드 |
| `device` | 실행 장치. 비어 있으면 Whisper 기본값 사용 |
| `temperature` | 디코딩 temperature. `0.0`이면 fallback 재시도를 사용하지 않음 |
| `beam_size` | beam search 크기. 비어 있으면 greedy decoding 사용 |

## `whisper_stt.py`

### `_load_whisper_module()`

Whisper 패키지를 지연 import한다.

```python
import whisper
```

Whisper가 설치되어 있지 않으면 설치 안내가 포함된 `ImportError`를 발생시킨다.

### `_load_model()`

Whisper 모델을 로드하고 `lru_cache`로 캐시한다.

```python
@lru_cache(maxsize=4)
def _load_model(model_size, device):
    return whisper.load_model(model_size, device=device)
```

같은 `model_size`, `device` 조합이면 같은 프로세스 안에서 모델을 재사용한다.

### `run_whisper_stt()`

오디오 전체를 한 번에 transcribe한다.

처리 순서:

1. 오디오 경로 검증
2. Whisper 모델 로드
3. transcribe 옵션 정리
4. `model.transcribe()` 호출
5. Whisper 원본 결과 반환

## `stt_formatter.py`

Whisper 결과를 프로젝트 공통 형식으로 변환한다.

예상 JSON 구조:

```json
{
  "audio_path": "runs/audio/audio.wav",
  "language": "ko",
  "model_size": "small",
  "segment_count": 10,
  "segments": [
    {
      "start": 0.0,
      "end": 3.5,
      "text": "인식된 문장"
    }
  ],
  "text": "전체 인식 텍스트"
}
```

저장 함수:

| 함수 | 역할 |
| --- | --- |
| `save_stt_json()` | STT 결과를 JSON 파일로 저장 |
| `save_stt_text()` | STT 텍스트를 TXT 파일로 저장 |

## 출력

전체 파이프라인 기본 출력:

```text
runs/stt/stt_result.json
runs/stt/stt_result.txt
```

## 예외

| 상황 | 예외 |
| --- | --- |
| 오디오 파일이 없음 | `FileNotFoundError` |
| 오디오 경로가 파일이 아님 | `ValueError` |
| Whisper 미설치 | `ImportError` |

## 주의 사항

1. Whisper는 내부적으로 PyTorch를 사용한다.
2. GPU 사용 여부는 `device` 설정과 PyTorch CUDA 상태에 따라 달라진다.
3. 긴 오디오는 Whisper의 내부 30초 처리 로직에 맡긴다.
4. 첫 실행 시 Whisper 모델 파일 다운로드가 필요할 수 있다.
