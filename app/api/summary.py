"""최종 요약 결과를 React 화면이 그대로 그릴 수 있는 JSON으로 바꿉니다."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.summary_parse import load_ocr_entries, parse_summary_markdown
from app.summary_result import get_summary_markdown, has_structured_summary, load_final_summary
from modules.common import find_existing_path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRUCTURED_KEYS = ("title", "main_topic", "keywords", "topics", "conclusion")


def frame_path(ocr_result_path: Path, index: int) -> Path | None:
    """OCR 결과의 ``index``번째 항목이 가리키는 프레임 이미지 경로입니다."""
    entries = load_ocr_entries(ocr_result_path)
    if not 0 <= index < len(entries) or not isinstance(entries[index], dict):
        return None
    image_path = entries[index].get("image_path")
    return find_existing_path(image_path, ocr_result_path, PROJECT_ROOT) if image_path else None


def _frame_indexes(ocr_result_path: Path) -> dict[Path, int]:
    indexes: dict[Path, int] = {}
    for index, entry in enumerate(load_ocr_entries(ocr_result_path)):
        image_path = entry.get("image_path") if isinstance(entry, dict) else None
        resolved = find_existing_path(image_path, ocr_result_path, PROJECT_ROOT) if image_path else None
        if resolved is not None:
            indexes.setdefault(resolved, index)
    return indexes


def _markdown_blocks(markdown_text: str, ocr_result_path: Path, frame_url: str) -> list[dict[str, Any]]:
    """타임라인 블록의 서버 이미지 경로를 ``{frame_url}/{OCR 항목 번호}`` URL로 바꿉니다."""
    blocks = parse_summary_markdown(markdown_text, ocr_result_path, PROJECT_ROOT)
    indexes = _frame_indexes(ocr_result_path) if any(b.get("show_images") for b in blocks) else {}
    for block in blocks:
        for item in block.get("items", []):
            image_path = item.pop("image_path", None)
            if item["type"] == "item":
                index = indexes.get(image_path) if image_path else None
                item["image_url"] = f"{frame_url}/{index}" if index is not None else None
    return blocks


def summary_payload(final_dir: Path, ocr_result_path: Path, frame_url: str) -> dict[str, Any]:
    """요약 결과를 ``structured``/``blocks``/``raw`` 중 하나의 형태로 반환합니다.

    Raises:
        FileNotFoundError, OSError, ValueError: 요약 파일이 없거나 읽을 수 없을 때 발생합니다.
    """
    final_summary = load_final_summary(final_dir)
    if final_summary.mode != "json":
        return {"mode": "blocks", "blocks": _markdown_blocks(final_summary.content, ocr_result_path, frame_url)}

    data = final_summary.content
    if has_structured_summary(data):
        structured = {key: data.get(key) for key in STRUCTURED_KEYS}
        structured["topics"] = [
            topic if isinstance(topic, dict) else {"content": topic} for topic in structured["topics"] or []
        ]
        return {"mode": "structured", "summary": structured}

    markdown_text = get_summary_markdown(data)
    if markdown_text:
        return {"mode": "blocks", "blocks": _markdown_blocks(markdown_text, ocr_result_path, frame_url)}
    return {"mode": "raw", "data": data}
