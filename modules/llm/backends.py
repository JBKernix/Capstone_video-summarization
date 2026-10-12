"""Explicit local-server or Claude routing shared by the UI and all CLIs."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests

from modules.llm import GPU_SERVER_URL
from modules.llm.local_models import DEFAULT_LOCAL_MODEL, LOCAL_MODEL_LABELS

BACKEND_LABELS = {"local": "로컬 모델 서버", "claude": "Claude API (Haiku)"}
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5"


@dataclass(frozen=True)
class BackendOptions:
    analysis_backend: str = "local"
    local_server_url: str = GPU_SERVER_URL
    claude_model: str = DEFAULT_CLAUDE_MODEL
    local_model: str = DEFAULT_LOCAL_MODEL

    def validate(self):
        if self.analysis_backend not in BACKEND_LABELS:
            raise ValueError("분석 방식은 local 또는 claude여야 합니다.")
        if self.analysis_backend == "claude" and not self.claude_model.strip():
            raise ValueError("Claude 모델 이름이 필요합니다.")
        url = urlsplit(self.local_server_url)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("분석 서버 URL은 인증정보·쿼리 없는 http(s) 주소여야 합니다.")
        try:
            response = requests.get(self.local_server_url.rstrip("/") + "/health", timeout=10)
            response.raise_for_status()
            health = response.json()
        except (requests.RequestException, ValueError):
            raise RuntimeError("분석 서버에 연결할 수 없습니다. 서버 주소와 실행 상태를 확인하세요.") from None
        if self.analysis_backend == "claude":
            if not isinstance(health, dict) or health.get("claude_api_proxy") is not True:
                raise RuntimeError("서버가 Claude API 경로를 지원하지 않습니다. 제공된 gpu-server 수정본을 적용하고 재시작하세요.")
            if health.get("claude_api_configured") is not True:
                raise RuntimeError("분석 서버 프로세스에 ANTHROPIC_API_KEY가 없습니다. 서버 컴퓨터의 환경변수와 서버 재시작 여부를 확인하세요.")
            return {"analysis_backend": "claude", "analysis_model": self.claude_model,
                    "local_server_url": self.local_server_url, "credential_source": "server_environment"}
        if self.local_model not in LOCAL_MODEL_LABELS:
            raise ValueError("지원하지 않는 로컬 모델입니다.")
        if isinstance(health, dict) and health.get("local_model_selection") is True:
            try:
                response = requests.get(self.local_server_url.rstrip("/") + "/models", timeout=10)
                response.raise_for_status()
                model = next((m for m in response.json()["models"] if m["id"] == self.local_model), None)
            except (requests.RequestException, ValueError, KeyError, TypeError):
                raise RuntimeError("서버의 모델 목록을 확인할 수 없습니다.") from None
            if not model or not model.get("ready"):
                raise RuntimeError("선택한 모델의 다운로드가 완료되지 않았습니다. GPU 서버에서 가중치를 다운로드하고 Streamlit 모델 설치 상태에서 확인하세요.")
            if model.get("runtime_ready") is False:
                raise RuntimeError("MiniCPM 실행 환경이 없습니다. 서버에서 python scripts/setup_minicpm.py를 실행하세요.")
            checkpoints = model.get("checkpoints", [])
            return {"analysis_backend": "local", "local_model": self.local_model,
                    "analysis_model": checkpoints[0]["repo"] if checkpoints else self.local_model,
                    "vision_model": checkpoints[-1]["repo"] if checkpoints else self.local_model,
                    "local_model_precision": model.get("precision"), "model_checkpoints": checkpoints,
                    "local_server_url": self.local_server_url}
        if self.local_model != DEFAULT_LOCAL_MODEL:
            raise RuntimeError("서버가 모델 선택을 지원하지 않습니다. gpu-server 수정본을 적용하고 재시작하세요.")
        if not isinstance(health, dict) or health.get("llm_backend") != "local" or health.get("vlm_backend") != "local":
            raise RuntimeError("로컬 모델 서버인지 확인할 수 없습니다. 제공된 gpu-server 수정본을 적용하고 LLM_BACKEND=local로 서버를 재시작하세요.")
        return {"analysis_backend": "local", "analysis_model": health.get("llm_model", "local"),
                "vision_model": health.get("vlm_model", "local"), "local_server_url": self.local_server_url}


ACTIVE_BACKEND = ContextVar("analysis_backend", default=BackendOptions())


@contextmanager
def use_backend(options):
    metadata = options.validate()
    token = ACTIVE_BACKEND.set(options)
    try:
        yield metadata
    finally:
        ACTIVE_BACKEND.reset(token)


def add_backend_arguments(parser):
    parser.add_argument("--analysis-backend", choices=tuple(BACKEND_LABELS), default="local", help="요약 실행 방식: 로컬 모델 서버 또는 Claude API")
    parser.add_argument("--local-server-url", "--server-url", dest="local_server_url", default=GPU_SERVER_URL, help="로컬/Claude 공통 분석 서버 주소")
    parser.add_argument("--local-model", choices=list(LOCAL_MODEL_LABELS), default=DEFAULT_LOCAL_MODEL)
    parser.add_argument("--claude-model", default=DEFAULT_CLAUDE_MODEL, help="Claude API 모델 이름")


def options_from_args(args):
    return BackendOptions(getattr(args, "analysis_backend", "local"),
                          getattr(args, "local_server_url", GPU_SERVER_URL),
                          getattr(args, "claude_model", DEFAULT_CLAUDE_MODEL),
                          getattr(args, "local_model", DEFAULT_LOCAL_MODEL))


def get_summary_client(kind):
    options = ACTIVE_BACKEND.get()
    if options.analysis_backend == "claude":
        from modules.llm.claude_backend import ClaudeSTTClient, ClaudeVLMClient, ClaudeFinalClient
        return {"stt": ClaudeSTTClient, "vlm": ClaudeVLMClient, "final": ClaudeFinalClient}[kind](options.claude_model, options.local_server_url)
    from modules.llm.stt_summarizer_client import GPULLMClient, GPULLMClientConfig
    from modules.llm.vlm_summarizer_client import GPUVLMClient, GPUVLMClientConfig
    from modules.llm.final_summarizer_client import GPUFinalSummaryClient, GPUFinalSummaryClientConfig
    client, config = {"stt": (GPULLMClient, GPULLMClientConfig), "vlm": (GPUVLMClient, GPUVLMClientConfig),
                      "final": (GPUFinalSummaryClient, GPUFinalSummaryClientConfig)}[kind]
    return client(config(server_url=options.local_server_url.rstrip("/"), local_model=options.local_model))
