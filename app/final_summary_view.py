from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.styles import apply_global_styles
from app.summary_result import get_summary_markdown, has_structured_summary, load_final_summary

DEFAULT_VIDEO_PATH = PROJECT_ROOT / "data" / "input" / "input.mp4"


def render_summary_data(summary_data: dict) -> None:
    if has_structured_summary(summary_data):
        title = summary_data.get("title", "영상 요약")
        main_topic = summary_data.get("main_topic", "")
        topics = summary_data.get("topics", [])
        conclusion = summary_data.get("conclusion", "")
        keywords = summary_data.get("keywords", [])

        st.markdown(f"## {title}")

        if main_topic:
            st.markdown('<div class="summary-box">', unsafe_allow_html=True)
            st.markdown("### 핵심 주제")
            st.write(main_topic)
            st.markdown("</div>", unsafe_allow_html=True)

        if keywords:
            st.markdown("### 키워드")
            keyword_html = "".join(
                f'<span class="keyword">{keyword}</span>' for keyword in keywords
            )
            st.markdown(keyword_html, unsafe_allow_html=True)

        if topics:
            st.markdown("### 주제별 요약")
            for index, topic in enumerate(topics, start=1):
                topic_title = topic.get("title", f"주제 {index}")
                timeline = topic.get("timeline", "")
                content = topic.get("content", "")
                label = f"{index}. {topic_title} {timeline}".strip()

                with st.expander(label, expanded=True):
                    st.write(content)

        if conclusion:
            st.markdown('<div class="summary-box">', unsafe_allow_html=True)
            st.markdown("### 종합 결론")
            st.write(conclusion)
            st.markdown("</div>", unsafe_allow_html=True)
        return

    summary_markdown = get_summary_markdown(summary_data)
    if summary_markdown:
        st.markdown(summary_markdown)
    else:
        st.json(summary_data)


def resolve_video_path(video_path: str | Path | None = None) -> Path | None:
    candidates = [
        Path(video_path) if video_path else None,
        DEFAULT_VIDEO_PATH,
    ]

    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate

    return None


def render_final_summary_page(
    final_dir: Path | None = None,
    video_path: str | Path | None = None,
) -> None:
    final_dir = final_dir or PROJECT_ROOT / "runs" / "final"
    selected_video_path = resolve_video_path(video_path)

    st.set_page_config(
        page_title="최종 요약 테스트",
        page_icon="video",
        layout="wide",
    )
    apply_global_styles(max_width=1500)

    st.markdown(
        '<div class="main-title">최종 요약 출력 테스트</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sub-title">data/input 영상과 runs/final 최종 요약본을 함께 표시합니다.</div>',
        unsafe_allow_html=True,
    )

    try:
        final_summary = load_final_summary(final_dir)
    except (FileNotFoundError, OSError, ValueError) as error:
        st.error("최종 요약 파일을 읽을 수 없습니다.")
        st.caption(str(error))
        return

    video_column, summary_column = st.columns([1, 1], gap="large")

    with video_column:
        with st.container(border=True):
            st.subheader("원본 영상")

            if selected_video_path:
                st.caption(f"파일 경로: {selected_video_path}")
                st.video(str(selected_video_path))
            else:
                st.warning("표시할 영상을 찾을 수 없습니다.")
                st.caption(f"기본 경로: {DEFAULT_VIDEO_PATH}")

    with summary_column:
        with st.container(border=True):
            st.subheader("요약 결과")
            st.caption(f"파일 경로: {final_summary.source_path}")

            if final_summary.mode == "json":
                render_summary_data(final_summary.content)
            else:
                st.markdown(final_summary.content)


if __name__ == "__main__":
    render_final_summary_page()
