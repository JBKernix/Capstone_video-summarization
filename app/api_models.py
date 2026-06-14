from typing import Any, Literal

from pydantic import BaseModel, Field

from configs.inference_config import LLM_INFERENCE_CONFIG


class STTSegment(BaseModel):
    segment_id: int
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str


class SummaryRequest(BaseModel):
    language: str = "unknown"
    segments: list[STTSegment] = Field(default_factory=list)
    full_text: str = ""
    max_new_tokens: int = Field(
        default=LLM_INFERENCE_CONFIG.default_max_new_tokens,
        ge=1,
        le=LLM_INFERENCE_CONFIG.max_new_tokens_limit,
    )


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
    result: SummaryResponse | list[dict[str, Any]] | None = None
    error: str | None = None
    created_at: str
    updated_at: str
    elapsed_seconds: float = 0.0
