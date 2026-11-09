import os
import subprocess
import sys
import time
from unittest.mock import patch

import pytest

from app import run_registry as registry
from app.auth import require_login
from modules.common.run_history import finish_external, prepare_run


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(registry, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(registry, "ACTIVE_FILE", tmp_path / "active.json")
    monkeypatch.setattr(registry, "_processes", {})
    return tmp_path


def _sleeper(seconds=30):
    return subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({seconds})"])


def test_job_dir_rejects_path_traversal(isolated):
    with pytest.raises(ValueError):
        registry.job_dir("../../etc")
    assert registry.load_job("..\\secrets") is None


def test_second_pipeline_is_refused_until_first_finishes(isolated):
    history = prepare_run(isolated / "history")
    process = None
    try:
        job, handle = registry.start_job(_sleeper, run_id=history.name, history_dir=history,
                                         info={"video_path": "v.mp4"})
        process = registry._processes[history.name]
        assert registry.active_job()["run_id"] == history.name
        assert handle.poll() is None
        other = prepare_run(isolated / "history")
        with pytest.raises(registry.PipelineBusyError):
            registry.start_job(_sleeper, run_id=other.name, history_dir=other, info={})
    finally:
        if process:
            process.kill()
            process.wait()
    assert registry.active_job() is None
    assert not registry.ACTIVE_FILE.exists()


def test_reattached_handle_tracks_pid_without_popen(isolated):
    history = prepare_run(isolated / "history")
    process = _sleeper()
    try:
        job = {"run_id": history.name, "history_dir": str(history), "pid": process.pid,
               "pid_identity": registry.process_identity(process.pid)}
        handle = registry.handle_for(job)  # Streamlit 재시작 후처럼 Popen 없이 추적
        assert handle.poll() is None
        assert registry.job_is_running(job)
        handle.kill()
        process.wait(timeout=10)
        assert handle.wait(timeout=10) == 1  # 실행 기록이 success가 아니면 실패로 간주
    finally:
        process.kill()


def test_terminal_history_status_is_not_running_even_if_pid_is_reused(isolated):
    history = prepare_run(isolated / "history")
    finish_external(history, "success", None)
    job = {"run_id": history.name, "history_dir": str(history), "pid": os.getpid(),
           "pid_identity": registry.process_identity(os.getpid())}
    assert not registry.job_is_running(job)
    assert registry.handle_for(job).poll() is None  # PID가 살아 있으면 poll은 아직 실행 중
    job["pid_identity"] = 12345  # 생성 시각이 다르면 다른 프로세스(PID 재사용)
    assert registry.handle_for(job).poll() == 0


def test_cleanup_removes_only_expired_inactive_folders(isolated, monkeypatch):
    old_upload = registry.new_upload_dir()
    fresh_upload = registry.new_upload_dir()
    old_job = registry.JOBS_DIR / "old-run"
    old_job.mkdir(parents=True)
    past = time.time() - 10 * 24 * 3600
    os.utime(old_upload, (past, past))
    os.utime(old_job, (past, past))
    monkeypatch.setattr(registry, "RETENTION_HOURS", 24)
    assert registry.cleanup_expired() == 2
    assert not old_upload.exists() and not old_job.exists()
    assert fresh_upload.exists()


def test_remove_upload_dir_ignores_paths_outside_upload_root(isolated):
    outside = isolated / "important"
    outside.mkdir()
    registry.remove_upload_dir(outside)
    registry.remove_upload_dir(registry.UPLOAD_DIR)
    assert outside.exists()


def test_free_space_check_reports_clear_error(isolated, monkeypatch):
    monkeypatch.setattr(registry.shutil, "disk_usage", lambda _path: type("U", (), {"free": 1024**3})())
    with pytest.raises(OSError, match="디스크 여유 공간"):
        registry.check_free_space(10 * 1024**2)


def test_external_access_without_password_is_blocked(tmp_path):
    with patch("app.auth.st") as st:
        st.secrets.get.return_value = None
        st.context.headers.get.side_effect = lambda name: "203.0.113.5" if name == "Cf-Connecting-Ip" else None
        st.stop.side_effect = RuntimeError("stopped")
        with pytest.raises(RuntimeError, match="stopped"):
            require_login()
        st.error.assert_called_once()


def test_default_api_url_is_localhost(monkeypatch):
    import importlib
    import modules.llm as llm

    monkeypatch.delenv("GPU_SERVER_URL", raising=False)
    assert importlib.reload(llm).GPU_SERVER_URL == "http://127.0.0.1:8000"
    monkeypatch.setenv("GPU_SERVER_URL", "http://10.0.0.5:9000/")
    assert importlib.reload(llm).GPU_SERVER_URL == "http://10.0.0.5:9000"
    monkeypatch.delenv("GPU_SERVER_URL")
    importlib.reload(llm)
