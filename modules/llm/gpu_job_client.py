# modules/llm/gpu_job_client.py

from __future__ import annotations

import time

import requests

from modules.common.progress import report_progress


class GPUJobClientMixin:
    """GPU LLM/VLM 클라이언트가 공유하는 HTTP 에러 처리와 비동기 작업 폴링 로직입니다."""

    job_label: str = "Job"
    # 파이프라인 진행률 표시에 사용할 단계 번호입니다. 하위 클래스가 재정의합니다.
    progress_step: int = 0

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(
                f"{exc}. Response body: {response.text}",
                response=response,
            ) from exc

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
                print(f"{self.job_label} job status: {data.get('status')} - {message}")
                last_message = message
                if self.progress_step:
                    report_progress(self.progress_step, f"{self.job_label} 처리 중: {message}")

            status = data.get("status")
            if status == "completed":
                return data
            if status == "failed":
                raise RuntimeError(f"{self.job_label} job failed: {data.get('error') or message}")

            time.sleep(self.config.poll_interval)

        raise TimeoutError(
            f"{self.job_label} job did not finish within {self.config.job_timeout} seconds: {url}"
        )
