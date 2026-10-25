"""최종 요약 결과를 React 화면이 그대로 그릴 수 있는 JSON으로 바꿉니다."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.summary_parse import (
    find_matching_frame_image,
    find_matching_frames,
    format_timeline_label,
    format_timestamp,
    load_ocr_entries,
    parse_summary_markdown,
)
from app.summary_result import get_summary_markdown, has_structured_summary, load_final_summary
from modules.common import find_existing_path, load_json

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STRUCTURED_KEYS = ("title", "main_topic", "keywords", "topics", "conclusion")

# 강의노트 구조(outline)를 만들 때 쓰는 최종 요약 마크다운의 관례입니다(gpu-server 최종 요약 프롬프트 기준).
SECTION_HEADING_PATTERN = re.compile(r"##\s+(.+)")
BULLET_PATTERN = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
SCREEN_NOTE_PATTERN = re.compile(r"VLM\s*요약\s*자료(?:에서는|에서|에는|에)\s*,?\s*")
QUOTED_TERM_PATTERN = re.compile(r"['‘\"“]([^'’\"”\n]+)['’\"”]")
KEY_POINT_HEADINGS = ("핵심",)
CONCLUSION_HEADINGS = ("결론",)
MAX_KEYWORDS = 6
MAX_KEYWORD_LENGTH = 15


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


def _frame_refs(frames: list[dict[str, Any]], indexes: dict[Path, int], frame_url: str) -> list[dict[str, Any]]:
    """``find_matching_frames`` 결과를 화면에서 쓰는 ``{url, time, label}`` 목록으로 바꿉니다."""
    refs = []
    for frame in frames:
        index = indexes.get(frame["path"])
        if index is not None:
            refs.append({"url": f"{frame_url}/{index}", "time": frame["timestamp"],
                         "label": format_timestamp(frame["timestamp"])})
    return refs


def _markdown_blocks(markdown_text: str, ocr_result_path: Path, frame_url: str) -> list[dict[str, Any]]:
    """타임라인 블록의 서버 이미지 경로를 ``{frame_url}/{OCR 항목 번호}`` URL로 바꿉니다."""
    blocks = parse_summary_markdown(markdown_text, ocr_result_path, PROJECT_ROOT)
    indexes = _frame_indexes(ocr_result_path) if any(b.get("show_images") for b in blocks) else {}
    for block in blocks:
        for item in block.get("items", []):
            image_path = item.pop("image_path", None)
            frames = item.pop("frames", [])
            if item["type"] == "item":
                index = indexes.get(image_path) if image_path else None
                item["image_url"] = f"{frame_url}/{index}" if index is not None else None
                item["frames"] = _frame_refs(frames, indexes, frame_url)
    return blocks


def _section(block: dict[str, Any]) -> tuple[str, str]:
    """``## 제목``으로 시작하는 마크다운 블록을 (제목, 본문)으로 나눕니다. 제목이 없으면 ("", 전체)."""
    text = block["text"].strip()
    match = SECTION_HEADING_PATTERN.match(text)
    if not match:
        return "", text
    return match.group(1).strip(), text[match.end():].strip()


def _bullets(text: str) -> list[str]:
    """마크다운 목록 항목(``-``, ``*``, ``1.``)만 뽑습니다. 목록이 없으면 문단 전체를 한 항목으로 봅니다."""
    items = [BULLET_PATTERN.sub("", line).strip() for line in text.splitlines() if BULLET_PATTERN.match(line)]
    items = [item for item in items if item]
    if items:
        return items
    return [text.strip()] if text.strip() else []


def _split_screen_notes(text: str) -> tuple[list[str], list[str]]:
    """챕터 본문을 (내용 항목, 화면 분석 항목)으로 나눕니다.

    최종 요약은 화면 분석에서 온 내용을 "VLM 요약 자료에서는 …"으로 시작해 적습니다. 사용자에게는 이 내부
    용어 대신 "화면에서 확인" 표시로 따로 보여 주도록 접두어를 떼어 냅니다.
    """
    points: list[str] = []
    screen: list[str] = []
    for item in _bullets(text):
        match = SCREEN_NOTE_PATTERN.match(item)
        if match:
            screen.append(item[match.end():].strip())
        else:
            points.append(item)
    return points, screen


def _keywords(markdown_text: str, stt_summary_path: Path | None) -> list[str]:
    """요약에서 따옴표로 강조한 용어와 음성 요약의 중요 구간 주제를 키워드로 씁니다(최대 6개)."""
    candidates = [match.group(1).strip() for match in QUOTED_TERM_PATTERN.finditer(markdown_text)]
    if stt_summary_path is not None and stt_summary_path.is_file():
        try:
            segments = load_json(stt_summary_path).get("important_segments") or []
        except (OSError, ValueError, AttributeError):
            segments = []
        candidates += [str(segment.get("topic", "")).strip() for segment in segments if isinstance(segment, dict)]
    keywords: list[str] = []
    for word in candidates:
        # "스타실드"가 있으면 "스타실드 통신 문제"처럼 겹치는 표현은 빼서 칩이 반복돼 보이지 않게 합니다.
        overlaps = any(word in kept or kept in word for kept in keywords)
        if 2 <= len(word) <= MAX_KEYWORD_LENGTH and not overlaps:
            keywords.append(word)
    return keywords[:MAX_KEYWORDS]


def _outline(
    blocks: list[dict[str, Any]],
    markdown_text: str,
    ocr_result_path: Path,
    frame_url: str,
    stt_summary_path: Path | None,
) -> dict[str, Any] | None:
    """사용자용 강의노트(챕터 플레이어) 화면에 쓸 구조입니다. 타임라인 챕터가 없으면 ``None``."""
    title = None
    key_points: list[str] = []
    conclusion: list[str] = []
    chapters: list[dict[str, Any]] = []
    visuals: list[dict[str, Any]] = []
    extras: list[str] = []
    ocr_entries = load_ocr_entries(ocr_result_path)
    indexes: dict[Path, int] | None = None

    for block in blocks:
        if block["type"] == "items":
            for item in block["items"]:
                if item["type"] != "item":
                    extras.append(item["text"])
                elif block["show_images"]:
                    visuals.append({**item, "section": block["heading"]})
                else:
                    points, screen = _split_screen_notes(item["text"])
                    image = find_matching_frame_image(ocr_entries, item["start"], item["end"], ocr_result_path, PROJECT_ROOT)
                    frames = find_matching_frames(ocr_entries, item["start"], item["end"], ocr_result_path, PROJECT_ROOT)
                    if (image is not None or frames) and indexes is None:
                        indexes = _frame_indexes(ocr_result_path)
                    index = indexes.get(image) if image is not None and indexes else None
                    chapters.append({
                        "index": item["index"],
                        "title": item["title"],
                        "start": item["start"],
                        "end": item["end"],
                        "label": item["label"],
                        "points": points,
                        "screen_notes": screen,
                        "thumb_url": f"{frame_url}/{index}" if index is not None else None,
                        "frames": _frame_refs(frames, indexes or {}, frame_url),
                    })
            continue

        text = block["text"].strip()
        if text.startswith("# ") and title is None:
            title = text.splitlines()[0][2:].strip()
            rest = "\n".join(text.splitlines()[1:]).strip()
            if rest:
                extras.append(rest)
            continue
        heading, body = _section(block)
        if any(word in heading for word in KEY_POINT_HEADINGS) and not key_points:
            key_points = _bullets(body)
        elif any(word in heading for word in CONCLUSION_HEADINGS) and not conclusion:
            conclusion = _bullets(body)
        elif text:
            extras.append(text)

    if not chapters:
        return None
    return {
        "title": title,
        "key_points": key_points or conclusion[:3],
        "keywords": _keywords(markdown_text, stt_summary_path),
        "chapters": chapters,
        "visuals": visuals,
        "conclusion": conclusion,
        # 마크다운 요약에는 용어 정의·공지 구분이 없습니다(강의 노트 JSON에만 있음).
        "terms": [],
        "notices": [],
        "extras": extras,
    }


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if number >= 0 and number != float("inf") else None


def _note_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _note_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [text for text in (_note_text(item) for item in value) if text]


def _note_records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def is_lecture_note(value: Any) -> bool:
    """gpu-server 최종 요약이 함께 주는 강의 노트 JSON(``lecture_note``)인지 확인합니다."""
    return isinstance(value, dict) and bool(_note_records(value.get("chapters")))


def _lecture_note_outline(
    note: dict[str, Any],
    markdown_text: str,
    ocr_result_path: Path,
    frame_url: str,
    stt_summary_path: Path | None,
) -> dict[str, Any] | None:
    """강의 노트 JSON을 마크다운 파싱 없이 강의노트 화면 구조(``outline``)로 바꿉니다.

    시간이 없는 챕터·자료도 버리지 않고 ``start: None``으로 넘깁니다(재생 버튼만 숨김).
    """
    ocr_entries = load_ocr_entries(ocr_result_path)
    indexes: dict[Path, int] | None = None

    def frames_for(start: float | None, end: float | None, charts_only: bool) -> tuple[str | None, list[dict[str, Any]]]:
        nonlocal indexes
        if start is None:
            return None, []
        image = find_matching_frame_image(ocr_entries, start, end, ocr_result_path, PROJECT_ROOT)
        frames = find_matching_frames(ocr_entries, start, end, ocr_result_path, PROJECT_ROOT, charts_only=charts_only)
        if (image is not None or frames) and indexes is None:
            indexes = _frame_indexes(ocr_result_path)
        index = indexes.get(image) if image is not None and indexes else None
        return (f"{frame_url}/{index}" if index is not None else None), _frame_refs(frames, indexes or {}, frame_url)

    def time_range(item: dict[str, Any]) -> tuple[float | None, float | None, str]:
        start, end = _seconds(item.get("start")), _seconds(item.get("end"))
        if start is None:
            return None, None, "시간 정보 없음"
        end = end if end is not None and end >= start else None
        return start, end, format_timeline_label(start, end)

    chapters = []
    for item in _note_records(note.get("chapters")):
        points = _note_texts(item.get("points"))
        title = _note_text(item.get("title"))
        if not title and not points:
            continue
        start, end, label = time_range(item)
        thumb_url, frames = frames_for(start, end, charts_only=False)
        chapters.append({
            "index": len(chapters) + 1,
            "title": title or f"주제 {len(chapters) + 1}",
            "start": start,
            "end": end,
            "label": label,
            "points": points,
            "screen_notes": _note_texts(item.get("screen_notes")),
            "thumb_url": thumb_url,
            "frames": frames,
        })
    if not chapters:
        return None

    visuals = []
    for item in _note_records(note.get("visuals")):
        title = _note_text(item.get("title"))
        content = _note_texts(item.get("content"))
        meaning = _note_text(item.get("meaning"))
        if not title and not content:
            continue
        start, end, label = time_range(item)
        image_url, frames = frames_for(start, end, charts_only=True)
        text = "\n".join(f"- {line}" for line in content)
        if meaning:
            text += f"\n\n**강의에서의 의미** {meaning}"
        visual_type = _note_text(item.get("type")) or "자료"
        visuals.append({
            "type": "item",
            "index": len(visuals) + 1,
            "title": title or visual_type,
            "start": start,
            "end": end,
            "label": label,
            "text": text.strip(),
            "image_url": image_url,
            "frames": frames,
            "section": "표/차트 기반 주요 정보",
            "kind": visual_type,
        })

    terms = [
        {"term": _note_text(item.get("term")), "definition": _note_text(item.get("definition"))}
        for item in _note_records(note.get("terms"))
        if _note_text(item.get("term"))
    ]
    # 키워드는 강의 노트의 핵심 용어를 먼저 쓰고, 모자라면 기존 방식(따옴표 강조·중요 구간 주제)으로 채웁니다.
    keywords: list[str] = []
    for word in [term["term"] for term in terms] + _keywords(markdown_text, stt_summary_path):
        if 2 <= len(word) <= MAX_KEYWORD_LENGTH and not any(word in kept or kept in word for kept in keywords):
            keywords.append(word)

    conclusion = _note_texts(note.get("conclusion"))
    return {
        "title": _note_text(note.get("title")) or None,
        "key_points": _note_texts(note.get("key_points")) or conclusion[:3],
        "keywords": keywords[:MAX_KEYWORDS],
        "terms": terms,
        "chapters": chapters,
        "visuals": visuals,
        "conclusion": conclusion,
        "notices": _note_texts(note.get("notices")),
        "extras": [],
    }


def summary_payload(
    final_dir: Path,
    ocr_result_path: Path,
    frame_url: str,
    stt_summary_path: Path | None = None,
) -> dict[str, Any]:
    """요약 결과를 ``structured``/``blocks``/``raw`` 중 하나의 형태로 반환합니다.

    ``blocks`` 형태이고 타임라인 챕터가 있으면 사용자용 강의노트 화면을 위한 ``outline``도 함께 줍니다.
    결과 JSON에 강의 노트(``lecture_note``)가 있으면 ``outline``은 마크다운 대신 그 JSON으로 만듭니다.
    ``stt_summary_path``(음성 요약 결과)가 있으면 그 중요 구간 주제를 키워드에 보탭니다.

    Raises:
        FileNotFoundError, OSError, ValueError: 요약 파일이 없거나 읽을 수 없을 때 발생합니다.
    """
    final_summary = load_final_summary(final_dir)
    if final_summary.mode != "json":
        markdown_text = final_summary.content
    else:
        data = final_summary.content
        markdown_text = get_summary_markdown(data)
        note = data.get("lecture_note")
        if is_lecture_note(note):
            return {
                "mode": "blocks",
                "blocks": _markdown_blocks(markdown_text, ocr_result_path, frame_url) if markdown_text else [],
                "outline": _lecture_note_outline(note, markdown_text, ocr_result_path, frame_url, stt_summary_path),
            }
        if has_structured_summary(data):
            structured = {key: data.get(key) for key in STRUCTURED_KEYS}
            structured["topics"] = [
                topic if isinstance(topic, dict) else {"content": topic} for topic in structured["topics"] or []
            ]
            return {"mode": "structured", "summary": structured}
        if not markdown_text:
            return {"mode": "raw", "data": data}

    blocks = _markdown_blocks(markdown_text, ocr_result_path, frame_url)
    return {
        "mode": "blocks",
        "blocks": blocks,
        "outline": _outline(blocks, markdown_text, ocr_result_path, frame_url, stt_summary_path),
    }
