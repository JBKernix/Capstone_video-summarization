from __future__ import annotations

import io
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from threading import Lock
from typing import Any, BinaryIO, TypeAlias

from PIL import Image, UnidentifiedImageError

DEFAULT_MAX_NEW_TOKENS = 512
MAX_NEW_TOKENS = 2048

ImageInput: TypeAlias = str | Path | bytes | bytearray | BinaryIO | Image.Image
OCRInput: TypeAlias = str | Path | list[dict[str, Any]] | dict[str, Any]
ProgressCallback = Callable[[str, int, int], None]


class VLMService:
    def __init__(self, generation_lock=None, loader=None):
        if loader is None:
            from models.vlm_loader import VLMConfig, VLMLoader

            config = VLMConfig(
                device="cuda",
                torch_dtype="float16",
            )
            loader = VLMLoader(config)
        self.loader = loader
        # LLM과 VLM이 같은 GPU를 동시에 점유하지 않도록 공용 lock을 사용합니다.
        self._generation_lock = generation_lock or Lock()

    def unload(self) -> None:
        with self._generation_lock:
            self.loader.unload()

    def summarize_frame(
        self,
        image_path: ImageInput,
        ocr_text: str = "",
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        frame_metadata: Mapping[str, Any] | None = None,
    ) -> str:
        """한 장의 프레임을 OCR 텍스트와 함께 분석합니다."""
        max_new_tokens = self._validate_max_new_tokens(max_new_tokens)
        pil_image = self._load_image(image_path)
        metadata_text = self._format_metadata(frame_metadata)

        prompt = f"""
다음 이미지는 영상에서 추출한 한 프레임입니다.

[프레임 메타데이터]
{metadata_text}

[OCR 분석 결과]
{ocr_text.strip() or "OCR 텍스트 없음"}

이미지와 OCR 결과를 함께 참고하여 한국어로 분석해 주세요.

[분석 기준]
1. 화면에서 실제로 확인되는 장면과 주요 객체를 설명
2. 발표 자료, 웹 페이지, 차트, 표, 코드, 문서 등의 화면 유형을 식별
3. OCR 텍스트 중 이미지 내용과 관련 있는 핵심 정보만 반영
4. 영상 요약에 도움이 되는 시각 정보를 구체적으로 정리
5. OCR이 깨졌거나 불확실한 내용은 추측하지 않기

[출력 형식]
## 프레임 시각 요약

### 장면 설명
-

### 화면 텍스트 기반 정보
-

### 영상 요약에 반영할 핵심 정보
-
"""

        try:
            with self._generation_lock:
                return self.loader.describe_image(
                    image=pil_image,
                    prompt=prompt,
                    max_new_tokens=max_new_tokens,
                )
        finally:
            pil_image.close()

    def summarize_frames(
        self,
        ocr_results: OCRInput,
        frames: Mapping[Any, ImageInput] | Sequence[ImageInput],
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        progress_callback: ProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        """OCR 결과와 여러 JPG 프레임을 매칭하여 프레임별로 분석합니다.

        ``frames``가 mapping이면 ``frame_id``, OCR의 ``image_path`` 전체 문자열,
        또는 그 파일명으로 이미지를 찾습니다. sequence이면 OCR 결과 순서와
        프레임 순서가 같아야 합니다.
        """
        entries = self.load_ocr_results(ocr_results)
        if not entries:
            return []

        matched_frames = self._match_frames(entries, frames)
        max_new_tokens = self._validate_max_new_tokens(max_new_tokens)
        results = []

        for index, (entry, image) in enumerate(
            zip(entries, matched_frames, strict=True),
            start=1,
        ):
            if progress_callback:
                progress_callback("vlm_frames", index, len(entries))

            summary = self.summarize_frame(
                image_path=image,
                ocr_text=str(entry.get("ocr_text", "")),
                max_new_tokens=max_new_tokens,
                frame_metadata=entry,
            )
            result = dict(entry)
            result["vlm_summary"] = summary
            results.append(result)

        return results

    @staticmethod
    def load_ocr_results(ocr_results: OCRInput) -> list[dict[str, Any]]:
        """OCR JSON 파일, JSON 문자열 또는 파싱된 객체를 정규화합니다."""
        data: Any
        if isinstance(ocr_results, Path):
            data = VLMService._read_json_file(ocr_results)
        elif isinstance(ocr_results, str):
            stripped = ocr_results.lstrip()
            if stripped.startswith(("[", "{")):
                try:
                    data = json.loads(ocr_results)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        "ocr_results는 유효한 JSON 문자열 또는 JSON 파일 경로여야 합니다."
                    ) from error
            else:
                data = VLMService._read_json_file(Path(ocr_results))
        else:
            data = ocr_results

        if isinstance(data, dict):
            for key in ("frames", "results", "ocr_results"):
                if key in data:
                    data = data[key]
                    break

        if not isinstance(data, list):
            raise ValueError("OCR 결과는 프레임 객체의 배열이어야 합니다.")

        normalized = []
        seen_frame_ids = set()
        for index, entry in enumerate(data):
            if not isinstance(entry, dict):
                raise ValueError(f"OCR 결과의 {index}번째 항목은 객체여야 합니다.")

            normalized_entry = dict(entry)
            frame_id = normalized_entry.get("frame_id", index)
            if frame_id in seen_frame_ids:
                raise ValueError(f"중복된 frame_id입니다: {frame_id}")
            seen_frame_ids.add(frame_id)
            normalized_entry["frame_id"] = frame_id
            normalized.append(normalized_entry)

        return normalized

    @staticmethod
    def _read_json_file(path: Path) -> Any:
        if not path.is_file():
            raise FileNotFoundError(f"OCR JSON 파일을 찾을 수 없습니다: {path}")
        with path.open("r", encoding="utf-8-sig") as file:
            return json.load(file)

    @staticmethod
    def _match_frames(
        entries: list[dict[str, Any]],
        frames: Mapping[Any, ImageInput] | Sequence[ImageInput],
    ) -> list[ImageInput]:
        if isinstance(frames, Mapping):
            matched = []
            missing = []
            for entry in entries:
                frame_id = entry["frame_id"]
                image_path = str(entry.get("image_path", ""))
                filename = Path(image_path).name if image_path else ""
                candidates = (frame_id, str(frame_id), image_path, filename)
                image = next(
                    (frames[key] for key in candidates if key and key in frames),
                    None,
                )
                if image is None:
                    missing.append(frame_id)
                else:
                    matched.append(image)

            if missing:
                raise ValueError(f"OCR 결과와 매칭되지 않은 프레임이 있습니다: {missing}")
            return matched

        if isinstance(frames, (str, bytes, bytearray)) or not isinstance(
            frames, Sequence
        ):
            raise TypeError("frames는 이미지 sequence 또는 mapping이어야 합니다.")
        if len(entries) != len(frames):
            raise ValueError(
                "OCR 결과와 프레임 수가 다릅니다: "
                f"ocr={len(entries)}, frames={len(frames)}"
            )
        return list(frames)

    @staticmethod
    def _load_image(image: ImageInput) -> Image.Image:
        try:
            if isinstance(image, Image.Image):
                return image.convert("RGB")
            if isinstance(image, (bytes, bytearray)):
                return Image.open(io.BytesIO(image)).convert("RGB")
            if hasattr(image, "read"):
                return Image.open(image).convert("RGB")

            path = Path(image)
            if not path.is_file():
                raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {path}")
            return Image.open(path).convert("RGB")
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("올바른 JPG/이미지 데이터를 읽을 수 없습니다.") from error

    @staticmethod
    def _format_metadata(metadata: Mapping[str, Any] | None) -> str:
        if not metadata:
            return "메타데이터 없음"
        keys = ("frame_id", "timestamp", "detected_language", "scene_type")
        lines = [f"- {key}: {metadata[key]}" for key in keys if key in metadata]
        return "\n".join(lines) or "메타데이터 없음"

    @staticmethod
    def _validate_max_new_tokens(max_new_tokens: int) -> int:
        if not 1 <= max_new_tokens <= MAX_NEW_TOKENS:
            raise ValueError(
                f"max_new_tokens는 1 이상 {MAX_NEW_TOKENS} 이하여야 합니다."
            )
        return max_new_tokens
