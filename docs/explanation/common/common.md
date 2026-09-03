# Common 모듈

`modules/common`은 여러 단계에서 함께 사용하는 기본 경로, 설정 로딩, 파일 경로 해석, JSON 유틸리티, 파이프라인 진행 상황 보고 기능을 제공합니다.

## 관련 파일

| 파일 | 상태 | 역할 |
| --- | --- | --- |
| `modules/common/defaults.py` | 구현됨 | 기본 입력/출력 경로와 경로 해석 함수 |
| `modules/common/json_utils.py` | 구현됨 | JSON 읽기/쓰기 |
| `modules/common/config.py` | 구현됨 | YAML 설정 로더 |
| `modules/common/file_utils.py` | 구현됨 | 저장된 경로를 실제 파일 경로로 해석 |
| `modules/common/progress.py` | 구현됨 | 파이프라인 진행 상황 보고 |
| `modules/common/__init__.py` | 구현됨 | public API export |

`modules/common/time_utils.py`는 빈 파일이었고 사용하는 곳이 없어 삭제되었습니다.

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
| `load_yaml_config(config_path)` | YAML 설정 파일을 dict로 읽기 |
| `find_existing_path(stored_path, anchor_path, project_root)` | 메타데이터/결과 JSON에 저장된 경로를 실제 파일 경로로 해석 |
| `report_progress(step, message, percent=None)` | 파이프라인 단계 진행 상황을 표준출력에 기록 |

## `load_yaml_config`

`modules/common/config.py`에 구현되어 있습니다.

```python
def load_yaml_config(config_path: str | Path) -> dict:
    ...
```

- 파일이 없으면 빈 `dict`를 반환합니다.
- PyYAML(`yaml`)이 설치되어 있지 않으면 `ImportError`를 발생시킵니다.
- 읽기에는 `utf-8-sig` 인코딩을 사용합니다.
- `scripts/run_stt.py`와 `scripts/run_pipeline.py`가 이 함수를 공유해서 STT 설정을 읽습니다. 이전에는 두 스크립트가 각자 다른 방식으로 YAML을 파싱해 PyYAML 미설치 시 동작이 서로 달랐으나, 이제 하나로 통일되었습니다.

## `find_existing_path`

`modules/common/file_utils.py`에 구현되어 있습니다.

```python
def find_existing_path(
    stored_path: str | Path,
    anchor_path: str | Path,
    project_root: str | Path,
) -> Path | None:
    ...
```

메타데이터/결과 JSON에는 이미지 경로가 절대경로, 현재 작업 디렉터리 기준, 프로젝트 루트 기준, 산출물 디렉터리 기준 등 다양한 형태로 저장될 수 있습니다. 이 함수는 다음 순서로 후보를 확인해 실제 존재하는 파일 경로를 반환합니다.

1. `stored_path`가 절대경로이면 그대로 존재 여부만 확인
2. `Path.cwd() / stored_path`
3. `project_root / stored_path`
4. `anchor_path`가 위치한 디렉터리 기준 `anchor_path.parent / stored_path`
5. `anchor_path.parent.parent / stored_path`

어떤 후보에서도 파일을 찾지 못하면 `None`을 반환합니다. `modules/ocr/ocr_formatter.py`와 `modules/llm/vlm_summarizer_client.py`가 이 함수를 공유합니다. 이전에는 두 모듈이 각자 비슷한 경로 탐색 로직을 중복 구현했었습니다.

## `progress` — 파이프라인 진행 상황 보고

`modules/common/progress.py`는 파이프라인 실행 로그에 진행 상황을 구조화된 형태로 남기고, `app/pages/1_upload.py`가 이 로그를 폴링/파싱해 UI에 단계별 진행률을 표시하는 데 사용합니다.

| 이름 | 값/설명 |
| --- | --- |
| `PROGRESS_MARKER` | `"##PROGRESS##"` — 진행 상황 로그 줄의 접두사 |
| `TOTAL_STEPS` | `7` |
| `STEP_AUDIO_EXTRACTION` | `1` |
| `STEP_STT` | `2` |
| `STEP_STT_SUMMARY` | `3` |
| `STEP_FRAME_EXTRACTION` | `4` |
| `STEP_OCR` | `5` |
| `STEP_VLM_SUMMARY` | `6` |
| `STEP_FINAL_SUMMARY` | `7` |
| `STEP_LABELS` | 단계 번호 → `(제목, 설명)` 딕셔너리 |

`STEP_LABELS`:

| 단계 | 제목 | 설명 |
| --- | --- | --- |
| 1 | 오디오 추출 | 영상에서 음성 분리 |
| 2 | STT 분석 | 음성을 텍스트로 변환 |
| 3 | STT 요약 | 핵심 내용 및 중요 구간 요약 |
| 4 | 프레임 추출 | 중요 구간 프레임 선택 |
| 5 | OCR 분석 | 화면 텍스트 및 시각 정보 이해 |
| 6 | VLM 요약 생성 | 프레임별 시각 요약 생성 |
| 7 | 최종 요약 생성 | 음성/시각 요약 통합 |

```python
def report_progress(step: int, message: str, percent: float | None = None) -> None:
    ...
```

`{PROGRESS_MARKER} {json}` 형태로 표준출력에 한 줄을 출력합니다 (`json`은 `{"step": ..., "message": ...}`, `percent`가 주어지면 0~100 사이로 clamp되어 소수 첫째 자리까지 포함). `flush=True`로 즉시 출력되므로 로그를 실시간으로 폴링하는 앱에서 바로 읽을 수 있습니다.

사용처:

| 파일 | 사용하는 단계 상수 |
| --- | --- |
| `modules/preprocess/audio_extractor.py` | `STEP_AUDIO_EXTRACTION` |
| `modules/preprocess/frame_sampler.py` | `STEP_FRAME_EXTRACTION` |
| `modules/ocr/ocr_formatter.py` | `STEP_OCR` |
| `modules/llm/stt_summarizer_client.py` | `STEP_STT_SUMMARY` |
| `modules/llm/vlm_summarizer_client.py` | `STEP_VLM_SUMMARY` |
| `modules/llm/final_summarizer_client.py` | `STEP_FINAL_SUMMARY` |
| `modules/llm/gpu_job_client.py` | 하위 클래스가 설정한 `progress_step` (GPU 작업 폴링 중 상태 메시지 보고용 공통 믹스인) |

`app/pages/1_upload.py`는 `PROGRESS_MARKER`, `STEP_LABELS`, `STEP_STT`, `TOTAL_STEPS`를 직접 import해서 로그 줄을 파싱하고, Whisper STT 자체 진행률 출력(`STEP_STT`)까지 포함해 전체 7단계 진행률 UI를 구성합니다.

## `__init__.py` 재노출 목록

`modules/common/__init__.py`는 아래 이름들을 `modules.common` 패키지에서 바로 import할 수 있도록 재노출합니다.

```python
from modules.common import (
    DEFAULT_AUDIO_RELATIVE_PATH,
    DEFAULT_FRAME_METADATA_RELATIVE_PATH,
    DEFAULT_INPUT_VIDEO_RELATIVE_PATH,
    DEFAULT_RUN_DIR_RELATIVE_PATH,
    DEFAULT_STT_CONFIG_RELATIVE_PATH,
    DEFAULT_STT_JSON_RELATIVE_PATH,
    DEFAULT_STT_TEXT_RELATIVE_PATH,
    DEFAULT_OCR_RESULT_RELATIVE_PATH,
    PROGRESS_MARKER,
    STEP_LABELS,
    TOTAL_STEPS,
    find_existing_path,
    load_json,
    load_yaml_config,
    project_path,
    report_progress,
    resolve_path_pattern,
    run_path,
    save_json,
)
```

`STEP_AUDIO_EXTRACTION` 등 개별 `STEP_*` 상수는 재노출 목록에 없으므로, 이 상수가 필요한 코드는 `modules.common.progress`에서 직접 import합니다.

## 사용 예

```python
from modules.common import DEFAULT_RUN_DIR_RELATIVE_PATH, run_path

output = run_path(DEFAULT_RUN_DIR_RELATIVE_PATH, "stt/stt_result.json")
```

```python
from modules.common.progress import STEP_OCR, report_progress

report_progress(STEP_OCR, "OCR 처리 중 (3/10)", percent=30.0)
```

## 주의 사항

- `load_json()`은 반환 타입을 `dict`로 가정하므로, 배열 JSON을 다루는 모듈은 자체 로더를 사용합니다.
- Windows에서 BOM이 붙은 JSON을 읽을 수 있도록 로딩에는 `utf-8-sig`를 사용합니다.
- `load_yaml_config()`도 같은 이유로 `utf-8-sig`로 읽습니다.
- `find_existing_path()`는 파일을 찾지 못해도 예외를 던지지 않고 `None`을 반환하므로, 호출 측에서 반드시 `None` 처리를 해야 합니다.
- `report_progress()`는 표준출력에만 기록하며 로그 파일 저장/전송은 호출하는 쪽(앱, 스크립트)의 책임입니다.
