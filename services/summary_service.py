from services.llm_service import LLMService
from services.vlm_service import VLMService


class SummaryService:
    def __init__(self):
        self.llm_service = LLMService()
        self.vlm_service = VLMService()

    def summarize_stt(self, stt_text: str) -> str:
        return self.llm_service.summarize_stt(stt_text)

    def get_important_segments(self, stt_text: str, stt_summary: str) -> str:
        return self.llm_service.extract_important_segments(
            stt_text=stt_text,
            stt_summary=stt_summary,
        )

    def summarize_frame(self, image_path: str, ocr_text: str = "") -> str:
        return self.vlm_service.summarize_frame(
            image_path=image_path,
            ocr_text=ocr_text,
        )