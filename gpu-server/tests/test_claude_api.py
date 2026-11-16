from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.claude_api import claude_api_configured, router

app = FastAPI()
app.include_router(router)
client = TestClient(app)
PAYLOAD = {"model": "claude-haiku-4-5", "max_tokens": 2048, "system": "요약",
           "messages": [{"role": "user", "content": [{"type": "text", "text": "sample"}]}],
           "tools": [{"name": "submit_result", "input_schema": {"type": "object"}}],
           "tool_choice": {"type": "tool", "name": "submit_result"}}


def test_reads_only_server_environment_and_preserves_usage(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "server-test-secret")
    response = MagicMock(status_code=200)
    response.json.return_value = {"content": [{"type": "tool_use", "name": "submit_result", "input": {"summary": "결과"}}],
                                  "stop_reason": "tool_use", "usage": {"input_tokens": 5, "output_tokens": 3}}
    with patch("app.claude_api.requests.post", return_value=response) as post:
        result = client.post("/claude/messages", json=PAYLOAD, headers={"x-api-key": "ignored-client-secret"})
    assert result.status_code == 200
    assert result.json()["usage"]["input_tokens"] == 5
    assert "server-test-secret" not in result.text
    assert post.call_args.kwargs["headers"]["x-api-key"] == "server-test-secret"
    assert post.call_args.args[0] == "https://api.anthropic.com/v1/messages"
    assert post.call_args.kwargs["json"] == PAYLOAD
    assert post.call_args.kwargs["allow_redirects"] is False
    assert claude_api_configured()


def test_missing_environment_stops_without_request(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with patch("app.claude_api.requests.post") as post:
        result = client.post("/claude/messages", json=PAYLOAD)
    assert result.status_code == 503
    post.assert_not_called()
    assert not claude_api_configured()


def test_client_cannot_supply_key_in_payload(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "server-test-secret")
    with patch("app.claude_api.requests.post") as post:
        result = client.post("/claude/messages", json={**PAYLOAD, "api_key": "client-test-key"})
    assert result.status_code == 422
    post.assert_not_called()


@pytest.mark.parametrize("status", [401, 429, 500])
def test_upstream_error_body_is_not_exposed(monkeypatch, status):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "server-test-secret")
    response = MagicMock(status_code=status, text="server-test-secret")
    with patch("app.claude_api.requests.post", return_value=response):
        result = client.post("/claude/messages", json=PAYLOAD)
    assert result.status_code == (status if status in (401, 429) else 502)
    assert "server-test-secret" not in result.text


def test_network_exception_is_sanitized(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "server-test-secret")
    with patch("app.claude_api.requests.post", side_effect=requests.ConnectionError("server-test-secret")):
        result = client.post("/claude/messages", json=PAYLOAD)
    assert result.status_code == 502
    assert "server-test-secret" not in result.text
