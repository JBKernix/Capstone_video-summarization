from __future__ import annotations

import io
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from threading import Lock
from typing import Any, BinaryIO, TypeAlias

from PIL import Image, UnidentifiedImageError

from configs.inference_config import VLM_INFERENCE_CONFIG

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
        max_new_tokens: int = VLM_INFERENCE_CONFIG.default_max_new_tokens,
        frame_metadata: Mapping[str, Any] | None = None,
    ) -> str:
        """한 장의 프레임을 OCR 텍스트와 함께 분석합니다."""
        max_new_tokens = self._validate_max_new_tokens(max_new_tokens)
        pil_image = self._resize_for_vlm(self._load_image(image_path))
        metadata_text = self._format_metadata(frame_metadata)

        prompt = f"""영상 프레임과 OCR을 한국어로 간단히 분석하세요.
메타데이터: {metadata_text}
OCR: {ocr_text.strip() or "없음"}

장면:
텍스트:
요약 반영 정보:
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
        max_new_tokens: int = VLM_INFERENCE_CONFIG.default_max_new_tokens,
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
    def _resize_for_vlm(image: Image.Image) -> Image.Image:
        width, height = image.size
        longest_edge = max(width, height)
        if longest_edge <= VLM_INFERENCE_CONFIG.image_max_side:
            return image

        scale = VLM_INFERENCE_CONFIG.image_max_side / longest_edge
        resized_size = (
            max(1, round(width * scale)),
            max(1, round(height * scale)),
        )
        resized_image = image.resize(resized_size, Image.Resampling.LANCZOS)
        image.close()
        return resized_image

    @staticmethod
    def _format_metadata(metadata: Mapping[str, Any] | None) -> str:
        if not metadata:
            return "메타데이터 없음"
        keys = ("frame_id", "timestamp", "detected_language", "scene_type")
        lines = [f"- {key}: {metadata[key]}" for key in keys if key in metadata]
        return "\n".join(lines) or "메타데이터 없음"

    @staticmethod
    def _validate_max_new_tokens(max_new_tokens: int) -> int:
        if not 1 <= max_new_tokens <= VLM_INFERENCE_CONFIG.max_new_tokens_limit:
            raise ValueError(
                "max_new_tokens는 1 이상 "
                f"{VLM_INFERENCE_CONFIG.max_new_tokens_limit} 이하여야 합니다."
            )
        return max_new_tokens
