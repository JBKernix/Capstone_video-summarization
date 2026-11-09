"""최종 요약 텍스트를 화면에 그리기 좋은 블록 구조로 해석합니다.

Streamlit 화면(summary_timeline)과 FastAPI 앱 API가 함께 사용하므로 UI 라이브러리에 의존하지 않습니다.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from modules.common import find_existing_path, load_json

# LLM이 생성하는 최종 요약 텍스트에 박혀 있는 "(타임라인: 0.0 ~ 7.0)" 형태의 표기입니다.
# 구간이 아니라 "(타임라인: 573.12)"처럼 단일 시점만 나올 때도 있어 끝 시각은 선택 사항입니다.
TIMELINE_PATTERN = re.compile(r"\(\s*타임라인\s*:\s*([\d.]+)\s*(?:~\s*([\d.]+)\s*)?\)")
CHART_HEADING_KEYWORDS = ("표", "차트")
NUMBERED_ITEM_PATTERN = re.compile(
    r"###\s+(\d+)\.\s*(.*?)\s*\(\s*타임라인\s*:\s*([\d.]+)\s*(?:~\s*([\d.]+)\s*)?\)"
)
HAS_NUMBERED_ITEM_PATTERN = re.compile(r"(^|\n)###\s+\d+\.")
# 타임라인 항목 하나에 보여 줄 최대 화면 수입니다(프레임 추출의 구간당 최대 대표 프레임 수와 같습니다).
MAX_FRAMES_PER_ITEM = 4


def format_timestamp(seconds: float) -> str:
    """초 단위 시간을 ``분:초`` 또는 ``시:분:초`` 문자열로 변환합니다."""
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_timeline_label(start: float, end: float | None) -> str:
    if end is None:
        return format_timestamp(start)
    return f"{format_timestamp(start)} ~ {format_timestamp(end)}"


def plain_timeline_text(text: str) -> str:
    """클릭 기능을 넣기 애매한 위치에서는 타임라인 표기를 읽기 쉬운 형식으로만 바꿉니다."""

    def _replace(match: re.Match[str]) -> str:
        start = float(match.group(1))
        end = float(match.group(2)) if match.group(2) else None
        return f"({format_timeline_label(start, end)})"

    return TIMELINE_PATTERN.sub(_replace, text)


def load_ocr_entries(ocr_result_path: Path) -> list[dict[str, Any]]:
    if not ocr_result_path.is_file():
        return []
    try:
        data = load_json(ocr_result_path)
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _entries_in_range(ocr_entries: list[dict[str, Any]], start: float, end: float | None) -> list[dict[str, Any]]:
    """타임라인 구간 안의 프레임입니다. 구간 안에 하나도 없을 때만 앞뒤 1초까지 넓혀 찾습니다.

    처음부터 넓혀 찾으면 바로 옆 구간의 프레임이 섞여 들어옵니다.
    """
    end = end if end is not None else start
    entries = [entry for entry in ocr_entries if isinstance(entry, dict) and entry.get("image_path")]
    for margin in (0.0, 1.0):
        in_range = [
            entry for entry in entries if start - margin <= float(entry.get("timestamp", -1)) <= end + margin
        ]
        if in_range:
            return in_range
    return []


def _prefer_charts(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [entry for entry in entries if entry.get("scene_type") == "chart_or_table"] or entries


def find_matching_frame_image(
    ocr_entries: list[dict[str, Any]],
    start: float,
    end: float | None,
    ocr_result_path: Path,
    project_root: Path,
) -> Path | None:
    """구간을 대표할 프레임 한 장입니다. 표/차트로 분류된 화면, 그다음 글자가 있는 화면을 우선합니다."""
    pool = sorted(
        _prefer_charts(_entries_in_range(ocr_entries, start, end)),
        key=lambda entry: not str(entry.get("ocr_text", "")).strip(),
    )
    for entry in pool:
        resolved = find_existing_path(entry["image_path"], ocr_result_path, project_root)
        if resolved is not None:
            return resolved
    return None


def find_matching_frames(
    ocr_entries: list[dict[str, Any]],
    start: float,
    end: float | None,
    ocr_result_path: Path,
    project_root: Path,
    charts_only: bool = False,
    limit: int = MAX_FRAMES_PER_ITEM,
) -> list[dict[str, Any]]:
    """구간 안의 프레임을 시간순으로 모두 돌려줍니다(``{"path", "timestamp"}``).

    프레임 추출 단계에서 같은 화면은 이미 하나로 묶었으므로, 여기 나오는 프레임은 서로 다른 화면입니다.
    ``charts_only``이면 표/차트 화면이 있을 때 그것만 씁니다. ``limit``장을 넘으면 시간상 고르게 줄입니다.
    """
    entries = _entries_in_range(ocr_entries, start, end)
    if charts_only:
        entries = _prefer_charts(entries)

    frames: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for entry in sorted(entries, key=lambda entry: float(entry.get("timestamp", 0))):
        resolved = find_existing_path(entry["image_path"], ocr_result_path, project_root)
        if resolved is None or resolved in seen:
            continue
        seen.add(resolved)
        frames.append({"path": resolved, "timestamp": float(entry.get("timestamp", start))})

    if len(frames) <= limit:
        return frames
    if limit == 1:
        return frames[:1]
    step = (len(frames) - 1) / (limit - 1)
    return [frames[round(position * step)] for position in range(limit)]


def _parse_numbered_items(
    body: str,
    show_images: bool,
    ocr_entries: list[dict[str, Any]],
    ocr_result_path: Path,
    project_root: Path,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in re.split(r"\n(?=###\s+\d+\.)", body.strip()):
        item = item.strip()
        if not item:
            continue

        match = NUMBERED_ITEM_PATTERN.match(item)
        if not match:
            items.append({"type": "markdown", "text": plain_timeline_text(item)})
            continue

        index, item_title, start_text, end_text = match.groups()
        start = float(start_text)
        end = float(end_text) if end_text else None
        image_path = (
            find_matching_frame_image(ocr_entries, start, end, ocr_result_path, project_root)
            if show_images
            else None
        )
        items.append({
            "type": "item",
            "index": int(index),
            "title": item_title,
            "start": start,
            "end": end,
            "label": format_timeline_label(start, end),
            "text": plain_timeline_text(item[match.end():].strip()),
            "image_path": image_path,
            "frames": (
                find_matching_frames(ocr_entries, start, end, ocr_result_path, project_root, charts_only=True)
                if show_images
                else []
            ),
        })
    return items


def parse_summary_markdown(
    markdown_text: str,
    ocr_result_path: Path,
    project_root: Path,
) -> list[dict[str, Any]]:
    """최종 요약 텍스트를 화면 블록 목록으로 나눕니다.

    번호가 매겨진 항목(``### N. 제목 (타임라인: ...)``)이 있는 구간은 ``items`` 블록으로,
    그 외 구간은 타임라인 표기만 분:초 형식으로 바꾼 ``markdown`` 블록으로 반환합니다.
    "표/차트" 성격의 구간(``show_images``)은 항목마다 대표 프레임 경로(``image_path``)와
    구간 안의 서로 다른 화면 목록(``frames``)을 찾습니다.
    """
    ocr_entries = load_ocr_entries(ocr_result_path)
    blocks: list[dict[str, Any]] = []

    for section in re.split(r"\n(?=##\s+[^#])", markdown_text.strip()):
        section = section.strip()
        if not section:
            continue

        heading_match = re.match(r"##\s+(.+)", section)
        if not heading_match:
            blocks.append({"type": "markdown", "text": plain_timeline_text(section)})
            continue

        heading = heading_match.group(1).strip()
        body = section[heading_match.end():]

        if HAS_NUMBERED_ITEM_PATTERN.search(body):
            show_images = any(keyword in heading for keyword in CHART_HEADING_KEYWORDS)
            blocks.append({
                "type": "items",
                "heading": heading,
                "show_images": show_images,
                "items": _parse_numbered_items(body, show_images, ocr_entries, ocr_result_path, project_root),
            })
            continue

        blocks.append({"type": "markdown", "text": plain_timeline_text(section)})

    return blocks
