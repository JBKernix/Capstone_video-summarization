from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.common import find_existing_path, load_json, save_json

# Windows 파일/폴더명에 사용할 수 없는 문자입니다: \ / : * ? " < > |
INVALID_FOLDER_CHARS_PATTERN = re.compile(r'[\\/:*?"<>|]')

SUMMARY_FILENAMES = ("final_summary.txt", "final_summary_result.json")
OCR_RESULT_FILENAME = "ocr_result.json"
FRAMES_DIRNAME = "frames"


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


def _copy_ocr_result_with_frames(ocr_result_path: Path, target_dir: Path) -> bool:
    """OCR 결과 JSON과 그 안에서 참조하는 프레임 이미지를 저장 폴더로 복사합니다.

    ``image_path``는 실행마다 새로 생성되는 ``runs/frames`` 아래 파일을 절대경로로 가리키므로,
    나중에 그 경로의 이미지가 다른 영상의 프레임으로 덮어써지면 저장된 요약이 엉뚱한 화면을
    보여주게 됩니다. 그래서 이미지 자체를 저장 폴더 안(``frames/``)으로 복사하고, JSON의
    ``image_path``도 그 복사본을 가리키는 상대경로로 고쳐 씁니다.
    """
    try:
        entries = load_json(ocr_result_path)
    except (OSError, ValueError):
        return False

    if not isinstance(entries, list):
        return False

    frames_dir = target_dir / FRAMES_DIRNAME
    copied_entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry = dict(entry)
        image_path = entry.get("image_path")
        if image_path:
            resolved = find_existing_path(image_path, ocr_result_path, PROJECT_ROOT)
            if resolved:
                frames_dir.mkdir(parents=True, exist_ok=True)
                destination = frames_dir / resolved.name
                if not destination.exists():
                    shutil.copy2(resolved, destination)
                entry["image_path"] = f"{FRAMES_DIRNAME}/{resolved.name}"
        copied_entries.append(entry)

    save_json(copied_entries, target_dir / OCR_RESULT_FILENAME)
    return True


def save_analysis_result(
    video_path: str | Path | None,
    final_dir: str | Path,
    save_root: str | Path,
    title: str | None = None,
    timestamp: datetime | None = None,
    ocr_result_path: str | Path | None = None,
) -> Path:
    """영상과 최종 요약 결과를 하나의 폴더에 복사해 저장합니다.

    Args:
        video_path: 원본 영상 파일 경로입니다. ``None``이면 영상은 저장하지 않습니다.
        final_dir: 최종 요약 결과(``final_summary.txt``/``final_summary_result.json``)가 있는 디렉터리입니다.
        save_root: 저장 폴더를 생성할 상위 디렉터리입니다.
        title: 폴더명에 사용할 영상 제목입니다.
        timestamp: 폴더명에 사용할 시각입니다. 기본값은 현재 시각입니다.
        ocr_result_path: 타임라인 구간별 프레임 화면을 복원하기 위한 OCR 결과 JSON 경로입니다.
            ``None``이거나 파일이 없으면 프레임 정보는 저장하지 않습니다.

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

    if ocr_result_path is not None:
        ocr_result_path = Path(ocr_result_path)
        if ocr_result_path.is_file() and _copy_ocr_result_with_frames(ocr_result_path, target_dir):
            saved_anything = True

    if not saved_anything:
        raise FileNotFoundError("저장할 영상과 요약 결과를 찾을 수 없습니다.")

    return target_dir
