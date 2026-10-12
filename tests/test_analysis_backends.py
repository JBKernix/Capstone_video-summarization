import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests
from PIL import Image

from modules.llm.backends import BackendOptions, get_summary_client, use_backend
from modules.llm.claude_backend import ClaudeMessages, ClaudeSTTClient, ClaudeVLMClient, ClaudeFinalClient
from modules.common.run_history import RunRecorder, prepare_run, read_record
from app.pipeline_process import launch_pipeline


def reply(result=None, status=200, stop="tool_use"):
    response = MagicMock(status_code=status)
    response.json.return_value = {"stop_reason": stop, "content": [{"type": "tool_use", "name": "submit_result", "input": result}],
                                  "usage": {"input_tokens": 100, "output_tokens": 20}}
    return response


@pytest.mark.parametrize("health", [{"status": "ok"}, {"llm_backend": "claude", "vlm_backend": "local"}])
def test_local_mode_refuses_unverified_or_cloud_server(health):
    response = MagicMock()
    response.json.return_value = health
    with patch("modules.llm.backends.requests.get", return_value=response), pytest.raises(RuntimeError, match="LLM_BACKEND=local"):
        BackendOptions().validate()


def test_local_routes_only_to_configured_server():
    response = MagicMock()
    response.json.return_value = {"llm_backend": "local", "vlm_backend": "local", "llm_model": "Qwen3-8B"}
    with patch("modules.llm.backends.requests.get", return_value=response) as health:
        with use_backend(BackendOptions(local_server_url="http://localhost:8000")) as metadata:
            assert metadata["analysis_model"] == "Qwen3-8B"
            assert get_summary_client("stt").config.server_url == "http://localhost:8000"
            assert get_summary_client("vlm").config.server_url == "http://localhost:8000"
        health.assert_called_once_with("http://localhost:8000/health", timeout=10)


def test_claude_uses_server_without_client_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = MagicMock()
    response.json.return_value = {"claude_api_proxy": True, "claude_api_configured": True}
    with patch("modules.llm.backends.requests.get", return_value=response) as get:
        with use_backend(BackendOptions(analysis_backend="claude", local_server_url="http://server:8000")):
            for kind, cls in [("stt", ClaudeSTTClient), ("vlm", ClaudeVLMClient), ("final", ClaudeFinalClient)]:
                client = get_summary_client(kind)
                assert isinstance(client, cls)
                assert client.api.url == "http://server:8000/claude/messages"
    get.assert_called_once_with("http://server:8000/health", timeout=10)


@pytest.mark.parametrize("health", [{"status": "ok"}, {"claude_api_proxy": True, "claude_api_configured": False}])
def test_missing_server_key_or_old_server_fails_before_inference(health):
    response = MagicMock()
    response.json.return_value = health
    with patch("requests.get", return_value=response), patch("requests.post") as post, pytest.raises(RuntimeError):
        BackendOptions(analysis_backend="claude").validate()
    post.assert_not_called()


@pytest.mark.parametrize("status", [401, 429, 500])
def test_api_errors_do_not_log_credentials_or_response_body(tmp_path, monkeypatch, status):
    secret = "sk-ant-do-not-log-this"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    response = reply(status=status)
    response.text = secret
    recorder = RunRecorder(tmp_path)
    with patch("modules.llm.claude_backend.requests.post", return_value=response), pytest.raises(RuntimeError):
        with recorder.capture():
            ClaudeMessages("claude-haiku-4-5").summary("sample")
    assert secret not in (recorder.directory / "pipeline.log").read_text()
    assert secret not in (recorder.directory / "metrics.json").read_text()


def test_network_error_hides_exception_context(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    with patch("requests.post", side_effect=requests.ConnectionError("test-secret")), pytest.raises(RuntimeError) as error:
        ClaudeMessages("haiku").summary("sample")
    assert "test-secret" not in str(error.value)
    assert error.value.__suppress_context__


def test_stt_preserves_timestamps_and_counts_usage(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    stt = tmp_path / "stt.json"
    stt.write_text(json.dumps({"segments": [{"segment_id": 7, "start": 3.25, "end": 6.5, "text": "테스트"}]}))
    recorder = RunRecorder(tmp_path / "history")
    with recorder.capture(), patch("requests.post", return_value=reply({"summary": "요약", "important_segment_ids": [0]})) as post:
        result = ClaudeSTTClient("claude-haiku-4-5").summarize_stt_file_result(stt)
    assert result["important_segments"][0]["start"] == 3.25
    assert result["important_segments"][0]["segment_id"] == 7
    assert recorder.record["counts"]["api_input_tokens"] == 100
    kwargs = post.call_args.kwargs
    assert "x-api-key" not in kwargs["headers"]
    assert "test-secret" not in json.dumps(kwargs["json"])
    assert kwargs["allow_redirects"] is False


def test_stt_rejects_invented_segment_id(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    with patch("requests.post", return_value=reply({"summary": "요약", "important_segment_ids": [999]})), pytest.raises(ValueError, match="입력에 없는"):
        ClaudeSTTClient("haiku")._post_summary_payload({"segments": [{"start": 0, "end": 1, "text": "예시"}]})


def test_vlm_sends_images_and_retains_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (160, 120), "blue").save(frame)
    ocr = tmp_path / "ocr.json"
    ocr.write_text(json.dumps([{"frame_id": 3, "timestamp": 1.5, "image_path": str(frame), "ocr_text": "example"}]))
    with patch("requests.post", return_value=reply({"results": [{"index": 0, "summary": "파란 화면"}]})) as post:
        result = ClaudeVLMClient("haiku").summarize_ocr_file(ocr)
    assert result[0]["frame_id"] == 3 and result[0]["timestamp"] == 1.5
    content = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert any(block["type"] == "image" and block["source"]["media_type"] == "image/jpeg" for block in content)
    assert post.call_args.args[0].endswith("/claude/messages")
    assert "anthropic.com" not in post.call_args.args[0]


@pytest.mark.parametrize("backend", ["local", "claude"])
def test_key_not_passed_to_pipeline_children(tmp_path, monkeypatch, backend):
    secret = "test-parent-secret"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    directory = prepare_run(tmp_path)
    with patch("app.pipeline_process.prepare_run", return_value=directory), patch("app.pipeline_process.subprocess.Popen") as popen:
        _, log, _ = launch_pipeline("video.mp4", "simple", "video", analysis_backend=backend)
        log.close()
    assert secret not in json.dumps(popen.call_args.args)
    assert "ANTHROPIC_API_KEY" not in popen.call_args.kwargs["env"]
    assert os.environ["ANTHROPIC_API_KEY"] == secret
    assert secret not in (directory / "metrics.json").read_text()


def test_long_stt_is_chunked_and_merged(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    payload = {"segments": [{"segment_id": i, "start": i, "end": i + 1, "text": "가" * 7000} for i in range(2)]}
    responses = [reply({"summary": "첫 요약", "important_segment_ids": [0]}),
                 reply({"summary": "둘째 요약", "important_segment_ids": [1]}), reply({"summary": "통합 요약"})]
    with patch("requests.post", side_effect=responses) as post:
        result = ClaudeSTTClient("haiku")._post_summary_payload(payload)
    assert result["summary"] == "통합 요약" and len(result["important_segments"]) == 2
    assert post.call_count == 3
