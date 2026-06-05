# Vision Pipeline

## 개요

`modules/vision`은 추출된 프레임 이미지에서 OCR 텍스트를 얻고, 그 텍스트를 기반으로 화면 유형, 간단한 캡션, 중요도 점수를 만든다.

현재 OCR 엔진은 EasyOCR이다. 기존 PaddleOCR/PaddlePaddle 의존성은 제거되었고, Whisper와 같은 PyTorch 계열 런타임을 사용한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `scripts/run_vision.py` | vision 단계 단독 실행 스크립트 |
| `modules/vision/vision_formatter.py` | 프레임 metadata를 읽고 프레임별 분석 결과를 JSON으로 저장 |
| `modules/vision/ocr_extractor.py` | EasyOCR 모델 로딩, OCR 실행, 결과 파싱 |
| `modules/vision/image_caption.py` | OCR 텍스트 기반 화면 유형 분류와 캡션 생성 |
| `modules/vision/__init__.py` | vision 모듈 public API export |

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
              -> readtext()
              -> _parse_ocr_result()
              -> detect_text_language()
          -> classify_scene_type()
          -> generate_text_based_caption()
          -> calculate_importance_score()
  -> vision_result.json 저장
```

## 입력

vision 단계의 기본 입력은 전처리 단계가 만든 metadata 파일이다.

```text
runs/metadata/frame_metadata.json
```

예시:

```json
[
  {
    "frame_id": 0,
    "timestamp": 0.0,
    "image_path": "runs/frames/frame_000001.jpg",
    "sampling_method": "interval"
  }
]
```

`image_path`는 프로젝트 루트 기준 상대경로일 수 있다.

## 출력

기본 출력 파일:

```text
runs/vision/vision_result.json
```

예시:

```json
[
  {
    "frame_id": 0,
    "timestamp": 0.0,
    "image_path": "C:\\developers_program\\Capstone\\Capstone_video-summarization\\runs\\frames\\frame_000001.jpg",
    "ocr_text": "인식된 텍스트",
    "detected_language": "ko",
    "scene_type": "text_screen",
    "image_caption": "텍스트 정보가 포함된 화면입니다.",
    "importance_score": 0.8
  }
]
```

## `vision_formatter.py`

### `_resolve_image_path()`

metadata에 저장된 이미지 경로를 실제 파일 경로로 복원한다.

처리 방식:

1. 절대경로면 그대로 반환한다.
2. 상대경로면 metadata 위치의 상위 폴더를 훑는다.
3. `modules/`와 `scripts/`가 함께 있는 폴더를 프로젝트 루트로 판단한다.
4. 후보 경로 중 실제 파일이 존재하는 첫 경로를 반환한다.

이 로직은 작업 디렉터리가 프로젝트 루트가 아니어도 `runs/frames/...` 경로를 안정적으로 찾기 위한 것이다.

### `analyze_frames_metadata()`

vision 단계의 중심 함수다.

처리 순서:

1. metadata JSON 파일을 `utf-8-sig`로 읽는다.
2. `OCRExtractor`를 한 번 생성하고 모델을 로드한다.
3. 각 프레임을 `analyze_single_frame()`으로 분석한다.
4. 일부 프레임 실패는 허용한다.
5. 모든 프레임이 실패하면 `RuntimeError`를 발생시킨다.
6. 성공 결과를 `vision_result.json`에 저장한다.

### `analyze_single_frame()`

프레임 하나의 분석 결과를 만든다.

반환 필드:

| 필드 | 설명 |
| --- | --- |
| `frame_id` | 프레임 순번 |
| `timestamp` | 영상 내 시간 |
| `image_path` | 분석한 이미지 경로 |
| `ocr_text` | OCR로 추출한 텍스트 |
| `detected_language` | `ko`, `en`, `mixed`, `unknown` |
| `scene_type` | 텍스트 기반 화면 유형 |
| `image_caption` | 간단한 텍스트 기반 캡션 |
| `importance_score` | 0.0부터 1.0 사이의 중요도 점수 |

### `calculate_importance_score()`

OCR 텍스트와 화면 유형을 기준으로 중요도를 계산한다.

| 조건 | 점수 |
| --- | --- |
| 기본값 | `0.3` |
| OCR 텍스트 있음 | `+0.3` |
| OCR 텍스트 길이 20자 초과 | `+0.2` |
| 화면 유형이 `presentation_slide` 또는 `chart_or_table` | `+0.2` |

최종 점수는 `1.0`을 넘지 않는다.

## `ocr_extractor.py`

OCR 처리의 세부 동작은 `vision/ocr.md`에 별도로 정리되어 있다.

### 언어 설정

프로젝트의 언어 이름을 EasyOCR 언어 코드로 변환한다.

| 입력 | EasyOCR 언어 목록 |
| --- | --- |
| `korean`, `ko`, `kor` | `["ko", "en"]` |
| `english`, `en` | `["en"]` |
| 기타 값 | 해당 값을 그대로 사용 |
| 빈 값 | `["ko", "en"]` |

한국어 OCR에서도 영어가 섞인 화면이 많기 때문에 `korean`은 `ko`와 `en`을 함께 사용한다.

### 모델 로딩

`OCRExtractor.load_model()`은 EasyOCR Reader를 한 번만 생성한다.

```python
self.ocr = easyocr.Reader(languages, gpu=torch.cuda.is_available(), verbose=False)
```

`verbose=False`는 Windows 콘솔에서 EasyOCR 다운로드 진행률 문자가 `cp949` 인코딩 오류를 일으키는 문제를 피하기 위한 설정이다.

### OCR 실행

```python
self.ocr.readtext(str(image_path), detail=1, paragraph=False)
```

`detail=1`로 텍스트, confidence, bbox를 함께 받는다. `paragraph=False`로 라인 단위 결과를 유지한다.

### 결과 파싱

EasyOCR의 결과 형식:

```python
[
    (bbox, text, confidence)
]
```

프로젝트 공통 형식:

```json
{
  "text": "인식된 텍스트",
  "confidence": 0.95,
  "bbox": [[0, 0], [100, 0], [100, 30], [0, 30]],
  "detected_language": "ko"
}
```

EasyOCR bbox에는 numpy scalar가 포함될 수 있으므로 `_to_jsonable()`로 JSON 저장 가능한 Python 기본 타입으로 변환한다.

## `image_caption.py`

OCR 텍스트를 기반으로 간단한 화면 유형과 캡션을 만든다.

대표 화면 유형:

| 유형 | 의미 |
| --- | --- |
| `text_screen` | 텍스트가 포함된 일반 화면 |
| `presentation_slide` | 발표 슬라이드로 보이는 화면 |
| `chart_or_table` | 표나 차트로 보이는 화면 |
| `visual_scene` | OCR 텍스트가 적거나 없는 화면 |

현재 캡션은 이미지 모델 기반 캡션이 아니라 OCR 텍스트 기반 휴리스틱 캡션이다.

## 주의 사항

1. EasyOCR 첫 실행 시 모델 파일을 다운로드한다.
2. 프레임 수가 많으면 OCR 단계가 오래 걸린다.
3. 한국어 OCR 결과는 글꼴, 해상도, 자막 위치에 따라 오인식이 생길 수 있다.
4. `scripts/run_vision.py`는 고정 경로를 사용하므로 일반 실행은 `scripts/run_pipeline.py`를 권장한다.
