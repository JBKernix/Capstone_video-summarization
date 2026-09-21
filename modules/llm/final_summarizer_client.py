from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from modules.common import load_json
from modules.common.progress import STEP_FINAL_SUMMARY, report_progress
from modules.llm.gpu_job_client import GPUJobClientMixin
from modules.llm.summary_levels import DEFAULT_SUMMARY_LEVEL
from . import GPU_SERVER_URL


@dataclass
class GPUFinalSummaryClientConfig:
    server_url: str = GPU_SERVER_URL
    timeout: int = 600
    poll_interval: int = 10
    job_timeout: int = 3600


class GPUFinalSummaryClient(GPUJobClientMixin):
    job_label = "Final summary"
    progress_step = STEP_FINAL_SUMMARY

    def __init__(self, config: Optional[GPUFinalSummaryClientConfig] = None):
        self.config = config or GPUFinalSummaryClientConfig()

    def health_check(self) -> dict:
        response = requests.get(f"{self.config.server_url}/health", timeout=10)
        self._raise_for_status(response)
        return response.json()

    def summarize_files_result(
        self,
        stt_summary_json_path: str | Path,
        vlm_summary_json_path: str | Path,
        summary_level: str = DEFAULT_SUMMARY_LEVEL,
    ) -> dict:
        return self._post_final_summary_files(
            stt_summary_json_path=Path(stt_summary_json_path),
            vlm_summary_json_path=Path(vlm_summary_json_path),
            summary_level=summary_level,
        )

    def _post_final_summary_files(
        self,
        stt_summary_json_path: Path,
        vlm_summary_json_path: Path,
        summary_level: str,
    ) -> dict:
        self._validate_summary_files(
            stt_summary_json_path=stt_summary_json_path,
            vlm_summary_json_path=vlm_summary_json_path,
        )
        report_progress(self.progress_step, "최종 요약 서버에 요청 전송 중")

        url = f"{self.config.server_url}/llm/final-summary"
        with ExitStack() as stack:
            stt_summary_json_file = stack.enter_context(stt_summary_json_path.open("rb"))
            vlm_summary_json_file = stack.enter_context(vlm_summary_json_path.open("rb"))

            files = [
                (
                    "stt_summary_result",
                    (stt_summary_json_path.name, stt_summary_json_file, "application/json"),
                ),
                (
                    "vlm_summary_result",
                    (vlm_summary_json_path.name, vlm_summary_json_file, "application/json"),
                ),
            ]

            response = requests.post(
                url,
                files=files,
                data={"summary_level": summary_level},
                timeout=self.config.timeout,
            )

        self._raise_for_status(response)
        result = self._extract_final_summary_result(response.json())
        report_progress(self.progress_step, "최종 요약 완료", 100.0)
        return result

    @staticmethod
    def _validate_summary_files(
        stt_summary_json_path: Path,
        vlm_summary_json_path: Path,
    ) -> None:
        stt_summary_data = GPUFinalSummaryClient._read_json_file(stt_summary_json_path)
        vlm_summary_data = GPUFinalSummaryClient._read_json_file(vlm_summary_json_path)

        if not str(stt_summary_data.get("summary", "")).strip():
            raise ValueError(f"STT summary JSON has no summary text: {stt_summary_json_path}")
        if not vlm_summary_data.get("results"):
            raise ValueError(f"VLM summary JSON has no results: {vlm_summary_json_path}")

    @staticmethod
    def _read_json_file(path: Path) -> dict:
        if not path.is_file():
            raise FileNotFoundError(f"JSON file does not exist: {path}")
        data = load_json(path)
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
        if job_id is None or not status_url:
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
