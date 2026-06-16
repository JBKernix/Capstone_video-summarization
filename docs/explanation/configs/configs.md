# 설정 파일

`configs/` 폴더는 실행 설정을 보관하는 위치입니다.

## 현재 파일

| 파일 | 상태 | 설명 |
| --- | --- | --- |
| `configs/stt_config.yaml` | 값 있음 | Whisper STT 기본 설정 |
| `configs/app_config.yaml` | 비어 있음 | 향후 UI 설정 예정 |
| `configs/ffmpeg_config.yaml` | 비어 있음 | 향후 FFmpeg 설정 예정 |
| `configs/llm_config.yaml` | 비어 있음 | 향후 LLM/VLM 설정 예정 |

## STT 설정

현재 `stt_config.yaml`:

```yaml
model_size: small
language: ko
device:
temperature: 0.0
beam_size:
```

| 키 | 설명 |
| --- | --- |
| `model_size` | Whisper 모델 크기 |
| `language` | STT 언어 코드 |
| `device` | `cpu`, `cuda`, 또는 빈 값 |
| `temperature` | Whisper transcribe temperature |
| `beam_size` | beam search 크기, 빈 값이면 사용하지 않음 |

## 적용 우선순위

STT 실행에서는 다음 순서로 값이 결정됩니다.

```text
CLI 옵션
  -> configs/stt_config.yaml
  -> modules/stt/whisper_stt.py fallback 기본값
```

## GPU 서버 설정

현재 GPU 서버 주소는 설정 파일이 아니라 코드에 있습니다.

```python
# modules/llm/__init__.py
GPU_SERVER_URL = "http://10.30.2.224:8000"
```

향후 `configs/llm_config.yaml`을 사용하려면 LLM/VLM 클라이언트에서 설정 로딩 로직을 추가해야 합니다.

## 주의 사항

- 비어 있는 설정 파일은 현재 실행에 영향을 주지 않습니다.
- YAML 파일은 UTF-8로 저장하는 것을 권장합니다.
