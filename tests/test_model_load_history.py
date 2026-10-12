import csv
import io
from unittest.mock import MagicMock, patch

import pytest

from modules.common.run_history import RunRecorder, record_model_loads, read_record, records_csv
from modules.llm.stt_summarizer_client import GPULLMClient
from tests.test_history_ui import app


def event(kind="llm", status="loaded", seconds=2.5):
    return {"kind": kind, "status": status, "duration_seconds": seconds,
            "model": "Qwen-test", "started_at": "2026-09-29T00:00:00+00:00"}


def test_poll_snapshots_do_not_double_count_and_csv_preserves_missing(tmp_path):
    recorder = RunRecorder(tmp_path)
    with recorder.capture():
        job = {"job_id": "one", "status": "running", "model_loads": [event()]}
        record_model_loads(job, 3)
        record_model_loads(job, 3)
        job = {**job, "status": "completed", "model_loads": [event(), event(status="reused", seconds=0)]}
        record_model_loads(job, 3)
        record_model_loads({"job_id": "two", "status": "failed", "model_loads": [event("vlm", "failed", 1)]}, 6)
    record = read_record(recorder.directory)
    assert record["model_loading"]["summary"] == {
        "model_load_seconds": 3.5, "llm_load_seconds": 2.5, "vlm_load_seconds": 1,
        "model_load_count": 1, "model_load_failed_count": 1, "model_reuse_count": 1,
    }
    rows = list(csv.DictReader(io.StringIO(records_csv([record, {"run_id": "old"}]).decode("utf-8-sig"))))
    assert rows[0]["model_load_seconds"] == "3.5"
    assert rows[1]["model_load_seconds"] == ""
    assert (recorder.directory / "pipeline.log").read_text().count("서버 모델 로딩 |") == 3


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_polling_saves_timings_before_return_or_error(tmp_path, status):
    recorder = RunRecorder(tmp_path)
    response = MagicMock()
    response.json.return_value = {"job_id": "one", "status": status, "error": "failed",
                                  "model_loads": [event(status="failed" if status == "failed" else "loaded")]}
    with recorder.capture(), patch("modules.llm.gpu_job_client.requests.get", return_value=response):
        if status == "failed":
            with pytest.raises(RuntimeError):
                GPULLMClient()._wait_for_job("/llm/jobs/one")
        else:
            GPULLMClient()._wait_for_job("/llm/jobs/one")
    assert read_record(recorder.directory)["model_loading"]["summary"]["model_load_seconds"] == 2.5


def test_legacy_or_invalid_metrics_remain_unmeasured(tmp_path):
    recorder = RunRecorder(tmp_path)
    with recorder.capture():
        record_model_loads({"job_id": "old", "status": "completed"}, 3)
        record_model_loads({"job_id": "bad", "model_loads": [event(seconds=float("nan"))]}, 3)
    assert "model_loading" not in recorder.record


def test_history_displays_loading_metrics_and_failures(tmp_path):
    recorder = RunRecorder(tmp_path)
    with recorder.capture():
        record_model_loads({"job_id": "one", "status": "completed", "model_loads": [event()]}, 3)
    with patch("modules.common.run_history.DEFAULT_HISTORY_DIR", tmp_path), patch("modules.common.run_history.list_records", return_value=[recorder.record]):
        at = app().run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["로딩 시간 합계"] == "2.500초"
    assert metrics["VLM 로딩"] == "0.000초"
