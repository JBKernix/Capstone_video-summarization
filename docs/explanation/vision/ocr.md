# OCR

## 개요

OCR 단계는 추출된 프레임 이미지에서 화면 텍스트를 읽어 `vision_result.json`에 들어갈 `ocr_text`, `detected_language`, `bbox`, `confidence` 정보를 만든다.

현재 OCR 엔진은 EasyOCR이다. 기존 PaddleOCR/PaddlePaddle 기반 구현은 제거되었고, Whisper STT와 같은 PyTorch 계열 런타임을 사용한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/vision/ocr_extractor.py` | EasyOCR Reader 로딩, OCR 실행, 결과 파싱 |
| `modules/vision/vision_formatter.py` | 프레임 metadata를 읽고 OCR 결과를 시각 정보로 통합 |
| `modules/vision/image_caption.py` | OCR 텍스트를 기반으로 화면 유형과 캡션 생성 |
| `docs/explanation/vision/vision.md` | vision 단계 전체 흐름 설명 |

## 실행 흐름

```text
analyze_frames_metadata()
  -> OCRExtractor(lang) 생성
  -> OCRExtractor.load_model()
      -> easyocr import
      -> torch.cuda.is_available() 확인
      -> easyocr.Reader(languages, gpu=gpu, verbose=False)
  -> 각 프레임 반복
      -> _resolve_image_path()
      -> OCRExtractor.extract_text_with_language()
          -> _run_ocr()
              -> readtext(image_path, detail=1, paragraph=False)
          -> _parse_ocr_result()
          -> detect_text_language()
```

## 입력

OCR이 직접 처리하는 입력은 프레임 이미지 파일이다.

```text
runs/frames/interval_000001.jpg
```

프레임 경로는 `frame_metadata.json`에서 읽는다.

```json
{
  "frame_id": 0,
  "timestamp": 0.0,
  "image_path": "runs/frames/interval_000001.jpg",
  "sampling_method": "interval"
}
```

## 출력

OCR 결과는 프레임별 vision 결과에 포함된다.

```json
{
  "ocr_text": "인식된 텍스트",
  "detected_language": "ko"
}
```

상세 OCR 결과 형식은 `extract_text_with_details()`에서 사용한다.

```json
{
  "text": "인식된 텍스트",
  "confidence": 0.95,
  "bbox": [[0, 0], [100, 0], [100, 30], [0, 30]],
  "detected_language": "ko"
}
```

## 언어 설정

`OCRExtractor`는 프로젝트 언어 설정을 EasyOCR 언어 코드로 변환한다.

| 입력 | EasyOCR 언어 목록 |
| --- | --- |
| `korean`, `ko`, `kor` | `["ko", "en"]` |
| `english`, `en` | `["en"]` |
| 빈 값 | `["ko", "en"]` |
| 기타 값 | 해당 값을 그대로 사용 |

한국어 화면에도 영어, 숫자, 약어가 섞이는 경우가 많기 때문에 `korean`은 `ko`와 `en`을 함께 사용한다.

## 모델 로딩

EasyOCR Reader는 프레임마다 새로 만들지 않고 한 번만 로드해 재사용한다.

```python
self.ocr = easyocr.Reader(languages, gpu=gpu, verbose=False)
```

| 설정 | 설명 |
| --- | --- |
| `languages` | EasyOCR 언어 코드 목록 |
| `gpu` | `torch.cuda.is_available()` 결과 |
| `verbose=False` | Windows 콘솔의 진행률 문자 인코딩 오류 방지 |

첫 실행 시 EasyOCR 모델 파일을 다운로드할 수 있다.

## OCR 실행

EasyOCR 호출은 다음 형태다.

```python
self.ocr.readtext(str(image_path), detail=1, paragraph=False)
```

| 옵션 | 설명 |
| --- | --- |
| `detail=1` | bbox, text, confidence를 함께 반환 |
| `paragraph=False` | 문단 병합 없이 라인 단위 결과 유지 |

## 결과 파싱

EasyOCR 원본 결과는 보통 다음 형식이다.

```python
[
    (bbox, text, confidence)
]
```

`_parse_ocr_result()`는 이 값을 프로젝트 공통 OCR 형식으로 바꾼다.

처리 내용:

1. 잘못된 항목은 건너뛴다.
2. 빈 문자열은 결과에서 제외한다.
3. confidence를 float로 저장한다.
4. bbox 안의 numpy 값을 JSON 저장 가능한 Python 기본 타입으로 변환한다.
5. 텍스트별 언어를 `detect_text_language()`로 판별한다.

## 언어 판별

`detect_text_language()`는 OCR 텍스트 안의 한글과 영문 포함 여부로 언어 유형을 판별한다.

| 결과 | 조건 |
| --- | --- |
| `ko` | 한글만 있음 |
| `en` | 영문만 있음 |
| `mixed` | 한글과 영문이 함께 있음 |
| `unknown` | 한글과 영문이 모두 없음 |

## 예외

| 상황 | 예외 |
| --- | --- |
| 이미지 파일이 없음 | `FileNotFoundError` |
| easyocr 또는 torch 미설치 | `ImportError` |
| EasyOCR Reader 초기화 실패 | `RuntimeError` |

## 주의 사항

1. 프레임 수가 많으면 OCR 단계가 오래 걸린다.
2. 한국어 OCR은 글꼴, 자막 크기, 해상도, 배경 대비에 따라 오인식이 생길 수 있다.
3. bbox에는 numpy scalar가 섞일 수 있으므로 JSON 저장 전에 변환이 필요하다.
4. 작업 디렉터리가 달라도 이미지 경로를 찾을 수 있도록 `vision_formatter.py`에서 프로젝트 루트를 탐색한다.
