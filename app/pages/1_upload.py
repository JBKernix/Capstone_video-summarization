import streamlit as st
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from styles import apply_global_styles
from modules.preprocess import download_youtube_video, is_youtube_url

INPUT_DIR = PROJECT_ROOT / "data" / "input"
RUN_LOG_PATH = PROJECT_ROOT / "runs" / "app_pipeline.log"
INPUT_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
PROGRESS_LINE_PATTERN = re.compile(r"^\s*\d{1,3}%\|")
PATH_FRAGMENT_PATTERN = re.compile(r"([A-Za-z]:[\\/]|(?:^|\s)(?:runs|data)[\\/])")
PATH_OUTPUT_KEYWORDS = (
    "저장",
    "결과",
    "완료:",
    "파일:",
    "메타데이터:",
    "saved:",
    "complete:",
)


def clean_pipeline_log_line(line: str) -> str:
    line = ANSI_ESCAPE_PATTERN.sub("", line)
    return line.strip()


def is_progress_log_line(line: str) -> bool:
    return bool(PROGRESS_LINE_PATTERN.search(line)) or (
        "|" in line and ("it/s" in line or "s/it" in line)
    )


def is_path_output_log_line(line: str) -> bool:
    lower_line = line.lower()
    return bool(PATH_FRAGMENT_PATTERN.search(line)) and any(
        keyword in lower_line for keyword in PATH_OUTPUT_KEYWORDS
    )


def read_pipeline_logs(limit: int = 40) -> list[str]:
    if not RUN_LOG_PATH.exists():
        return []

    raw_text = RUN_LOG_PATH.read_bytes()
    try:
        text = raw_text.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_text.decode("cp949", errors="replace")

    lines = []

    for raw_line in text.splitlines():
        clean_line = clean_pipeline_log_line(raw_line)
        if (
            clean_line
            and not is_progress_log_line(clean_line)
            and not is_path_output_log_line(clean_line)
        ):
            lines.append(clean_line)

    return lines[-limit:]


def get_latest_progress_message(logs: list[str]) -> str:
    if logs:
        return logs[-1]
    return "파이프라인을 시작하는 중입니다."


def set_current_video(save_path: Path, display_name: str, source_key: str, title: str = "") -> None:
    st.session_state["video_path"] = str(save_path)
    st.session_state["uploaded_filename"] = display_name
    st.session_state["uploaded_file_key"] = source_key
    st.session_state["video_title"] = title
    st.session_state["analysis_done"] = False
    st.session_state.pop("last_analysis_log", None)


def close_analysis_log_handle() -> None:
    log_handle = st.session_state.pop("analysis_log_handle", None)
    if log_handle:
        log_handle.close()


def start_analysis_process(video_path: str) -> None:
    close_analysis_log_handle()
    log_handle = RUN_LOG_PATH.open("wb")
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            str(PROJECT_ROOT / "scripts" / "run_pipeline.py"),
            "--video",
            video_path,
        ],
        cwd=str(PROJECT_ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=creationflags,
        env=env,
    )

    st.session_state["analysis_process"] = process
    st.session_state["analysis_log_handle"] = log_handle
    st.session_state["analysis_done"] = False
    st.session_state["analysis_cancelled"] = False


def stop_analysis_process() -> None:
    process = st.session_state.get("analysis_process")

    if process and process.poll() is None:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
            )
        else:
            process.terminate()

    close_analysis_log_handle()
    st.session_state["analysis_done"] = False
    st.session_state["analysis_cancelled"] = True


# NOTE: 두 분기 모두 동일한 값을 반환해 poll() 체크가 의미가 없던 죽은 로직이라 비활성화합니다.
# def get_analysis_process():
#     process = st.session_state.get("analysis_process")
#     return process if process and process.poll() is None else process


st.set_page_config(
    page_title="영상 업로드",
    page_icon="🎬",
    layout="wide",
)

apply_global_styles()

current_process = st.session_state.get("analysis_process")
analysis_running = bool(current_process and current_process.poll() is None)

st.markdown(
    '<div class="main-title">멀티모달 기반 영상 요약 시스템</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-title">분석할 영상을 업로드한 뒤 영상 분석을 시작하세요.</div>',
    unsafe_allow_html=True,
)

# =========================
# 영상 업로드 박스
# =========================
with st.container(border=True):
    st.subheader("🎥 영상 업로드")

    upload_mode = st.radio(
        "업로드 방식",
        options=["파일 업로드", "유튜브 링크"],
        horizontal=True,
        disabled=analysis_running,
        label_visibility="collapsed",
    )

    if upload_mode == "파일 업로드":
        uploaded_file = st.file_uploader(
            "분석할 영상을 업로드하세요.",
            type=["mp4", "mov", "avi"],
            disabled=analysis_running,
        )

        st.caption("지원 형식: MP4, MOV, AVI")
        if uploaded_file is not None and not analysis_running:
            uploaded_key = f"{uploaded_file.name}_{uploaded_file.size}"

            if st.session_state.get("uploaded_file_key") != uploaded_key:
                upload_suffix = Path(uploaded_file.name).suffix.lower() or ".mp4"
                save_path = INPUT_DIR / f"input{upload_suffix}"

                uploaded_file.seek(0)
                with open(save_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                if save_path.stat().st_size != uploaded_file.size:
                    st.error(
                        f"파일 저장 크기 불일치: 업로드={uploaded_file.size}, 저장={save_path.stat().st_size}"
                    )
                    st.stop()

                set_current_video(
                    save_path,
                    uploaded_file.name,
                    uploaded_key,
                    title=Path(uploaded_file.name).stem,
                )

            st.success("영상 업로드가 완료되었습니다.")
            st.info(f"업로드 파일명: {uploaded_file.name}")
        elif not analysis_running:
            st.info("분석할 영상을 먼저 업로드하세요.")

    else:
        youtube_url = st.text_input(
            "유튜브 영상 링크를 입력하세요.",
            placeholder="https://www.youtube.com/watch?v=...",
            disabled=analysis_running,
        )
        download_clicked = st.button(
            "다운로드",
            disabled=analysis_running or not youtube_url.strip(),
        )

        if download_clicked:
            if not is_youtube_url(youtube_url):
                st.error("유효한 유튜브 링크가 아닙니다.")
            else:
                download_key = f"youtube_{youtube_url.strip()}"
                with st.spinner("유튜브 영상을 다운로드하는 중입니다..."):
                    try:
                        save_path, video_title = download_youtube_video(youtube_url, INPUT_DIR / "input")
                    except Exception as error:
                        st.error(f"유튜브 영상 다운로드에 실패했습니다: {error}")
                    else:
                        set_current_video(save_path, save_path.name, download_key, title=video_title)

        if str(st.session_state.get("uploaded_file_key", "")).startswith("youtube_"):
            st.success("유튜브 영상 다운로드가 완료되었습니다.")
            st.info(f"저장 파일명: {st.session_state['uploaded_filename']}")
        elif not analysis_running:
            st.info("유튜브 링크를 입력하고 다운로드하세요.")

    if analysis_running:
        st.info("분석이 진행 중일 때는 새 영상을 업로드할 수 없습니다.")

st.write("")

# =========================
# 분석 절차 박스
# =========================
with st.container(border=True):
    st.subheader("🔎 분석 절차")

    steps = [
        ("1", "영상 업로드", "파일 업로드 및 검증"),
        ("2", "오디오 추출", "영상에서 음성 분리"),
        ("3", "STT 분석", "음성을 텍스트로 변환"),
        ("4", "프레임 추출", "중요 구간 프레임 선택"),
        ("5", "OCR 분석", "화면 텍스트 및 시각 정보 이해"),
        ("6", "VLM 요약 생성", "프레임별 시각 요약 생성"),
        ("7", "최종 요약 생성", "음성/시각 요약 통합"),
    ]

    cols = st.columns(7)

    for col, (num, title, desc) in zip(cols, steps):
        with col:
            st.markdown(
                f"""
                <div class="step-item">
                    <div class="step-circle">{num}</div>
                    <div class="step-title">{title}</div>
                    <div class="step-desc">{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# =========================
# 분석 시작 버튼
# =========================
left, center, right = st.columns([1, 1.2, 1])

with center:
    start_button = st.button(
        "✨ 영상 분석 시작",
        use_container_width=True,
        type="primary",
        disabled="video_path" not in st.session_state or analysis_running,
    )

if start_button:
    start_analysis_process(st.session_state["video_path"])
    st.rerun()

process = st.session_state.get("analysis_process")

if process:
    returncode = process.poll()
    logs = read_pipeline_logs()
    visible_logs = logs[-40:]

    if returncode is None:
        with st.status("영상 분석을 진행하고 있습니다.", expanded=True):
            st.write("1. 영상 파일 확인 중...")
            st.write("2. 분석 파이프라인 실행 중...")

            if visible_logs:
                st.write(f"현재 단계: {get_latest_progress_message(logs)}")
                st.code("\n".join(visible_logs), language="text")
            else:
                st.info("분석 로그를 기다리는 중입니다.")

            if st.button("분석 중지", type="secondary", use_container_width=True):
                stop_analysis_process()
                st.warning("분석을 중지했습니다.")
                st.rerun()

        time.sleep(1)
        st.rerun()

    else:
        close_analysis_log_handle()
        logs = read_pipeline_logs()
        visible_logs = logs[-40:]
        st.session_state["last_analysis_log"] = "\n".join(visible_logs)
        st.session_state.pop("analysis_process", None)

        if returncode == 0:
            st.session_state["analysis_done"] = True
            st.success("분석 완료! 결과 화면으로 이동합니다.")
            st.switch_page("pages/2_analysis_result.py")
        elif st.session_state.get("analysis_cancelled"):
            st.session_state["analysis_done"] = False
            st.warning("분석이 중지되었습니다.")
            if visible_logs:
                st.code("\n".join(visible_logs), language="text")
        else:
            st.session_state["analysis_done"] = False
            st.error("분석 중 오류가 발생했습니다.")
            if visible_logs:
                st.caption("마지막 실행 로그를 확인하세요.")
                st.code("\n".join(visible_logs), language="text")
            else:
                st.caption("표시할 수 있는 로그가 없습니다.")
