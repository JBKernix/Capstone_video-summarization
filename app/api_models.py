from typing import Any, Literal

from pydantic import BaseModel, Field

from configs.inference_config import DEFAULT_SUMMARY_LEVEL, SummaryLevel


class STTSegment(BaseModel):
    segment_id: int
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str


class SummaryRequest(BaseModel):
    language: str = "unknown"
    segments: list[STTSegment] = Field(default_factory=list)
    full_text: str = ""
    # "simple"(간단요약) / "standard"(기본요약) / "detailed"(상세요약).
    # 실제 토큰 수 등은 configs.inference_config.SUMMARY_LEVEL_PRESETS에서 결정됩니다.
    summary_level: SummaryLevel = DEFAULT_SUMMARY_LEVEL


class ImportantSegment(BaseModel):
    segment_id: int
    start: float
    end: float
    topic: str
    reason: str


class SummaryResponse(BaseModel):
    summary: str
    important_segments: list[ImportantSegment]


class FinalSummaryResponse(BaseModel):
    final_summary: str


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
    result: SummaryResponse | FinalSummaryResponse | list[dict[str, Any]] | None = None
    error: str | None = None
    created_at: str
    updated_at: str
    elapsed_seconds: float = 0.0
