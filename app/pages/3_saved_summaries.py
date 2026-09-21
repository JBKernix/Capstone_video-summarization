from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
import shutil
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.final_summary_view import render_video_and_summary
from app.styles import apply_global_styles
from app.summary_result import load_final_summary

SAVE_ROOT = PROJECT_ROOT / "data" / "saved"
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi")

# result_export.build_save_folder_name()이 만드는 "[제목] - 년월일-시분초" 형식입니다.
SAVED_FOLDER_NAME_PATTERN = re.compile(r"^\[(?P<title>.*)\] - (?P<timestamp>\d{8}-\d{6})$")


def parse_saved_folder_name(folder_name: str) -> tuple[str, datetime | None]:
    """저장 폴더명에서 영상 제목과 저장 시각을 추출합니다."""
    match = SAVED_FOLDER_NAME_PATTERN.match(folder_name)
    timestamp_text = match.group("timestamp") if match else folder_name

    try:
        timestamp = datetime.strptime(timestamp_text, "%Y%m%d-%H%M%S")
    except ValueError:
        timestamp = None

    title = match.group("title") if match else folder_name
    return title, timestamp


def find_saved_video(folder: Path) -> Path | None:
    for extension in VIDEO_EXTENSIONS:
        matches = sorted(folder.glob(f"*{extension}"))
        if matches:
            return matches[0]
    return None


def list_saved_items() -> list[dict]:
    if not SAVE_ROOT.exists():
        return []

    items = []
    for folder in SAVE_ROOT.iterdir():
        if not folder.is_dir():
            continue
        title, timestamp = parse_saved_folder_name(folder.name)
        items.append({"folder": folder, "title": title, "timestamp": timestamp})

    items.sort(key=lambda item: item["timestamp"] or datetime.min, reverse=True)
    return items


st.set_page_config(
    page_title="저장된 요약",
    page_icon="🗂️",
    layout="wide",
)

apply_global_styles()

st.markdown(
    '<div class="main-title">멀티모달 기반 영상 요약 시스템</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-title">저장해 둔 영상과 요약 결과를 다시 확인하세요.</div>',
    unsafe_allow_html=True,
)

saved_items = list_saved_items()

if not saved_items:
    st.info("저장된 요약 결과가 없습니다.")
    if st.button("영상 업로드로 이동", type="primary"):
        st.switch_page("pages/1_upload.py")
    st.stop()

with st.container(border=True):
    st.subheader("🗂️ 저장된 요약 목록")

    option_labels = [
        f"{item['title']}  ·  {item['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if item['timestamp'] else '시각 알수없음'}"
        for item in saved_items
    ]

    selected_index = st.radio(
        "확인할 저장 결과를 선택하세요.",
        options=range(len(saved_items)),
        format_func=lambda index: option_labels[index],
        label_visibility="collapsed",
    )

selected_item = saved_items[selected_index]
selected_folder: Path = selected_item["folder"]
selected_video_path = find_saved_video(selected_folder)

st.write("")

try:
    final_summary = load_final_summary(selected_folder)
except (FileNotFoundError, OSError, ValueError) as error:
    st.warning("선택한 저장 결과의 요약 파일을 찾거나 읽을 수 없습니다.")
    st.caption(str(error))
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

if st.button("🗑️ 이 저장 결과 삭제"):
    st.session_state["confirm_delete_folder"] = str(selected_folder)

if st.session_state.get("confirm_delete_folder") == str(selected_folder):
    st.warning(f"'{selected_item['title']}' 저장 결과를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.")
    confirm_col, cancel_col = st.columns([1, 1])
    with confirm_col:
        if st.button("삭제 확인", type="primary", use_container_width=True):
            shutil.rmtree(selected_folder, ignore_errors=True)
            st.session_state.pop("confirm_delete_folder", None)
            st.success("삭제되었습니다.")
            st.rerun()
    with cancel_col:
        if st.button("취소", use_container_width=True):
            st.session_state.pop("confirm_delete_folder", None)
            st.rerun()
