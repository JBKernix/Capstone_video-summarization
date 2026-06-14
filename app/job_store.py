import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4


class JobStore:
    def __init__(self):
        self.lock = Lock()
        self.jobs: dict[str, dict[str, Any]] = {}

    @staticmethod
    def create_id(job_type: str) -> str:
        return f"{job_type}-{uuid4().hex[:12]}"

    def create(self, job_id: str, message: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.lock:
            self.jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "message": message,
                "current_step": 0,
                "total_steps": 0,
                "result": None,
                "error": None,
                "created_at": now,
                "updated_at": now,
                "started_monotonic": time.perf_counter(),
            }

    def update(self, job_id: str, **changes: Any) -> None:
        with self.lock:
            self.jobs[job_id].update(changes)
            self.jobs[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()

    def elapsed(self, job_id: str) -> float:
        with self.lock:
            started_at = self.jobs[job_id]["started_monotonic"]
        return round(time.perf_counter() - started_at, 1)

    def active_count(self) -> int:
        with self.lock:
            return sum(
                job["status"] in {"queued", "running"}
                for job in self.jobs.values()
            )

    def response_data(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return None
            response = job.copy()
            response["elapsed_seconds"] = round(
                time.perf_counter() - job["started_monotonic"],
                1,
            )
            return response
