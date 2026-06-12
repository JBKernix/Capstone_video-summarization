import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Literal
from uuid import uuid4

# scripts 폴더에서 직접 실행해도 프로젝트 패키지를 찾을 수 있게 합니다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from services.summary_service import SummaryService


class ColoredConsoleFormatter(logging.Formatter):
    RESET = "\x1b[0m"
    SEPARATOR = "\x1b[90m"
    TIME = "\x1b[36m"
    LOGGER = "\x1b[35m"
    MESSAGE = "\x1b[97m"
    LEVEL_COLORS = {
        logging.DEBUG: "\x1b[34m",
        logging.INFO: "\x1b[32m",
        logging.WARNING: "\x1b[33m",
        logging.ERROR: "\x1b[31m",
        logging.CRITICAL: "\x1b[1;31m",
    }

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt)
        level_color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        separator = f" {self.SEPARATOR}|{self.RESET} "
        output = separator.join(
            (
                f"{self.TIME}{timestamp}{self.RESET}",
                f"{level_color}{record.levelname}{self.RESET}",
                f"{self.LOGGER}{record.name}{self.RESET}",
                f"{self.MESSAGE}{record.getMessage()}{self.RESET}",
            )
        )
        if record.exc_info:
            output = f"{output}\n{self.formatException(record.exc_info)}"
        if record.stack_info:
            output = f"{output}\n{self.formatStack(record.stack_info)}"
        return output


LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
log_formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
file_handler = RotatingFileHandler(
    LOG_DIR / "server.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
file_handler.setFormatter(log_formatter)
console_colors_enabled = sys.stderr.isatty() and not os.getenv("NO_COLOR")
if console_colors_enabled:
    try:
        from colorama import just_fix_windows_console

        just_fix_windows_console()
    except ImportError:
        pass

console_handler = logging.StreamHandler()
if console_colors_enabled:
    console_handler.setFormatter(
        ColoredConsoleFormatter(datefmt="%Y-%m-%d %H:%M:%S")
    )
else:
    console_handler.setFormatter(log_formatter)
logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler, file_handler],
    force=True,
)

# Uvicorn uses dedicated handlers by default. Route its logs through the
# application handlers so console and file output share one format.
for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    uvicorn_logger = logging.getLogger(uvicorn_logger_name)
    uvicorn_logger.handlers.clear()
    uvicorn_logger.propagate = True

logger = logging.getLogger(__name__)
logger.info("File logging enabled: %s", file_handler.baseFilename)

app = FastAPI(
    title="Video Summarization AI Server",
    description="LLM/VLM 처리를 위한 FastAPI 서버",
    version="0.1.0",
)

# 서버 구동 시 SummaryService를 전역으로 단일 인스턴스화 (메모리 낭비 방지)
summary_service = SummaryService()
# By default, release the LLM after each completed job so an idle server does
# not keep model weights in VRAM. Set KEEP_LLM_LOADED=1 to favor warm requests.
keep_llm_loaded = os.getenv("KEEP_LLM_LOADED", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
# GPU 추론 작업은 한 번에 하나씩 실행하고 상태는 메모리에 보관합니다.
job_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="summary-job")
job_lock = Lock()
jobs: dict[str, dict[str, Any]] = {}


def create_job_id(job_type: str) -> str:
    unique_suffix = uuid4().hex[:12]
    return f"{job_type}-{unique_suffix}"


class STTSegment(BaseModel):
    segment_id: int
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str


class SummaryRequest(BaseModel):
    language: str = "unknown"
    segments: list[STTSegment] = Field(default_factory=list)
    full_text: str = ""
    # 과도한 생성 요청으로 인한 GPU 메모리 부족을 방지합니다.
    max_new_tokens: int = Field(default=1024, ge=1, le=2048)


class ImportantSegment(BaseModel):
    segment_id: int
    start: float
    end: float
    topic: str
    reason: str


class SummaryResponse(BaseModel):
    summary: str
    important_segments: list[ImportantSegment]


class JobSubmissionResponse(BaseModel):
    job_id: str
    status: Literal["queued"]
    message: str
    status_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    message: str
    current_step: int = 0
    total_steps: int = 0
    result: SummaryResponse | None = None
    error: str | None = None
    created_at: str
    updated_at: str
    elapsed_seconds: float = 0.0


@app.get("/")
def root():
    return {"message": "FastAPI server is running"}


@app.get("/health")
def health_check():
    with job_lock:
        active_jobs = sum(
            job["status"] in {"queued", "running"}
            for job in jobs.values()
        )
    return {"status": "ok", "active_jobs": active_jobs}


def update_job(job_id: str, **changes: Any) -> None:
    with job_lock:
        jobs[job_id].update(changes)
        jobs[job_id]["updated_at"] = datetime.now(timezone.utc).isoformat()


def get_job_elapsed(job_id: str) -> float:
    with job_lock:
        started_at = jobs[job_id]["started_monotonic"]
    return round(time.perf_counter() - started_at, 1)


@contextmanager
def log_job_stage(job_id: str, stage: str):
    """긴 추론 단계의 시작, 주기적 경과 시간, 종료 시간을 기록합니다."""
    stop_event = Event()
    stage_started = time.perf_counter()
    logger.info("job_id=%s | stage=%s | 시작", job_id, stage)

    def heartbeat() -> None:
        while not stop_event.wait(10):
            logger.info(
                "job_id=%s | stage=%s | 진행 중 | stage_elapsed=%.1fs | total_elapsed=%.1fs",
                job_id,
                stage,
                time.perf_counter() - stage_started,
                get_job_elapsed(job_id),
            )

    reporter = Thread(target=heartbeat, daemon=True)
    reporter.start()
    succeeded = False
    try:
        yield
        succeeded = True
    finally:
        stop_event.set()
        reporter.join()
        logger.info(
            "job_id=%s | stage=%s | %s | stage_elapsed=%.1fs | total_elapsed=%.1fs",
            job_id,
            stage,
            "완료" if succeeded else "중단",
            time.perf_counter() - stage_started,
            get_job_elapsed(job_id),
        )


def run_summary_job(job_id: str, request_data: dict[str, Any]) -> None:
    try:
        request = SummaryRequest.model_validate(request_data)
        stt_text = request.full_text.strip() or " ".join(
            segment.text.strip()
            for segment in request.segments
            if segment.text.strip()
        )
        segment_data = [segment.model_dump() for segment in request.segments]

        update_job(
            job_id,
            status="running",
            message="STT 전체 요약을 생성하고 있습니다.",
            current_step=1,
            total_steps=2 if segment_data else 1,
        )
        with log_job_stage(job_id, "STT 전체 요약"):
            summary = summary_service.summarize_stt(
                stt_text=stt_text,
                max_new_tokens=request.max_new_tokens,
            )

        important_segments = []
        if segment_data:
            chunks = summary_service.llm_service.split_segments(
                segment_data,
                max_chunk_chars=12000,
            )

            def report_progress(_task: str, index: int, total: int) -> None:
                update_job(
                    job_id,
                    message=f"중요 구간을 추출하고 있습니다. ({index}/{total})",
                    current_step=index,
                    total_steps=total,
                )
                logger.info(
                    "job_id=%s | 중요 구간 묶음 시작 | chunk=%d/%d | total_elapsed=%.1fs",
                    job_id,
                    index,
                    total,
                    get_job_elapsed(job_id),
                )

            update_job(
                job_id,
                message=f"중요 구간을 추출하고 있습니다. (0/{len(chunks)})",
                current_step=0,
                total_steps=len(chunks),
            )
            with log_job_stage(job_id, "중요 구간 추출"):
                important_segments = summary_service.get_important_segments_in_chunks(
                    stt_segments=segment_data,
                    stt_summary=summary,
                    max_new_tokens=min(request.max_new_tokens, 256),
                    progress_callback=report_progress,
                )

        result = SummaryResponse(
            summary=summary,
            important_segments=important_segments,
        )
        update_job(
            job_id,
            status="completed",
            message="요약과 중요 구간 추출이 완료되었습니다.",
            result=result.model_dump(),
            current_step=1,
            total_steps=1,
        )
        logger.info(
            "job_id=%s | 작업 완료 | total_elapsed=%.1fs | important_segments=%d",
            job_id,
            get_job_elapsed(job_id),
            len(important_segments),
        )
    except Exception as error:
        logger.exception("요약 작업 실패: job_id=%s", job_id)
        update_job(
            job_id,
            status="failed",
            message="추론 작업 중 오류가 발생했습니다.",
            error=str(error),
        )
        logger.error(
            "job_id=%s | 작업 실패 | total_elapsed=%.1fs",
            job_id,
            get_job_elapsed(job_id),
        )
    finally:
        if not keep_llm_loaded:
            summary_service.unload_llm()
            logger.info("job_id=%s | LLM GPU 메모리 해제 완료", job_id)


@app.post(
    "/llm/summarize",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def summarize(request: SummaryRequest):
    # full_text가 비어 있으면 세그먼트 텍스트로 복원합니다.
    stt_text = request.full_text.strip() or " ".join(
        segment.text.strip()
        for segment in request.segments
        if segment.text.strip()
    )
    logger.info(
        "STT 텍스트 길이: %d, 세그먼트 수: %d",
        len(stt_text),
        len(request.segments),
    )
    if not stt_text:
        raise HTTPException(status_code=422, detail="STT 텍스트가 비어 있습니다.")

    job_id = create_job_id("stt-summary")
    now = datetime.now(timezone.utc).isoformat()
    with job_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "message": "추론 대기열에 등록되었습니다.",
            "current_step": 0,
            "total_steps": 0,
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "started_monotonic": time.perf_counter(),
        }

    logger.info(
        "job_id=%s | 작업 접수 | text_length=%d | segments=%d | max_new_tokens=%d",
        job_id,
        len(stt_text),
        len(request.segments),
        request.max_new_tokens,
    )
    job_executor.submit(run_summary_job, job_id, request.model_dump())
    return JobSubmissionResponse(
        job_id=job_id,
        status="queued",
        message="요청을 접수했습니다. status_url을 조회해 진행 상태를 확인하세요.",
        status_url=f"/llm/jobs/{job_id}",
    )


@app.get("/llm/jobs/{job_id}", response_model=JobStatusResponse)
def get_summary_job(job_id: str):
    with job_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
        response_data = job.copy()
        response_data["elapsed_seconds"] = round(
            time.perf_counter() - job["started_monotonic"],
            1,
        )
        return JobStatusResponse.model_validate(response_data)


if __name__ == "__main__":
    import uvicorn

    # GPU 모델이 프로세스마다 중복 로드되지 않도록 worker를 1개로 유지합니다.
    uvicorn.run(
        app,
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", "8000")),
    )
