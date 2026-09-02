from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

# Windows 파일/폴더명에 사용할 수 없는 문자입니다: \ / : * ? " < > |
INVALID_FOLDER_CHARS_PATTERN = re.compile(r'[\\/:*?"<>|]')

SUMMARY_FILENAMES = ("final_summary.txt", "final_summary_result.json")


def sanitize_folder_name(name: str) -> str:
    """폴더명으로 쓸 수 없는 문자를 제거하고 앞뒤 공백/마침표를 정리합니다."""
    cleaned = INVALID_FOLDER_CHARS_PATTERN.sub("", name).strip().strip(".")
    return cleaned


def build_save_folder_name(title: str | None, timestamp: datetime) -> str:
    """``[영상 제목] - 년-월-일 시분초`` 형식의 폴더명을 만듭니다."""
    date_text = timestamp.strftime("%Y%m%d-%H%M%S")
    cleaned_title = sanitize_folder_name(title) if title else ""

    if cleaned_title:
        return f"[{cleaned_title}] - {date_text}"
    return date_text


def save_analysis_result(
    video_path: str | Path | None,
    final_dir: str | Path,
    save_root: str | Path,
    title: str | None = None,
    timestamp: datetime | None = None,
) -> Path:
    """영상과 최종 요약 결과를 하나의 폴더에 복사해 저장합니다.

    Args:
        video_path: 원본 영상 파일 경로입니다. ``None``이면 영상은 저장하지 않습니다.
        final_dir: 최종 요약 결과(``final_summary.txt``/``final_summary_result.json``)가 있는 디렉터리입니다.
        save_root: 저장 폴더를 생성할 상위 디렉터리입니다.
        title: 폴더명에 사용할 영상 제목입니다.
        timestamp: 폴더명에 사용할 시각입니다. 기본값은 현재 시각입니다.

    Returns:
        생성된 저장 폴더 경로입니다.

    Raises:
        FileNotFoundError: 저장할 영상과 요약 결과가 모두 없을 때 발생합니다.
    """
    timestamp = timestamp or datetime.now()
    final_dir = Path(final_dir)
    save_root = Path(save_root)

    target_dir = save_root / build_save_folder_name(title, timestamp)
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_anything = False

    if video_path and Path(video_path).is_file():
        video_path = Path(video_path)
        shutil.copy2(video_path, target_dir / video_path.name)
        saved_anything = True

    for filename in SUMMARY_FILENAMES:
        source = final_dir / filename
        if source.is_file():
            shutil.copy2(source, target_dir / filename)
            saved_anything = True

    if not saved_anything:
        raise FileNotFoundError("저장할 영상과 요약 결과를 찾을 수 없습니다.")

    return target_dir
