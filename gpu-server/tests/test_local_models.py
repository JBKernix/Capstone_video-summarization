import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from configs import local_models as catalog
from app.local_model_manager import LocalModelManager
from scripts.download_models import download_profile

@pytest.fixture
def model_root(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "MODEL_ROOT", tmp_path)
    return tmp_path

def write_checkpoint(repo, *, revision="abc123"):
    directory = catalog.repo_path(repo)
    directory.mkdir(parents=True, exist_ok=True)
    files = {"config.json": b"{}", "model.safetensors": b"weights"}
    for name, data in files.items():
        (directory / name).write_bytes(data)
    (directory / "download-manifest.json").write_text(json.dumps({"repo": repo, "revision": revision,
        "files": {name: len(data) for name, data in files.items()}}))
    return directory

def test_partial_download_is_never_ready(model_root):
    repo = catalog.get_profile("qwen3.5-9b").repos[0]
    directory = write_checkpoint(repo)
    assert catalog.profile_status("qwen3.5-9b")["ready"]
    (directory / "model.safetensors").write_bytes(b"bad")
    assert not catalog.profile_status("qwen3.5-9b")["ready"]
    with pytest.raises(ValueError, match="다운로드"):
        catalog.require_downloaded("qwen3.5-9b")

def test_unknown_model_not_a_path(model_root):
    with pytest.raises(ValueError):
        catalog.get_profile("../../arbitrary-model")

def test_download_plan_retry_and_snapshot_pinning(model_root, monkeypatch):
    repo = catalog.get_profile("qwen3.5-9b").repos[0]
    revisions = []
    payload = {"config.json": b"{}", "model.safetensors": b"weights"}
    def model_info(repo_id, revision, files_metadata):
        revisions.append(revision)
        return SimpleNamespace(sha="commit-1", siblings=[SimpleNamespace(rfilename=n, size=len(v)) for n,v in payload.items()])
    snapshot = Mock()
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(
        HfApi=lambda: SimpleNamespace(model_info=model_info), snapshot_download=snapshot))
    download_profile("qwen3.5-9b", plan=True)
    snapshot.assert_not_called()
    assert not catalog.repo_path(repo).exists()
    snapshot.side_effect = RuntimeError("interrupted")
    with pytest.raises(RuntimeError):
        download_profile("qwen3.5-9b")
    assert not catalog.profile_status("qwen3.5-9b")["ready"]
    def complete(**kwargs):
        assert kwargs["revision"] == "commit-1"
        for name, data in payload.items():
            (catalog.repo_path(repo) / name).write_bytes(data)
    snapshot.side_effect = complete
    download_profile("qwen3.5-9b")
    assert revisions == ["main", "main", "commit-1"]
    assert catalog.profile_status("qwen3.5-9b")["ready"]

def test_manager_keeps_one_profile_and_unloads_before_switch(monkeypatch):
    original = SimpleNamespace(summary_service=Mock(), job_store=Mock(), logger=Mock())
    monkeypatch.setattr("app.local_model_manager.require_downloaded", lambda _: {})
    services = []
    def service(llm, vlm, **limits):
        assert llm is vlm
        value = Mock(llm_service=SimpleNamespace(loader=llm), limits=limits)
        services.append(value)
        return value
    monkeypatch.setitem(sys.modules, "services.summary_service", SimpleNamespace(SummaryService=service))
    monkeypatch.setattr("models.multimodal_loader.MultimodalLoader", Mock())
    manager = LocalModelManager(original)
    first = manager._runner_for("qwen3.5-9b")
    assert manager._runner_for("qwen3.5-9b") is first
    assert len(services) == 1
    second = manager._runner_for("qwen3-vl-8b")
    assert second is not first and len(services) == 2
    first.summary_service.unload_llm.assert_called_once()
    first.summary_service.unload_vlm.assert_called_once()
    assert second.keep_llm_loaded and second.keep_vlm_loaded
    # Qwen3-VL 8B만 측정한 GPU 메모리 한도에 맞춘 입력 제한을 받습니다.
    assert services[0].limits == {"max_stt_chars": None, "max_vlm_chars": None}
    assert services[1].limits == {"max_stt_chars": 4000, "max_vlm_chars": 4000}
    assert (first.segment_chunk_chars, second.segment_chunk_chars) == (None, 6000)

def test_profile_setup_failure_marks_job_failed(monkeypatch):
    original = SimpleNamespace(summary_service=Mock(), job_store=Mock(), logger=Mock())
    manager = LocalModelManager(original)
    monkeypatch.setattr(manager, "_runner_for", Mock(side_effect=ValueError("not downloaded")))
    manager.run("qwen3.5-9b", "run_summary", "job1", {})
    assert original.job_store.update.call_args.kwargs["status"] == "failed"

def test_model_api_unknown_and_duplicate_download(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import local_model_api as api
    monkeypatch.setattr(api, "_downloads", {})
    executor = Mock()
    monkeypatch.setattr(api, "_executor", executor)
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    assert client.post("/models/unknown/download").status_code == 422
    for _ in range(2):
        assert client.post("/models/qwen3.5-9b/download").status_code == 202
    executor.submit.assert_called_once()
    models = client.get("/models").json()["models"]
    assert len(models) == 7
    assert next(m for m in models if m["id"] == "qwen3.5-9b")["download"]["status"] == "queued"

def test_text_and_vision_share_loader_and_log_reuse(monkeypatch):
    from contextlib import nullcontext
    from PIL import Image
    from app.model_load_metrics import ACTIVE_LOAD_SINK
    from models.multimodal_loader import MultimodalLoader
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext))
    loader = MultimodalLoader("qwen3.5-9b")
    ids = SimpleNamespace(shape=(1, 3))
    class Inputs(dict):
        def to(self, device):
            return self
    processor = Mock()
    processor.apply_chat_template.return_value = Inputs(input_ids=ids)
    processor.batch_decode.return_value = ["한국어 요약"]
    output = Mock()
    output.__getitem__ = Mock(return_value=[123])
    model = Mock(device="cuda:0")
    model.generate.return_value = output
    def load():
        loader.model, loader.processor = model, processor
        return model, processor
    monkeypatch.setattr(loader, "_load", load)
    events = []
    token = ACTIVE_LOAD_SINK.set(events.append)
    try:
        assert loader.generate("뉴스 요약", 128) == "한국어 요약"
        assert loader.describe_image(Image.new("RGB", (20, 20)), "장면 분석", 64) == "한국어 요약"
    finally:
        ACTIVE_LOAD_SINK.reset(token)
    assert [e["status"] for e in events] == ["loaded", "reused"]
    assert [e["kind"] for e in events] == ["llm", "vlm"]
    assert events[1]["duration_seconds"] == 0
    assert events[0]["local_model"] == "qwen3.5-9b"
    assert model.generate.call_args.kwargs["max_new_tokens"] == 64
    content = processor.apply_chat_template.call_args.args[0][0]["content"]
    assert content[0]["type"] == "image"


def test_server_routes_keep_selected_model_in_all_three_jobs(monkeypatch):
    import importlib
    from fastapi.testclient import TestClient
    from services.vlm_service import VLMService
    fake_service = SimpleNamespace(vlm_service=VLMService(loader=Mock()))
    monkeypatch.setitem(sys.modules, "services.summary_service", SimpleNamespace(SummaryService=lambda: fake_service))
    sys.modules.pop("app.server", None)
    server = importlib.import_module("app.server")
    try:
        executor = Mock()
        monkeypatch.setattr(server, "job_executor", executor)
        monkeypatch.setattr(server, "require_downloaded", lambda model: catalog.get_profile(model))
        client = TestClient(server.app)
        model = "qwen3.5-9b"
        assert client.post("/llm/summarize", json={"full_text": "뉴스입니다", "local_model": model}).status_code == 202
        assert executor.submit.call_args.args[1:3] == (model, "run_summary")
        ocr = json.dumps([{"image_path": "frame.jpg", "frame_id": 0, "texts": []}])
        result = client.post("/vlm/summarize", data={"local_model": model}, files={
            "ocr_result": ("ocr.json", ocr, "application/json"), "frames": ("frame.jpg", b"image", "image/jpeg")})
        assert result.status_code == 202, result.text
        assert executor.submit.call_args.args[1:3] == (model, "run_vlm")
        result = client.post("/llm/final-summary", data={"local_model": model}, files={
            "stt_summary_result": ("stt.json", b"{}", "application/json"),
            "vlm_summary_result": ("vlm.json", b"[]", "application/json")})
        assert result.status_code == 202, result.text
        assert executor.submit.call_args.args[1:3] == (model, "run_final")
        assert client.post("/llm/summarize", json={"full_text": "뉴스", "local_model": "unknown"}).status_code == 422
    finally:
        sys.modules.pop("app.server", None)
