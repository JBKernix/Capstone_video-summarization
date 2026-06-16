from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import Lock
from typing import Any

from services.llm_service import LLMService


TextInput = str | bytes | bytearray | Path
JSONInput = str | bytes | bytearray | Path | Mapping[str, Any] | Sequence[Any]

MAX_STT_TEXT_CHARS = 5000
MAX_VLM_TEXT_CHARS = 5000
MAX_IMPORTANT_SEGMENTS = 8
MAX_VLM_ITEMS = 12
MAX_ITEM_TEXT_CHARS = 350
DEFAULT_FINAL_MAX_NEW_TOKENS = 2048
MAX_FINAL_NEW_TOKENS_LIMIT = 4096


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
        max_new_tokens: int = DEFAULT_FINAL_MAX_NEW_TOKENS,
    ) -> str:
        """STT 요약과 VLM 요약 결과를 종합해 최종 요약을 생성합니다."""
        stt_section = self.build_stt_section(stt_text=stt_text, stt_json=stt_json)
        vlm_section = self.build_vlm_section(vlm_text=vlm_text, vlm_json=vlm_json)
        if not stt_section.strip():
            raise ValueError("STT 요약 내용이 비어 있습니다.")
        if not vlm_section.strip():
            raise ValueError("VLM 요약 내용이 비어 있습니다.")

        prompt = f"""
당신은 영상의 최종 요약을 작성하는 한국어 요약 전문가입니다.

제공된 STT 요약과 VLM 요약에 있는 정보만 사용하세요.
입력 자료에 없는 사실, 수치, 항목, 원인, 결론을 추측하거나 추가하지 마세요.
STT 요약과 VLM 요약에서 중복되는 내용은 하나로 통합하세요.
두 자료의 내용이 충돌하면 단정하지 말고 "확인 필요"로 표시하세요.

최종 요약은 영상의 흐름을 따라 주제별로 구성하세요.
각 주제에는 해당 내용이 등장하는 영상 구간을 타임라인으로 표시하세요.
타임라인은 반드시 입력 자료에 포함된 시간 정보만 사용하세요.
정확한 시작/종료 시간을 알 수 없는 경우에는 "타임라인: 확인 필요"라고 표시하세요.

VLM 요약 자료에서 표, 차트, 그래프, 도식, 수치 비교, 비율, 추세, 항목별 비교가 확인되는 경우에는
"표/차트 기반 주요 정보" 섹션을 추가하세요.
확인되지 않으면 "표/차트 기반 주요 정보" 섹션은 작성하지 마세요.
표나 차트의 수치, 항목명, 추세, 비교 내용은 입력 자료에 있는 내용만 사용하세요.
없는 수치나 항목을 임의로 생성하지 마세요.

주제는 영상의 흐름에 따라 3~7개 정도로 구성하세요.
너무 짧거나 반복되는 내용은 인접한 주제와 통합하세요.

[STT 요약 자료]
{stt_section}

[VLM 요약 자료]
{vlm_section}

아래 형식을 지켜 한국어로 작성하세요.

# {{영상 내용을 대표하는 제목}}

## 핵심 주제
- 영상 전체의 핵심 주제를 1~3개의 bullet point로 요약하세요.

## 주요 내용

### 1. {{주제 제목}} (타임라인: HH:MM:SS ~ HH:MM:SS)
- 해당 구간의 핵심 내용을 요약하세요.
- STT 요약에서 확인되는 주요 발언이나 설명을 반영하세요.
- VLM 요약에서 확인되는 화면, 슬라이드, 장면, 시각 자료 정보를 함께 반영하세요.

### 2. {{주제 제목}} (타임라인: HH:MM:SS ~ HH:MM:SS)
- 해당 구간의 핵심 내용을 요약하세요.
- STT와 VLM 정보를 종합하세요.

필요한 만큼 주제를 추가하세요.

## 표/차트 기반 주요 정보

### 1. {{표/차트/도식 제목 또는 핵심 내용}} (타임라인: HH:MM:SS 또는 확인 필요)
- 자료 유형: 표 / 차트 / 그래프 / 도식 / 기타 시각 자료
- 확인된 내용:
  - 입력 자료에서 확인되는 항목, 수치, 비교, 추세를 정리하세요.
- 요약 해석:
  - 해당 시각 자료가 영상 내용에서 어떤 의미를 가지는지 정리하세요.
  - 단, 입력 자료에 없는 해석은 추가하지 마세요.

※ VLM 요약 자료에서 표, 차트, 그래프, 도식, 수치 비교가 확인되지 않으면 이 섹션은 생략하세요.

## 종합 결론
- 영상 전체의 결론을 2~4개의 bullet point로 정리하세요.
- 제공된 정보만 바탕으로 작성하세요.
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
        if not 1 <= max_new_tokens <= MAX_FINAL_NEW_TOKENS_LIMIT:
            raise ValueError(
                "max_new_tokens는 1 이상 "
                f"{MAX_FINAL_NEW_TOKENS_LIMIT} 이하이어야 합니다."
            )
        return max_new_tokens
