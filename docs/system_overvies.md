# 시스템 개요

이 프로젝트는 영상의 음성 정보와 화면 정보를 함께 사용해 요약을 생성하는 멀티모달 영상 요약 파이프라인입니다.

파일명은 현재 저장소의 기존 이름인 `system_overvies.md`를 유지합니다.

## 전체 구조

```text
입력 영상
  -> MP4 확인/변환
  -> 오디오 추출
  -> Whisper STT
  -> LLM STT 요약 및 주요 구간 추출
  -> 주요 구간 프레임 샘플링
  -> EasyOCR 화면 텍스트 추출
  -> VLM 프레임 요약
  -> 최종 LLM 통합 요약
```

## 주요 컴포넌트

| 영역 | 위치 | 역할 |
| --- | --- | --- |
| 실행 스크립트 | `scripts/` | 단계별 CLI와 전체 파이프라인 진입점 |
| 전처리 | `modules/preprocess/` | 영상 정보 조회, MP4 변환, 오디오 추출, 프레임 샘플링 |
| STT | `modules/stt/` | Whisper 실행 및 STT 결과 포맷팅 |
| OCR | `modules/ocr/` | EasyOCR 실행, 화면 유형 추정, OCR 결과 저장 |
| LLM/VLM | `modules/llm/` | 외부 GPU 서버 API 클라이언트 |
| 공통 유틸리티 | `modules/common/` | 기본 경로와 JSON 유틸리티 |
| UI | `app/` | Streamlit UI 예정 영역, 현재 미구현 |

## 기본 실행 진입점

| 목적 | 명령 |
| --- | --- |
| 전체 파이프라인 | `python scripts/run_pipeline.py` |
| 전처리만 실행 | `python scripts/run_preprocess.py` |
| STT만 실행 | `python scripts/run_stt.py` |
| OCR만 실행 | `python scripts/run_ocr.py` |
| STT 요약 | `python scripts/run_llm_summary.py` |
| VLM 요약 | `python scripts/run_vlm_summary.py` |
| 최종 요약 | `python scripts/run_final_summary.py` |

## 외부 의존성

| 의존성 | 사용 단계 |
| --- | --- |
| FFmpeg | MP4 변환, 오디오 추출, 프레임 추출 |
| FFprobe | 영상 길이, 해상도, FPS 조회 |
| Whisper | STT |
| EasyOCR | OCR |
| PyTorch | Whisper/EasyOCR 실행 |
| GPU 서버 | LLM 요약, VLM 요약, 최종 요약 |

## 실행 결과 위치

기본 결과 루트는 `runs/`입니다.

```text
runs/
  audio/
  stt/
  llm/
  frames/
  metadata/
  ocr/
  vlm/
  final/
```

## 현재 상태

| 항목 | 상태 |
| --- | --- |
| CLI 파이프라인 | 구현됨 |
| 전처리/STT/OCR | 구현됨 |
| LLM/VLM 서버 클라이언트 | 구현됨 |
| Streamlit UI | 파일만 존재, 미구현 |
| 설정 파일 | `stt_config.yaml`만 값이 있음, 나머지는 비어 있음 |

## 참고 문서

- `docs/setup_guide.md`: 설치와 실행 준비
- `docs/data_format.md`: JSON/TXT 산출물 구조
- `docs/explanation/README.md`: 모듈별 상세 문서 색인
