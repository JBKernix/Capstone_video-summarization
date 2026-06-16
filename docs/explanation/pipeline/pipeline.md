# 전체 파이프라인

`scripts/run_pipeline.py`는 영상 하나를 입력받아 오디오, STT, STT 요약, 프레임 샘플링, OCR, VLM 요약까지 순차 실행하는 CLI 진입점입니다.

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
```

현재 전체 파이프라인 안에서는 `run_final_summary.py`의 최종 통합 요약 단계가 자동 호출되지 않습니다. 최종 요약은 별도 명령으로 실행합니다.

```bash
python scripts/run_final_summary.py
```

## 단계별 산출물

| 단계 | 함수 | 출력 |
| --- | --- | --- |
| MP4 확인/변환 | `ensure_mp4_video()` | 원본 MP4 또는 변환된 MP4 |
| 오디오 추출 | `run_audio_step()` | `runs/audio/audio.wav` |
| STT | `run_stt_step()` | `runs/stt/stt_result.json`, `runs/stt/stt_result.txt` |
| STT 요약 | `run_llm_summary_step()` | `runs/llm/stt_summary.txt`, `runs/llm/stt_summary_result.json` |
| 프레임 샘플링 | `run_preprocess_step()` | `runs/frames/`, `runs/metadata/frame_metadata.json` |
| OCR | `run_ocr_step()` | `runs/ocr/ocr_result.json` |
| VLM 요약 | `run_vlm_summary_step()` | `runs/vlm/vlm_summary.txt`, `runs/vlm/vlm_summary_result.json` |

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
| `--skip-stt` | false | STT와 이후 STT 의존 단계 건너뛰기 |
| `--skip-ocr` | false | OCR 단계 건너뛰기 |
| `--skip-vlm` | false | VLM 단계 건너뛰기 |
| `--vlm-max-new-tokens` | `384` | 프레임당 VLM 생성 토큰 수 |
| `--stt-config` | `configs/stt_config.yaml` | STT 설정 파일 |
| `--stt-model-size` | 설정 파일 또는 `medium` | Whisper 모델 크기 |
| `--stt-language` | 설정 파일 또는 `ko` | STT 언어 |
| `--stt-device` | 설정 파일 또는 `None` | `cpu`, `cuda` 등 |
| `--stt-timestamps` | false | STT TXT에 timestamp 포함 |

## 건너뛰기 동작

- `--skip-stt`를 사용하면 STT 결과가 없으므로 STT 요약과 프레임 샘플링도 건너뜁니다.
- 프레임 메타데이터가 없거나 `--skip-ocr`가 지정되면 OCR 결과가 생성되지 않습니다.
- OCR 결과가 없거나 `--skip-vlm`가 지정되면 VLM 요약이 실행되지 않습니다.

## 실패 조건

| 상황 | 결과 |
| --- | --- |
| 입력 영상 없음 | `FileNotFoundError` |
| `data/input/*.mp4`에 일치 파일 없음 | `FileNotFoundError` |
| FFmpeg/FFprobe 없음 | `RuntimeError` 또는 `CalledProcessError` |
| GPU 서버 접근 실패 | `requests` 예외 |
| STT/OCR/VLM 결과 형식 오류 | 각 단계에서 예외 발생 |

같은 `run_dir`를 반복 사용하면 이전 산출물을 덮어쓸 수 있습니다.
