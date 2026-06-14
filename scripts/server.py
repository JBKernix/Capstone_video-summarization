import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# scripts 폴더에서 직접 실행해도 프로젝트 패키지를 찾을 수 있게 합니다.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status

from scripts.api_models import (
    JobStatusResponse,
    JobSubmissionResponse,
    SummaryRequest,
)
from scripts.inference_jobs import InferenceJobRunner
from scripts.job_store import JobStore
from scripts.server_logging import configure_logging
from scripts.vlm_upload import (
    MAX_FRAME_BYTES,
    MAX_FRAME_COUNT,
    MAX_OCR_JSON_BYTES,
    read_upload_limited,
    select_ocr_entries_for_frames,
    validate_frame_filename,
)
from services.summary_service import SummaryService


def env_flag(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in {"1", "true", "yes", "on"}


logger = configure_logging(PROJECT_ROOT)
app = FastAPI(
    title="Video Summarization AI Server",
    description="LLM/VLM 처리를 위한 FastAPI 서버",
    version="0.1.0",
)

summary_service = SummaryService()
job_store = JobStore()
job_runner = InferenceJobRunner(
    summary_service=summary_service,
    job_store=job_store,
    logger=logger,
    keep_llm_loaded=env_flag("KEEP_LLM_LOADED"),
    keep_vlm_loaded=env_flag("KEEP_VLM_LOADED"),
)
job_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="summary-job")


@app.get("/")
def root():
    return {"message": "FastAPI server is running"}


@app.get("/health")
def health_check():
    return {"status": "ok", "active_jobs": job_store.active_count()}


@app.post(
    "/llm/summarize",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def summarize(request: SummaryRequest):
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

    job_id = job_store.create_id("stt-summary")
    job_store.create(job_id, "추론 대기열에 등록되었습니다.")
    logger.info(
        "job_id=%s | 작업 접수 | text_length=%d | segments=%d | "
        "max_new_tokens=%d",
        job_id,
        len(stt_text),
        len(request.segments),
        request.max_new_tokens,
    )
    job_executor.submit(job_runner.run_summary, job_id, request.model_dump())
    return JobSubmissionResponse(
        job_id=job_id,
        status="queued",
        message="요청을 접수했습니다. status_url을 조회해 진행 상태를 확인하세요.",
        status_url=f"/llm/jobs/{job_id}",
    )


@app.post(
    "/vlm/summarize",
    response_model=JobSubmissionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def summarize_frames(
    ocr_result: UploadFile = File(...),
    frames: list[UploadFile] = File(...),
    max_new_tokens: int = Form(default=512, ge=1, le=2048),
):
    if not frames:
        raise HTTPException(status_code=422, detail="프레임 이미지가 필요합니다.")
    if len(frames) > MAX_FRAME_COUNT:
        raise HTTPException(
            status_code=422,
            detail=f"프레임은 최대 {MAX_FRAME_COUNT}장까지 업로드할 수 있습니다.",
        )

    try:
        ocr_bytes = await read_upload_limited(ocr_result, MAX_OCR_JSON_BYTES)
        ocr_entries = summary_service.vlm_service.load_ocr_results(
            ocr_bytes.decode("utf-8-sig")
        )
    except (UnicodeDecodeError, ValueError) as error:
        raise HTTPException(
            status_code=422,
            detail=f"OCR JSON 형식이 올바르지 않습니다: {error}",
        ) from error

    frame_data = []
    frame_names = []
    seen_frame_names = set()
    for frame in frames:
        try:
            filename = validate_frame_filename(frame.filename or "")
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

        normalized_name = filename.casefold()
        if normalized_name in seen_frame_names:
            raise HTTPException(
                status_code=422,
                detail=f"중복된 프레임 파일명입니다: {filename}",
            )
        seen_frame_names.add(normalized_name)
        frame_data.append(await read_upload_limited(frame, MAX_FRAME_BYTES))
        frame_names.append(filename)

    try:
        selected_entries = select_ocr_entries_for_frames(ocr_entries, frame_names)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    job_id = job_store.create_id("vlm-summary")
    job_store.create(job_id, "VLM 추론 대기열에 등록되었습니다.")
    logger.info(
        "job_id=%s | VLM 작업 접수 | ocr_entries=%d | frames=%d | "
        "max_new_tokens=%d",
        job_id,
        len(ocr_entries),
        len(frame_data),
        max_new_tokens,
    )
    job_executor.submit(
        job_runner.run_vlm,
        job_id,
        selected_entries,
        frame_data,
        max_new_tokens,
    )
    return JobSubmissionResponse(
        job_id=job_id,
        status="queued",
        message="요청을 접수했습니다. status_url을 조회해 진행 상태를 확인하세요.",
        status_url=f"/vlm/jobs/{job_id}",
    )


def get_job(job_id: str) -> JobStatusResponse:
    response_data = job_store.response_data(job_id)
    if response_data is None:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    return JobStatusResponse.model_validate(response_data)


@app.get("/llm/jobs/{job_id}", response_model=JobStatusResponse)
def get_summary_job(job_id: str):
    return get_job(job_id)


@app.get("/vlm/jobs/{job_id}", response_model=JobStatusResponse)
def get_vlm_job(job_id: str):
    return get_job(job_id)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", "8000")),
    )
