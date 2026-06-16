from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import Lock
from typing import Any

from configs.inference_config import LLM_INFERENCE_CONFIG
from services.llm_service import LLMService


TextInput = str | bytes | bytearray | Path
JSONInput = str | bytes | bytearray | Path | Mapping[str, Any] | Sequence[Any]

MAX_STT_TEXT_CHARS = 5000
MAX_VLM_TEXT_CHARS = 5000
MAX_IMPORTANT_SEGMENTS = 8
MAX_VLM_ITEMS = 12
MAX_ITEM_TEXT_CHARS = 350


class FinalService:
    def __init__(self, generation_lock=None, llm_service: LLMService | None = None):
        self.llm_service = llm_service or LLMService(
            generation_lock=generation_lock or Lock()
        )
        self._generation_lock = self.llm_service._generation_lock

    def summarize_final(
        self,
        stt_text: TextInput | None = None,
        stt_json: JSONInput | None = None,
        vlm_text: TextInput | None = None,
        vlm_json: JSONInput | None = None,
        max_new_tokens: int = LLM_INFERENCE_CONFIG.default_max_new_tokens,
    ) -> str:
        """STT 요약과 VLM 요약 산출물을 종합해 최종 요약을 생성합니다."""
        stt_section = self.build_stt_section(stt_text=stt_text, stt_json=stt_json)
        vlm_section = self.build_vlm_section(vlm_text=vlm_text, vlm_json=vlm_json)
        if not stt_section.strip():
            raise ValueError("STT 요약 내용이 비어 있습니다.")
        if not vlm_section.strip():
            raise ValueError("VLM 요약 내용이 비어 있습니다.")

        prompt = f"""
당신은 영상의 최종 요약을 작성하는 한국어 요약 전문가입니다.
제공된 STT 요약과 VLM 요약에 있는 정보만 사용하고, 없는 사실을 추측하거나 추가하지 마세요.

[STT 요약 자료]
{stt_section}

[VLM 요약 자료]
{vlm_section}

아래 형식을 지켜 한국어로 작성하세요.

## 최종 요약

### 핵심 주제
- 

### 전체 흐름
- 

### 음성 기반 주요 내용
- 

### 화면/시각 자료 기반 주요 내용
- 

### 종합 결론
-

각 항목은 간결한 bullet point로 작성하세요.
"""

        with self._generation_lock:
            return self.llm_service.loader.generate(
                prompt=prompt,
                max_new_tokens=self._validate_max_new_tokens(max_new_tokens),
            )

    def build_stt_section(
        self,
        stt_text: TextInput | None = None,
        stt_json: JSONInput | None = None,
    ) -> str:
        parts = []
        text = self._read_text(stt_text).strip() if stt_text is not None else ""
        if text:
            text = self._limit_text(text, MAX_STT_TEXT_CHARS)
            parts.append(f"[STT 요약 텍스트]\n{text}")

        if stt_json is not None:
            data = self._load_json(stt_json, "STT 요약 JSON")
            normalized = self._format_stt_json(data)
            if normalized:
                parts.append(f"[STT 주요 구간]\n{normalized}")

        return "\n\n".join(parts)

    def build_vlm_section(
        self,
        vlm_text: TextInput | None = None,
        vlm_json: JSONInput | None = None,
    ) -> str:
        parts = []
        text = self._read_text(vlm_text).strip() if vlm_text is not None else ""
        if text:
            text = self._limit_text(text, MAX_VLM_TEXT_CHARS)
            parts.append(f"[VLM 요약 텍스트]\n{text}")

        if vlm_json is not None:
            data = self._load_json(vlm_json, "VLM 요약 JSON")
            normalized = self._format_vlm_json(data)
            if normalized:
                parts.append(f"[VLM 프레임별 요약]\n{normalized}")

        return "\n\n".join(parts)

    @staticmethod
    def _read_text(value: TextInput) -> str:
        if isinstance(value, Path):
            if not value.is_file():
                raise FileNotFoundError(f"텍스트 파일을 찾을 수 없습니다: {value}")
            return value.read_text(encoding="utf-8-sig")
        if isinstance(value, (bytes, bytearray)):
            return bytes(value).decode("utf-8-sig")
        return str(value)

    @staticmethod
    def _load_json(value: JSONInput, label: str) -> Any:
        if isinstance(value, Path):
            if not value.is_file():
                raise FileNotFoundError(f"{label} 파일을 찾을 수 없습니다: {value}")
            with value.open("r", encoding="utf-8-sig") as file:
                return json.load(file)
        if isinstance(value, (bytes, bytearray)):
            value = bytes(value).decode("utf-8-sig")
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError as error:
                raise ValueError(f"{label} 형식이 올바른 JSON이 아닙니다.") from error
        return value

    @staticmethod
    def _format_stt_json(data: Any) -> str:
        if isinstance(data, Mapping):
            important_segments = data.get("important_segments")
            if isinstance(important_segments, Sequence) and not isinstance(
                important_segments, (str, bytes, bytearray)
            ):
                formatted_segments = FinalService._format_important_segments(
                    important_segments
                )
                if formatted_segments:
                    return f"중요 구간:\n{formatted_segments}"

        return ""

    @staticmethod
    def _format_important_segments(segments: Sequence[Any]) -> str:
        lines = []
        for segment in FinalService._sample_items(segments, MAX_IMPORTANT_SEGMENTS):
            if not isinstance(segment, Mapping):
                continue
            segment_id = segment.get("segment_id", "")
            start = segment.get("start", "")
            end = segment.get("end", "")
            topic = FinalService._limit_text(
                str(segment.get("topic", "")).strip(),
                80,
            )
            reason = str(segment.get("reason", "")).strip()
            text = str(segment.get("text", "")).strip()
            detail = FinalService._limit_text(reason or text, MAX_ITEM_TEXT_CHARS)
            lines.append(
                f"- {segment_id} ({start}-{end}) {topic}: {detail}".strip()
            )
        return "\n".join(lines)

    @staticmethod
    def _format_vlm_json(data: Any) -> str:
        if isinstance(data, Mapping):
            for key in ("results", "frames", "vlm_results"):
                if key in data:
                    data = data[key]
                    break

        if isinstance(data, Sequence) and not isinstance(
            data, (str, bytes, bytearray)
        ):
            lines = []
            for entry in FinalService._sample_items(data, MAX_VLM_ITEMS):
                if not isinstance(entry, Mapping):
                    continue
                timestamp = entry.get("timestamp", "")
                vlm_summary = FinalService._limit_text(
                    str(entry.get("vlm_summary", "")).strip(),
                    MAX_ITEM_TEXT_CHARS,
                )
                if not vlm_summary:
                    continue
                lines.append(
                    "\n".join(
                        item
                        for item in (
                            (
                                f"- 시간: {timestamp}"
                                if timestamp != ""
                                else "- 시간: 알 수 없음"
                            ),
                            f"  VLM 요약: {vlm_summary}",
                        )
                        if item
                    )
                )
            if lines:
                return "\n".join(lines)

        return ""

    @staticmethod
    def _limit_text(text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars].rstrip() + "\n... (길이 제한으로 일부 생략)"

    @staticmethod
    def _sample_items(items: Sequence[Any], max_items: int) -> list[Any]:
        if max_items < 1:
            return []
        if len(items) <= max_items:
            return list(items)
        if max_items == 1:
            return [items[0]]

        last_index = len(items) - 1
        return [
            items[round(last_index * index / (max_items - 1))]
            for index in range(max_items)
        ]

    @staticmethod
    def _validate_max_new_tokens(max_new_tokens: int) -> int:
        if not 1 <= max_new_tokens <= LLM_INFERENCE_CONFIG.max_new_tokens_limit:
            raise ValueError(
                "max_new_tokens는 1 이상 "
                f"{LLM_INFERENCE_CONFIG.max_new_tokens_limit} 이하이어야 합니다."
            )
        return max_new_tokens
