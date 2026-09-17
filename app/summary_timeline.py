from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import streamlit as st

from modules.common import find_existing_path, load_json

# LLM이 생성하는 최종 요약 텍스트에 박혀 있는 "(타임라인: 0.0 ~ 7.0)" 형태의 표기입니다.
# 구간이 아니라 "(타임라인: 573.12)"처럼 단일 시점만 나올 때도 있어 끝 시각은 선택 사항입니다.
TIMELINE_PATTERN = re.compile(r"\(\s*타임라인\s*:\s*([\d.]+)\s*(?:~\s*([\d.]+)\s*)?\)")
CHART_HEADING_KEYWORDS = ("표", "차트")
NUMBERED_ITEM_PATTERN = re.compile(
    r"###\s+(\d+)\.\s*(.*?)\s*\(\s*타임라인\s*:\s*([\d.]+)\s*(?:~\s*([\d.]+)\s*)?\)"
)
HAS_NUMBERED_ITEM_PATTERN = re.compile(r"(^|\n)###\s+\d+\.")


def format_timestamp(seconds: float) -> str:
    """초 단위 시간을 ``분:초`` 또는 ``시:분:초`` 문자열로 변환합니다."""
    total_seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_timeline_label(start: float, end: float | None) -> str:
    if end is None:
        return format_timestamp(start)
    return f"{format_timestamp(start)} ~ {format_timestamp(end)}"


def _plain_timeline_text(text: str) -> str:
    """클릭 기능을 넣기 애매한 위치에서는 타임라인 표기를 읽기 쉬운 형식으로만 바꿉니다."""

    def _replace(match: re.Match[str]) -> str:
        start = float(match.group(1))
        end = float(match.group(2)) if match.group(2) else None
        return f"({_format_timeline_label(start, end)})"

    return TIMELINE_PATTERN.sub(_replace, text)


def _render_timeline_badge(start: float, end: float | None = None) -> None:
    """클릭하면 페이지 새로고침 없이 영상을 해당 지점으로 이동시키는 뱃지를 렌더링합니다.

    ``onclick="..."`` 같은 인라인 이벤트 핸들러 속성은 ``st.markdown(unsafe_allow_html=True)``
    뿐 아니라 ``st.html(unsafe_allow_javascript=True)``에서도 React #231 오류를 일으킵니다
    (둘 다 내부적으로 HTML 속성을 React prop으로 변환하려 시도하는 것으로 보입니다). 그래서
    HTML 속성으로는 이벤트를 걸지 않고, 별도 ``<script>`` 태그 안에서 ``addEventListener``로
    이벤트를 붙입니다. ``document.currentScript.previousElementSibling``으로 바로 앞에 있는
    이 뱃지 자신만 정확히 찾아서 연결하므로 다른 뱃지와 섞이지 않습니다.
    """
    label = _format_timeline_label(start, end)
    st.html(
        f'<span class="timeline-badge">▶ {label}</span>'
        "<script>"
        "(function(){"
        "var badge = document.currentScript.previousElementSibling;"
        "if (badge) {"
        "badge.addEventListener('click', function(){"
        "var v = document.querySelector('video');"
        f"if (v) {{ v.currentTime = {start}; v.play(); }}"
        "});"
        "}"
        "})();"
        "</script>",
        unsafe_allow_javascript=True,
        width="content",
    )


def _load_ocr_entries(ocr_result_path: Path) -> list[dict[str, Any]]:
    if not ocr_result_path.is_file():
        return []
    try:
        data = load_json(ocr_result_path)
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _find_matching_frame_image(
    ocr_entries: list[dict[str, Any]],
    start: float,
    end: float | None,
    ocr_result_path: Path,
    project_root: Path,
) -> Path | None:
    """타임라인 구간과 겹치는 프레임 중 표/차트로 분류된 화면을 우선으로 찾습니다."""
    end = end if end is not None else start
    in_range = [
        entry
        for entry in ocr_entries
        if isinstance(entry, dict) and start - 1 <= float(entry.get("timestamp", -1)) <= end + 1
    ]
    if not in_range:
        return None

    chart_entries = [entry for entry in in_range if entry.get("scene_type") == "chart_or_table"]
    pool = chart_entries or in_range
    pool = sorted(pool, key=lambda entry: not str(entry.get("ocr_text", "")).strip())

    image_path = pool[0].get("image_path")
    if not image_path:
        return None

    return find_existing_path(image_path, ocr_result_path, project_root)


def _render_numbered_items_section(
    heading: str,
    body: str,
    show_images: bool,
    ocr_entries: list[dict[str, Any]],
    ocr_result_path: Path,
    project_root: Path,
) -> None:
    """번호가 매겨진 하위 항목(``### N. 제목 (타임라인: ...)``)을 카드로 렌더링합니다."""
    st.markdown(f"## {heading}")

    items = re.split(r"\n(?=###\s+\d+\.)", body.strip())
    for item in items:
        item = item.strip()
        if not item:
            continue

        match = NUMBERED_ITEM_PATTERN.match(item)
        if not match:
            st.markdown(_plain_timeline_text(item))
            continue

        index, item_title, start_text, end_text = match.groups()
        start = float(start_text)
        end = float(end_text) if end_text else None
        remaining = item[match.end():].strip()

        with st.container(border=True):
            st.markdown(f"**{index}. {item_title}**")
            _render_timeline_badge(start, end)

            if show_images:
                image_column, text_column = st.columns([1, 2])
                image_path = _find_matching_frame_image(
                    ocr_entries, start, end, ocr_result_path, project_root
                )
                with image_column:
                    if image_path:
                        st.image(str(image_path), caption="해당 구간 화면", width="stretch")
                    else:
                        st.caption("해당 구간 화면을 찾을 수 없습니다.")
                with text_column:
                    st.markdown(_plain_timeline_text(remaining))
            else:
                st.markdown(_plain_timeline_text(remaining))


def render_summary_with_timeline(
    markdown_text: str,
    ocr_result_path: Path,
    project_root: Path,
) -> None:
    """최종 요약 텍스트를 렌더링합니다.

    번호가 매겨진 항목(``### N. 제목 (타임라인: ...)``)이 있는 구간은 항목별 카드로 표시하고,
    각 카드에는 분:초 단위의 클릭 가능한 타임라인 뱃지를 붙입니다. "표/차트 기반 주요 정보"
    성격의 구간은 해당 구간 화면 스크린샷도 함께 보여줍니다. 그 외 구간은 마크다운 그대로
    표시하되 "(타임라인: ...)" 표기만 읽기 쉬운 분:초 형식으로 바꿉니다.
    """
    ocr_entries = _load_ocr_entries(ocr_result_path)

    sections = re.split(r"\n(?=##\s+[^#])", markdown_text.strip())
    for section in sections:
        section = section.strip()
        if not section:
            continue

        heading_match = re.match(r"##\s+(.+)", section)
        if not heading_match:
            st.markdown(_plain_timeline_text(section))
            continue

        heading = heading_match.group(1).strip()
        body = section[heading_match.end():]

        if HAS_NUMBERED_ITEM_PATTERN.search(body):
            show_images = any(keyword in heading for keyword in CHART_HEADING_KEYWORDS)
            _render_numbered_items_section(
                heading, body, show_images, ocr_entries, ocr_result_path, project_root
            )
            continue

        st.markdown(_plain_timeline_text(section))
