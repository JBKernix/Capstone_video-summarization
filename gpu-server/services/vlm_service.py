from __future__ import annotations

import io
import json
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from threading import Lock
from typing import Any, BinaryIO, TypeAlias

from PIL import Image, UnidentifiedImageError

from configs.inference_config import VLM_INFERENCE_CONFIG

ImageInput: TypeAlias = str | Path | bytes | bytearray | BinaryIO | Image.Image
OCRInput: TypeAlias = str | Path | list[dict[str, Any]] | dict[str, Any]
ProgressCallback = Callable[[str, int, int], None]

SCREEN_TYPES = ("슬라이드", "판서", "코드", "표", "그래프", "수식", "도식", "강사 화면", "기타")
LECTURER_SCREEN = "강사 화면"
# 공백·구분자를 지운 항목 이름 → 필드 이름입니다. 모델이 표기를 조금 바꿔도 읽을 수 있게 합니다.
FIELD_LABELS = {
    "화면유형": "screen_type",
    "유형": "screen_type",
    "제목": "title",
    "핵심내용": "content",
    "내용": "content",
    "수식·코드·수치": "formula",
    "수식·코드": "formula",
    "수식": "formula",
    "코드": "formula",
    "수치": "formula",
}
MAX_LABEL_CHARS = 12
NONE_VALUES = {"없음", "없음.", "없습니다", "없습니다.", "해당 없음", "해당없음", "-", "n/a", "none"}
# (패턴, 화면 유형) 순서대로 값에서 가장 먼저 나오는 유형을 고릅니다.
SCREEN_TYPE_PATTERNS = (
    (re.compile(r"강사|인물|얼굴|사람"), "강사 화면"),
    (re.compile(r"판서|칠판|화이트보드"), "판서"),
    (re.compile(r"코드|프로그램|터미널|소스"), "코드"),
    (re.compile(r"그래프|차트"), "그래프"),
    (re.compile(r"도표|(?<![가-힣])표(?![가-힣])"), "표"),
    (re.compile(r"수식|공식"), "수식"),
    (re.compile(r"도식|다이어그램|흐름도|구조도"), "도식"),
    (re.compile(r"슬라이드|ppt|발표\s*자료", re.IGNORECASE), "슬라이드"),
    (re.compile(r"기타"), "기타"),
)


def normalize_screen_type(value: str) -> str:
    matches = [
        (match.start(), screen_type)
        for pattern, screen_type in SCREEN_TYPE_PATTERNS
        if (match := pattern.search(value))
    ]
    return min(matches)[1] if matches else "기타"


def _split_label(line: str) -> tuple[str, str, str]:
    """첫 콜론(``:`` 또는 ``：``)을 기준으로 (항목 이름, 구분자, 값)으로 나눕니다."""
    match = re.search(r"[:：]", line)
    if not match:
        return line, "", ""
    return line[: match.start()], match.group(), line[match.end():]


def _field_name(label: str) -> str | None:
    key = re.sub(r"[\s*#\-•]", "", label)
    key = re.sub(r"[/,ㆍ・]", "·", key)
    if not key or len(key) > MAX_LABEL_CHARS:
        return None
    return FIELD_LABELS.get(key)


def parse_vlm_fields(text: str) -> dict[str, Any]:
    """VLM의 ``항목 이름: 값`` 줄 출력을 필드로 나눕니다.

    항목 이름이 없는 줄은 바로 앞 항목에 이어 붙입니다(여러 줄 코드·수식).
    항목을 하나도 찾지 못하면 ``parsed=False``이고 원문 전체를 ``content``에 둡니다.
    """
    fields = {"screen_type": "", "title": "", "content": "", "formula": ""}
    current = None
    parsed = False

    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        label, separator, value = _split_label(line)
        name = _field_name(label) if separator else None
        if name:
            parsed = True
            current = name
            value = value.strip()
            fields[name] = f"{fields[name]}\n{value}".strip() if fields[name] else value
        elif current:
            fields[current] = f"{fields[current]}\n{line}".strip()

    if not parsed:
        content = str(text).strip()
        return {
            "screen_type": None,
            "title": "",
            "content": content,
            "formula": "",
            "has_content": bool(content),
            "parsed": False,
        }

    for name in ("title", "content", "formula"):
        if fields[name].strip().lower() in NONE_VALUES:
            fields[name] = ""
    raw_type = fields["screen_type"].strip()
    screen_type = normalize_screen_type(raw_type) if raw_type.lower() not in NONE_VALUES else "기타"
    return {
        "screen_type": screen_type,
        "title": fields["title"],
        "content": fields["content"],
        "formula": fields["formula"],
        "has_content": screen_type != LECTURER_SCREEN and bool(fields["content"] or fields["formula"]),
        "parsed": True,
    }


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

        prompt = f"""강의 영상의 한 프레임과 OCR 결과입니다.
메타데이터: {metadata_text}
OCR: {ocr_text.strip() or "없음"}

[규칙]
- 화면과 OCR에서 확인되는 내용만 적으세요. 읽을 수 없는 글자나 수치는 "판독 불가"로 적으세요.
- 아래 4줄만 출력하세요. 항목 이름과 순서를 바꾸지 말고 다른 설명은 쓰지 마세요.
- 해당 내용이 없으면 "없음"이라고 적으세요.

화면 유형: <슬라이드, 판서, 코드, 표, 그래프, 수식, 도식, 강사 화면, 기타 중 하나>
제목: <화면에 보이는 제목>
핵심 내용: <화면이 설명하는 내용, 한두 문장>
수식·코드·수치: <화면의 식, 코드, 수치를 그대로>
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
            result["vlm_fields"] = parse_vlm_fields(summary)
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
