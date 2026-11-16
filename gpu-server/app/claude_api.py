"""Claude requests authenticated exclusively with this server's environment."""
import os
from typing import Any

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


def claude_api_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())


class ClaudeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(pattern=r"^claude-[a-zA-Z0-9._-]+$")
    max_tokens: int = Field(ge=1, le=8192)
    system: str
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=1)
    tools: list[dict[str, Any]] = Field(min_length=1, max_length=1)
    tool_choice: dict[str, str]


@router.post("/claude/messages")
def claude_messages(payload: ClaudeRequest):
    # Read on the server at request time; never accept a key from the client.
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="서버의 ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
    try:
        response = requests.post(
            ANTHROPIC_MESSAGES_URL,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json=payload.model_dump(), timeout=(15, 600), allow_redirects=False,
        )
    except requests.RequestException:
        raise HTTPException(status_code=502, detail="서버에서 Claude API에 연결하지 못했습니다.") from None
    if response.status_code != 200:
        code = response.status_code if response.status_code in (400, 401, 403, 429) else 502
        # Upstream error text may contain request data; never relay or log it.
        raise HTTPException(status_code=code, detail="Claude API 요청에 실패했습니다.")
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Claude API 응답 형식이 잘못되었습니다.") from None
    if not isinstance(data, dict) or not isinstance(data.get("content"), list):
        raise HTTPException(status_code=502, detail="Claude API 응답 형식이 잘못되었습니다.")
    return {name: data.get(name) for name in ("content", "stop_reason", "usage")}
