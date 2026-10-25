import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.api_models import JobStatusResponse
from app.inference_jobs import InferenceJobRunner
from app.job_store import JobStore
from app.model_load_metrics import ACTIVE_LOAD_SINK, measure_model_load


class FakeLoader:
    def __init__(self):
        self.model = self.tokenizer = None
        self.config = SimpleNamespace(model_path="models/Test-LLM")
        self.fail = False

    @measure_model_load("llm", "tokenizer")
    def load(self):
        if self.fail:
            raise RuntimeError("load failed")
        self.model = self.tokenizer = object()
        return self.model, self.tokenizer


def test_load_reuse_and_failure_have_separate_timings():
    loader, events = FakeLoader(), []
    token = ACTIVE_LOAD_SINK.set(events.append)
    try:
        with patch("app.model_load_metrics.time.perf_counter", side_effect=[10, 12.5, 20, 30, 34]):
            loader.load()
            loader.load()
            loader.model = loader.tokenizer = None
            loader.fail = True
            with pytest.raises(RuntimeError):
                loader.load()
    finally:
        ACTIVE_LOAD_SINK.reset(token)
    assert [event["status"] for event in events] == ["loaded", "reused", "failed"]
    assert [event["duration_seconds"] for event in events] == [2.5, 0, 4]


@pytest.mark.parametrize("kind", ["summary", "vlm", "final"])
def test_runner_publishes_loads_before_terminal_response(kind):
    loader, store = FakeLoader(), JobStore()
    def load_result(result):
        loader.load()
        loader.load()
        return result
    service = SimpleNamespace(
        summarize_stt=lambda **kwargs: load_result("요약"),
        summarize_frames=lambda **kwargs: load_result([{"vlm_summary": "화면"}]),
        summarize_final_note=lambda **kwargs: load_result(
            {"markdown": "통합", "lecture_note": None, "format": "json", "attempts": [], "warnings": []}),
        unload_llm=lambda: None, unload_vlm=lambda: None,
    )
    runner = InferenceJobRunner(service, store, logging.getLogger("test"))
    store.create("job-1", "queued")
    if kind == "summary":
        runner.run_summary("job-1", {"full_text": "예시", "summary_level": "simple"})
    elif kind == "vlm":
        runner.run_vlm("job-1", [{}], [b"image"], 160)
    else:
        runner.run_final("job-1", None, b"{}", None, b"{}", 2048)
    response = store.response_data("job-1")
    assert response["status"] == "completed"
    assert [e["status"] for e in response["model_loads"]] == ["loaded", "reused"]
    wire = JobStatusResponse(**response).model_dump()
    assert wire["model_loads"] == response["model_loads"]
    assert ACTIVE_LOAD_SINK.get() is None
    # Job snapshots cannot mutate the store or inherit another job's measurements.
    response["model_loads"][0]["status"] = "corrupted"
    assert store.response_data("job-1")["model_loads"][0]["status"] == "loaded"
    store.create("job-2", "queued")
    runner.run_final("job-2", None, b"{}", None, b"{}", 2048)
    assert [e["status"] for e in store.response_data("job-2")["model_loads"]] == ["reused", "reused"]


def test_runner_preserves_failed_load():
    loader, store = FakeLoader(), JobStore()
    loader.fail = True
    service = SimpleNamespace(summarize_stt=lambda **kwargs: loader.load(), unload_llm=lambda: None)
    store.create("failure", "queued")
    InferenceJobRunner(service, store, logging.getLogger("test")).run_summary(
        "failure", {"full_text": "예시", "summary_level": "simple"})
    response = store.response_data("failure")
    assert response["status"] == "failed"
    assert response["model_loads"][0]["status"] == "failed"
    assert ACTIVE_LOAD_SINK.get() is None
