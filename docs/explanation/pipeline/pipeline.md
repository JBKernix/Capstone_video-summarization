# 전체 파이프라인

`scripts/run_pipeline.py`는 영상 하나를 입력받아 오디오, STT, STT 요약, 프레임 샘플링, OCR, VLM 요약, 최종 통합 요약까지 순차 실행하는 CLI 진입점입니다.

## 실행 흐름

```text
main()
  -> resolve_path_pattern()
  -> ensure_mp4_video()
  -> run_audio_step()
  -> run_stt_step()
  -> run_llm_summary_step()
  -> run_preprocess_step()
  -> run_ocr_step()
  -> run_vlm_summary_step()
  -> run_final_summary_step()
```

최종 통합 요약만 다시 생성해야 할 때는 `python scripts/run_final_summary.py`를 별도로 실행할 수 있습니다.

## 단계별 산출물

| 단계 | 함수 | 출력 |
| --- | --- | --- |
| MP4 확인/변환 | `ensure_mp4_video()` | 원본 MP4 또는 `<run-dir>/data/input/`에 변환된 MP4 |
| 오디오 추출 | `run_audio_step()` | `runs/audio/audio.wav` |
| STT | `run_stt_step()` | `runs/stt/stt_result.json`, `runs/stt/stt_result.txt` |
| STT 요약 | `run_llm_summary_step()` | `runs/llm/stt_summary.txt`, `runs/llm/stt_summary_result.json` |
| 프레임 샘플링 | `run_preprocess_step()` | `runs/frames/`, `runs/metadata/frame_metadata.json` |
| OCR | `run_ocr_step()` | `runs/ocr/ocr_result.json` |
| VLM 요약 | `run_vlm_summary_step()` | `runs/vlm/vlm_summary.txt`, `runs/vlm/vlm_summary_result.json` |
| 최종 통합 요약 | `run_final_summary_step()` | `runs/final/final_summary.txt`, `runs/final/final_summary_result.json` |

## 주요 옵션

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
| `--summary-level` | `standard` | 요약 크기/속도 프리셋 (`simple`/`standard`/`detailed`, `modules/llm/summary_levels.py`) |
| `--stt-config` | `configs/stt_config.yaml` | STT 설정 파일 |
| `--stt-model-size` | 설정 파일 또는 `medium` | Whisper 모델 크기 |
| `--stt-language` | 설정 파일 또는 `ko` | STT 언어 |
| `--stt-device` | 설정 파일 또는 `None` | `cpu`, `cuda` 등 |
| `--stt-timestamps` | false | STT TXT에 timestamp 포함 |

`--skip-stt` 옵션은 존재하지 않습니다. 과거에는 있었지만, 이 옵션을 켜면 STT뿐 아니라 이후 모든 단계(STT 요약/프레임 추출/OCR/VLM/최종 요약)까지 연쇄적으로 건너뛰어져 옵션 설명("STT만 건너뜀")과 실제 동작이 달라 혼란을 줄 수 있어 `scripts/run_pipeline.py`에서 주석 처리되어 비활성화되었습니다. STT는 항상 실행됩니다.

## STT 설정 로딩

`build_stt_options()`는 `modules.common.config.load_yaml_config()`로 `--stt-config` YAML을 읽은 뒤, 명령줄 인자가 있으면 그 값을 우선하고 없으면 설정 파일 값을, 그마저도 없으면 `modules.stt`의 `DEFAULT_STT_*` 상수를 사용합니다. `run_stt.py`와 동일한 `load_yaml_config()`를 공유하므로 두 스크립트의 STT 설정 로딩 방식이 일치합니다. (과거에는 `run_pipeline.py`에 별도의 `load_stt_config()`/`_parse_simple_stt_config()` 함수가 있었으나 삭제되었습니다.)

## 건너뛰기 동작

- `--summary-level simple`이면 `skip_visual_stages = True`가 되어 프레임 추출(4단계)부터 아예 건너뛰고, OCR/VLM도 이어서 건너뜁니다.
- 프레임 메타데이터가 없거나 `--skip-ocr`가 지정되면(또는 위 `simple` 프리셋이면) OCR 결과가 생성되지 않습니다.
- OCR 결과가 없거나 `--skip-vlm`가 지정되면 VLM 요약이 실행되지 않습니다.
- VLM 요약이 없는 상태로 최종 요약 단계에 도달하면(`simple` 프리셋 또는 `--skip-vlm`), `run_final_summary_step()`(서버 호출) 대신 `write_stt_only_final_summary_step()`으로 STT 요약을 최종 요약으로 그대로 저장합니다. 이때 진행 상황 메시지는 "완료 (STT 요약만 사용)"으로 표시됩니다. STT 요약 자체가 없으면(`llm_summary_path`/`llm_summary_json_path`가 `None`) 최종 요약 단계 자체가 "건너뜀"으로 표시됩니다.

## 진행률 보고

각 단계는 `modules.common.progress.report_progress(step, message, percent)`를 호출해 표준 출력에 `##PROGRESS##`로 시작하는 JSON 마커 줄을 남깁니다. 앱(Streamlit UI)은 파이프라인 프로세스의 로그를 폴링하며 이 마커를 파싱해 단계별 진행 상황을 표시합니다.

| 단계 번호(`STEP_*`) | 이름 | 진행률 표시 방식 |
| --- | --- | --- |
| 1 `STEP_AUDIO_EXTRACTION` | 오디오 추출 | ffmpeg 진행률(%) |
| 2 `STEP_STT` | STT 분석 | Whisper 자체 tqdm 표시줄 (별도 `report_progress` 없음) |
| 3 `STEP_STT_SUMMARY` | STT 요약 | GPU 서버 job 상태 메시지 |
| 4 `STEP_FRAME_EXTRACTION` | 프레임 추출 | ffmpeg 진행률(%) 또는 "N/M" 프레임 카운트 |
| 5 `STEP_OCR` | OCR 분석 | 진행률(%) |
| 6 `STEP_VLM_SUMMARY` | VLM 요약 생성 | GPU 서버 job 상태 메시지 |
| 7 `STEP_FINAL_SUMMARY` | 최종 요약 생성 | GPU 서버 job 상태 메시지 |

단계 이름/설명 문자열은 `modules/common/progress.py`의 `STEP_LABELS`에 정의되어 있으며, `run_pipeline.py`와 앱 UI가 동일한 번호 체계를 공유합니다.

## 실패 조건

| 상황 | 결과 |
| --- | --- |
| 입력 영상 없음 | `FileNotFoundError` |
| `data/input/*.mp4`에 일치 파일 없음 | `FileNotFoundError` |
| FFmpeg/FFprobe 없음 또는 실행 실패 | `RuntimeError` |
| GPU 서버 접근 실패 | `requests` 예외 |
| STT/OCR/VLM 결과 형식 오류 | 각 단계에서 예외 발생 |

같은 `run_dir`를 반복 사용하면 이전 산출물을 덮어쓸 수 있습니다.

## 참고: `scripts/run_preprocess.py`와의 경로 통일

프레임 샘플링만 단독 실행하는 `scripts/run_preprocess.py`도 동일하게 `ensure_mp4_video(video_path, run_dir / "data" / "input")`를 호출합니다. 과거에는 `run_pipeline.py`와 `run_preprocess.py`가 변환된 MP4 저장 경로로 각각 `run_dir / "data" / "input"`과 `run_dir / "input"`을 서로 다르게 사용해, 같은 `run-dir`에 대해 파이프라인 전체 실행과 전처리 단독 실행을 번갈아 하면 변환본이 두 곳에 중복 생성되는 문제가 있었습니다. 두 스크립트가 같은 경로를 쓰도록 통일되었습니다.
