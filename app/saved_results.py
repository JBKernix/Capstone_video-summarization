"""저장된 요약 결과(data/saved/<폴더>) 목록과 파일을 찾습니다.

Streamlit 저장 결과 페이지와 FastAPI 앱 API가 함께 사용하므로 UI 라이브러리에 의존하지 않습니다.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAVE_ROOT = PROJECT_ROOT / "data" / "saved"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi")

# result_export.build_save_folder_name()이 만드는 "[제목] - 년월일-시분초" 형식입니다.
SAVED_FOLDER_NAME_PATTERN = re.compile(r"^\[(?P<title>.*)\] - (?P<timestamp>\d{8}-\d{6})$")


def parse_saved_folder_name(folder_name: str) -> tuple[str, datetime | None]:
    """저장 폴더명에서 영상 제목과 저장 시각을 추출합니다."""
    match = SAVED_FOLDER_NAME_PATTERN.match(folder_name)
    timestamp_text = match.group("timestamp") if match else folder_name

    try:
        timestamp = datetime.strptime(timestamp_text, "%Y%m%d-%H%M%S")
    except ValueError:
        timestamp = None

    title = match.group("title") if match else folder_name
    return title, timestamp


def find_saved_video(folder: Path) -> Path | None:
    for extension in VIDEO_EXTENSIONS:
        matches = sorted(folder.glob(f"*{extension}"))
        if matches:
            return matches[0]
    return None


def list_saved_items(save_root: Path = SAVE_ROOT) -> list[dict]:
    if not save_root.exists():
        return []

    items = []
    for folder in save_root.iterdir():
        if not folder.is_dir():
            continue
        title, timestamp = parse_saved_folder_name(folder.name)
        items.append({"folder": folder, "title": title, "timestamp": timestamp})

    items.sort(key=lambda item: item["timestamp"] or datetime.min, reverse=True)
    return items


def saved_folder(name: str, save_root: Path = SAVE_ROOT) -> Path | None:
    """폴더 이름으로 저장 결과 폴더를 찾습니다. ``save_root`` 바로 아래 폴더만 허용합니다."""
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return None
    folder = save_root / name
    if folder.resolve().parent != save_root.resolve() or not folder.is_dir():
        return None
    return folder
