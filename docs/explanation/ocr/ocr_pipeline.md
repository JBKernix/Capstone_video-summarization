# OCR 파이프라인

`modules/ocr`는 샘플링된 프레임 이미지를 읽고 OCR 텍스트, 화면 유형, 간단 캡션, 중요도 점수를 생성합니다.

## 실행 흐름

```text
analyze_frames_metadata()
  -> frame_metadata.json 로드
  -> OCRExtractor(lang) 생성
  -> EasyOCR Reader 로드
  -> 각 frame_info 반복
      -> _resolve_image_path()
      -> analyze_single_frame()
          -> extract_text_with_language()
          -> classify_scene_type()
          -> generate_text_based_caption()
          -> calculate_importance_score()
  -> ocr_result.json 저장
```

## 입력

기본 입력:

```text
runs/metadata/frame_metadata.json
```

예시:

```json
[
  {
    "frame_id": 0,
    "timestamp": 10.0,
    "image_path": "runs/frames/frame_000001.jpg",
    "sampling_method": "interval"
  }
]
```

## 출력

기본 출력:

```text
runs/ocr/ocr_result.json
```

예시:

```json
[
  {
    "frame_id": 0,
    "timestamp": 10.0,
    "image_path": "C:\\capstone\\Capstone_video-summarization\\runs\\frames\\frame_000001.jpg",
    "ocr_text": "인식된 화면 텍스트",
    "detected_language": "ko",
    "scene_type": "presentation_slide",
    "image_caption": "텍스트 정보가 포함된 화면입니다.",
    "importance_score": 0.8
  }
]
```

## 이미지 경로 복원

`_resolve_image_path()`는 metadata에 저장된 경로를 실제 이미지 파일 경로로 복원합니다.

확인 순서:

1. 절대 경로이면 그대로 사용합니다.
2. 현재 작업 디렉터리 기준 경로를 확인합니다.
3. `modules/`와 `scripts/`가 함께 있는 프로젝트 루트 기준 경로를 확인합니다.
4. metadata 파일 위치와 그 상위 디렉터리 기준 경로를 확인합니다.
5. 실제 파일을 찾지 못하면 첫 번째 후보 경로를 반환합니다.

## 화면 유형

`classify_scene_type()`은 OCR 텍스트 키워드 기반으로 화면 유형을 추정합니다.

| 유형 | 의미 |
| --- | --- |
| `generic_scene` | OCR 텍스트가 거의 없음 |
| `text_screen` | 일반 텍스트 화면 |
| `presentation_slide` | 발표 자료 또는 슬라이드로 보이는 화면 |
| `chart_or_table` | 표, 그래프, 결과 화면으로 보이는 화면 |

## 중요도 점수

`calculate_importance_score()`는 0.0에서 1.0 사이 점수를 만듭니다.

| 조건 | 점수 |
| --- | --- |
| 기본값 | `0.3` |
| OCR 텍스트 존재 | `+0.3` |
| OCR 텍스트 길이 20자 초과 | `+0.2` |
| `presentation_slide` 또는 `chart_or_table` | `+0.2` |

최종 점수는 `1.0`을 넘지 않습니다.

## 실패 처리

- 개별 프레임 분석 실패는 로그를 남기고 다음 프레임으로 진행합니다.
- 모든 프레임이 실패하면 `RuntimeError`가 발생합니다.
- metadata 파일이 없으면 `FileNotFoundError`가 발생합니다.

## CLI

```bash
python scripts/run_ocr.py
```

현재 `run_ocr.py`는 기본 경로만 사용합니다. 다른 metadata/output 경로가 필요하면 `analyze_frames_metadata()`를 직접 호출하거나 스크립트 확장이 필요합니다.
