# 실행 스크립트

`scripts/` 폴더는 현재 프로젝트의 실제 실행 진입점입니다. Streamlit UI가 아직 비어 있으므로 CLI 스크립트를 기준으로 실행합니다.

## 스크립트 목록

| 스크립트 | 역할 |
| --- | --- |
| `run_pipeline.py` | 오디오 추출부터 VLM 요약까지 순차 실행 |
| `run_preprocess.py` | 영상 정보 확인과 프레임 샘플링 |
| `run_stt.py` | Whisper STT 실행 |
| `run_ocr.py` | 프레임 메타데이터 기반 OCR 실행 |
| `run_llm_summary.py` | STT 결과를 LLM 서버로 요약 |
| `run_vlm_summary.py` | OCR 결과와 프레임 이미지를 VLM 서버로 요약 |
| `run_final_summary.py` | STT/VLM 요약 결과를 최종 통합 요약 |

## 기본 실행 순서

```bash
python scripts/run_pipeline.py --video data/input/sample.mp4 --run-dir runs
python scripts/run_final_summary.py
```

`run_pipeline.py`는 최종 통합 요약까지 자동 실행하지 않으므로, 최종 결과가 필요하면 `run_final_summary.py`를 이어서 실행합니다.

## 단계별 실행 예

```bash
python scripts/run_preprocess.py --video data/input/sample.mp4 --run-dir runs
python scripts/run_stt.py --audio runs/audio/audio.wav
python scripts/run_llm_summary.py --stt-json runs/stt/stt_result.json
python scripts/run_ocr.py
python scripts/run_vlm_summary.py --ocr-json runs/ocr/ocr_result.json
python scripts/run_final_summary.py
```

## 경로 기본값

대부분의 스크립트는 `modules/common/defaults.py`의 기본 경로를 사용합니다.

| 기본값 | 경로 |
| --- | --- |
| 입력 영상 | `data/input/*.mp4` |
| 실행 결과 루트 | `runs` |
| 오디오 | `runs/audio/audio.wav` |
| STT JSON | `runs/stt/stt_result.json` |
| OCR JSON | `runs/ocr/ocr_result.json` |

## 주의 사항

- 단계별 스크립트는 앞 단계 산출물이 이미 존재한다고 가정합니다.
- GPU 서버가 필요한 스크립트는 서버 접근 실패 시 중단됩니다.
- 같은 `runs/`를 반복 사용하면 일부 결과 파일이 덮어써집니다.
