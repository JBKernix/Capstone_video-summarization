"""Launch and stop pipeline children while retaining startup/crash logs."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

from modules.common.run_history import DEFAULT_HISTORY_DIR, prepare_run, finish_external
from modules.llm import GPU_SERVER_URL
from modules.llm.backends import DEFAULT_CLAUDE_MODEL
from modules.llm.local_models import DEFAULT_LOCAL_MODEL

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def launch_pipeline(video_path, summary_level, input_name, *, analysis_backend="local",
                    local_server_url=GPU_SERVER_URL, claude_model=DEFAULT_CLAUDE_MODEL,
                    local_model=DEFAULT_LOCAL_MODEL):
    directory = prepare_run(input_name=input_name, settings={"summary_level": summary_level,
                            "analysis_backend": analysis_backend, "local_model": local_model if analysis_backend == "local" else None, "preset_semantics": "whisper_only_v1"})
    log = (directory / "process.log").open("wb")
    env = os.environ.copy()
    env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    # Only the inference server reads the key; pipeline children never need it.
    env.pop("ANTHROPIC_API_KEY", None)
    try:
        process = subprocess.Popen(
            [sys.executable, "-u", str(PROJECT_ROOT / "scripts" / "run_pipeline.py"),
             "--video", video_path, "--summary-level", summary_level,
             "--history-dir", str(DEFAULT_HISTORY_DIR), "--run-id", directory.name,
             "--input-name", input_name, "--analysis-backend", analysis_backend,
             "--local-server-url", local_server_url, "--claude-model", claude_model,
             "--local-model", local_model],
            cwd=str(PROJECT_ROOT), stdout=log, stderr=subprocess.STDOUT, env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
            start_new_session=sys.platform != "win32",
        )
    except Exception as error:
        log.close()
        finish_external(directory, "failed", f"프로세스 시작 실패: {error}")
        raise
    return process, log, directory


def stop_pipeline(process, directory):
    if process.poll() is None:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, check=False)
        else:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if sys.platform != "win32":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait(timeout=5)
        finish_external(directory, "cancelled", "사용자가 분석을 중지했습니다.")
