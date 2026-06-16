# 모듈 설명 문서

이 폴더는 프로젝트의 실행 스크립트와 핵심 모듈을 영역별로 설명하는 문서 모음입니다. 루트 `README.md`가 설치와 실행 방법을 다룬다면, 이 문서는 코드 구조를 파악할 때 들어가는 색인 역할을 합니다.

## 문서 구성

| 영역 | 문서 | 관련 코드 | 설명 |
| --- | --- | --- | --- |
| App | `app/app.md` | `app/` | Streamlit UI 구조와 실행 흐름 |
| Configs | `configs/configs.md` | `configs/` | STT 설정과 비어 있는 설정 파일 상태 |
| Scripts | `scripts/scripts.md` | `scripts/` | CLI 실행 스크립트별 역할 |
| 전체 파이프라인 | `pipeline/pipeline.md` | `scripts/run_pipeline.py` | 오디오 추출, STT, LLM 요약, 프레임 추출, OCR, VLM 요약 순서 |
| 전처리 | `preprocess/frame_sampling.md` | `modules/preprocess/frame_sampler.py` | interval/scene 기반 프레임 샘플링과 메타데이터 생성 |
| 전처리 | `preprocess/audio_extraction.md` | `modules/preprocess/audio_extractor.py` | 영상에서 WAV 오디오 추출 |
| 전처리 | `preprocess/video_info.md` | `modules/preprocess/video_info.py` | FFprobe 기반 영상 길이, 해상도, FPS 조회 |
| 전처리 | `preprocess/ffmpeg_utils.md` | `modules/preprocess/ffmpeg_utils.py` | FFmpeg/FFprobe 실행 유틸리티와 MP4 보장 로직 |
| OCR | `ocr/ocr_pipeline.md` | `modules/ocr/ocr_extractor.py`, `modules/ocr/ocr_formatter.py` | 프레임 메타데이터 기반 OCR 실행 흐름 |
| OCR | `ocr/ocr.md` | `modules/ocr/` | EasyOCR 처리 세부 구조 |
| STT | `stt/stt.md` | `modules/stt/`, `scripts/run_stt.py` | Whisper 기반 음성 인식과 결과 저장 |
| LLM/VLM | `llm/llm.md` | `modules/llm/`, `scripts/run_llm_summary.py`, `scripts/run_vlm_summary.py`, `scripts/run_final_summary.py` | GPU 서버 기반 요약 클라이언트 |
| Common | `common/common.md` | `modules/common/` | 기본 경로, JSON 저장/로드 등 공통 유틸리티 |
| Tests | `tests/tests.md` | `tests/` | pytest 테스트 파일 구성 |

## 현재 실행 스크립트

| 스크립트 | 역할 | 기본 입력 | 기본 출력 |
| --- | --- | --- | --- |
| `scripts/run_pipeline.py` | 구현된 단계를 순차 실행 | `data/input/*.mp4` | `runs/` 하위 전체 산출물 |
| `scripts/run_preprocess.py` | 영상 정보 확인 및 프레임 샘플링 | `data/input/*.mp4` | `runs/metadata/frame_metadata.json` |
| `scripts/run_stt.py` | Whisper STT 실행 | `runs/audio/audio.wav` | `runs/stt/stt_result.json`, `runs/stt/stt_result.txt` |
| `scripts/run_llm_summary.py` | STT 결과 요약 및 주요 구간 추출 | `runs/stt/stt_result.json` | `runs/llm/stt_summary.txt`, `runs/llm/stt_summary_result.json` |
| `scripts/run_ocr.py` | 프레임별 OCR 실행 | `runs/metadata/frame_metadata.json` | `runs/ocr/ocr_result.json` |
| `scripts/run_vlm_summary.py` | OCR 결과와 프레임 이미지를 VLM 서버로 전송 | `runs/ocr/ocr_result.json` | `runs/vlm/vlm_summary.txt`, `runs/vlm/vlm_summary_result.json` |
| `scripts/run_final_summary.py` | STT/VLM 요약을 통합한 최종 요약 생성 | `runs/llm/`, `runs/vlm/` 산출물 | `runs/final/final_summary.txt`, `runs/final/final_summary_result.json` |

## 구현 상태 요약

| 영역 | 상태 | 비고 |
| --- | --- | --- |
| 영상 전처리 | 구현됨 | FFmpeg/FFprobe 필요 |
| 프레임 추출 | 구현됨 | `interval`, `scene` 방식 지원 |
| 오디오 추출 | 구현됨 | 기본 출력은 `runs/audio/audio.wav` |
| STT | 구현됨 | Whisper 사용, 설정은 `configs/stt_config.yaml` |
| OCR | 구현됨 | EasyOCR 사용 |
| STT 요약 | 구현됨 | 외부 GPU LLM 서버 필요 |
| VLM 프레임 요약 | 구현됨 | 외부 GPU VLM 서버 필요, JPG 프레임만 전송 |
| 최종 요약 | 구현됨 | STT/VLM 요약 파일 필요 |
| Streamlit UI | 구현됨 | 업로드, 분석 실행, 최종 요약 결과 확인 |

## 기본 경로

기본 경로는 `modules/common/defaults.py`에서 정의합니다.

| 상수 | 기본값 |
| --- | --- |
| `DEFAULT_INPUT_VIDEO_RELATIVE_PATH` | `data/input/*.mp4` |
| `DEFAULT_RUN_DIR_RELATIVE_PATH` | `runs` |
| `DEFAULT_AUDIO_RELATIVE_PATH` | `audio/audio.wav` |
| `DEFAULT_FRAME_METADATA_RELATIVE_PATH` | `metadata/frame_metadata.json` |
| `DEFAULT_STT_JSON_RELATIVE_PATH` | `stt/stt_result.json` |
| `DEFAULT_STT_TEXT_RELATIVE_PATH` | `stt/stt_result.txt` |
| `DEFAULT_OCR_RESULT_RELATIVE_PATH` | `ocr/ocr_result.json` |

## 문서 작성 기준

각 세부 문서는 다음 내용을 우선 포함합니다.

```text
개요
관련 파일
실행 흐름
주요 함수 또는 주요 단계
입력/출력
예외
주의 사항 또는 현재 제한
```

문서를 업데이트할 때는 실제 코드의 기본값, 파일명, 출력 경로와 맞는지 먼저 확인합니다.
