from unittest.mock import Mock
import pytest
from streamlit.testing.v1 import AppTest
from modules.llm.backends import BackendOptions, ACTIVE_BACKEND, get_summary_client
from modules.llm.local_models import LOCAL_MODEL_LABELS

def response(data):
    return Mock(json=lambda: data, raise_for_status=lambda: None)

def test_selected_model_metadata_and_missing_weights(monkeypatch):
    state = {"id": "qwen3.5-9b", "ready": True, "precision": "nf4", "checkpoints": [{"repo": "Qwen/Qwen3.5-9B", "revision": "abc"}]}
    monkeypatch.setattr("modules.llm.backends.requests.get", Mock(side_effect=[
        response({"local_model_selection": True}), response({"models": [state]})]))
    metadata = BackendOptions(local_model="qwen3.5-9b").validate()
    assert metadata["local_model_precision"] == "nf4"
    assert metadata["model_checkpoints"][0]["revision"] == "abc"
    state["ready"] = False
    monkeypatch.setattr("modules.llm.backends.requests.get", Mock(side_effect=[
        response({"local_model_selection": True}), response({"models": [state]})]))
    with pytest.raises(RuntimeError, match="다운로드"):
        BackendOptions(local_model="qwen3.5-9b").validate()

def test_new_model_rejects_legacy_server(monkeypatch):
    monkeypatch.setattr("modules.llm.backends.requests.get", lambda *a, **k: response({"llm_backend": "local", "vlm_backend": "local"}))
    with pytest.raises(RuntimeError, match="모델 선택"):
        BackendOptions(local_model="qwen3.5-9b").validate()

@pytest.mark.parametrize("kind", ["stt", "vlm", "final"])
def test_all_clients_receive_same_profile(kind):
    token = ACTIVE_BACKEND.set(BackendOptions(local_model="internvl3.5-8b"))
    try:
        assert get_summary_client(kind).config.local_model == "internvl3.5-8b"
    finally:
        ACTIVE_BACKEND.reset(token)

def test_ui_model_selection_preserved_across_backend_and_whisper_changes():
    app = AppTest.from_string("from app.analysis_options import render_analysis_options\nrender_analysis_options()")
    app.run()
    assert not app.exception
    assert len(app.selectbox(key="local_model").options) == len(LOCAL_MODEL_LABELS)
    app.selectbox(key="local_model").set_value("qwen3.5-9b").run()
    app.radio(key="summary_level").set_value("detailed").run()
    app.radio(key="analysis_backend").set_value("claude").run()
    assert not app.selectbox
    assert not app.text_input
    app.radio(key="analysis_backend").set_value("local").run()
    assert app.selectbox(key="local_model").value == "qwen3.5-9b"
    assert app.radio(key="summary_level").value == "detailed"
    assert not app.exception

def test_ui_model_status_without_download_action(monkeypatch):
    get = Mock(return_value=response({"models": [{"id": "qwen3-vl-8b", "label": "Qwen3-VL 8B Instruct", "precision": "nf4", "ready": True}]}))
    monkeypatch.setattr("app.analysis_options.requests.get", get)
    app = AppTest.from_string("from app.analysis_options import render_analysis_options\nrender_analysis_options()")
    app.run().selectbox(key="local_model").set_value("qwen3-vl-8b").run()
    assert all("다운로드" not in button.label for button in app.button)
    next(b for b in app.button if b.label == "설치 상태 확인 / 새로고침").click().run()
    assert get.call_args.args[0].endswith("/models")
    assert app.dataframe[0].value.iloc[0]["상태"] == "다운로드 완료"
    assert not app.exception
