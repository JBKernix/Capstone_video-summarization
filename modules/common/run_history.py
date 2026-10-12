"""Per-run metrics and console archives; independent of Streamlit and ML packages."""
from __future__ import annotations

import csv
import io
import json
import math
import os
import platform
import re
import sys
import time
import traceback
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from modules.common.progress import STEP_LABELS

DEFAULT_HISTORY_DIR = Path(__file__).resolve().parents[2] / "runs" / "history"
ACTIVE_RUN = ContextVar("active_run", default=None)
TERMINAL_STATUSES = {"success", "failed", "cancelled", "interrupted"}
MODEL_LOAD_FIELDS = ["model_load_seconds", "llm_load_seconds", "vlm_load_seconds",
                     "model_load_count", "model_load_failed_count", "model_reuse_count"]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_run_id():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:12]


def run_directory(history_dir, run_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
        raise ValueError("Invalid run ID")
    return Path(history_dir) / run_id


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def prepare_run(history_dir=DEFAULT_HISTORY_DIR, *, run_id=None, input_name="", settings=None):
    run_id = run_id or new_run_id()
    directory = run_directory(history_dir, run_id)
    directory.mkdir(parents=True, exist_ok=False)
    record = {
        "schema_version": 1, "run_id": run_id, "status": "queued",
        "created_at": now_iso(), "started_at": None, "finished_at": None,
        "duration_seconds": None, "input": {"name": input_name},
        "settings": settings or {}, "counts": {}, "stages": [], "error": None,
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
    }
    atomic_json(directory / "metrics.json", record)
    return directory


def read_record(directory):
    record = json.loads((Path(directory) / "metrics.json").read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("schema_version") != 1:
        raise ValueError("Unsupported history record")
    return record


def list_records(history_dir=DEFAULT_HISTORY_DIR):
    records = []
    for path in Path(history_dir).glob("*/metrics.json"):
        try:
            record = read_record(path.parent)
            if record.get("run_id") != path.parent.name:
                continue
            records.append(record)
        except (OSError, ValueError):
            continue
    return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)


def records_csv(records):
    fields = ["run_id", "input_name", "status", "started_at", "finished_at",
              "duration_seconds", "video_duration_seconds", "summary_level", "stt_model",
              "analysis_backend", "analysis_model", "vision_model", "local_model", "local_model_precision", "preset_semantics", "api_calls", "api_input_tokens", "api_output_tokens",
              "frames_extracted", "ocr_success", "ocr_failed", "vlm_frames", "vlm_batches",
              "stt_segments", "error"] + MODEL_LOAD_FIELDS + [f"stage_{n}_seconds" for n in STEP_LABELS]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for record in records:
        settings = record.get("settings", {})
        row = {key: record.get(key) for key in fields if key in record}
        row.update(input_name=record.get("input", {}).get("name"),
                   video_duration_seconds=record.get("input", {}).get("duration_seconds"),
                   summary_level=settings.get("summary_level"),
                   analysis_backend=settings.get("analysis_backend"), analysis_model=settings.get("analysis_model"),
                   vision_model=settings.get("vision_model"), local_model=settings.get("local_model"),
                   local_model_precision=settings.get("local_model_precision"),
                   preset_semantics=settings.get("preset_semantics", "legacy"),
                   stt_model=settings.get("stt", {}).get("model_size"))
        row.update({key: value for key, value in record.get("counts", {}).items() if key in fields})
        row.update(record.get("model_loading", {}).get("summary", {}))
        for stage in record.get("stages", []):
            key = f"stage_{stage['step']}_seconds"
            if key in fields:
                row[key] = stage.get("duration_seconds")
        # Avoid spreadsheet formula execution for filenames/errors supplied externally.
        row = {key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
               else value for key, value in row.items()}
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")


def finish_external(directory, status, reason):
    """Call only after the child has exited; never race a live recorder."""
    record = read_record(directory)
    if record["status"] in TERMINAL_STATUSES:
        return
    finished = now_iso()
    record.update(status=status, finished_at=finished, error=reason)
    started = record.get("started_at") or record["created_at"]
    record["duration_seconds"] = max(0, (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds())
    for stage in record["stages"]:
        if stage["status"] == "running":
            stage.update(status=status, finished_at=finished, error=reason)
            stage["duration_seconds"] = max(0, (datetime.fromisoformat(finished) - datetime.fromisoformat(stage["started_at"])).total_seconds())
    atomic_json(Path(directory) / "metrics.json", record)


class _Tee:
    def __init__(self, console, logfile):
        self.console, self.logfile = console, logfile

    def write(self, value):
        self.logfile.write(value)
        self.logfile.flush()
        return self.console.write(value)

    def flush(self):
        self.logfile.flush()
        self.console.flush()

    def __getattr__(self, name):
        return getattr(self.console, name)


class RunRecorder:
    def __init__(self, history_dir=DEFAULT_HISTORY_DIR, *, run_id=None, input_name="", settings=None):
        if run_id:
            self.directory = run_directory(history_dir, run_id)
            self.record = read_record(self.directory)
            if self.record["status"] != "queued":
                raise ValueError("Run ID already used")
        else:
            self.directory = prepare_run(history_dir, input_name=input_name, settings=settings)
            self.record = read_record(self.directory)
        self.record["settings"].update(settings or {})

    def save(self):
        atomic_json(self.directory / "metrics.json", self.record)

    def update(self, section, **values):
        self.record[section].update(values)
        self.save()

    def snapshot(self, path, name):
        """Copy only the just-produced JSON, never inspect older output files."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        atomic_json(self.directory / name, data)

    @contextmanager
    def capture(self):
        self.started = time.monotonic()
        self.record.update(status="running", started_at=now_iso())
        self.save()
        token = ACTIVE_RUN.set(self)
        try:
            with (self.directory / "pipeline.log").open("a", encoding="utf-8", buffering=1) as log:
                with redirect_stdout(_Tee(sys.stdout, log)), redirect_stderr(_Tee(sys.stderr, log)):
                    print(f"Run ID: {self.record['run_id']}")
                    try:
                        yield self
                    except BaseException as error:
                        self.record.update(status="cancelled" if isinstance(error, KeyboardInterrupt) else "failed",
                                           error=f"{type(error).__name__}: {error}")
                        traceback.print_exc()
                        raise
                    else:
                        self.record["status"] = "success"
                    finally:
                        self.record.update(finished_at=now_iso(), duration_seconds=round(time.monotonic() - self.started, 6))
                        self.save()
                        print(f"전체 실행 소요: {self.record['duration_seconds']:.3f}초")
        finally:
            ACTIVE_RUN.reset(token)

    @contextmanager
    def stage(self, step, name):
        started = time.monotonic()
        item = {"step": step, "name": name, "status": "running", "started_at": now_iso(),
                "finished_at": None, "duration_seconds": None, "error": None}
        self.record["stages"].append(item)
        self.save()
        state = {"status": "완료"}
        try:
            yield state
        except BaseException as error:
            item.update(status="cancelled" if isinstance(error, KeyboardInterrupt) else "failed",
                        error=f"{type(error).__name__}: {error}")
            raise
        else:
            item["status"] = "skipped" if state["status"] == "건너뜀" else "success"
            item["detail"] = state["status"]
        finally:
            item.update(finished_at=now_iso(), duration_seconds=round(time.monotonic() - started, 6))
            self.save()


def record_counts(**values):
    recorder = ACTIVE_RUN.get()
    if recorder:
        recorder.update("counts", **values)


def model_load_rows(record):
    return [{**event, "job_id": job_id, "step": job["step"]}
            for job_id, job in record.get("model_loading", {}).get("jobs", {}).items()
            for event in job["events"]]


def record_model_loads(job, step):
    """Save cumulative server snapshots idempotently, including failed jobs."""
    recorder = ACTIVE_RUN.get()
    events = job.get("model_loads")
    job_id = job.get("job_id")
    if recorder is None or not isinstance(events, list) or not isinstance(job_id, str):
        return
    normalized = []
    for event in events:
        if not isinstance(event, dict):
            return
        seconds = event.get("duration_seconds")
        if (event.get("kind") not in ("llm", "vlm") or event.get("status") not in ("loaded", "reused", "failed")
                or type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0):
            return
        normalized.append({"kind": event["kind"], "model": str(event.get("model", "")),
                           "status": event["status"], "duration_seconds": 0.0 if event["status"] == "reused" else seconds,
                           "started_at": event.get("started_at")})
    loading = recorder.record.setdefault("model_loading", {"jobs": {}, "summary": {}})
    old = loading["jobs"].get(job_id, {})
    previous_count = len(old.get("events", []))
    if len(normalized) < previous_count:
        return
    snapshot = {"step": step, "status": job.get("status"), "events": normalized}
    if old == snapshot:
        return
    loading["jobs"][job_id] = snapshot
    rows = model_load_rows(recorder.record)
    loading["summary"] = {
        "model_load_seconds": round(sum(e["duration_seconds"] for e in rows), 6),
        "llm_load_seconds": round(sum(e["duration_seconds"] for e in rows if e["kind"] == "llm"), 6),
        "vlm_load_seconds": round(sum(e["duration_seconds"] for e in rows if e["kind"] == "vlm"), 6),
        "model_load_count": sum(e["status"] == "loaded" for e in rows),
        "model_load_failed_count": sum(e["status"] == "failed" for e in rows),
        "model_reuse_count": sum(e["status"] == "reused" for e in rows),
    }
    recorder.save()
    for event in normalized[previous_count:]:
        print(f"서버 모델 로딩 | job={job_id} | step={step} | {event['kind']} | "
              f"{event['model']} | {event['status']} | {event['duration_seconds']:.6f}초")


def snapshot_result(path, name):
    recorder = ACTIVE_RUN.get()
    if recorder:
        recorder.snapshot(path, name)
