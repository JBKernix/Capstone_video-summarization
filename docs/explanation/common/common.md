# Common 모듈

`modules/common`은 여러 단계에서 함께 사용하는 기본 경로와 JSON 유틸리티를 제공합니다.

## 관련 파일

| 파일 | 상태 | 역할 |
| --- | --- | --- |
| `modules/common/defaults.py` | 구현됨 | 기본 입력/출력 경로와 경로 해석 함수 |
| `modules/common/json_utils.py` | 구현됨 | JSON 읽기/쓰기 |
| `modules/common/__init__.py` | 구현됨 | public API export |
| `modules/common/config.py` | 비어 있음 | 향후 설정 로더 자리 |
| `modules/common/file_utils.py` | 비어 있음 | 향후 파일 유틸리티 자리 |
| `modules/common/time_utils.py` | 비어 있음 | 향후 시간 변환 유틸리티 자리 |

## 기본 경로

| 상수 | 값 |
| --- | --- |
| `DEFAULT_INPUT_VIDEO_RELATIVE_PATH` | `data/input/*.mp4` |
| `DEFAULT_RUN_DIR_RELATIVE_PATH` | `runs` |
| `DEFAULT_STT_CONFIG_RELATIVE_PATH` | `configs/stt_config.yaml` |
| `DEFAULT_AUDIO_RELATIVE_PATH` | `audio/audio.wav` |
| `DEFAULT_FRAME_METADATA_RELATIVE_PATH` | `metadata/frame_metadata.json` |
| `DEFAULT_STT_JSON_RELATIVE_PATH` | `stt/stt_result.json` |
| `DEFAULT_STT_TEXT_RELATIVE_PATH` | `stt/stt_result.txt` |
| `DEFAULT_OCR_RESULT_RELATIVE_PATH` | `ocr/ocr_result.json` |

## 주요 함수

| 함수 | 설명 |
| --- | --- |
| `resolve_path_pattern(path)` | glob 패턴이 포함된 경로에서 첫 번째 실제 파일을 반환 |
| `project_path(project_root, relative_path)` | 프로젝트 루트 기준 경로 생성 |
| `run_path(run_dir, relative_path)` | 실행 결과 루트 기준 경로 생성 |
| `load_json(json_path)` | `utf-8-sig`로 JSON 파일 읽기 |
| `save_json(data, json_path)` | 부모 디렉터리를 만들고 UTF-8 JSON 저장 |

## 사용 예

```python
from modules.common import DEFAULT_RUN_DIR_RELATIVE_PATH, run_path

output = run_path(DEFAULT_RUN_DIR_RELATIVE_PATH, "stt/stt_result.json")
```

## 주의 사항

- `load_json()`은 반환 타입을 `dict`로 가정하므로, 배열 JSON을 다루는 모듈은 자체 로더를 사용합니다.
- Windows에서 BOM이 붙은 JSON을 읽을 수 있도록 로딩에는 `utf-8-sig`를 사용합니다.
- `config.py`, `file_utils.py`, `time_utils.py`는 아직 구현되지 않았습니다.
