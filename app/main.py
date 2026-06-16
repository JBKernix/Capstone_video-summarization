import streamlit as st
from pathlib import Path
import sys

from styles import apply_global_styles

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.final_summary_view import render_final_summary_page

st.set_page_config(
    page_title="멀티모달 기반 영상 요약 시스템",
    page_icon="🎬",
    layout="wide",
)

apply_global_styles(max_width=None)

st.switch_page("pages/1_upload.py")