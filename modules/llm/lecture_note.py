"""강의 노트(lecture_note) 공통 규칙입니다. Claude 경로(claude_backend.py)에서 씁니다.

gpu-server/services(final_service.py, vlm_service.py)와 같은 규칙을 따릅니다. gpu-server 모듈은
모델 로더(torch)를 함께 불러오므로 앱에서 직접 import하지 않고 순수 함수만 옮겨 두었습니다.
규칙을 바꾸면 두 곳을 함께 고치세요.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

SCREEN_TYPES = ("슬라이드", "판서", "코드", "표", "그래프", "수식", "도식", "강사 화면", "기타")
LECTURER_SCREEN = "강사 화면"
VISUAL_TYPES = ("표", "그래프", "수식", "코드", "도식")
# 최종 요약 입력에 넣을 화면을 고를 때의 우선순위입니다. 값이 클수록 먼저 고릅니다.
SCREEN_PRIORITY = {"수식": 3, "코드": 3, "표": 3, "그래프": 3, "도식": 3, "슬라이드": 2, "판서": 2}
NOTE_LIMITS = {
    "key_points": 3,
    "terms": 15,
    "chapters": 10,
    "points": 6,
    "screen_notes": 4,
    "visuals": 10,
    "content": 6,
    "conclusion": 5,
    "notices": 5,
}
# 모델이 쓴 시간이 입력 자료의 마지막 시간보다 이만큼(초) 넘으면 잘못된 값으로 봅니다.
TIME_TOLERANCE_SEC = 5.0
SCREEN_NOTE_PREFIX = re.compile(r"^VLM\s*요약\s*자료(?:에서는|에서|에는|에)\s*,?\s*")
PLACEHOLDER_PATTERN = re.compile(r"^<[^<>]*>$")
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


def vlm_fields(screen_type: str, title: str, content: str, formula: str) -> dict[str, Any]:
    """화면 분석 결과를 gpu-server ``parse_vlm_fields``와 같은 모양으로 만듭니다."""
    screen_type = screen_type if screen_type in SCREEN_TYPES else normalize_screen_type(screen_type)
    return {
        "screen_type": screen_type,
        "title": title,
        "content": content,
        "formula": formula,
        "has_content": screen_type != LECTURER_SCREEN and bool(content or formula),
        "parsed": True,
    }


def vlm_summary_text(fields: Mapping[str, Any]) -> str:
    """``vlm_summary``(사람이 읽는 원문)를 gpu-server VLM 프롬프트의 4줄 형식으로 만듭니다."""
    return "\n".join([
        f"화면 유형: {fields['screen_type']}",
        f"제목: {fields['title'] or '없음'}",
        f"핵심 내용: {fields['content'] or '없음'}",
        f"수식·코드·수치: {fields['formula'] or '없음'}",
    ])


def seconds(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value.strip() if isinstance(value, str) else value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return round(number, 2)


def format_range(start: float | None, end: float | None) -> str:
    if start is None:
        return "시간 알 수 없음"
    if end is None or end == start:
        return str(start)
    return f"{start} ~ {end}"


def clean_text(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return ""
    text = value.strip()
    # 모델이 프롬프트의 <설명> 자리표시를 그대로 베낀 경우는 빈 값으로 봅니다.
    return "" if PLACEHOLDER_PATTERN.match(text) else text


def format_important_segments(segments: Sequence[Any]) -> str:
    lines = []
    for segment in segments:
        if not isinstance(segment, Mapping):
            continue
        topic = clean_text(segment.get("topic"))[:80]
        detail = clean_text(segment.get("reason")) or clean_text(segment.get("text"))
        time_range = format_range(seconds(segment.get("start")), seconds(segment.get("end")))
        lines.append(f"- [{time_range}] {topic}: {detail[:350]}".strip())
    return "\n".join(lines)


def _vlm_item(entry: Mapping[str, Any]) -> dict[str, Any] | None:
    fields = entry.get("vlm_fields")
    if not isinstance(fields, Mapping):
        raw = clean_text(entry.get("vlm_summary"))
        if not raw:
            return None
        fields = {"screen_type": None, "title": "", "content": raw, "formula": "", "has_content": True}
    if not fields.get("has_content"):
        return None
    timestamp = seconds(entry.get("timestamp"))
    return {
        "start": timestamp,
        "end": timestamp,
        "screen_type": fields.get("screen_type"),
        "title": clean_text(fields.get("title")),
        "content": " ".join(clean_text(fields.get("content")).split()),
        "formula": clean_text(fields.get("formula")),
    }


def _screen_priority(screen_type: str | None) -> int:
    return SCREEN_PRIORITY.get(screen_type or "", 1)


def _vlm_rank(item: Mapping[str, Any]) -> tuple[int, int]:
    return _screen_priority(item["screen_type"]), len(item["content"]) + len(item["formula"])


def _merge_same_screens(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for item in items:
        key = re.sub(r"\s+", "", item["title"]).casefold()
        previous = merged[-1] if merged else None
        if previous is not None and key and key == previous["_key"]:
            previous["end"] = item["end"] if item["end"] is not None else previous["end"]
            if _screen_priority(item["screen_type"]) > _screen_priority(previous["screen_type"]):
                previous["screen_type"] = item["screen_type"]
            for name in ("content", "formula"):
                if len(item[name]) > len(previous[name]):
                    previous[name] = item[name]
            continue
        merged.append({**item, "_key": key})
    for item in merged:
        item.pop("_key")
    return merged


def _select_spread(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(items) <= limit:
        return items
    selected = []
    for bucket_index in range(limit):
        bucket = items[round(len(items) * bucket_index / limit):round(len(items) * (bucket_index + 1) / limit)]
        if bucket:
            selected.append(max(bucket, key=_vlm_rank))
    return selected


def format_vlm_entries(entries: Sequence[Any], max_items: int, max_item_chars: int = 300) -> str:
    """강의 내용이 있는 화면만 골라 시간순 목록으로 만듭니다.

    강사 화면처럼 내용이 없는 프레임은 빼고, 시간상 이어진 같은 제목의 화면은 한 항목(시간 구간)으로
    합칩니다. 그래도 많으면 전체를 같은 크기로 나눠 구간마다 우선순위가 가장 높은 항목을 고릅니다.
    """
    items = [item for item in (_vlm_item(entry) for entry in entries if isinstance(entry, Mapping)) if item]
    items.sort(key=lambda item: (item["start"] is None, item["start"] or 0.0))
    blocks = []
    for item in _select_spread(_merge_same_screens(items), max_items):
        header = f"- [{format_range(item['start'], item['end'])}] {item['screen_type'] or '화면'}"
        if item["title"]:
            header += f" | {item['title']}"
        lines = [header]
        if item["content"]:
            lines.append(f"  내용: {item['content']}")
        if item["formula"]:
            lines.append(f"  수식·코드·수치: {item['formula']}")
        block = "\n".join(lines)
        if len(block) > max_item_chars:
            block = block[:max_item_chars].rstrip() + "…"
        blocks.append(block)
    return "\n".join(blocks)


def collect_known_times(important_segments: Sequence[Any], vlm_entries: Sequence[Any]) -> list[float]:
    """입력 자료에 있는 시간(초)을 모읍니다. 모델이 쓴 시간의 범위 검증에 씁니다."""
    times = []
    for segment in important_segments:
        if isinstance(segment, Mapping):
            times += [segment.get("start"), segment.get("end")]
    for entry in vlm_entries:
        if isinstance(entry, Mapping):
            times.append(entry.get("timestamp"))
    return [value for value in (seconds(time) for time in times) if value is not None]


def normalize_lecture_note(
    data: Mapping[str, Any],
    known_times: Sequence[float] = (),
) -> tuple[dict[str, Any], list[str]]:
    """모델이 만든 강의 노트를 화면에서 쓸 수 있는 형태로 검증·정리합니다.

    잘못된 시간은 ``None``으로 바꾸고, 빈 항목은 버리고, 개수 상한을 넘으면 자릅니다.
    고친 내용은 경고 목록으로 함께 반환합니다. 챕터가 하나도 남지 않으면 ``ValueError``입니다.
    """
    warnings: list[str] = []
    max_time = max(known_times) + TIME_TOLERANCE_SEC if known_times else None

    def texts(value: Any, key: str) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        items = [text for text in (clean_text(item) for item in value) if text]
        limit = NOTE_LIMITS[key]
        if len(items) > limit:
            warnings.append(f"{key}: {len(items)}개 중 {limit}개만 사용")
        return items[:limit]

    def time_range(item: Mapping[str, Any], label: str) -> tuple[float | None, float | None]:
        values = []
        for key in ("start", "end"):
            raw = item.get(key)
            value = seconds(raw)
            if value is not None and max_time is not None and value > max_time:
                value = None
            if raw is not None and value is None:
                warnings.append(f"{label}: {key} 값 {raw!r}을(를) 사용할 수 없어 null로 바꿈")
            values.append(value)
        start, end = values
        if start is None and end is not None:
            start, end = end, None
        if start is not None and end is not None and end < start:
            warnings.append(f"{label}: end가 start보다 앞서 end를 null로 바꿈")
            end = None
        return start, end

    def records(value: Any, key: str) -> list[Mapping[str, Any]]:
        if not isinstance(value, list):
            return []
        items = [item for item in value if isinstance(item, Mapping)]
        limit = NOTE_LIMITS[key]
        if len(items) > limit:
            warnings.append(f"{key}: {len(items)}개 중 {limit}개만 사용")
        return items[:limit]

    terms = []
    for item in records(data.get("terms"), "terms"):
        term = clean_text(item.get("term"))
        if term:
            terms.append({"term": term, "definition": clean_text(item.get("definition"))})

    chapters = []
    for index, item in enumerate(records(data.get("chapters"), "chapters"), start=1):
        points = texts(item.get("points"), "points")
        title = clean_text(item.get("title"))
        if not title and not points:
            continue
        start, end = time_range(item, f"chapters[{index}]")
        screen_notes = [SCREEN_NOTE_PREFIX.sub("", note).strip() for note in texts(item.get("screen_notes"), "screen_notes")]
        chapters.append({
            "title": title or f"주제 {len(chapters) + 1}",
            "start": start,
            "end": end,
            "points": points,
            "screen_notes": [note for note in screen_notes if note],
        })
    if not chapters:
        raise ValueError("chapters가 비어 있습니다.")

    visuals = []
    for index, item in enumerate(records(data.get("visuals"), "visuals"), start=1):
        title = clean_text(item.get("title"))
        content = texts(item.get("content"), "content")
        if not title and not content:
            continue
        visual_type = clean_text(item.get("type"))
        if visual_type not in VISUAL_TYPES:
            normalized = normalize_screen_type(visual_type)
            visual_type = normalized if normalized in VISUAL_TYPES else "기타"
        start, end = time_range(item, f"visuals[{index}]")
        visuals.append({
            "type": visual_type,
            "title": title or visual_type,
            "start": start,
            "end": end,
            "content": content,
            "meaning": clean_text(item.get("meaning")),
        })

    title = clean_text(data.get("title"))
    if not title:
        warnings.append("title이 비어 있음")
    note = {
        "title": title,
        "key_points": texts(data.get("key_points"), "key_points"),
        "terms": terms,
        "chapters": chapters,
        "visuals": visuals,
        "conclusion": texts(data.get("conclusion"), "conclusion"),
        "notices": texts(data.get("notices"), "notices"),
    }
    return note, warnings


def _timeline(start: float | None, end: float | None) -> str:
    return "타임라인: 확인 필요" if start is None else f"타임라인: {format_range(start, end)}"


def render_note_markdown(note: Mapping[str, Any]) -> str:
    """강의 노트 JSON을 앱의 기존 마크다운 파서가 읽는 형식으로 바꿉니다(txt 저장·이전 화면 호환)."""
    lines = [f"# {note.get('title') or '강의 요약'}"]

    def section(heading: str, body: list[str]) -> None:
        if body:
            lines.extend(["", f"## {heading}", *body])

    section("핵심 주제", [f"- {point}" for point in note.get("key_points", [])])
    section("주요 용어", [
        f"- '{term['term']}': {term['definition']}" if term["definition"] else f"- '{term['term']}'"
        for term in note.get("terms", [])
    ])

    chapter_lines = []
    for index, chapter in enumerate(note.get("chapters", []), start=1):
        chapter_lines += ["", f"### {index}. {chapter['title']} ({_timeline(chapter['start'], chapter['end'])})"]
        chapter_lines += [f"- {point}" for point in chapter["points"]]
        chapter_lines += [f"- VLM 요약 자료에서는 {note_text}" for note_text in chapter["screen_notes"]]
    section("주요 내용", chapter_lines)

    visual_lines = []
    for index, visual in enumerate(note.get("visuals", []), start=1):
        visual_lines += ["", f"### {index}. {visual['title']} ({_timeline(visual['start'], visual['end'])})"]
        visual_lines.append(f"- 자료 유형: {visual['type']}")
        if visual["content"]:
            visual_lines.append("- 확인된 내용:")
            visual_lines += [f"  - {content}" for content in visual["content"]]
        if visual["meaning"]:
            visual_lines.append(f"- 강의에서의 의미: {visual['meaning']}")
    section("표/차트 기반 주요 정보", visual_lines)

    section("종합 결론", [f"- {point}" for point in note.get("conclusion", [])])
    section("공지 사항", [f"- {notice}" for notice in note.get("notices", [])])
    return "\n".join(lines).strip() + "\n"
