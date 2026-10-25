from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.auth import require_login
from app.final_summary_view import OCR_RESULT_PATH, render_video_and_summary, resolve_video_path
from app.result_export import save_analysis_result
from app.run_registry import load_job
from app.styles import apply_global_styles
from app.summary_result import load_final_summary

FINAL_DIR = PROJECT_ROOT / "runs" / "final"
SAVE_ROOT = PROJECT_ROOT / "data" / "saved"

st.set_page_config(
    page_title="요약 결과",
    page_icon="video",
    layout="wide",
)

require_login()

apply_global_styles()

st.markdown(
    '<div class="main-title">멀티모달 기반 영상 요약 시스템</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-title">원본 영상과 최종 요약 결과를 확인하세요.</div>',
    unsafe_allow_html=True,
)

st.page_link("pages/4_run_history.py", label="실행 시간과 처리량 확인", icon="📊")

# 실행별 산출물 폴더(runs/jobs/<run_id>)에서 결과를 읽습니다. URL의 run 값이 있으면
# 새로고침·재접속 후에도 같은 결과를 보여주고, 없으면 기존 단일 실행 경로(runs/final)를 사용합니다.
job = load_job(st.query_params.get("run") or st.session_state.get("analysis_run_id"))
if job:
    run_dir = Path(job["run_dir"])
    final_dir = run_dir / "final"
    ocr_result_path = run_dir / "ocr" / "ocr_result.json"
    video_path = job.get("video_path")
    video_title = job.get("video_title") or job.get("input_name")
    st.query_params["run"] = job["run_id"]
else:
    final_dir = FINAL_DIR
    ocr_result_path = OCR_RESULT_PATH
    video_path = st.session_state.get("video_path")
    video_title = st.session_state.get("video_title")
selected_video_path = resolve_video_path(video_path)

try:
    final_summary = load_final_summary(final_dir)
except (FileNotFoundError, OSError, ValueError):
    st.warning("요약 결과 파일을 찾거나 읽을 수 없습니다. 분석이 완료되지 않았거나 보존 기간이 지나 정리되었을 수 있습니다.")
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
    ocr_result_path=ocr_result_path,
)

st.write("")

if st.button("💾 영상과 요약 결과 저장", use_container_width=False):
    try:
        saved_dir = save_analysis_result(
            selected_video_path,
            final_dir,
            SAVE_ROOT,
            title=video_title,
            ocr_result_path=ocr_result_path,
        )
    except FileNotFoundError as error:
        st.error(str(error))
    else:
        # 서버 내부 절대경로는 외부 사용자에게 노출하지 않습니다.
        st.success(f"저장 완료: {saved_dir.name} (저장된 요약 페이지에서 확인할 수 있습니다)")
