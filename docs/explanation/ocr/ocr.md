# OCR 모듈

`modules/ocr/ocr_extractor.py`는 EasyOCR를 사용해 프레임 이미지에서 텍스트를 추출합니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/ocr/ocr_extractor.py` | EasyOCR Reader 로딩, OCR 실행, 결과 파싱 |
| `modules/ocr/ocr_formatter.py` | 프레임 메타데이터 기반 OCR 결과 생성 |
| `modules/ocr/image_caption.py` | OCR 텍스트 기반 화면 유형과 간단 캡션 생성 |
| `scripts/run_ocr.py` | OCR 단독 실행 |

## 언어 설정

기본값은 `korean`입니다.

| 입력 | EasyOCR 언어 목록 |
| --- | --- |
| `korean`, `ko`, `kor` | `["ko", "en"]` |
| `english`, `en` | `["en"]` |
| 빈 값 | `["ko", "en"]` |
| 기타 값 | 해당 값을 그대로 사용 |

한국어 화면에도 영어, 숫자, 약어가 섞이는 경우가 많아 한국어 기본 설정은 `ko`, `en`을 함께 사용합니다.

## 모델 로딩

`OCRExtractor.load_model()`은 EasyOCR Reader를 한 번만 생성하고 재사용합니다.

```python
self.ocr = easyocr.Reader(languages, gpu=torch.cuda.is_available(), verbose=False)
```

`verbose=False`는 Windows 콘솔에서 EasyOCR 진행 출력이 인코딩 문제를 일으키는 경우를 줄이기 위한 설정입니다.

## OCR 실행

```python
self.ocr.readtext(str(image_path), detail=1, paragraph=False)
```

| 옵션 | 설명 |
| --- | --- |
| `detail=1` | bbox, text, confidence를 함께 반환 |
| `paragraph=False` | 문단 병합 없이 라인 단위 결과 유지 |

EasyOCR 원본 결과:

```python
[
    (bbox, text, confidence)
]
```

프로젝트 공통 결과:

```json
{
  "text": "인식된 텍스트",
  "confidence": 0.95,
  "bbox": [[0, 0], [100, 0], [100, 30], [0, 30]],
  "detected_language": "ko"
}
```

## 언어 감지

`detect_text_language()`은 OCR 텍스트 안의 한글과 영문 포함 여부를 기준으로 분류합니다.

| 결과 | 조건 |
| --- | --- |
| `ko` | 한글만 있음 |
| `en` | 영문만 있음 |
| `mixed` | 한글과 영문이 함께 있음 |
| `unknown` | 한글과 영문이 모두 없음 |

## 공개 메서드

| 메서드 | 반환 |
| --- | --- |
| `extract_text(image_path)` | OCR 텍스트를 공백으로 합친 문자열 |
| `extract_text_with_language(image_path)` | `ocr_text`, `detected_language` 딕셔너리 |
| `extract_text_with_details(image_path)` | bbox/confidence를 포함한 상세 리스트 |

## 예외

| 상황 | 예외 |
| --- | --- |
| 이미지 파일 없음 | `FileNotFoundError` |
| `easyocr` 또는 `torch` 미설치 | `ImportError` |
| EasyOCR Reader 초기화 실패 | `RuntimeError` |

## 주의 사항

- 첫 실행 시 EasyOCR 모델 파일 다운로드가 필요할 수 있습니다.
- 프레임 수가 많으면 OCR 시간이 길어집니다.
- bbox에는 numpy scalar가 섞일 수 있어 저장 전 JSON 가능 타입으로 변환합니다.
