from threading import Lock
from collections.abc import Mapping, Sequence
from typing import Any

from services.llm_service import LLMService
from services.vlm_service import VLMService
from services.final_service import FinalService


class SummaryService:
    def __init__(self):
        # 두 모델이 같은 GPU를 동시에 점유하지 않도록 공용 lock을 사용합니다.
        generation_lock = Lock()
        self.llm_service = LLMService(generation_lock=generation_lock)
        self.vlm_service = VLMService(generation_lock=generation_lock)
        self.final_service = FinalService(llm_service=self.llm_service)

    def summarize_stt(self, stt_text: str, **kwargs) -> str:
        return self.llm_service.summarize_stt(stt_text, **kwargs)

    def unload_llm(self) -> None:
        self.llm_service.unload()

    def unload_vlm(self) -> None:
        self.vlm_service.unload()

    def get_important_segments(
        self,
        stt_segments: list[dict[str, Any]],
        stt_summary: str,
        **kwargs,
    ) -> str:
        return self.llm_service.extract_important_segments(
            stt_segments=stt_segments,
            stt_summary=stt_summary,
            **kwargs
        )

    def get_important_segments_in_chunks(
        self,
        stt_segments: list[dict[str, Any]],
        stt_summary: str,
        **kwargs,
    ) -> list[dict[str, Any]]:
        return self.llm_service.extract_important_segments_in_chunks(
            stt_segments=stt_segments,
            stt_summary=stt_summary,
            **kwargs,
        )

    def summarize_frame(
        self,
        image_path: str,
        ocr_text: str = "",
        max_new_tokens: int = 512,
    ) -> str:
        # VLM 서비스의 명시적인 인자 계약을 그대로 노출합니다.
        return self.vlm_service.summarize_frame(
            image_path=image_path,
            ocr_text=ocr_text,
            max_new_tokens=max_new_tokens,
        )

    def summarize_frames(
        self,
        ocr_results: Any,
        frames: Mapping[Any, Any] | Sequence[Any],
        **kwargs,
    ) -> list[dict[str, Any]]:
        return self.vlm_service.summarize_frames(
            ocr_results=ocr_results,
            frames=frames,
            **kwargs,
        )

    def summarize_final(self, **kwargs) -> str:
        return self.final_service.summarize_final(**kwargs)
