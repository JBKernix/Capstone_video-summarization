from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile


MAX_OCR_JSON_BYTES = 10 * 1024 * 1024
MAX_FRAME_BYTES = 20 * 1024 * 1024
MAX_FRAME_COUNT = 32
ALLOWED_FRAME_SUFFIXES = {".jpg", ".jpeg"}


async def read_upload_limited(upload: UploadFile, max_bytes: int) -> bytes:
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"업로드 파일 크기가 제한을 초과했습니다: {upload.filename}",
        )
    return data


def validate_frame_filename(filename: str) -> str:
    safe_name = Path(filename).name
    if not safe_name or Path(safe_name).suffix.lower() not in ALLOWED_FRAME_SUFFIXES:
        raise ValueError(f"JPG 프레임만 업로드할 수 있습니다: {filename}")
    return safe_name


def select_ocr_entries_for_frames(
    ocr_entries: list[dict[str, Any]],
    frame_names: list[str],
) -> list[dict[str, Any]]:
    entries_by_name: dict[str, dict[str, Any]] = {}
    duplicate_names = set()
    for entry in ocr_entries:
        filename = str(entry.get("image_path", "")).replace("\\", "/").rsplit("/", 1)[-1]
        if not filename:
            continue
        normalized_name = filename.casefold()
        if normalized_name in entries_by_name:
            duplicate_names.add(normalized_name)
        entries_by_name[normalized_name] = entry

    if not entries_by_name:
        if len(ocr_entries) == len(frame_names):
            return ocr_entries
        raise ValueError("OCR 결과에 image_path가 없어 일부 프레임을 선택할 수 없습니다.")

    selected = []
    missing = []
    for filename in frame_names:
        normalized_name = filename.casefold()
        entry = entries_by_name.get(normalized_name)
        if entry is None or normalized_name in duplicate_names:
            missing.append(filename)
        else:
            selected.append(entry)

    if missing:
        raise ValueError(
            "OCR 결과의 image_path 파일명과 매칭되지 않은 프레임이 있습니다: "
            f"{missing}"
        )
    return selected
