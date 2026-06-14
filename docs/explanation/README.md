# 🎥 멀티모달 기반 영상 요약 시스템

## 개요

이 폴더는 프로젝트 코드 설명 문서를 모아둔 위치다.

각 문서는 같은 기본 양식을 따른다.

```text
개요
관련 파일
실행 흐름
주요 함수 또는 주요 단계
입력/출력
예외
주의 사항 또는 현재 제한
```

## 문서 목록

| 영역 | 문서 | 설명 |
| --- | --- | --- |
| 전체 파이프라인 | `pipeline/pipeline.md` | `scripts/run_pipeline.py` 기준 전체 실행 흐름 |
| 전처리 | `preprocess/frame_sampling.md` | 프레임 추출과 metadata 생성 |
| 전처리 | `preprocess/audio_extraction.md` | 영상에서 STT용 오디오 추출 |
| 전처리 | `preprocess/video_info.md` | FFprobe 기반 영상 정보 추출 |
| 전처리 | `preprocess/ffmpeg_utils.md` | FFmpeg/FFprobe 실행 유틸리티 |
| OCR | `ocr/ocr_pipeline.md` | EasyOCR 기반 프레임 분석 |
| OCR | `ocr/ocr.md` | EasyOCR 처리 상세 |
| STT | `stt/stt.md` | Whisper 기반 음성 인식 |
| LLM | `llm/llm.md` | 요약 단계의 현재 상태와 설계 방향 |
| Common | `common/common.md` | 공통 유틸리티 모듈 |

## 현재 구현 상태 요약

| 영역 | 상태 |
| --- | --- |
| 영상 전처리 | 구현됨 |
| 프레임 추출 | 구현됨 |
| 오디오 추출 | 구현됨 |
| OCR 분석 | EasyOCR 기반으로 구현됨 |
| STT | Whisper 기반으로 구현됨 |
| LLM 요약 | 미구현 |
| UI | 미구현 또는 별도 정리 필요 |

## 최근 반영 사항

1. OCR 엔진 설명을 PaddleOCR 기준에서 EasyOCR 기준으로 갱신했다.
2. PaddleOCR/PaddlePaddle 의존성 제거 상태를 문서에 반영했다.
3. 프레임 이미지 상대경로 복원 로직을 `modules/`와 `scripts/` 기준 프로젝트 루트 탐색 방식으로 설명했다.
4. LLM 요약 단계가 아직 구현되지 않았다는 점을 명확히 분리했다.
