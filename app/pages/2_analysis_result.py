from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.final_summary_view import render_video_and_summary, resolve_video_path
from app.result_export import save_analysis_result
from app.styles import apply_global_styles
from app.summary_result import load_final_summary

FINAL_DIR = PROJECT_ROOT / "runs" / "final"
SAVE_ROOT = PROJECT_ROOT / "data" / "saved"

st.set_page_config(
    page_title="요약 결과",
    page_icon="video",
    layout="wide",
)

apply_global_styles()

st.markdown(
    '<div class="main-title">멀티모달 기반 영상 요약 시스템</div>',
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

render_video_and_summary(
    selected_video_path,
    final_summary,
    column_ratio=(0.85, 1.15),
    column_gap="medium",
    show_captions=False,
    summary_container_height=600,
)

st.write("")

if st.button("💾 영상과 요약 결과 저장", use_container_width=False):
    try:
        saved_dir = save_analysis_result(
            selected_video_path,
            FINAL_DIR,
            SAVE_ROOT,
            title=st.session_state.get("video_title"),
        )
    except FileNotFoundError as error:
        st.error(str(error))
    else:
        st.success(f"저장 완료: {saved_dir}")
