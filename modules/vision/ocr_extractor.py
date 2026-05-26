# modules/vision/ocr_extractor.py

from pathlib import Path
from typing import Any, Dict, List
import os
import re
import sysconfig


def _add_paddle_cuda_dll_path() -> None:
    site_packages = Path(sysconfig.get_paths()["purelib"])
    nvidia_dir = site_packages / "nvidia"

    if not nvidia_dir.is_dir():
        return

    dll_dirs = sorted({dll.parent for dll in nvidia_dir.rglob("*.dll")})
    if not dll_dirs:
        return

    dll_path = os.pathsep.join(str(path) for path in dll_dirs)
    os.environ["PATH"] = dll_path + os.pathsep + os.environ.get("PATH", "")

    if hasattr(os, "add_dll_directory"):
        for dll_dir in dll_dirs:
            os.add_dll_directory(str(dll_dir))


def detect_text_language(text: str) -> str:
    """OCR 텍스트의 언어 유형을 ko, en, mixed, unknown 중 하나로 반환합니다.

    Args:
        text: 언어를 판별할 OCR 텍스트입니다.

    Returns:
        감지된 언어 코드입니다. 한글만 있으면 "ko", 영문만 있으면 "en",
        둘 다 있으면 "mixed", 둘 다 없으면 "unknown"을 반환합니다.
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


class OCRExtractor:
    """PaddleOCR 3.x를 사용해 프레임 이미지에서 OCR 정보를 추출합니다.

    Args:
        lang: PaddleOCR에 전달할 언어 코드입니다. 예: "korean", "en".

    Typical usage:
        extractor = OCRExtractor(lang="korean")
        text = extractor.extract_text("runs/sample/frames/frame_000001.jpg")
    """

    def __init__(self, lang: str):
        self.lang = lang
        self.ocr = None
        self._load_error = None

    def load_model(self):
        """PaddleOCR 모델을 초기화합니다.

        모델은 OCR이 처음 필요할 때 한 번만 로드되며, 이후 프레임 분석에서는
        같은 모델 인스턴스를 재사용합니다.
        """
        if self.ocr is not None:
            return
        if self._load_error is not None:
            raise RuntimeError(self._load_error)

        try:
            import torch  # noqa: F401
        except Exception:
            pass

        _add_paddle_cuda_dll_path()

        try:
            import paddle
            from paddleocr import PaddleOCR
        except ImportError as e:
            raise ImportError(
                "paddleocr가 설치되어 있지 않습니다. "
                "pip install paddleocr paddlepaddle 명령으로 설치하세요."
            ) from e

        device = "cpu"
        if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            device = "gpu"
            paddle.set_device("gpu")

        # 현재 환경은 GPU 대신 CPU를 사용합니다.
        # 문서 방향/보정/텍스트라인 방향 모델은 프레임 OCR에 필수는 아니므로 끕니다.
        # enable_mkldnn=False는 Windows CPU 환경의 oneDNN 관련 실행 오류를 피하기 위한 설정입니다.
        try:
            self.ocr = PaddleOCR(
                lang=self.lang,
                device=device,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
            )
        except Exception as e:
            self._load_error = (
                "PaddleOCR model initialization failed. "
                "Check whether paddlepaddle can be imported in the current Python environment. "
                f"Cause: {e}"
            )
            raise RuntimeError(self._load_error) from e

    def _run_ocr(self, image_path: str):
        """이미지 파일에 대해 PaddleOCR 예측을 실행합니다.

        Args:
            image_path: OCR을 수행할 이미지 파일 경로입니다.

        Returns:
            PaddleOCR 3.x의 predict() 결과 객체 리스트입니다.
        """
        image_path = Path(image_path)

        if not image_path.is_file():
            raise FileNotFoundError(f"OCR을 실행할 이미지 파일이 존재하지 않습니다: {image_path}")

        # PaddleOCR 모델은 첫 OCR 요청 시 한 번만 로드합니다.
        if self.ocr is None:
            self.load_model()

        # PaddleOCR 3.x에서는 ocr() 대신 predict()를 사용합니다.
        return self.ocr.predict(str(image_path))

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
        """PaddleOCR 3.x predict() 결과를 프로젝트 공통 OCR 형식으로 변환합니다.

        Args:
            result: PaddleOCR 3.x ``predict()``가 반환한 결과 리스트입니다.

        Returns:
            각 OCR 라인의 ``text``, ``confidence``, ``bbox``, ``detected_language``를
            담은 딕셔너리 리스트입니다.
        """
        parsed = []

        if not result:
            return parsed

        for page_result in result:
            data = page_result

            # PaddleOCR 3.x OCRResult는 json 속성 또는 json() 메서드로 결과를 제공합니다.
            if hasattr(page_result, "json"):
                data = page_result.json
            if callable(data):
                data = data()

            # 일부 결과는 {"res": {...}} 형태로 감싸져 있어 실제 결과만 꺼냅니다.
            if isinstance(data, dict) and "res" in data:
                data = data["res"]

            # 현재 코드는 PaddleOCR 3.x predict() 결과 형식만 처리합니다.
            if not isinstance(data, dict) or "rec_texts" not in data:
                continue

            texts = data.get("rec_texts") or []
            scores = data.get("rec_scores") or []
            boxes = data.get("rec_polys") or data.get("rec_boxes") or []

            for index, text in enumerate(texts):
                if not text:
                    continue

                confidence = scores[index] if index < len(scores) else 0.0
                bbox = boxes[index] if index < len(boxes) else []

                # numpy 배열 형태의 좌표는 JSON 저장 가능한 리스트로 변환합니다.
                if hasattr(bbox, "tolist"):
                    bbox = bbox.tolist()

                text = str(text)
                parsed.append(
                    {
                        "text": text,
                        "confidence": float(confidence),
                        "bbox": bbox,
                        "detected_language": detect_text_language(text),
                    }
                )

        return parsed
