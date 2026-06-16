from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.final_summary_view import (
    DEFAULT_VIDEO_PATH,
    render_summary_data,
    resolve_video_path,
)
from app.styles import apply_global_styles
from app.summary_result import load_final_summary

FINAL_DIR = PROJECT_ROOT / "runs" / "final"

st.set_page_config(
    page_title="요약 결과",
    page_icon="video",
    layout="wide",
)

apply_global_styles()

st.markdown(
    '<div class="main-title">메타모어 기반 영상 요약 시스템</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-title">원본 영상과 최종 요약 결과를 확인하세요.</div>',
    unsafe_allow_html=True,
)

video_path = st.session_state.get("video_path")
selected_video_path = resolve_video_path(video_path)

try:
    final_summary = load_final_summary(FINAL_DIR)
except (FileNotFoundError, OSError, ValueError) as error:
    st.warning("요약 결과 파일을 찾거나 읽을 수 없습니다.")
    st.caption(str(error))
    if st.button("영상 업로드로 이동", type="primary"):
        st.switch_page("pages/1_upload.py")
    st.stop()

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
