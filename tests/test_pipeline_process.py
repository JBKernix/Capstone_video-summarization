import subprocess
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline_process import launch_pipeline, stop_pipeline
from modules.common.run_history import prepare_run, read_record


def test_startup_failure_is_archived(tmp_path):
    directory = prepare_run(tmp_path)
    with patch("app.pipeline_process.prepare_run", return_value=directory), patch(
        "app.pipeline_process.subprocess.Popen", side_effect=OSError("cannot start")
    ), pytest.raises(OSError):
        launch_pipeline("video.mp4", "simple", "video.mp4")
    record = read_record(directory)
    assert record["status"] == "failed"
    assert "cannot start" in record["error"]
    assert (directory / "process.log").exists()


def test_stop_waits_for_exit_before_recording_cancel(tmp_path):
    directory = prepare_run(tmp_path)
    process = MagicMock()
    process.poll.return_value = None
    process.pid = 1234
    process.wait.side_effect = [subprocess.TimeoutExpired("pipeline", 5), 0]
    with patch("app.pipeline_process.sys.platform", "linux"), patch("app.pipeline_process.os.killpg") as kill:
        stop_pipeline(process, directory)
    assert kill.call_count == 2
    assert process.wait.call_count == 2
    assert read_record(directory)["status"] == "cancelled"
