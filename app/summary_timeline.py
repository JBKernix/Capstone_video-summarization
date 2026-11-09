from __future__ import annotations

from pathlib import Path

import streamlit as st

from app.summary_parse import format_timeline_label, format_timestamp, parse_summary_markdown

__all__ = ["format_timestamp", "render_summary_with_timeline"]


def _render_timeline_badge(start: float, end: float | None = None) -> None:
    """클릭하면 페이지 새로고침 없이 영상을 해당 지점으로 이동시키는 뱃지를 렌더링합니다.

    ``onclick="..."`` 같은 인라인 이벤트 핸들러 속성은 ``st.markdown(unsafe_allow_html=True)``
    뿐 아니라 ``st.html(unsafe_allow_javascript=True)``에서도 React #231 오류를 일으킵니다
    (둘 다 내부적으로 HTML 속성을 React prop으로 변환하려 시도하는 것으로 보입니다). 그래서
    HTML 속성으로는 이벤트를 걸지 않고, 별도 ``<script>`` 태그 안에서 ``addEventListener``로
    이벤트를 붙입니다. ``document.currentScript.previousElementSibling``으로 바로 앞에 있는
    이 뱃지 자신만 정확히 찾아서 연결하므로 다른 뱃지와 섞이지 않습니다.
    """
    label = format_timeline_label(start, end)
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


def _render_numbered_items_section(block: dict) -> None:
    """번호가 매겨진 하위 항목(``### N. 제목 (타임라인: ...)``)을 카드로 렌더링합니다."""
    st.markdown(f"## {block['heading']}")

    for item in block["items"]:
        if item["type"] == "markdown":
            st.markdown(item["text"])
            continue

        with st.container(border=True):
            st.markdown(f"**{item['index']}. {item['title']}**")
            _render_timeline_badge(item["start"], item["end"])

            if block["show_images"]:
                image_column, text_column = st.columns([1, 2])
                with image_column:
                    if item["image_path"]:
                        st.image(str(item["image_path"]), caption="해당 구간 화면", width="stretch")
                    else:
                        st.caption("해당 구간 화면을 찾을 수 없습니다.")
                with text_column:
                    st.markdown(item["text"])
            else:
                st.markdown(item["text"])


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
    for block in parse_summary_markdown(markdown_text, ocr_result_path, project_root):
        if block["type"] == "items":
            _render_numbered_items_section(block)
        else:
            st.markdown(block["text"])
