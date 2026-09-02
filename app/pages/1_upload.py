import streamlit as st
from pathlib import Path
import json
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
from modules.common.progress import PROGRESS_MARKER, STEP_LABELS, STEP_STT, TOTAL_STEPS
from modules.preprocess import download_youtube_video, is_youtube_url

INPUT_DIR = PROJECT_ROOT / "data" / "input"
RUN_LOG_PATH = PROJECT_ROOT / "runs" / "app_pipeline.log"
INPUT_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
# Whisper STT의 tqdm 진행률 표시줄(예: "45%|████  | 12/27 ...")을 감지하고 퍼센트를 추출합니다.
STT_TQDM_PATTERN = re.compile(r"^\s*(\d{1,3})%\|")
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
    return bool(STT_TQDM_PATTERN.search(line)) or (
        "|" in line and ("it/s" in line or "s/it" in line)
    )


def is_path_output_log_line(line: str) -> bool:
    lower_line = line.lower()
    return bool(PATH_FRAGMENT_PATTERN.search(line)) and any(
        keyword in lower_line for keyword in PATH_OUTPUT_KEYWORDS
    )


def read_raw_log_lines() -> list[str]:
    if not RUN_LOG_PATH.exists():
        return []

    raw_text = RUN_LOG_PATH.read_bytes()
    try:
        text = raw_text.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_text.decode("cp949", errors="replace")

    return [clean_pipeline_log_line(raw_line) for raw_line in text.splitlines()]


def read_pipeline_logs(raw_lines: list[str], limit: int = 40) -> list[str]:
    """사람이 읽기 편하도록 진행률 마커/tqdm 진행바/산출물 경로 줄을 걸러낸 로그입니다."""
    lines = [
        line
        for line in raw_lines
        if line
        and not line.startswith(PROGRESS_MARKER)
        and not is_progress_log_line(line)
        and not is_path_output_log_line(line)
    ]
    return lines[-limit:]


def parse_progress_state(raw_lines: list[str]) -> dict[int, dict]:
    """로그 원본 줄에서 단계별 최신 진행 상황(퍼센트/메시지)을 추출합니다.

    같은 단계에서 퍼센트 없는 메시지가 나중에 와도 이전 퍼센트는 유지합니다(sticky).
    """
    state: dict[int, dict] = {}

    def _update(step: int, message: str | None, percent: float | None) -> None:
        entry = state.setdefault(step, {"percent": None, "message": ""})
        if message:
            entry["message"] = message
        if percent is not None:
            entry["percent"] = percent

    for line in raw_lines:
        if line.startswith(PROGRESS_MARKER):
            try:
                payload = json.loads(line[len(PROGRESS_MARKER):].strip())
            except json.JSONDecodeError:
                continue
            step = payload.get("step")
            if isinstance(step, int):
                _update(step, payload.get("message"), payload.get("percent"))
            continue

        match = STT_TQDM_PATTERN.match(line)
        if match:
            _update(STEP_STT, "음성 인식 처리 중", float(match.group(1)))

    return state


def describe_step_status(step: int, progress_state: dict[int, dict]) -> dict:
    """단계 하나의 렌더링 상태(done/active-percent/active-indeterminate/pending)를 계산합니다."""
    if not progress_state:
        return {"state": "pending", "percent": None, "message": ""}

    current_step = max(progress_state.keys())
    if step < current_step:
        return {"state": "done", "percent": 100.0, "message": ""}
    if step > current_step:
        return {"state": "pending", "percent": None, "message": ""}

    entry = progress_state[step]
    percent = entry.get("percent")
    message = entry.get("message") or ""
    if percent is not None:
        return {"state": "active-percent", "percent": percent, "message": message}
    return {"state": "active-indeterminate", "percent": None, "message": message}


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

process = st.session_state.get("analysis_process")
analysis_running = bool(process and process.poll() is None)

# 분석이 이번 세션에서 시작된 경우에만 로그를 읽어 진행 상황을 계산합니다.
# (그렇지 않으면 이전에 실행된 파이프라인의 로그가 남아 있어 착시를 일으킬 수 있습니다.)
if process is not None:
    raw_log_lines = read_raw_log_lines()
    progress_state = parse_progress_state(raw_log_lines)
else:
    raw_log_lines = []
    progress_state = {}

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

    step_items_html = []
    for step_num in range(1, TOTAL_STEPS + 1):
        title, desc = STEP_LABELS[step_num]
        status = describe_step_status(step_num, progress_state)

        if status["state"] == "done":
            circle_class = "step-circle step-done"
            circle_style = ""
            circle_label = "✓"
            desc_class = "step-desc"
            desc_text = desc
        elif status["state"] == "active-percent":
            percent = status["percent"]
            circle_class = "step-circle step-active-percent"
            circle_style = (
                f' style="background: conic-gradient(#2563eb {percent:.0f}%, #eaf2ff {percent:.0f}%)"'
            )
            circle_label = f"{percent:.0f}%"
            desc_class = "step-desc step-live"
            desc_text = status["message"] or desc
        elif status["state"] == "active-indeterminate":
            circle_class = "step-circle step-active-indeterminate"
            circle_style = ""
            circle_label = str(step_num)
            desc_class = "step-desc step-live"
            desc_text = status["message"] or desc
        else:
            circle_class = "step-circle"
            circle_style = ""
            circle_label = str(step_num)
            desc_class = "step-desc"
            desc_text = desc

        step_items_html.append(
            f'<div class="step-item">'
            f'<div class="{circle_class}"{circle_style}>{circle_label}</div>'
            f'<div class="step-title">{title}</div>'
            f'<div class="{desc_class}">{desc_text}</div>'
            f"</div>"
        )

    st.markdown(
        '<div class="step-wrap">' + "".join(step_items_html) + "</div>",
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

if process:
    returncode = process.poll()

    if returncode is None:
        visible_logs = read_pipeline_logs(raw_log_lines)
        current_step_num = max(progress_state.keys()) if progress_state else None

        with st.status("영상 분석을 진행하고 있습니다.", expanded=True):
            if current_step_num:
                step_title, _ = STEP_LABELS[current_step_num]
                entry = progress_state[current_step_num]
                percent = entry.get("percent")
                message = entry.get("message") or step_title
                step_line = f"현재 단계: {current_step_num}/{TOTAL_STEPS} {step_title} — {message}"
                if percent is not None:
                    st.write(f"{step_line} ({percent:.0f}%)")
                    st.progress(min(1.0, percent / 100))
                else:
                    st.write(step_line)
            else:
                st.write("파이프라인을 시작하는 중입니다...")

            if visible_logs:
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
        logs = read_pipeline_logs(read_raw_log_lines())
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
