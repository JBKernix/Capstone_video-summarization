from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Optional

import requests

from . import GPU_SERVER_URL


@dataclass
class GPUFinalSummaryClientConfig:
    server_url: str = GPU_SERVER_URL
    timeout: int = 600
    poll_interval: int = 10
    job_timeout: int = 3600


class GPUFinalSummaryClient:
    def __init__(self, config: Optional[GPUFinalSummaryClientConfig] = None):
        self.config = config or GPUFinalSummaryClientConfig()

    def health_check(self) -> dict:
        response = requests.get(f"{self.config.server_url}/health", timeout=10)
        self._raise_for_status(response)
        return response.json()

    def summarize_files_result(
        self,
        stt_summary_path: str | Path,
        stt_summary_json_path: str | Path,
        vlm_summary_path: str | Path,
        vlm_summary_json_path: str | Path,
    ) -> dict:
        return self._post_final_summary_files(
            stt_summary_path=Path(stt_summary_path),
            stt_summary_json_path=Path(stt_summary_json_path),
            vlm_summary_path=Path(vlm_summary_path),
            vlm_summary_json_path=Path(vlm_summary_json_path),
        )

    def _post_final_summary_files(
        self,
        stt_summary_path: Path,
        stt_summary_json_path: Path,
        vlm_summary_path: Path,
        vlm_summary_json_path: Path,
    ) -> dict:
        self._validate_summary_files(
            stt_summary_path=stt_summary_path,
            stt_summary_json_path=stt_summary_json_path,
            vlm_summary_path=vlm_summary_path,
            vlm_summary_json_path=vlm_summary_json_path,
        )

        url = f"{self.config.server_url}/llm/final-summary"
        with ExitStack() as stack:
            stt_summary_file = stack.enter_context(stt_summary_path.open("rb"))
            stt_summary_json_file = stack.enter_context(stt_summary_json_path.open("rb"))
            vlm_summary_file = stack.enter_context(vlm_summary_path.open("rb"))
            vlm_summary_json_file = stack.enter_context(vlm_summary_json_path.open("rb"))

            files = [
                ("stt_summary", (stt_summary_path.name, stt_summary_file, "text/plain")),
                (
                    "stt_summary_result",
                    (stt_summary_json_path.name, stt_summary_json_file, "application/json"),
                ),
                ("vlm_summary", (vlm_summary_path.name, vlm_summary_file, "text/plain")),
                (
                    "vlm_summary_result",
                    (vlm_summary_json_path.name, vlm_summary_json_file, "application/json"),
                ),
            ]

            response = requests.post(
                url,
                files=files,
                timeout=self.config.timeout,
            )

        self._raise_for_status(response)
        return self._extract_final_summary_result(response.json())

    @staticmethod
    def _validate_summary_files(
        stt_summary_path: Path,
        stt_summary_json_path: Path,
        vlm_summary_path: Path,
        vlm_summary_json_path: Path,
    ) -> None:
        stt_summary = GPUFinalSummaryClient._read_text_file(stt_summary_path)
        vlm_summary = GPUFinalSummaryClient._read_text_file(vlm_summary_path)
        GPUFinalSummaryClient._read_json_file(stt_summary_json_path)
        GPUFinalSummaryClient._read_json_file(vlm_summary_json_path)

        if not stt_summary.strip():
            raise ValueError(f"STT summary text is empty: {stt_summary_path}")
        if not vlm_summary.strip():
            raise ValueError(f"VLM summary text is empty: {vlm_summary_path}")

    @staticmethod
    def _read_text_file(path: Path) -> str:
        if not path.is_file():
            raise FileNotFoundError(f"Text file does not exist: {path}")
        return path.read_text(encoding="utf-8-sig").strip()

    @staticmethod
    def _read_json_file(path: Path) -> dict:
        if not path.is_file():
            raise FileNotFoundError(f"JSON file does not exist: {path}")
        with path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            raise ValueError(f"JSON file must contain an object: {path}")
        return data

    def _extract_final_summary_result(self, data: dict) -> dict:
        if "summary" in data or "final_summary" in data:
            return self._normalize_final_summary_result(data)

        result = data.get("result")
        if isinstance(result, dict) and ("summary" in result or "final_summary" in result):
            return self._normalize_final_summary_result(result)

        job_id = data.get("job_id")
        status_url = data.get("status_url")
        if not job_id or not status_url:
            raise ValueError(f"Unexpected final summary response: {data}")

        job = self._wait_for_job(status_url)
        result = job.get("result") or {}
        if not isinstance(result, dict):
            raise ValueError(f"Completed final summary job has no object result: {job}")
        return self._normalize_final_summary_result(result)

    @staticmethod
    def _normalize_final_summary_result(result: dict) -> dict:
        summary = result.get("summary") or result.get("final_summary")
        if not summary:
            raise ValueError(f"Completed final summary job has no summary: {result}")

        normalized = dict(result)
        normalized["summary"] = summary
        return normalized

    def _wait_for_job(self, status_url: str) -> dict:
        url = (
            status_url
            if status_url.startswith(("http://", "https://"))
            else f"{self.config.server_url}{status_url}"
        )
        deadline = time.monotonic() + self.config.job_timeout
        last_message = None

        while time.monotonic() < deadline:
            response = requests.get(url, timeout=self.config.timeout)
            self._raise_for_status(response)
            data = response.json()

            message = data.get("message")
            if message and message != last_message:
                print(f"Final summary job status: {data.get('status')} - {message}")
                last_message = message

            status = data.get("status")
            if status == "completed":
                return data
            if status == "failed":
                raise RuntimeError(
                    f"Final summary job failed: {data.get('error') or message}"
                )

            time.sleep(self.config.poll_interval)

        raise TimeoutError(
            f"Final summary job did not finish within {self.config.job_timeout} seconds: {url}"
        )

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(
                f"{exc}. Response body: {response.text}",
                response=response,
            ) from exc
