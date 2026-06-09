# Common Modules

## 개요

`modules/common`은 여러 단계에서 함께 사용할 수 있는 공통 유틸리티를 두는 영역이다.

현재 실제 구현이 들어 있는 파일은 `json_utils.py`와 `defaults.py`다. `defaults.py`는 파이프라인 스크립트들이 함께 사용하는 기본 입력/출력 경로 상수와 경로 생성 함수를 제공한다.

## 관련 파일

| 파일 | 상태 | 역할 |
| --- | --- | --- |
| `modules/common/defaults.py` | 구현됨 | 기본 입력/출력 상대 경로와 경로 생성 유틸리티 |
| `modules/common/json_utils.py` | 구현됨 | JSON 읽기/쓰기 유틸리티 |
| `modules/common/config.py` | 비어 있음 | 설정 로딩 공통화 예정 |
| `modules/common/file_utils.py` | 비어 있음 | 파일/경로 유틸리티 예정 |
| `modules/common/time_utils.py` | 비어 있음 | timestamp 변환 유틸리티 예정 |
| `modules/common/__init__.py` | 구현됨 | common 모듈 export |

## 사용 목적

공통 모듈은 특정 파이프라인 단계에 종속되지 않는 코드를 모으기 위한 위치다.

예시:

```text
JSON 저장
JSON 로드
경로 생성
시간 포맷 변환
설정 파일 로드
```

## 실행 흐름

현재 공통 모듈은 독립 실행 단계가 아니라 다른 모듈에서 필요할 때 import해 사용하는 구조다.

```text
preprocess / vision / stt
  -> modules.common 기본 경로 또는 JSON 유틸리티 import
  -> 실행 경로와 JSON 입출력 처리
```

아직 일부 공통 파일은 비어 있지만, 기본 산출물 경로는 `defaults.py`를 통해 여러 스크립트에서 공유한다.

## `defaults.py`

파이프라인에서 반복해서 쓰는 기본 상대 경로를 한곳에 모은다.

| 상수 | 기본 경로 |
| --- | --- |
| `DEFAULT_INPUT_VIDEO_RELATIVE_PATH` | `data/input/input.mp4` |
| `DEFAULT_RUN_DIR_RELATIVE_PATH` | `runs` |
| `DEFAULT_STT_CONFIG_RELATIVE_PATH` | `configs/stt_config.yaml` |
| `DEFAULT_AUDIO_RELATIVE_PATH` | `audio/audio.wav` |
| `DEFAULT_FRAME_METADATA_RELATIVE_PATH` | `metadata/frame_metadata.json` |
| `DEFAULT_STT_JSON_RELATIVE_PATH` | `stt/stt_result.json` |
| `DEFAULT_STT_TEXT_RELATIVE_PATH` | `stt/stt_result.txt` |
| `DEFAULT_VISION_RESULT_RELATIVE_PATH` | `vision/vision_result.json` |

경로 생성 함수:

| 함수 | 역할 |
| --- | --- |
| `project_path(project_root, relative_path)` | 프로젝트 루트 기준 경로 생성 |
| `run_path(run_dir, relative_path)` | 실행 디렉터리 기준 산출물 경로 생성 |

## `json_utils.py`

JSON 파일을 저장하거나 읽는 기능을 제공한다.

일반적으로 파이프라인 결과는 다음처럼 JSON 파일로 저장된다.

```text
runs/metadata/frame_metadata.json
runs/vision/vision_result.json
runs/stt/stt_result.json
```

공통 JSON 유틸리티는 이런 저장 방식을 한곳에 모으기 위한 파일이다.

## 설계 기준

1. 특정 단계 전용 로직은 `preprocess`, `vision`, `stt`에 둔다.
2. 여러 단계에서 반복되는 파일 처리만 `common`으로 올린다.
3. JSON 저장 시 기본 인코딩은 UTF-8을 사용한다.
4. Windows 환경에서 BOM이 붙은 파일을 읽을 수 있도록 `utf-8-sig` 사용을 고려한다.

## 현재 제한

1. `config.py`, `file_utils.py`, `time_utils.py`는 아직 구현되지 않았다.
2. 기존 코드 일부는 아직 `common` 유틸리티를 사용하지 않고 각 모듈에서 직접 파일을 처리한다.
3. 공통 유틸리티를 확장할 때는 기존 파이프라인 동작을 먼저 유지해야 한다.
