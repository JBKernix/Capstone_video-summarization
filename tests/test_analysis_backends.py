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
    pick = {"index": 0, "topic": "경사하강법", "reason": "갱신식 정의"}
    with recorder.capture(), patch("requests.post", return_value=reply({"summary": "요약", "important_segments": [pick]})) as post:
        result = ClaudeSTTClient("claude-haiku-4-5").summarize_stt_file_result(stt)
    assert result["important_segments"][0]["start"] == 3.25
    assert result["important_segments"][0]["segment_id"] == 7
    assert (result["important_segments"][0]["topic"], result["important_segments"][0]["reason"]) == ("경사하강법", "갱신식 정의")
    assert "강의 영상에서 추출한 STT" in post.call_args.kwargs["json"]["messages"][0]["content"][0]["text"]
    assert recorder.record["counts"]["api_input_tokens"] == 100
    kwargs = post.call_args.kwargs
    assert "x-api-key" not in kwargs["headers"]
    assert "test-secret" not in json.dumps(kwargs["json"])
    assert kwargs["allow_redirects"] is False


def test_stt_rejects_invented_segment_id(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    pick = {"index": 999, "topic": "t", "reason": "r"}
    with patch("requests.post", return_value=reply({"summary": "요약", "important_segments": [pick]})), pytest.raises(ValueError, match="입력에 없는"):
        ClaudeSTTClient("haiku")._post_summary_payload({"segments": [{"start": 0, "end": 1, "text": "예시"}]})


def test_vlm_sends_images_and_retains_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    frame = tmp_path / "frame.jpg"
    Image.new("RGB", (160, 120), "blue").save(frame)
    ocr = tmp_path / "ocr.json"
    ocr.write_text(json.dumps([{"frame_id": 3, "timestamp": 1.5, "image_path": str(frame), "ocr_text": "example"}]))
    frame_result = {"index": 0, "screen_type": "수식", "title": "갱신식", "content": "파란 화면", "formula": ""}
    with patch("requests.post", return_value=reply({"results": [frame_result]})) as post:
        result = ClaudeVLMClient("haiku").summarize_ocr_file(ocr)
    assert result[0]["frame_id"] == 3 and result[0]["timestamp"] == 1.5
    assert result[0]["vlm_summary"] == "화면 유형: 수식\n제목: 갱신식\n핵심 내용: 파란 화면\n수식·코드·수치: 없음"
    assert result[0]["vlm_fields"]["has_content"] is True
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
    responses = [reply({"summary": "첫 요약", "important_segments": [{"index": 0, "topic": "a", "reason": "r"}]}),
                 reply({"summary": "둘째 요약", "important_segments": [{"index": 1, "topic": "b", "reason": "r"}]}),
                 reply({"summary": "통합 요약"})]
    with patch("requests.post", side_effect=responses) as post:
        result = ClaudeSTTClient("haiku")._post_summary_payload(payload)
    assert result["summary"] == "통합 요약" and len(result["important_segments"]) == 2
    assert post.call_count == 3


def test_final_returns_lecture_note_and_compatible_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    stt = tmp_path / "stt_summary_result.json"
    stt.write_text(json.dumps({"summary": "## 강의 요약", "important_segments": [
        {"segment_id": 2, "start": 10.0, "end": 20.0, "topic": "갱신식", "reason": "정의"}]}), encoding="utf-8")
    vlm = tmp_path / "vlm_summary_result.json"
    vlm.write_text(json.dumps({"results": [
        {"timestamp": 12.0, "vlm_fields": {"screen_type": "수식", "title": "갱신식", "content": "가중치 갱신",
                                           "formula": "w-ηg", "has_content": True}},
        {"timestamp": 30.0, "vlm_fields": {"screen_type": "강사 화면", "title": "", "content": "", "formula": "",
                                           "has_content": False}}]}), encoding="utf-8")
    note = {"title": "경사하강법", "key_points": ["갱신"], "terms": [{"term": "학습률", "definition": "보폭"}],
            "chapters": [{"title": "갱신식", "start": 10.0, "end": 9999, "points": ["설명"], "screen_notes": ["식"]}],
            "visuals": [{"type": "수식", "title": "갱신식", "start": 12.0, "end": None, "content": ["w-ηg"], "meaning": ""}],
            "conclusion": ["정리"], "emphasis": ["꼭 기억: 학습률"], "notices": ["시험에 나온다: 갱신식"]}
    with patch("requests.post", return_value=reply(note)) as post:
        result = ClaudeFinalClient("haiku").summarize_files_result(stt, vlm)
    sent = post.call_args.kwargs["json"]
    prompt = sent["messages"][0]["content"][0]["text"]
    assert "- [10.0 ~ 20.0] 갱신식: 정의" in prompt and "- [12.0] 수식 | 갱신식" in prompt
    assert "강사 화면" not in prompt.split("[VLM 요약 자료]")[1]
    assert sent["tools"][0]["input_schema"]["required"][3] == "chapters"
    # 입력 범위를 벗어난 시간은 null로 바뀝니다.
    assert (result["lecture_note"]["chapters"][0]["start"], result["lecture_note"]["chapters"][0]["end"]) == (10.0, None)
    assert "### 1. 갱신식 (타임라인: 10.0)" in result["summary"]
    assert "- '학습률': 보폭" in result["summary"]
    assert "emphasis" in sent["tools"][0]["input_schema"]["required"]
    assert result["lecture_note"]["emphasis"] == ["꼭 기억: 학습률", "시험에 나온다: 갱신식"]
    assert result["lecture_note"]["notices"] == []


def test_final_retries_then_fails_without_chapters(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    stt = tmp_path / "stt.json"
    stt.write_text(json.dumps({"summary": "요약"}), encoding="utf-8")
    vlm = tmp_path / "vlm.json"
    vlm.write_text(json.dumps({"results": [{"timestamp": 1.0, "vlm_summary": "화면"}]}), encoding="utf-8")
    empty = {"title": "t", "key_points": [], "terms": [], "chapters": [], "visuals": [], "conclusion": [], "notices": []}
    with patch("requests.post", return_value=reply(empty)) as post, pytest.raises(ValueError, match="강의 노트"):
        ClaudeFinalClient("haiku").summarize_files_result(stt, vlm)
    assert post.call_count == 2
