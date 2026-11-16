"""Single-server job bookkeeping shared by every browser session.

Streamlit 세션 상태는 브라우저 탭마다 따로 있고 새로고침하면 사라집니다. 이 모듈은
서버 PC 한 대에서 여러 원격 사용자가 접속해도 다음이 보장되도록 서버 측 상태를 관리합니다.

- 업로드 영상과 파이프라인 산출물을 실행별 폴더에 분리 저장해 결과가 섞이지 않게 합니다.
- GPU가 하나이므로 전체 파이프라인은 서버 전체에서 한 번에 하나만 실행합니다.
- 브라우저 연결이 끊기거나 새로고침해도 run_id(URL 쿼리)로 진행 중/완료된 작업에 다시 연결합니다.
- 오래된 업로드/실행 폴더는 보존 기간이 지나면 정리합니다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

from modules.common.run_history import TERMINAL_STATUSES, atomic_json, read_record, run_directory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOBS_DIR = PROJECT_ROOT / "runs" / "jobs"
UPLOAD_DIR = PROJECT_ROOT / "data" / "input" / "uploads"
ACTIVE_FILE = PROJECT_ROOT / "runs" / "active_pipeline.json"
JOB_FILENAME = "job.json"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# 업로드 영상·실행 산출물 보존 기간입니다. 저장 버튼으로 data/saved에 복사한 결과는 지우지 않습니다.
RETENTION_HOURS = _env_float("JOB_RETENTION_HOURS", 72)
# 업로드 저장 전 확보해야 하는 디스크 여유 공간입니다(오디오·프레임 등 중간 산출물 포함).
MIN_FREE_DISK_GB = _env_float("MIN_FREE_DISK_GB", 5)
# Cloudflare 무료/Pro 플랜의 요청 본문 한도(100MB)입니다. 외부 접속 업로드에만 적용합니다.
EXTERNAL_UPLOAD_LIMIT_MB = int(_env_float("EXTERNAL_UPLOAD_LIMIT_MB", 100))

_lock = threading.Lock()
# 같은 Streamlit 프로세스 안의 모든 세션이 공유합니다. Streamlit 재시작 후에는 PID로 추적합니다.
_processes: dict[str, subprocess.Popen] = {}


class PipelineBusyError(RuntimeError):
    """다른 사용자의 분석이 이미 실행 중일 때 발생합니다."""


# ---------------------------------------------------------------------------
# 프로세스 식별 (PID 재사용으로 엉뚱한 프로세스를 실행 중으로 오인하지 않도록 생성 시각을 함께 확인)
# ---------------------------------------------------------------------------
def process_identity(pid: int) -> int | None:
    """실행 중인 프로세스의 생성 시각 값을 반환합니다. 프로세스가 없으면 ``None``입니다."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != 259:
                return None  # 259 = STILL_ACTIVE
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                return None
            return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        finally:
            kernel32.CloseHandle(handle)
    try:
        stat = Path(f"/proc/{int(pid)}/stat").read_text()
        return int(stat.rsplit(")", 1)[1].split()[19])
    except (OSError, ValueError, IndexError):
        try:
            os.kill(int(pid), 0)
        except OSError:
            return None
        return 0


def _process_matches(pid: int | None, identity: int | None) -> bool:
    if not pid:
        return False
    current = process_identity(pid)
    return current is not None and (identity is None or current == identity)


class PipelineHandle:
    """``subprocess.Popen``과 같은 poll/wait/kill/pid를 제공하는 실행 핸들입니다.

    Streamlit이 재시작돼 Popen 객체가 사라져도 PID와 실행 기록(metrics.json)으로 상태를 판단합니다.
    """

    def __init__(self, job: dict):
        self.job = job
        self.run_id = job["run_id"]
        self.pid = job.get("pid")

    def poll(self) -> int | None:
        process = _processes.get(self.run_id)
        if process is not None:
            return process.poll()
        if _process_matches(self.pid, self.job.get("pid_identity")):
            return None
        return 0 if _history_status(self.job) == "success" else 1

    def wait(self, timeout: float | None = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        while (code := self.poll()) is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(f"pipeline {self.run_id}", timeout)
            time.sleep(0.2)
        return code

    def kill(self) -> None:
        process = _processes.get(self.run_id)
        if process is not None:
            process.kill()
        elif self.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(self.pid), "/T", "/F"], capture_output=True, check=False)
            else:
                os.kill(self.pid, 9)


def _history_status(job: dict) -> str | None:
    try:
        return read_record(job["history_dir"]).get("status")
    except (OSError, ValueError, KeyError):
        return None


# ---------------------------------------------------------------------------
# 실행별 폴더와 작업 정보
# ---------------------------------------------------------------------------
def job_dir(run_id: str) -> Path:
    """run_id 형식을 검증한 뒤 실행 산출물 폴더를 반환합니다(경로 탐색 차단)."""
    return run_directory(JOBS_DIR, run_id)


def load_job(run_id: str | None) -> dict | None:
    if not run_id:
        return None
    try:
        path = job_dir(run_id) / JOB_FILENAME
        job = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return job if isinstance(job, dict) and job.get("run_id") == run_id else None


def save_job(job: dict) -> None:
    directory = job_dir(job["run_id"])
    directory.mkdir(parents=True, exist_ok=True)
    atomic_json(directory / JOB_FILENAME, job)


def job_is_running(job: dict) -> bool:
    if job.get("run_id") in _processes:
        return _processes[job["run_id"]].poll() is None
    if _history_status(job) in TERMINAL_STATUSES:
        return False
    return _process_matches(job.get("pid"), job.get("pid_identity"))


def active_job() -> dict | None:
    """서버 전체에서 현재 실행 중인 분석 작업을 반환합니다. 끝난 작업 표시는 지웁니다."""
    with _lock:
        return _active_job_locked()


def _active_job_locked() -> dict | None:
    try:
        active = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    job = load_job(active.get("run_id")) if isinstance(active, dict) else None
    if job and job_is_running(job):
        return job
    ACTIVE_FILE.unlink(missing_ok=True)
    return None


def start_job(spawn, *, run_id: str, history_dir: Path, info: dict):
    """실행 슬롯을 확보한 뒤 ``spawn()``으로 파이프라인을 시작합니다.

    Args:
        spawn: 실제 프로세스를 시작하고 ``subprocess.Popen``을 반환하는 함수입니다.
        run_id: 실행 ID(실행 이력 폴더명과 동일)입니다.
        history_dir: 실행 이력 폴더입니다.
        info: 새로고침 후 화면 복원에 쓸 영상 경로/제목 등 부가 정보입니다.

    Raises:
        PipelineBusyError: 다른 분석이 이미 실행 중일 때 발생합니다.
    """
    with _lock:
        if _active_job_locked() is not None:
            raise PipelineBusyError("다른 사용자의 영상 분석이 진행 중입니다. 완료된 뒤 다시 시작하세요.")
        process = spawn()
        _processes[run_id] = process
        job = {
            **info,
            "run_id": run_id,
            "history_dir": str(history_dir),
            "run_dir": str(job_dir(run_id)),
            "pid": int(process.pid),
            "pid_identity": process_identity(int(process.pid)),
            "started_at": time.time(),
        }
        save_job(job)
        atomic_json(ACTIVE_FILE, {"run_id": run_id})
    return job, PipelineHandle(job)


def handle_for(job: dict) -> PipelineHandle:
    return PipelineHandle(job)


def forget_process(run_id: str) -> None:
    _processes.pop(run_id, None)


# ---------------------------------------------------------------------------
# 업로드 저장과 정리
# ---------------------------------------------------------------------------
def new_upload_dir() -> Path:
    directory = UPLOAD_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:12]}"
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def check_free_space(required_bytes: int, path: Path = PROJECT_ROOT) -> None:
    """업로드 크기와 중간 산출물 여유분을 저장할 공간이 없으면 ``OSError``를 발생시킵니다."""
    free = shutil.disk_usage(path).free
    needed = int(required_bytes) * 2 + int(MIN_FREE_DISK_GB * 1024**3)
    if free < needed:
        raise OSError(
            f"서버 디스크 여유 공간이 부족합니다 (남은 공간 {free / 1024**3:.1f}GB, "
            f"필요 공간 약 {needed / 1024**3:.1f}GB). 관리자에게 문의하세요."
        )


def remove_upload_dir(path: str | Path | None) -> None:
    """``UPLOAD_DIR`` 안의 업로드 폴더만 삭제합니다. 실행 중인 작업의 영상은 지우지 않습니다."""
    if not path:
        return
    directory = Path(path).resolve()
    root = UPLOAD_DIR.resolve()
    if directory == root or root not in directory.parents:
        return
    active = active_job()
    if active and Path(active.get("video_path", "")).resolve().parent == directory:
        return
    shutil.rmtree(directory, ignore_errors=True)


def cleanup_expired(now: float | None = None) -> int:
    """보존 기간이 지난 업로드/실행 산출물 폴더를 삭제하고 삭제한 개수를 반환합니다."""
    if RETENTION_HOURS <= 0:
        return 0
    cutoff = (now or time.time()) - RETENTION_HOURS * 3600
    active = active_job()
    keep = set()
    if active:
        keep = {Path(active["run_dir"]).resolve(), Path(active.get("video_path", "")).resolve().parent}
    removed = 0
    for root in (UPLOAD_DIR, JOBS_DIR):
        if not root.is_dir():
            continue
        for child in root.iterdir():
            try:
                if child.is_dir() and child.resolve() not in keep and child.stat().st_mtime < cutoff:
                    shutil.rmtree(child, ignore_errors=True)
                    removed += 1
            except OSError:
                continue
    return removed
