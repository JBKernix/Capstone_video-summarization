import streamlit as st
from pathlib import Path
import sys

from styles import apply_global_styles

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

st.set_page_config(
    page_title="멀티모달 기반 영상 요약 시스템",
    page_icon="🎬",
    layout="wide",
)

apply_global_styles(max_width=None)

st.markdown(
    '<div class="main-title">멀티모달 기반 영상 요약 시스템</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-title">새 영상을 업로드해 분석하거나, 저장해 둔 요약 결과를 확인하세요.</div>',
    unsafe_allow_html=True,
)

upload_col, saved_col = st.columns(2, gap="large")

with upload_col:
    with st.container(border=True):
        st.subheader("🎥 영상 업로드")
        st.write("새 영상을 업로드하거나 유튜브 링크로 영상을 가져와 분석을 시작합니다.")
        if st.button("업로드 페이지로 이동", type="primary", use_container_width=True):
            st.switch_page("pages/1_upload.py")

with saved_col:
    with st.container(border=True):
        st.subheader("🗂️ 저장된 요약 확인")
        st.write("이전에 저장해 둔 영상과 요약 결과를 다시 확인합니다.")
        if st.button("저장된 요약 보기", use_container_width=True):
            st.switch_page("pages/3_saved_summaries.py")
