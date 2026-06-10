from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from services.summary_service import SummaryService


app = FastAPI(
    title="Video Summarization AI Server",
    description="LLM/VLM 처리를 위한 FastAPI 서버",
    version="0.1.0",
)


class SummaryRequest(BaseModel):
    stt_text: str
    ocr_text: Optional[str] = ""
    vision_text: Optional[str] = ""


class SummaryResponse(BaseModel):
    summary: str


@app.get("/")
def root():
    return {
        "message": "FastAPI server is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok"
    }

# stt 요약 요청
@app.post("/llm/summarize", response_model=SummaryResponse)
def summarize(request: SummaryRequest):
    stt_text = request.stt_text
    text_len = (f"STT 텍스트 길이: {len(stt_text)}")


    summary = SummaryService.SttSummary(stt_text)

    return SummaryResponse(summary = summary)