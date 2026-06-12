from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Optional

import requests

from modules.common import (
    DEFAULT_RUN_DIR_RELATIVE_PATH,
    DEFAULT_STT_JSON_RELATIVE_PATH,
    run_path,
)
from . import GPU_SERVER_URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STT_JSON_PATH = run_path(
    PROJECT_ROOT / DEFAULT_RUN_DIR_RELATIVE_PATH,
    DEFAULT_STT_JSON_RELATIVE_PATH,
)

@dataclass
class GPULLMClientConfig:
    server_url = GPU_SERVER_URL
    timeout: int = 600
    poll_interval: int = 10
    job_timeout: int = 3600
    stt_json_path: Path = DEFAULT_STT_JSON_PATH


class GPULLMClient:
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

    def summarize_stt(
        self,
        stt_text: str,
    ) -> str:
        return self.summarize_stt_result(stt_text=stt_text)["summary"]

    def summarize_stt_result(
        self,
        stt_text: str,
    ) -> dict:
        if not stt_text.strip():
            raise ValueError("stt_text is empty")

        payload = {
            "full_text": stt_text,
        }

        return self._post_summary_payload(payload)

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
    def _load_stt_text(stt_json_path: Path) -> str:
        payload = GPULLMClient._load_stt_payload(stt_json_path)
        return str(payload.get("full_text", "")).strip()

    @staticmethod
    def _load_stt_payload(stt_json_path: Path) -> dict:
        if not stt_json_path.exists():
            raise FileNotFoundError(f"STT JSON file does not exist: {stt_json_path}")

        with stt_json_path.open("r", encoding="utf-8-sig") as file:
            stt_result = json.load(file)

        segments = stt_result.get("segments")
        if isinstance(segments, list):
            texts = [
                str(segment.get("text", "")).strip()
                for segment in segments
                if isinstance(segment, dict) and str(segment.get("text", "")).strip()
            ]
            full_text = "\n".join(texts)
            if not full_text.strip():
                raise ValueError(f"STT JSON has no text content: {stt_json_path}")

            return {
                "language": stt_result.get("language", "unknown"),
                "segments": segments,
                "full_text": full_text,
            }

        text = str(stt_result.get("text", "")).strip()
        if text:
            return {
                "language": stt_result.get("language", "unknown"),
                "full_text": text,
            }

        raise ValueError(f"STT JSON has no text content: {stt_json_path}")

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(
                f"{exc}. Response body: {response.text}",
                response=response,
            ) from exc

    def _extract_summary(self, data: dict) -> str:
        return self._extract_summary_result(data)["summary"]

    def _extract_summary_result(self, data: dict) -> dict:
        if "summary" in data:
            return self._normalize_summary_result(data)

        job_id = data.get("job_id")
        status_url = data.get("status_url")
        if not job_id or not status_url:
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

    def _wait_for_job(self, status_url: str) -> dict:
        if status_url.startswith("http://") or status_url.startswith("https://"):
            url = status_url
        else:
            url = f"{self.config.server_url}{status_url}"

        deadline = time.monotonic() + self.config.job_timeout
        last_message = None

        while time.monotonic() < deadline:
            response = requests.get(url, timeout=self.config.timeout)
            self._raise_for_status(response)
            data = response.json()

            message = data.get("message")
            if message and message != last_message:
                print(f"LLM job status: {data.get('status')} - {message}")
                last_message = message

            status = data.get("status")
            if status == "completed":
                return data
            if status == "failed":
                raise RuntimeError(f"LLM job failed: {data.get('error') or message}")

            time.sleep(self.config.poll_interval)

        raise TimeoutError(f"LLM job did not finish within {self.config.job_timeout} seconds: {url}")
