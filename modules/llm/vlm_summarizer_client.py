from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Optional

import requests

from modules.common import DEFAULT_OCR_RESULT_RELATIVE_PATH, DEFAULT_RUN_DIR_RELATIVE_PATH, run_path
from . import GPU_SERVER_URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OCR_RESULT_PATH = run_path(
    PROJECT_ROOT / DEFAULT_RUN_DIR_RELATIVE_PATH,
    DEFAULT_OCR_RESULT_RELATIVE_PATH,
)
MAX_FRAME_COUNT = 32
ALLOWED_FRAME_SUFFIXES = {".jpg", ".jpeg"}


@dataclass
class GPUVLMClientConfig:
    server_url: str = GPU_SERVER_URL
    timeout: int = 600
    poll_interval: int = 10
    job_timeout: int = 3600
    ocr_json_path: Path = DEFAULT_OCR_RESULT_PATH


class GPUVLMClient:
    def __init__(self, config: Optional[GPUVLMClientConfig] = None):
        self.config = config or GPUVLMClientConfig()

    def health_check(self) -> dict:
        response = requests.get(f"{self.config.server_url}/health", timeout=10)
        self._raise_for_status(response)
        return response.json()

    def summarize_ocr_file(
        self,
        ocr_json_path: str | Path | None = None,
        max_new_tokens: int = 512,
    ) -> list[dict]:
        path = Path(ocr_json_path or self.config.ocr_json_path)
        entries = self._load_ocr_entries(path)
        frame_paths = self._resolve_frame_paths(entries, path)
        results: list[dict] = []
        total_batches = (len(frame_paths) + MAX_FRAME_COUNT - 1) // MAX_FRAME_COUNT
        for batch_index, start in enumerate(
            range(0, len(frame_paths), MAX_FRAME_COUNT),
            start=1,
        ):
            batch = frame_paths[start : start + MAX_FRAME_COUNT]
            print(
                f"VLM batch submitted: {batch_index}/{total_batches} "
                f"({len(batch)} frames)"
            )
            results.extend(self._post_vlm_files(path, batch, max_new_tokens))
        return results

    def _post_vlm_files(
        self,
        ocr_json_path: Path,
        frame_paths: list[Path],
        max_new_tokens: int,
    ) -> list[dict]:
        if not 1 <= max_new_tokens <= 2048:
            raise ValueError("max_new_tokens must be between 1 and 2048")

        url = f"{self.config.server_url}/vlm/summarize"
        with ExitStack() as stack:
            ocr_file = stack.enter_context(ocr_json_path.open("rb"))
            files = [
                ("ocr_result", (ocr_json_path.name, ocr_file, "application/json"))
            ]
            for frame_path in frame_paths:
                frame_file = stack.enter_context(frame_path.open("rb"))
                files.append(
                    ("frames", (frame_path.name, frame_file, "image/jpeg"))
                )

            response = requests.post(
                url,
                files=files,
                data={"max_new_tokens": str(max_new_tokens)},
                timeout=self.config.timeout,
            )

        self._raise_for_status(response)
        return self._extract_vlm_result(response.json())

    def _extract_vlm_result(self, data: dict) -> list[dict]:
        if isinstance(data.get("result"), list):
            return self._validate_result(data["result"])

        job_id = data.get("job_id")
        status_url = data.get("status_url")
        if not job_id or not status_url:
            raise ValueError(f"Unexpected VLM response: {data}")

        job = self._wait_for_job(status_url)
        return self._validate_result(job.get("result"))

    @staticmethod
    def _validate_result(result: object) -> list[dict]:
        if not isinstance(result, list):
            raise ValueError(f"Completed VLM job has no frame result list: {result}")
        if any(not isinstance(entry, dict) for entry in result):
            raise ValueError("VLM result entries must be objects")
        return result

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
                print(f"VLM job status: {data.get('status')} - {message}")
                last_message = message

            status = data.get("status")
            if status == "completed":
                return data
            if status == "failed":
                raise RuntimeError(f"VLM job failed: {data.get('error') or message}")

            time.sleep(self.config.poll_interval)

        raise TimeoutError(
            f"VLM job did not finish within {self.config.job_timeout} seconds: {url}"
        )

    @staticmethod
    def _load_ocr_entries(ocr_json_path: Path) -> list[dict]:
        if not ocr_json_path.is_file():
            raise FileNotFoundError(f"OCR JSON file does not exist: {ocr_json_path}")

        with ocr_json_path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)

        if isinstance(data, dict):
            for key in ("frames", "results", "ocr_results"):
                if key in data:
                    data = data[key]
                    break

        if not isinstance(data, list):
            raise ValueError("OCR JSON must contain a list of frame objects")
        if not data:
            raise ValueError("OCR JSON has no frame entries")
        if any(not isinstance(entry, dict) for entry in data):
            raise ValueError("OCR JSON entries must be objects")
        return data

    @staticmethod
    def _resolve_frame_paths(entries: list[dict], ocr_json_path: Path) -> list[Path]:
        frame_paths: list[Path] = []
        seen_names: set[str] = set()

        for index, entry in enumerate(entries):
            image_path = str(entry.get("image_path", "")).strip()
            if not image_path:
                raise ValueError(f"OCR entry {index} has no image_path")

            path = Path(image_path)
            candidates = [path] if path.is_absolute() else [
                Path.cwd() / path,
                PROJECT_ROOT / path,
                ocr_json_path.parent / path,
                ocr_json_path.parent.parent / path,
            ]
            resolved = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
            if resolved is None:
                raise FileNotFoundError(f"Frame image does not exist: {image_path}")
            if resolved.suffix.lower() not in ALLOWED_FRAME_SUFFIXES:
                raise ValueError(f"VLM server accepts JPG frames only: {resolved}")

            normalized_name = resolved.name.casefold()
            if normalized_name in seen_names:
                raise ValueError(f"Duplicate frame filename: {resolved.name}")
            seen_names.add(normalized_name)
            frame_paths.append(resolved)

        return frame_paths

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(
                f"{exc}. Response body: {response.text}",
                response=response,
            ) from exc
