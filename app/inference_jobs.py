import logging
import time
from contextlib import contextmanager
from threading import Event, Thread
from typing import Any

from app.api_models import SummaryRequest, SummaryResponse
from app.job_store import JobStore
from services.summary_service import SummaryService


class InferenceJobRunner:
    def __init__(
        self,
        summary_service: SummaryService,
        job_store: JobStore,
        logger: logging.Logger,
        keep_llm_loaded: bool = False,
        keep_vlm_loaded: bool = False,
    ):
        self.summary_service = summary_service
        self.job_store = job_store
        self.logger = logger
        self.keep_llm_loaded = keep_llm_loaded
        self.keep_vlm_loaded = keep_vlm_loaded

    @contextmanager
    def log_stage(self, job_id: str, stage: str):
        stop_event = Event()
        stage_started = time.perf_counter()
        self.logger.info("job_id=%s | stage=%s | 시작", job_id, stage)

        def heartbeat() -> None:
            while not stop_event.wait(10):
                self.logger.info(
                    "job_id=%s | stage=%s | 진행 중 | stage_elapsed=%.1fs | "
                    "total_elapsed=%.1fs",
                    job_id,
                    stage,
                    time.perf_counter() - stage_started,
                    self.job_store.elapsed(job_id),
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
            self.logger.info(
                "job_id=%s | stage=%s | %s | stage_elapsed=%.1fs | "
                "total_elapsed=%.1fs",
                job_id,
                stage,
                "완료" if succeeded else "중단",
                time.perf_counter() - stage_started,
                self.job_store.elapsed(job_id),
            )

    def run_summary(self, job_id: str, request_data: dict[str, Any]) -> None:
        try:
            request = SummaryRequest.model_validate(request_data)
            stt_text = request.full_text.strip() or " ".join(
                segment.text.strip()
                for segment in request.segments
                if segment.text.strip()
            )
            segment_data = [segment.model_dump() for segment in request.segments]

            self.job_store.update(
                job_id,
                status="running",
                message="STT 전체 요약을 생성하고 있습니다.",
                current_step=1,
                total_steps=2 if segment_data else 1,
            )
            with self.log_stage(job_id, "STT 전체 요약"):
                summary = self.summary_service.summarize_stt(
                    stt_text=stt_text,
                    max_new_tokens=request.max_new_tokens,
                )

            important_segments = []
            if segment_data:
                chunks = self.summary_service.llm_service.split_segments(
                    segment_data,
                    max_chunk_chars=12000,
                )

                def report_progress(_task: str, index: int, total: int) -> None:
                    self.job_store.update(
                        job_id,
                        message=f"중요 구간을 추출하고 있습니다. ({index}/{total})",
                        current_step=index,
                        total_steps=total,
                    )
                    self.logger.info(
                        "job_id=%s | 중요 구간 묶음 시작 | chunk=%d/%d | "
                        "total_elapsed=%.1fs",
                        job_id,
                        index,
                        total,
                        self.job_store.elapsed(job_id),
                    )

                self.job_store.update(
                    job_id,
                    message=f"중요 구간을 추출하고 있습니다. (0/{len(chunks)})",
                    current_step=0,
                    total_steps=len(chunks),
                )
                with self.log_stage(job_id, "중요 구간 추출"):
                    important_segments = (
                        self.summary_service.get_important_segments_in_chunks(
                            stt_segments=segment_data,
                            stt_summary=summary,
                            max_new_tokens=min(request.max_new_tokens, 256),
                            progress_callback=report_progress,
                        )
                    )

            result = SummaryResponse(
                summary=summary,
                important_segments=important_segments,
            )
            self.job_store.update(
                job_id,
                status="completed",
                message="요약과 중요 구간 추출이 완료되었습니다.",
                result=result.model_dump(),
                current_step=1,
                total_steps=1,
            )
            self.logger.info(
                "job_id=%s | 작업 완료 | total_elapsed=%.1fs | "
                "important_segments=%d",
                job_id,
                self.job_store.elapsed(job_id),
                len(important_segments),
            )
        except Exception as error:
            self.logger.exception("요약 작업 실패: job_id=%s", job_id)
            self.job_store.update(
                job_id,
                status="failed",
                message="추론 작업 중 오류가 발생했습니다.",
                error=str(error),
            )
        finally:
            if not self.keep_llm_loaded:
                self.summary_service.unload_llm()
                self.logger.info("job_id=%s | LLM GPU 메모리 해제 완료", job_id)

    def run_vlm(
        self,
        job_id: str,
        ocr_entries: list[dict[str, Any]],
        frame_data: list[bytes],
        max_new_tokens: int,
    ) -> None:
        try:
            total_frames = len(ocr_entries)

            def report_progress(_task: str, index: int, total: int) -> None:
                self.job_store.update(
                    job_id,
                    status="running",
                    message=f"프레임을 분석하고 있습니다. ({index}/{total})",
                    current_step=index,
                    total_steps=total,
                )
                self.logger.info(
                    "job_id=%s | VLM 프레임 분석 | frame=%d/%d | "
                    "total_elapsed=%.1fs",
                    job_id,
                    index,
                    total,
                    self.job_store.elapsed(job_id),
                )

            self.job_store.update(
                job_id,
                status="running",
                message=f"프레임을 분석하고 있습니다. (0/{total_frames})",
                current_step=0,
                total_steps=total_frames,
            )
            with self.log_stage(job_id, "VLM 프레임 분석"):
                result = self.summary_service.summarize_frames(
                    ocr_results=ocr_entries,
                    frames=frame_data,
                    max_new_tokens=max_new_tokens,
                    progress_callback=report_progress,
                )

            self.job_store.update(
                job_id,
                status="completed",
                message="프레임 분석이 완료되었습니다.",
                result=result,
                current_step=total_frames,
                total_steps=total_frames,
            )
            self.logger.info(
                "job_id=%s | VLM 작업 완료 | total_elapsed=%.1fs | frames=%d",
                job_id,
                self.job_store.elapsed(job_id),
                total_frames,
            )
        except Exception as error:
            self.logger.exception("VLM 작업 실패: job_id=%s", job_id)
            self.job_store.update(
                job_id,
                status="failed",
                message="프레임 분석 중 오류가 발생했습니다.",
                error=str(error),
            )
        finally:
            if not self.keep_vlm_loaded:
                self.summary_service.unload_vlm()
                self.logger.info("job_id=%s | VLM GPU 메모리 해제 완료", job_id)
