# 실행 스크립트

`scripts/` 폴더는 CLI 실행 진입점입니다. Streamlit 앱도 내부적으로 `scripts/run_pipeline.py`를 백그라운드 프로세스로 실행하고, 표준출력의 `##PROGRESS##` 로그를 폴링해 단계별 진행률을 표시합니다.

## 스크립트 목록

| 스크립트 | 역할 |
| --- | --- |
| `run_pipeline.py` | 오디오 추출부터 최종 통합 요약까지 순차 실행 |
| `run_preprocess.py` | 영상 정보 확인과 프레임 샘플링 |
| `run_stt.py` | Whisper STT 실행 |
| `run_ocr.py` | 프레임 메타데이터 기반 OCR 실행 |
| `run_llm_summary.py` | STT 결과를 LLM 서버로 요약 |
| `run_vlm_summary.py` | OCR 결과와 프레임 이미지를 VLM 서버로 요약 |
| `run_final_summary.py` | STT/VLM 요약 결과를 최종 통합 요약 |

## 기본 실행 순서

Streamlit 앱:

```bat
run_app.bat
```

CLI:

```bash
python scripts/run_pipeline.py --video data/input/sample.mp4 --run-dir runs
```

`run_final_summary.py`는 최종 통합 요약만 다시 생성해야 할 때 별도로 실행합니다.

## 단계별 실행 예

```bash
python scripts/run_preprocess.py --video data/input/sample.mp4 --run-dir runs
python scripts/run_stt.py --audio runs/audio/audio.wav
python scripts/run_llm_summary.py --stt-json runs/stt/stt_result.json
python scripts/run_ocr.py
python scripts/run_vlm_summary.py --ocr-json runs/ocr/ocr_result.json
python scripts/run_final_summary.py
```

## `run_pipeline.py` 옵션

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| `--video` | `data/input/*.mp4` | 분석할 영상 경로 또는 glob 패턴 |
| `--run-dir` | `runs` | 결과 저장 루트 |
| `--method` | `interval` | `interval` 또는 `scene_change` |
| `--interval-seconds` | `5.0` | interval 방식 프레임 추출 간격 |
| `--scene-threshold` | `0.5` | FFmpeg scene score 임계값 |
| `--scene-min-gap-seconds` | `1.0` | 장면 전환 프레임 간 최소 간격 |
| `--ocr-lang` | `korean` | EasyOCR 언어 설정 |
| `--skip-ocr` | false | OCR 단계 건너뛰기 |
| `--skip-vlm` | false | VLM 단계 건너뛰기 |
| `--summary-level` | `standard` | 요약 크기/속도 프리셋 (`simple`/`standard`/`detailed`). `simple`이면 프레임 추출/OCR/VLM 단계를 건너뛰고 STT 요약을 최종 요약으로 사용 |
| `--stt-config` | `configs/stt_config.yaml` | STT 설정 파일 |
| `--stt-model-size` | 설정 파일 또는 `medium` | Whisper 모델 크기 |
| `--stt-language` | 설정 파일 또는 `ko` | STT 언어 |
| `--stt-device` | 설정 파일 또는 `None` | `cpu`, `cuda` 등 |
| `--stt-timestamps` | false | STT TXT에 timestamp 포함 |

`--skip-stt` 옵션은 존재하지 않습니다. `argparse` 정의와 사용 코드가 모두 주석 처리되어 비활성화되었습니다 (건너뛰면 이후 요약/프레임/OCR/VLM 단계까지 연쇄적으로 건너뛰어져 옵션 설명과 실제 동작이 어긋나는 문제가 있었기 때문). STT는 항상 실행됩니다.

## 공용 유틸리티 사용

이번 세션에서 스크립트들이 `modules/common`의 공용 함수를 공유하도록 정리되었습니다. 자세한 내용은 [`common.md`](../common/common.md)를 참고하세요.

- **STT 설정 로딩**: `run_stt.py`, `run_pipeline.py` 모두 자체 YAML 파서 대신 `modules.common.config.load_yaml_config()`를 사용합니다. 설정 파일이 없으면 빈 dict, PyYAML 미설치 시 `ImportError`로 동작이 통일되었습니다.
- **JSON 읽기/쓰기**: `run_llm_summary.py`, `run_vlm_summary.py`, `run_final_summary.py`는 각자 JSON을 직접 다루던 코드를 `modules.common.load_json()` / `save_json()` 호출로 대체했습니다. 동작은 동일하고 구현 위치만 정리되었습니다.
- **진행률 보고**: `run_pipeline.py`가 호출하는 오디오 추출, 프레임 샘플링, OCR, STT/VLM/최종 요약 각 단계 내부에서 `modules.common.progress.report_progress()`를 호출해 `##PROGRESS##` 마커가 붙은 JSON 한 줄을 표준출력에 남깁니다. `app/pages/1_upload.py`가 이 로그를 읽어 실시간 진행률 UI를 구성합니다.

## STT 요약(`run_llm_summary.py`) 수정 사항

`stt_result.get("duration_sec")`가 이제 실제 값을 반환합니다. STT 포맷터가 이 필드를 생성하도록 고쳐지기 전에는 항상 `None`이었습니다.

## 요약 레벨(`--summary-level`)

`run_llm_summary.py`, `run_vlm_summary.py`, `run_final_summary.py`, `run_pipeline.py`는 모두 `--summary-level simple|standard|detailed`(기본값 `standard`, `modules/llm/summary_levels.py`) 옵션을 공유합니다. `run_vlm_summary.py`의 옛 `--max-new-tokens` 옵션은 이 옵션으로 대체되었습니다. 자세한 내용은 [`llm.md`](../llm/llm.md)를 참고하세요.

`run_final_summary.py`에는 GPU 서버를 호출하지 않는 `write_stt_only_final_summary_step()`도 추가되었습니다. `run_pipeline.py`는 VLM 요약이 없을 때(`--summary-level simple` 또는 `--skip-vlm`) 이 함수로 STT 요약을 최종 요약 대신 그대로 저장합니다.

## 경로 기본값

대부분의 스크립트는 `modules/common/defaults.py`의 기본 경로를 사용합니다.

| 기본값 | 경로 |
| --- | --- |
| 입력 영상 | `data/input/*.mp4` |
| 실행 결과 루트 | `runs` |
| 오디오 | `runs/audio/audio.wav` |
| STT JSON | `runs/stt/stt_result.json` |
| OCR JSON | `runs/ocr/ocr_result.json` |

`--video`로 mp4가 아닌 영상을 지정하면 `ensure_mp4_video()`가 변환한 mp4를 `<run-dir>/data/input/`에 저장합니다. `run_pipeline.py`와 `run_preprocess.py` 모두 이 경로를 사용하도록 통일되었습니다 (이전에는 `run_preprocess.py`만 `<run-dir>/input/`을 사용해 두 스크립트의 결과 위치가 달랐습니다).

## 주의 사항

- 단계별 스크립트는 앞 단계 산출물이 이미 존재한다고 가정합니다.
- GPU 서버가 필요한 스크립트는 서버 접근 실패 시 중단됩니다.
- 같은 `runs/`를 반복 사용하면 일부 결과 파일이 덮어써집니다.
