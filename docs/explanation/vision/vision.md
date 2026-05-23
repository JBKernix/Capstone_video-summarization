# Vision Pipeline

이 문서는 `modules/vision` 모듈과 `scripts/run_vision.py`가 프레임 이미지에서 시각 정보를 추출하는 흐름을 설명한다. 현재 vision 파이프라인은 프레임 메타데이터 JSON을 입력으로 받아 각 프레임 이미지에 OCR을 수행하고, OCR 텍스트를 기반으로 장면 유형, 간단한 캡션, 중요도 점수를 생성한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `scripts/run_vision.py` | vision 파이프라인 실행 진입점 |
| `modules/vision/vision_formatter.py` | 프레임 메타데이터를 읽고 프레임별 분석 결과를 JSON으로 저장 |
| `modules/vision/ocr_extractor.py` | PaddleOCR 3.x를 사용해 이미지에서 OCR 텍스트와 세부 정보를 추출 |
| `modules/vision/image_caption.py` | OCR 텍스트를 기반으로 장면 유형과 텍스트 기반 캡션 생성 |

## 전체 실행 흐름

```text
scripts/run_vision.py
    -> analyze_frames_metadata()
        -> OCRExtractor(lang="korean") 생성
        -> frame_metadata.json 로드
        -> 각 frame_info 반복
            -> analyze_single_frame()
                -> OCRExtractor.extract_text_with_language()
                    -> _run_ocr()
                        -> load_model()
                        -> PaddleOCR.predict(image_path)
                    -> _parse_ocr_result()
                    -> detect_text_language()
                -> classify_scene_type()
                -> generate_text_based_caption()
                -> calculate_importance_score()
            -> 결과 리스트에 추가
        -> vision_result.json 저장
```

## 1. `scripts/run_vision.py`

`run_vision.py`는 vision 파이프라인을 실행하는 스크립트다.

```python
run_dir = PROJECT_ROOT / "runs" / "sample"
metadata_path = run_dir / "metadata" / "frame_metadata.json"
output_path = run_dir / "vision" / "vision_result.json"
```

이 스크립트는 프로젝트 루트를 기준으로 `runs/sample` 디렉터리를 찾는다. 따라서 어느 위치에서 실행하더라도 동일한 샘플 입력과 출력 경로를 사용한다.

실행 시 호출되는 핵심 함수는 다음과 같다.

```python
analyze_frames_metadata(
    metadata_path=str(metadata_path),
    output_path=str(output_path),
    lang="korean",
)
```

`lang="korean"`은 PaddleOCR에 전달되는 언어 설정이다.

## 2. `vision_formatter.py`

`vision_formatter.py`는 프레임 단위 분석 흐름을 조립하고 결과 JSON을 저장한다.

### `analyze_frames_metadata()`

이 함수는 전체 vision 파이프라인의 중심 함수다.

역할은 다음과 같다.

1. `frame_metadata.json` 파일을 읽는다.
2. `OCRExtractor`를 한 번 생성한다.
3. 각 프레임 메타데이터를 순회하며 `analyze_single_frame()`을 호출한다.
4. 성공한 분석 결과를 리스트에 저장한다.
5. 모든 프레임이 실패하면 `RuntimeError`를 발생시킨다.
6. 성공한 결과를 `vision_result.json`으로 저장한다.

메타데이터 파일은 다음처럼 읽는다.

```python
with open(metadata_path, "r", encoding="utf-8-sig") as f:
    frames_metadata = json.load(f)
```

`utf-8-sig`를 사용하는 이유는 Windows 환경에서 JSON 파일에 UTF-8 BOM이 붙어도 정상적으로 읽기 위해서다.

### `analyze_single_frame()`

이 함수는 프레임 하나를 분석한다.

입력으로 받는 `frame_info`는 다음 필드를 가진다.

```json
{
  "frame_id": 0,
  "timestamp": 0,
  "image_path": "runs/sample/frames/frame_000001.jpg"
}
```

처리 순서는 다음과 같다.

1. `image_path`를 가져온다.
2. OCR 텍스트와 감지 언어를 추출한다.
3. OCR 텍스트를 기반으로 장면 유형을 분류한다.
4. OCR 텍스트 양을 기반으로 간단한 캡션을 만든다.
5. OCR 텍스트와 장면 유형을 기반으로 중요도 점수를 계산한다.
6. 결과 딕셔너리를 반환한다.

반환 형식은 다음과 같다.

```json
{
  "frame_id": 0,
  "timestamp": 0,
  "image_path": "runs/sample/frames/frame_000001.jpg",
  "ocr_text": "...",
  "detected_language": "mixed",
  "scene_type": "presentation_slide",
  "image_caption": "비교적 많은 텍스트 정보가 포함된 장면입니다.",
  "importance_score": 1.0
}
```

### `calculate_importance_score()`

OCR 텍스트와 장면 유형을 기준으로 중요도 점수를 계산한다.

기본 점수는 `0.3`이다.

| 조건 | 추가 점수 |
| --- | --- |
| OCR 텍스트가 있음 | `+0.3` |
| OCR 텍스트 길이가 20자 초과 | `+0.2` |
| 장면 유형이 `presentation_slide` 또는 `chart_or_table` | `+0.2` |

최종 점수는 `1.0`을 넘지 않도록 제한한다.

## 3. `ocr_extractor.py`

`ocr_extractor.py`는 PaddleOCR 3.x 기반 OCR 추출을 담당한다.

### `OCRExtractor`

`OCRExtractor`는 프레임 이미지에 OCR을 수행하는 클래스다.

사용 예시는 다음과 같다.

```python
extractor = OCRExtractor(lang="korean")
text = extractor.extract_text("runs/sample/frames/frame_000001.jpg")
```

### 모델 로드 방식

PaddleOCR 모델은 객체 생성 시 바로 로드하지 않는다. 첫 OCR 요청이 들어오면 `_run_ocr()`에서 `load_model()`을 호출해 한 번만 로드한다.

```python
if self.ocr is None:
    self.load_model()
```

이후 프레임들은 같은 모델 인스턴스를 재사용한다. 프레임마다 모델을 다시 만들지 않기 때문에 반복 분석 비용을 줄일 수 있다.

### PaddleOCR 설정

현재 PaddleOCR 초기화 설정은 다음과 같다.

```python
self.ocr = PaddleOCR(
    lang=self.lang,
    device="cpu",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    enable_mkldnn=False,
)
```

각 설정의 의미는 다음과 같다.

| 설정 | 의미 |
| --- | --- |
| `device="cpu"` | 현재 환경에서 GPU 대신 CPU로 실행 |
| `use_doc_orientation_classify=False` | 문서 방향 분류 모델 비활성화 |
| `use_doc_unwarping=False` | 문서 보정 모델 비활성화 |
| `use_textline_orientation=False` | 텍스트라인 방향 분류 모델 비활성화 |
| `enable_mkldnn=False` | Windows CPU 환경의 oneDNN 관련 오류 회피 |

프레임 이미지 OCR에는 문서 방향 분류나 문서 보정 모델이 필수적이지 않으므로 비활성화했다.

### OCR 실행

PaddleOCR 3.x에서는 구버전의 `ocr()` 호출 대신 `predict()`를 사용한다.

```python
return self.ocr.predict(str(image_path))
```

`_run_ocr()`는 이미지 파일이 실제로 존재하는지도 검사한다. 파일이 없으면 `FileNotFoundError`를 발생시킨다.

### 결과 파싱

`_parse_ocr_result()`는 PaddleOCR 3.x의 `predict()` 결과를 프로젝트에서 쓰기 쉬운 딕셔너리 리스트로 변환한다.

PaddleOCR 결과에서 주로 사용하는 필드는 다음과 같다.

| 필드 | 의미 |
| --- | --- |
| `rec_texts` | 인식된 텍스트 목록 |
| `rec_scores` | 각 텍스트의 신뢰도 목록 |
| `rec_polys` 또는 `rec_boxes` | 각 텍스트의 위치 좌표 |

변환 결과는 다음 형식이다.

```json
[
  {
    "text": "인식된 텍스트",
    "confidence": 0.98,
    "bbox": [[0, 0], [100, 0], [100, 30], [0, 30]],
    "detected_language": "ko"
  }
]
```

좌표값이 numpy 배열 형태로 들어오는 경우 JSON 저장이 가능하도록 `tolist()`로 리스트로 변환한다.

### 언어 감지

`detect_text_language()`는 OCR 텍스트에 한글과 영문이 포함되어 있는지 간단한 정규식으로 확인한다.

반환값은 다음 중 하나다.

| 반환값 | 의미 |
| --- | --- |
| `ko` | 한글만 포함 |
| `en` | 영문만 포함 |
| `mixed` | 한글과 영문이 모두 포함 |
| `unknown` | 한글과 영문 모두 없음 |

## 4. `image_caption.py`

`image_caption.py`는 OCR 결과를 기반으로 장면을 간단히 해석한다. 현재는 이미지 자체를 분석하는 모델을 사용하지 않고 OCR 텍스트만 사용한다.

### `generate_text_based_caption()`

OCR 텍스트 양에 따라 간단한 설명 문장을 만든다.

| 조건 | 반환 문장 |
| --- | --- |
| OCR 텍스트 없음 | `텍스트 정보가 거의 없는 장면입니다.` |
| OCR 텍스트 길이 30자 이상 | `비교적 많은 텍스트 정보가 포함된 장면입니다.` |
| 그 외 | `텍스트 정보가 포함된 장면입니다.` |

이미지 경로가 실제로 존재하지 않으면 `FileNotFoundError`를 발생시킨다.

### `classify_scene_type()`

OCR 텍스트에 포함된 키워드를 기준으로 장면 유형을 분류한다.

반환값은 다음 중 하나다.

| 반환값 | 의미 |
| --- | --- |
| `generic_scene` | OCR 텍스트가 없는 일반 장면 |
| `chart_or_table` | 표, 그래프, 성능 지표 등이 포함된 장면 |
| `presentation_slide` | 목차, 개요, 요약, 시스템 등 발표 자료 성격의 장면 |
| `text_screen` | 텍스트는 있지만 위 조건에 해당하지 않는 장면 |

분류 우선순위는 `chart_or_table`이 `presentation_slide`보다 앞선다. 즉, OCR 텍스트에 차트 관련 키워드와 발표 자료 키워드가 모두 있으면 `chart_or_table`로 분류된다.

## 입력 파일 형식

`runs/sample/metadata/frame_metadata.json`은 프레임 목록을 담은 JSON 배열이다.

```json
[
  {
    "frame_id": 0,
    "timestamp": 0,
    "image_path": "runs/sample/frames/frame_000001.jpg"
  },
  {
    "frame_id": 1,
    "timestamp": 5,
    "image_path": "runs/sample/frames/frame_000002.jpg"
  }
]
```

| 필드 | 의미 |
| --- | --- |
| `frame_id` | 프레임 식별자 |
| `timestamp` | 영상 내 시각 정보 |
| `image_path` | OCR을 수행할 프레임 이미지 경로 |

## 출력 파일 형식

`runs/sample/vision/vision_result.json`은 프레임별 분석 결과를 담은 JSON 배열이다.

```json
[
  {
    "frame_id": 0,
    "timestamp": 0,
    "image_path": "runs/sample/frames/frame_000001.jpg",
    "ocr_text": "...",
    "detected_language": "mixed",
    "scene_type": "presentation_slide",
    "image_caption": "비교적 많은 텍스트 정보가 포함된 장면입니다.",
    "importance_score": 1.0
  }
]
```

| 필드 | 의미 |
| --- | --- |
| `frame_id` | 입력 메타데이터의 프레임 식별자 |
| `timestamp` | 입력 메타데이터의 타임스탬프 |
| `image_path` | 분석한 프레임 이미지 경로 |
| `ocr_text` | OCR로 인식한 텍스트 |
| `detected_language` | OCR 텍스트의 간단한 언어 감지 결과 |
| `scene_type` | OCR 키워드 기반 장면 유형 |
| `image_caption` | OCR 텍스트 기반 장면 설명 |
| `importance_score` | 후속 요약 단계에서 사용할 수 있는 중요도 점수 |

## 실패 처리

프레임 하나에서 오류가 발생해도 전체 처리를 즉시 중단하지 않는다. 실패한 프레임은 로그로 남기고 다음 프레임 분석을 계속 진행한다.

```text
프레임 분석 중 오류 발생 (frame_id: 1) error=...
```

다만 모든 프레임 분석이 실패해 결과가 하나도 없으면 `RuntimeError`를 발생시킨다.

```python
if not results:
    raise RuntimeError(...)
```

이렇게 하면 결과가 비어 있는데도 정상 완료처럼 보이는 상황을 막을 수 있다.

## 현재 한계

현재 vision 파이프라인은 OCR 중심으로 동작한다. 따라서 실제 이미지 장면을 이해하는 이미지 캡션 모델은 아직 사용하지 않는다.

주요 한계는 다음과 같다.

1. `image_caption`은 이미지 픽셀 내용이 아니라 OCR 텍스트 양만 보고 설명을 만든다.
2. `scene_type`은 키워드 기반 규칙으로 분류하므로 복잡한 화면 의미를 정확히 이해하지는 못한다.
3. OCR 언어 감지는 한글/영문 포함 여부만 보는 단순 규칙이다.
4. 중요도 점수는 휴리스틱 기반이므로 학습된 점수는 아니다.

이 구조는 후속 단계에서 이미지 캡션 모델, 더 정교한 장면 분류기, 요약 모델을 붙이기 전의 기본 시각 정보 추출 단계로 볼 수 있다.