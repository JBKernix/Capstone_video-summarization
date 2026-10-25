import streamlit as st
from pathlib import Path
import shutil
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.auth import require_login
from app.analysis_options import render_analysis_options
from modules.llm import GPU_SERVER_URL
from modules.llm.local_models import DEFAULT_LOCAL_MODEL
from app.pipeline_process import launch_pipeline, stop_pipeline
from app.run_registry import (
    EXTERNAL_UPLOAD_LIMIT_MB,
    PipelineBusyError,
    active_job,
    check_free_space,
    cleanup_expired,
    handle_for,
    job_is_running,
    load_job,
    new_upload_dir,
    remove_upload_dir,
)
from modules.common.run_history import finish_external, read_record
from app.styles import apply_global_styles
from app.pipeline_log import (
    describe_step_status,
    parse_progress_state,
    read_pipeline_logs,
    read_raw_log_lines as _read_raw_log_lines,
)
from modules.common.progress import STEP_LABELS, TOTAL_STEPS
from modules.preprocess import download_youtube_video, get_video_info, is_youtube_url
from modules.llm.summary_levels import (
    DEFAULT_SUMMARY_LEVEL,
    SUMMARY_LEVEL_CAPTIONS,
    SUMMARY_LEVEL_LABELS,
    SUMMARY_LEVELS,
)

INPUT_DIR = PROJECT_ROOT / "data" / "input"
RUN_LOG_PATH = PROJECT_ROOT / "runs" / "app_pipeline.log"
INPUT_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def read_raw_log_lines() -> list[str]:
    return _read_raw_log_lines(st.session_state.get("analysis_log_path", RUN_LOG_PATH))


def is_cloudflare_request() -> bool:
    """Cloudflare Tunnel을 거친 요청인지 확인합니다(Cloudflare가 붙이는 헤더 기준)."""
    try:
        return bool(st.context.headers.get("Cf-Connecting-Ip"))
    except Exception:
        return False


def set_current_video(save_path: Path, display_name: str, source_key: str, title: str = "") -> None:
    previous = st.session_state.get("video_path")
    if previous and Path(previous).parent != Path(save_path).parent:
        # 이 세션이 이전에 올린 영상만 정리합니다. 실행 중인 작업의 영상은 보존됩니다.
        remove_upload_dir(Path(previous).parent)
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


def save_uploaded_video(uploaded_file) -> Path:
    """업로드 영상을 서버의 업로드별 고유 폴더에 저장하고 영상 파일인지 검증합니다."""
    check_free_space(uploaded_file.size)
    upload_suffix = Path(uploaded_file.name).suffix.lower() or ".mp4"
    upload_dir = new_upload_dir()
    save_path = upload_dir / f"input{upload_suffix}"
    try:
        uploaded_file.seek(0)
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        if save_path.stat().st_size != uploaded_file.size:
            raise ValueError(
                f"파일 저장 크기 불일치: 업로드={uploaded_file.size}, 저장={save_path.stat().st_size}"
            )
        try:
            get_video_info(save_path)
        except (OSError, RuntimeError, ValueError) as error:
            raise ValueError("영상 정보를 읽을 수 없습니다. 손상되었거나 지원하지 않는 영상 파일입니다.") from error
    except BaseException:
        remove_upload_dir(upload_dir)
        raise
    return save_path


def attach_job(job: dict) -> None:
    """새로고침·재접속한 세션을 서버에 남아 있는 분석 작업에 다시 연결합니다."""
    st.session_state["attached_run_id"] = job["run_id"]
    st.session_state["analysis_run_id"] = job["run_id"]
    st.session_state["analysis_run_dir"] = job["run_dir"]
    st.session_state["analysis_history_dir"] = job["history_dir"]
    st.session_state["analysis_log_path"] = str(Path(job["history_dir"]) / "process.log")
    st.session_state["video_path"] = job.get("video_path")
    st.session_state["uploaded_filename"] = job.get("uploaded_filename") or job.get("input_name")
    st.session_state["uploaded_file_key"] = job.get("uploaded_file_key") or ""
    st.session_state["video_title"] = job.get("video_title") or ""
    try:
        status = read_record(job["history_dir"]).get("status")
    except (OSError, ValueError):
        status = None
    st.session_state["analysis_cancelled"] = status == "cancelled"
    if job_is_running(job):
        st.session_state["analysis_process"] = handle_for(job)
        st.session_state["analysis_done"] = False
    else:
        st.session_state["analysis_done"] = status == "success"


def start_analysis_process(video_path: str, summary_level: str) -> None:
    close_analysis_log_handle()
    process, log_handle, directory = launch_pipeline(
        video_path, summary_level,
        st.session_state.get("video_title") or st.session_state.get("uploaded_filename") or Path(video_path).name,
        analysis_backend=st.session_state.get("analysis_backend", "local"),
        local_server_url=GPU_SERVER_URL,
        local_model=st.session_state.get("local_model", DEFAULT_LOCAL_MODEL),
        job_info={
            "uploaded_filename": st.session_state.get("uploaded_filename"),
            "uploaded_file_key": st.session_state.get("uploaded_file_key"),
            "video_title": st.session_state.get("video_title"),
        },
    )
    st.session_state["analysis_run_id"] = directory.name
    st.session_state["attached_run_id"] = directory.name
    st.session_state["analysis_run_dir"] = load_job(directory.name)["run_dir"]
    st.query_params["run"] = directory.name
    st.session_state["analysis_history_dir"] = str(directory)
    st.session_state["analysis_log_path"] = str(directory / "process.log")
    st.session_state["analysis_process"] = process
    st.session_state["analysis_log_handle"] = log_handle
    st.session_state["analysis_done"] = False
    st.session_state["analysis_cancelled"] = False


def stop_analysis_process() -> None:
    process = st.session_state.get("analysis_process")

    if process:
        stop_pipeline(process, st.session_state["analysis_history_dir"])

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

require_login()

apply_global_styles()

if not st.session_state.get("upload_cleanup_done"):
    st.session_state["upload_cleanup_done"] = True
    cleanup_expired()

# 새로고침하거나 브라우저 연결이 끊겼다가 다시 접속하면 URL의 run 값으로 작업에 다시 연결합니다.
_run_param = st.query_params.get("run")
if (
    _run_param
    and st.session_state.get("analysis_process") is None
    and st.session_state.get("attached_run_id") != _run_param
):
    _job = load_job(_run_param)
    if _job:
        attach_job(_job)
    else:
        st.session_state["attached_run_id"] = _run_param

process = st.session_state.get("analysis_process")
returncode = process.poll() if process is not None else None
analysis_running = process is not None and returncode is None
analysis_finished_with_error = (
    process is not None
    and returncode is not None
    and returncode != 0
    and not st.session_state.get("analysis_cancelled")
)

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

st.page_link("pages/4_run_history.py", label="실행 이력과 성능 지표 보기", icon="📊")

# =========================
# 영상 업로드 박스 / 요약 옵션 박스 (3:2 좌우 분할)
# =========================
upload_col, option_col = st.columns([3, 2])

with upload_col, st.container(border=True):
    st.subheader("🎥 영상 업로드")

    upload_mode = st.radio(
        "업로드 방식",
        options=["파일 업로드", "유튜브 링크"],
        horizontal=True,
        disabled=analysis_running,
        label_visibility="collapsed",
    )

    if upload_mode == "파일 업로드":
        external_upload = is_cloudflare_request()
        uploaded_file = st.file_uploader(
            "분석할 영상을 업로드하세요.",
            type=["mp4", "mov", "avi"],
            disabled=analysis_running,
            max_upload_size=EXTERNAL_UPLOAD_LIMIT_MB if external_upload else None,
        )

        if external_upload:
            st.caption(
                f"지원 형식: MP4, MOV, AVI · 외부 접속 업로드 한도: 파일당 {EXTERNAL_UPLOAD_LIMIT_MB}MB "
                "(Cloudflare 요청 크기 제한). 더 큰 영상은 유튜브 링크를 사용하거나 서버 PC에서 직접 업로드하세요."
            )
        else:
            st.caption("지원 형식: MP4, MOV, AVI")
        if uploaded_file is not None and not analysis_running:
            uploaded_key = f"{uploaded_file.name}_{uploaded_file.size}"

            if st.session_state.get("uploaded_file_key") != uploaded_key:
                try:
                    save_path = save_uploaded_video(uploaded_file)
                except (OSError, ValueError) as error:
                    st.error(f"영상 저장에 실패했습니다: {error}")
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
                    upload_dir = None
                    try:
                        check_free_space(0)
                        upload_dir = new_upload_dir()
                        save_path, video_title = download_youtube_video(youtube_url, upload_dir / "input")
                    except Exception as error:
                        remove_upload_dir(upload_dir)
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
    elif process is None and st.session_state.get("analysis_done") and st.session_state.get("analysis_run_id"):
        st.page_link("pages/2_analysis_result.py", label="최근 분석 결과 보기", icon="📄",
                     query_params={"run": st.session_state["analysis_run_id"]})

with option_col, st.container(border=True):
    backend_ready = render_analysis_options(disabled=analysis_running)

st.write("")

# =========================
# 분석 절차 박스
# =========================
with st.container(border=True):
    st.subheader("🔎 분석 절차")

    step_items_html = []
    for step_num in range(1, TOTAL_STEPS + 1):
        title, desc = STEP_LABELS[step_num]
        status = describe_step_status(
            step_num, progress_state, has_error=analysis_finished_with_error
        )

        if status["state"] == "done":
            circle_class = "step-circle step-done"
            circle_style = ""
            circle_label = "✓"
            desc_class = "step-desc"
            desc_text = desc
        elif status["state"] == "error":
            circle_class = "step-circle step-error"
            circle_style = ""
            circle_label = "✕"
            desc_class = "step-desc step-error-text"
            desc_text = status["message"] or "오류 발생"
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
# GPU 서버 한 대에서 전체 파이프라인은 한 번에 하나만 실행합니다.
other_job = None if analysis_running else active_job()
if other_job is not None:
    st.warning("다른 사용자의 영상 분석이 진행 중입니다. 완료된 뒤 분석을 시작할 수 있습니다.")

left, center, right = st.columns([1, 1.2, 1])

with center:
    start_button = st.button(
        "✨ 영상 분석 시작",
        use_container_width=True,
        type="primary",
        disabled=not st.session_state.get("video_path") or analysis_running or not backend_ready
        or other_job is not None,
    )

if start_button:
    try:
        start_analysis_process(
            st.session_state["video_path"],
            st.session_state.get("summary_level", DEFAULT_SUMMARY_LEVEL),
        )
    except PipelineBusyError as error:
        st.error(str(error))
    else:
        st.rerun()

if process:
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
        history_dir = st.session_state.get("analysis_history_dir")
        if history_dir:
            finish_external(history_dir, "interrupted", f"프로세스 종료 (코드 {returncode}). 정상 종료 기록이 없습니다.")
        logs = read_pipeline_logs(read_raw_log_lines())
        visible_logs = logs[-40:]
        st.session_state["last_analysis_log"] = "\n".join(visible_logs)
        st.session_state.pop("analysis_process", None)

        if returncode == 0:
            st.session_state["analysis_done"] = True
            st.success("분석 완료! 결과 화면으로 이동합니다.")
            st.switch_page("pages/2_analysis_result.py",
                           query_params={"run": st.session_state["analysis_run_id"]})
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
