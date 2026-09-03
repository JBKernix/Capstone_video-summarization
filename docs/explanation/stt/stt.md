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
  "duration_sec": 3.5,
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

`duration_sec`은 모든 segment의 `end` 시각 중 최댓값입니다(segment가 없으면 `0.0`). `save_stt_json()`은 내부적으로 `modules.common.save_json()`을 사용해 파일을 저장합니다.

> `duration_sec`은 예전에는 생성되지 않던 필드였습니다. 이로 인해 `scripts/run_llm_summary.py`가 참조하던 `stt_result.get("duration_sec")`가 항상 `None`이었는데, `format_stt_result()`에 이 필드가 추가되면서 해결되었습니다.

TXT:

```text
runs/stt/stt_result.txt
```

`--timestamps` 또는 전체 파이프라인의 `--stt-timestamps`를 사용하면 TXT 파일에 구간 시간이 포함됩니다.

## 진행률 보고 방식

다른 파이프라인 단계(OCR, VLM 요약 등)는 `modules.common.progress.report_progress()`를 직접 호출해 진행률을 앱에 알립니다. `run_whisper_stt()`는 이런 호출을 하지 않습니다. 대신 Whisper 라이브러리가 `model.transcribe()` 실행 중 자체적으로 출력하는 tqdm 진행률 표시줄(예: `45%|████      | 12/27 [00:05<00:06]`)을 `app/pages/1_upload.py`가 로그에서 파싱해 `STEP_STT` 진행률로 변환합니다.

```python
# app/pages/1_upload.py
STT_TQDM_PATTERN = re.compile(r"^\s*(\d{1,3})%\|")
...
match = STT_TQDM_PATTERN.match(line)
if match:
    _update(STEP_STT, "음성 인식 처리 중", float(match.group(1)))
```

STT 단계만 이렇게 별도 방식을 쓰는 이유는 Whisper가 이미 자체 진행률을 표준 출력으로 내보내기 때문입니다. `modules/stt` 코드에 진행률 보고 호출이 없다고 해서 누락된 것이 아니라 의도된 설계입니다.

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
