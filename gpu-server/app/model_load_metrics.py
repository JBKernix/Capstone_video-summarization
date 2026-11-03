"""Job-scoped model load measurements without GPU or API dependencies."""
import logging
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

ACTIVE_LOAD_SINK = ContextVar("model_load_sink", default=None)
logger = logging.getLogger(__name__)


def collect_job_loads(method):
    @wraps(method)
    def wrapped(self, job_id, *args, **kwargs):
        token = ACTIVE_LOAD_SINK.set(lambda event: self.job_store.record_model_load(job_id, event))
        try:
            return method(self, job_id, *args, **kwargs)
        finally:
            ACTIVE_LOAD_SINK.reset(token)
    return wrapped


def measure_model_load(kind, companion):
    """Measure actual loading; cache hits are recorded as reuse with zero load time."""
    def decorate(method):
        @wraps(method)
        def wrapped(self, *args, **kwargs):
            cached = self.model is not None and getattr(self, companion) is not None
            event = {"kind": kind, "model": Path(self.config.model_path).name,
                     "started_at": datetime.now(timezone.utc).isoformat(),
                     "status": "reused" if cached else "loaded", "duration_seconds": 0.0}
            profile = getattr(self, "profile", None)
            if profile is not None:
                event.update(local_model=profile.id, precision=profile.precision)
            started = time.perf_counter()
            try:
                return method(self, *args, **kwargs)
            except BaseException:
                event["status"] = "failed"
                raise
            finally:
                if event["status"] != "reused":
                    event["duration_seconds"] = round(time.perf_counter() - started, 6)
                sink = ACTIVE_LOAD_SINK.get()
                if sink:
                    sink(event)
                logger.info("model_load | kind=%s | model=%s | status=%s | elapsed_seconds=%.6f",
                            kind, event["model"], event["status"], event["duration_seconds"])
        return wrapped
    return decorate
