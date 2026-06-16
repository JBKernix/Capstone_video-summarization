# STT 파이프라인

`modules/stt`는 추출된 오디오를 Whisper로 인식하고 프로젝트 공통 JSON/TXT 형식으로 저장합니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `scripts/run_stt.py` | STT 단독 실행 |
| `modules/stt/whisper_stt.py` | Whisper 모델 로딩과 transcribe 실행 |
| `modules/stt/stt_formatter.py` | Whisper 결과 포맷팅과 저장 |
| `modules/stt/__init__.py` | STT public API export |
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

현재 설정 파일:

```yaml
model_size: small
language: ko
device:
temperature: 0.0
beam_size:
```

코드 fallback 기본값:

| 상수 | 값 |
| --- | --- |
| `DEFAULT_STT_MODEL_SIZE` | `medium` |
| `DEFAULT_STT_LANGUAGE` | `ko` |
| `DEFAULT_STT_DEVICE` | `None` |
| `DEFAULT_STT_TEMPERATURE` | `0.0` |
| `DEFAULT_STT_BEAM_SIZE` | `None` |

실행 옵션이 있으면 실행 옵션이 가장 우선이고, 그다음 설정 파일, 마지막으로 코드 fallback 값이 사용됩니다.

## Whisper 실행

`run_whisper_stt()`는 오디오 파일 경로를 검증하고 Whisper 모델을 로드한 뒤 `model.transcribe()`를 호출합니다.

```python
run_whisper_stt(
    audio_path="runs/audio/audio.wav",
    model_size="small",
    language="ko",
    device=None,
    temperature=0.0,
    beam_size=None,
)
```

모델 로딩은 `lru_cache(maxsize=4)`로 캐시됩니다. 같은 `model_size`, `device` 조합은 같은 프로세스 안에서 재사용됩니다.

## 출력 형식

JSON:

```text
runs/stt/stt_result.json
```

```json
{
  "language": "ko",
  "segment_count": 2,
  "segments": [
    {
      "segment_id": 0,
      "start": 0.0,
      "end": 3.5,
      "text": "인식된 문장"
    }
  ],
  "full_text": "인식된 전체 텍스트"
}
```

TXT:

```text
runs/stt/stt_result.txt
```

`--timestamps` 또는 전체 파이프라인의 `--stt-timestamps`를 사용하면 TXT 파일에 구간 시간이 포함됩니다.

## CLI

```bash
python scripts/run_stt.py --audio runs/audio/audio.wav
```

자주 쓰는 옵션:

```bash
python scripts/run_stt.py --model-size small --language ko --device cuda --timestamps
```

## 예외

| 상황 | 예외 |
| --- | --- |
| 오디오 파일 없음 | `FileNotFoundError` |
| 오디오 경로가 파일이 아님 | `ValueError` |
| `openai-whisper` 미설치 | `ImportError` |

## 주의 사항

- 첫 실행 시 Whisper 모델 다운로드가 필요할 수 있습니다.
- GPU 사용 가능 여부는 PyTorch 설치와 CUDA 환경에 좌우됩니다.
- 긴 오디오일수록 처리 시간이 크게 증가합니다.
