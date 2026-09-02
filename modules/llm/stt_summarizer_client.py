from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from modules.common import (
    DEFAULT_RUN_DIR_RELATIVE_PATH,
    DEFAULT_STT_JSON_RELATIVE_PATH,
    load_json,
    run_path,
)
from modules.llm.gpu_job_client import GPUJobClientMixin
from . import GPU_SERVER_URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STT_JSON_PATH = run_path(
    PROJECT_ROOT / DEFAULT_RUN_DIR_RELATIVE_PATH,
    DEFAULT_STT_JSON_RELATIVE_PATH,
)

@dataclass
class GPULLMClientConfig:
    server_url: str = GPU_SERVER_URL
    timeout: int = 600
    poll_interval: int = 10
    job_timeout: int = 3600
    stt_json_path: Path = DEFAULT_STT_JSON_PATH


class GPULLMClient(GPUJobClientMixin):
    job_label = "LLM"

    def __init__(self, config: Optional[GPULLMClientConfig] = None):
        self.config = config or GPULLMClientConfig()

    def health_check(self) -> dict:
        url = f"{self.config.server_url}/health"

        response = requests.get(
            url,
            timeout=10,
        )
        response.raise_for_status()

        return response.json()

    def summarize_stt_file(
        self,
        stt_json_path: str | Path | None = None,
    ) -> str:
        return self.summarize_stt_file_result(stt_json_path=stt_json_path)["summary"]

    def summarize_stt_file_result(
        self,
        stt_json_path: str | Path | None = None,
    ) -> dict:
        path = Path(stt_json_path or self.config.stt_json_path)
        payload = self._load_stt_payload(path)
        if not payload.get("full_text", "").strip():
            return {
                "summary": "음성이 감지되지 않았습니다.",
                "important_segments": [],
                "no_speech": True,
            }
        return self._post_summary_payload(payload)

    def _post_summary_payload(self, payload: dict) -> dict:
        url = f"{self.config.server_url}/llm/summarize"
        response = requests.post(
            url,
            json=payload,
            timeout=self.config.timeout,
        )

        self._raise_for_status(response)

        return self._extract_summary_result(response.json())

    @staticmethod
    def _load_stt_payload(stt_json_path: Path) -> dict:
        if not stt_json_path.exists():
            raise FileNotFoundError(f"STT JSON file does not exist: {stt_json_path}")

        stt_result = load_json(stt_json_path)

        segments = stt_result.get("segments")
        if isinstance(segments, list):
            texts = [
                str(segment.get("text", "")).strip()
                for segment in segments
                if isinstance(segment, dict) and str(segment.get("text", "")).strip()
            ]
            full_text = "\n".join(texts)

            # 음성이 감지되지 않은 경우(빈 segments)도 정상 케이스이므로 예외를 발생시키지 않습니다.
            return {
                "language": stt_result.get("language", "unknown"),
                "segments": segments,
                "full_text": full_text,
            }

        text = str(stt_result.get("text", "")).strip()
        return {
            "language": stt_result.get("language", "unknown"),
            "full_text": text,
        }

    def _extract_summary_result(self, data: dict) -> dict:
        if "summary" in data:
            return self._normalize_summary_result(data)

        job_id = data.get("job_id")
        status_url = data.get("status_url")
        if job_id is None or not status_url:
            raise ValueError(f"Unexpected LLM response: {data}")

        job = self._wait_for_job(status_url)
        result = job.get("result") or {}
        return self._normalize_summary_result(result)

    @staticmethod
    def _normalize_summary_result(result: dict) -> dict:
        summary = result.get("summary")
        if not summary:
            raise ValueError(f"Completed LLM job has no summary: {result}")

        important_segments = result.get("important_segments", [])
        if isinstance(important_segments, str):
            try:
                important_segments = json.loads(important_segments)
            except json.JSONDecodeError:
                important_segments = []

        return {
            "summary": summary,
            "important_segments": important_segments,
        }
