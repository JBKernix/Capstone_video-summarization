# App 폴더

`app/` 폴더는 Streamlit UI를 위한 예정 영역입니다. 현재 파일은 존재하지만 내용은 비어 있습니다.

## 현재 파일

| 파일 | 상태 | 예정 역할 |
| --- | --- | --- |
| `app/main.py` | 비어 있음 | Streamlit 앱 메인 페이지 |
| `app/pages/1_upload.py` | 비어 있음 | 영상 업로드 화면 |
| `app/pages/2_analysis_result.py` | 비어 있음 | 분석 결과 화면 |
| `app/pages/3_settings.py` | 비어 있음 | 설정 화면 |

## 현재 실행 기준

UI가 구현되어 있지 않으므로 현재 실행과 검증은 `scripts/`의 CLI를 사용합니다.

```bash
python scripts/run_pipeline.py --video data/input/sample.mp4 --run-dir runs
python scripts/run_final_summary.py
```

## 향후 UI에서 연결할 산출물

| 화면 | 사용할 가능성이 높은 파일 |
| --- | --- |
| 업로드 | `data/input/` 또는 임시 업로드 경로 |
| 분석 진행 | `scripts/run_pipeline.py` 실행 상태 |
| STT 결과 | `runs/stt/stt_result.txt`, `runs/stt/stt_result.json` |
| OCR/VLM 결과 | `runs/ocr/ocr_result.json`, `runs/vlm/vlm_summary.txt` |
| 최종 요약 | `runs/final/final_summary.txt` |
| 설정 | `configs/stt_config.yaml`, GPU 서버 주소 |

## 구현 시 주의 사항

- 긴 처리 시간이 필요한 단계가 많으므로 UI에서는 진행 상태와 오류 메시지를 보여주는 구조가 필요합니다.
- GPU 서버 의존 단계는 서버 연결 확인을 먼저 제공하는 것이 좋습니다.
- 업로드한 영상이 MP4가 아니어도 `ensure_mp4_video()`가 변환할 수 있지만, 변환 결과 저장 위치를 UI에서 명확히 관리해야 합니다.
