from pathlib import Path
from typing import Any, Dict, List
import re


def _normalize_easyocr_languages(lang: str) -> list[str]:
    """프로젝트 언어 설정을 EasyOCR 언어 코드 목록으로 변환합니다.

    Args:
        lang: 명령줄 인자나 설정에서 전달된 OCR 언어 이름입니다.

    Returns:
        EasyOCR Reader에 전달할 언어 코드 목록입니다.
    """
    lang = (lang or "").strip().lower()

    if lang in {"korean", "ko", "kor"}:
        return ["ko", "en"]
    if lang in {"english", "en"}:
        return ["en"]

    return [lang] if lang else ["ko", "en"]


def detect_text_language(text: str) -> str:
    """OCR 텍스트의 언어 유형을 ko, en, mixed, unknown 중 하나로 반환합니다.

    Args:
        text: 언어를 판별할 OCR 텍스트입니다.

    Returns:
        감지된 언어 코드입니다. 한글만 있으면 ``ko``, 영문만 있으면 ``en``,
        둘 다 있으면 ``mixed``, 둘 다 없으면 ``unknown``을 반환합니다.
    """
    if not text:
        return "unknown"

    korean_count = len(re.findall(r"[가-힣]", text))
    english_count = len(re.findall(r"[a-zA-Z]", text))

    if korean_count > 0 and english_count == 0:
        return "ko"
    if english_count > 0 and korean_count == 0:
        return "en"
    if korean_count > 0 and english_count > 0:
        return "mixed"
    return "unknown"


def _to_jsonable(value: Any) -> Any:
    """OCR 결과 안의 numpy 값을 JSON 저장 가능한 Python 기본 타입으로 변환합니다.

    Args:
        value: EasyOCR 결과에 포함된 bbox, numpy scalar, list, tuple 값입니다.

    Returns:
        ``json.dump``로 저장 가능한 값입니다.
    """
    if hasattr(value, "tolist"):
        return _to_jsonable(value.tolist())
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    return value


class OCRExtractor:
    """EasyOCR을 사용해 프레임 이미지에서 OCR 정보를 추출합니다.

    Args:
        lang: OCR에 사용할 언어 설정입니다. 예: ``korean``, ``ko``, ``en``.

    Typical usage:
        extractor = OCRExtractor(lang="korean")
        text = extractor.extract_text("runs/frames/frame_000001.jpg")
    """

    def __init__(self, lang: str):
        self.lang = lang
        self.ocr = None
        self._load_error = None

    def load_model(self):
        """EasyOCR Reader를 초기화합니다.

        모델은 OCR이 처음 필요할 때 한 번만 로드되며, 이후 프레임 분석에서는
        같은 Reader 인스턴스를 재사용합니다.
        """
        if self.ocr is not None:
            return
        if self._load_error is not None:
            raise RuntimeError(self._load_error)

        try:
            import easyocr
            import torch
        except ImportError as exc:
            raise ImportError(
                "easyocr가 설치되어 있지 않습니다. "
                "pip install easyocr 명령으로 설치하세요."
            ) from exc

        languages = _normalize_easyocr_languages(self.lang)
        gpu = torch.cuda.is_available()

        try:
            self.ocr = easyocr.Reader(languages, gpu=gpu, verbose=False)
        except Exception as exc:
            self._load_error = (
                "EasyOCR 모델 초기화에 실패했습니다. "
                "현재 Python 환경에서 easyocr와 torch를 정상적으로 import할 수 있는지 확인하세요. "
                f"원인: {exc}"
            )
            raise RuntimeError(self._load_error) from exc

    def _run_ocr(self, image_path: str):
        """이미지 파일에 대해 EasyOCR 인식을 실행합니다.

        Args:
            image_path: OCR을 수행할 이미지 파일 경로입니다.

        Returns:
            EasyOCR ``readtext()``가 반환한 원본 OCR 결과입니다.
        """
        image_path = Path(image_path)

        if not image_path.is_file():
            raise FileNotFoundError(f"OCR을 실행할 이미지 파일이 존재하지 않습니다: {image_path}")

        if self.ocr is None:
            self.load_model()

        return self.ocr.readtext(str(image_path), detail=1, paragraph=False)

    def extract_text(self, image_path: str) -> str:
        """이미지에서 OCR 텍스트만 추출해 하나의 문자열로 반환합니다.

        Args:
            image_path: OCR을 수행할 이미지 파일 경로입니다.

        Returns:
            OCR로 인식한 텍스트를 공백으로 이어 붙인 문자열입니다.
        """
        result = self._run_ocr(image_path)
        details = self._parse_ocr_result(result)

        texts = [item["text"] for item in details if item["text"]]
        return " ".join(texts).strip()

    def extract_text_with_language(self, image_path: str) -> Dict[str, Any]:
        """이미지에서 OCR 텍스트와 감지 언어를 함께 반환합니다.

        Args:
            image_path: OCR을 수행할 이미지 파일 경로입니다.

        Returns:
            ``ocr_text``와 ``detected_language`` 키를 가진 딕셔너리입니다.
        """
        text = self.extract_text(image_path)
        return {"ocr_text": text, "detected_language": detect_text_language(text)}

    def extract_text_with_details(self, image_path: str) -> List[Dict[str, Any]]:
        """이미지에서 OCR 텍스트, 신뢰도, 좌표, 감지 언어를 추출합니다.

        Args:
            image_path: OCR을 수행할 이미지 파일 경로입니다.

        Returns:
            각 OCR 라인의 ``text``, ``confidence``, ``bbox``, ``detected_language``를
            담은 딕셔너리 리스트입니다.
        """
        result = self._run_ocr(image_path)
        return self._parse_ocr_result(result)

    @staticmethod
    def _parse_ocr_result(result: List[Any]) -> List[Dict[str, Any]]:
        """EasyOCR 결과를 프로젝트 공통 OCR 형식으로 변환합니다.

        Args:
            result: EasyOCR ``readtext()``가 반환한 결과 리스트입니다.

        Returns:
            각 OCR 라인의 ``text``, ``confidence``, ``bbox``, ``detected_language``를
            담은 딕셔너리 리스트입니다.
        """
        parsed = []

        for item in result or []:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue

            bbox = item[0]
            text = str(item[1]).strip()
            confidence = item[2] if len(item) > 2 else 0.0

            if not text:
                continue

            bbox = _to_jsonable(bbox)

            parsed.append(
                {
                    "text": text,
                    "confidence": float(confidence),
                    "bbox": bbox,
                    "detected_language": detect_text_language(text),
                }
            )

        return parsed
