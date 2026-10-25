from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from threading import Lock
from typing import Any

from services.llm_service import LLMService
from services.vlm_service import normalize_screen_type, parse_vlm_fields


TextInput = str | bytes | bytearray | Path
JSONInput = str | bytes | bytearray | Path | Mapping[str, Any] | Sequence[Any]

MAX_STT_TEXT_CHARS = 5000
MAX_VLM_TEXT_CHARS = 5000
MAX_IMPORTANT_SEGMENTS = 8
MAX_VLM_ITEMS = 16
MAX_VLM_ITEM_TEXT_CHARS = 300
MAX_ITEM_TEXT_CHARS = 350
DEFAULT_FINAL_MAX_NEW_TOKENS = 3072
MAX_FINAL_NEW_TOKENS_LIMIT = 4096
# 모델이 쓴 시간이 입력 자료의 마지막 시간보다 이만큼(초) 넘으면 잘못된 값으로 봅니다.
TIME_TOLERANCE_SEC = 5.0

# 판서 위주 강의에서는 판서의 식·그림이 핵심 자료이므로 함께 허용합니다. 그 밖의 유형(기타 등)은 버립니다.
VISUAL_TYPES = ("표", "그래프", "수식", "코드", "도식", "판서")
# 최종 요약 입력에 넣을 화면을 고를 때의 우선순위입니다. 값이 클수록 먼저 고릅니다.
SCREEN_PRIORITY = {"수식": 3, "코드": 3, "표": 3, "그래프": 3, "도식": 3, "슬라이드": 2, "판서": 2}
NOTE_LIMITS = {
    "key_points": 3,
    "terms": 15,
    "chapters": 10,
    "points": 6,
    "screen_notes": 4,
    "visuals": 10,
    "content": 6,
    "conclusion": 5,
    "emphasis": 6,
    "notices": 5,
}
# 공지(notices)에 잘못 들어온 강조 표현입니다. "시험 범위는 3장까지" 같은 일정 공지는 해당하지 않습니다.
EMPHASIS_IN_NOTICE = re.compile(r"시험에\s*(?:나온|나와|나올|출제)|꼭\s*(?:기억|알아)|중요(?:하|한|합)")
SCREEN_NOTE_PREFIX = re.compile(r"^VLM\s*요약\s*자료(?:에서는|에서|에는|에)\s*,?\s*")
PLACEHOLDER_PATTERN = re.compile(r"^<[^<>]*>$")
NO_VLM_CONTENT = "(화면 자료에서 확인된 강의 내용이 없습니다.)"

NOTE_PROMPT = """
당신은 강의 영상을 학습용 강의 노트로 정리하는 한국어 요약 전문가입니다.

[작성 원칙]
- 제공된 STT 요약과 VLM 요약에 있는 정보만 사용하세요.
- 입력 자료에 없는 개념 설명, 예시, 수치, 공식, 결론을 추측하거나 추가하지 마세요.
- STT와 VLM에서 중복되는 내용은 하나로 합치고, 서로 충돌하면 문장 끝에 "(확인 필요)"를 붙이세요.
- 강의 흐름을 따라 chapters를 3~7개로 나누세요. 너무 짧은 챕터는 인접 챕터와 합치세요.
- start와 end는 입력 자료에 있는 초 단위 숫자를 그대로 쓰세요. HH:MM:SS로 바꾸지 마세요.
  시간을 알 수 없으면 null을 쓰세요.
- VLM 자료의 [시작 ~ 끝]은 해당 화면이 보인 시간(초)입니다.
- emphasis에는 강사가 "중요하다", "시험에 나온다", "꼭 기억하라" 등으로 강조한 내용을 쓰세요.
- notices에는 과제 제출, 시험 일정, 다음 수업 안내 같은 일정·행정 공지만 쓰세요. 강조한 내용은 넣지 마세요.
- visuals에는 표, 그래프, 수식, 코드, 도식, 판서 자료만 넣으세요. 일반 화면이나 강사 화면은 넣지 마세요.

[STT 요약 자료]
{stt_section}

[VLM 요약 자료]
{vlm_section}

[출력 규칙]
- 아래 구조의 JSON 객체 하나만 출력하세요. 설명 문장, Markdown, ``` 코드 블록은 출력하지 마세요.
- 키 이름은 바꾸지 말고, 문자열은 큰따옴표를 쓰고, 마지막 항목 뒤에 쉼표를 붙이지 마세요.
- 해당 내용이 없으면 빈 배열 []을 쓰세요.
- 각 문자열은 한 문장으로 짧게 쓰세요.

{
  "title": "<강의 주제를 대표하는 제목>",
  "key_points": ["<이 강의에서 배우는 핵심 내용, 1~3개>"],
  "terms": [
    {"term": "<핵심 용어>", "definition": "<강의에서 설명한 정의>"}
  ],
  "chapters": [
    {
      "title": "<챕터 제목>",
      "start": <시작 초 숫자 또는 null>,
      "end": <끝 초 숫자 또는 null>,
      "points": ["<이 구간에서 설명한 개념, 설명 흐름, 예시, 2~4개>"],
      "screen_notes": ["<슬라이드·판서·코드에서 확인된 내용, 없으면 빈 배열>"]
    }
  ],
  "visuals": [
    {
      "type": "<표 | 그래프 | 수식 | 코드 | 도식 | 판서 중 하나>",
      "title": "<자료 제목 또는 핵심 내용>",
      "start": <시작 초 숫자 또는 null>,
      "end": <끝 초 숫자 또는 null>,
      "content": ["<입력 자료에 있는 항목, 수치, 식, 코드 동작>"],
      "meaning": "<이 자료가 설명하는 개념, 근거가 없으면 빈 문자열>"
    }
  ],
  "conclusion": ["<복습할 때 꼭 기억할 내용, 2~4개>"],
  "emphasis": ["<강사가 강조한 내용, 없으면 빈 배열>"],
  "notices": ["<과제 제출·시험 일정·다음 수업 안내, 없으면 빈 배열>"]
}
"""

# 생성이 결정적(do_sample=False)이라 같은 프롬프트로 다시 요청하면 같은 답이 나옵니다.
# 재요청에는 오류 내용을 덧붙여 다른 입력으로 만듭니다.
NOTE_RETRY_SUFFIX = """
[재요청]
이전 출력은 JSON으로 읽을 수 없었습니다 (오류: {error}).
설명이나 코드 블록 없이 위 구조의 JSON 객체 하나만 처음부터 끝까지 다시 출력하세요.
각 문자열을 더 짧게 써서 출력이 중간에 끊기지 않게 하세요.
"""

MARKDOWN_FALLBACK_PROMPT = """
당신은 강의 영상을 학습용 강의 노트로 정리하는 한국어 요약 전문가입니다.

제공된 STT 요약과 VLM 요약에 있는 정보만 사용하세요.
입력 자료에 없는 개념 설명, 예시, 수치, 공식, 결론을 추측하거나 추가하지 마세요.
STT 요약과 VLM 요약에서 중복되는 내용은 하나로 통합하세요.
두 자료의 내용이 충돌하면 단정하지 말고 "확인 필요"로 표시하세요.

[구성 규칙]
- 강의 흐름을 따라 3~7개의 챕터로 나누세요. 너무 짧은 챕터는 인접 챕터와 합치세요.
- 핵심 용어는 처음 등장할 때 '작은따옴표'로 감싸세요.
- 각 챕터 끝에는 화면 자료에서 확인된 내용을 "VLM 요약 자료에서는"으로 시작하는 bullet로 적으세요.
- 타임라인은 입력 자료의 초 단위 숫자를 그대로 쓰세요. 예: (타임라인: 125.7 ~ 310.0)
  HH:MM:SS로 변환하지 마세요. 정확한 시간을 알 수 없을 때만 (타임라인: 확인 필요)로 쓰세요.

[STT 요약 자료]
{stt_section}

[VLM 요약 자료]
{vlm_section}

아래 형식을 지켜 한국어로 작성하세요.

# {강의 주제를 대표하는 제목}

## 핵심 주제
- 이 강의에서 배우는 핵심 내용을 1~3개의 bullet point로 정리하세요.

## 주요 내용

### 1. {챕터 제목} (타임라인: 시작초 ~ 끝초)
- 개념: 이 구간에서 설명한 개념과 정의
- 설명: 강사의 설명 흐름, 예시, 예제 풀이의 핵심
- VLM 요약 자료에서는 슬라이드·판서·코드에서 확인된 내용

### 2. {챕터 제목} (타임라인: 시작초 ~ 끝초)
- (같은 방식)

필요한 만큼 챕터를 추가하세요.

## 표/차트 기반 주요 정보

### 1. {표·그래프·수식·코드·도식 제목} (타임라인: 시작초 ~ 끝초)
- 자료 유형: 표 / 그래프 / 수식 / 코드 / 도식 / 판서
- 확인된 내용: 입력 자료에 있는 항목, 수치, 식, 코드 동작만 정리
- 강의에서의 의미: 이 자료가 설명하는 개념 (입력 자료에 근거가 있을 때만)

※ VLM 요약 자료에 표, 그래프, 수식, 코드, 도식, 판서 자료가 없으면 이 섹션은 생략하세요.

## 종합 결론
- 복습할 때 꼭 기억해야 할 내용을 2~4개의 bullet point로 정리하세요.
- 강사가 강조한 내용은 "강조:"로, 과제 제출·시험 일정·다음 수업 안내는 "공지:"로 시작하는 bullet로 적으세요.
"""


class FinalService:
    def __init__(
        self,
        generation_lock=None,
        llm_service: LLMService | None = None,
        max_stt_chars: int | None = None,
        max_vlm_chars: int | None = None,
    ):
        self.llm_service = llm_service or LLMService(
            generation_lock=generation_lock or Lock()
        )
        self._generation_lock = self.llm_service._generation_lock
        # 모델 프로필이 입력 토큰 한도에 맞춰 더 작게 지정할 수 있습니다.
        self.max_stt_chars = max_stt_chars or MAX_STT_TEXT_CHARS
        self.max_vlm_chars = max_vlm_chars or MAX_VLM_TEXT_CHARS

    def summarize_final(
        self,
        stt_text: TextInput | None = None,
        stt_json: JSONInput | None = None,
        vlm_text: TextInput | None = None,
        vlm_json: JSONInput | None = None,
        max_new_tokens: int = DEFAULT_FINAL_MAX_NEW_TOKENS,
    ) -> str:
        """최종 요약 마크다운을 반환합니다. 기존 서버 코드와의 호환용입니다."""
        return self.summarize_final_note(
            stt_text=stt_text,
            stt_json=stt_json,
            vlm_text=vlm_text,
            vlm_json=vlm_json,
            max_new_tokens=max_new_tokens,
        )["markdown"]

    def summarize_final_note(
        self,
        stt_text: TextInput | None = None,
        stt_json: JSONInput | None = None,
        vlm_text: TextInput | None = None,
        vlm_json: JSONInput | None = None,
        max_new_tokens: int = DEFAULT_FINAL_MAX_NEW_TOKENS,
        max_important_segments: int | None = None,
    ) -> dict[str, Any]:
        """STT 요약과 VLM 요약을 종합해 강의 노트 JSON과 마크다운을 만듭니다.

        JSON을 읽지 못하면 오류 내용을 덧붙여 한 번 다시 요청하고, 그래도 실패하면
        마크다운 프롬프트로 대체합니다. 이때 ``lecture_note``는 ``None``입니다.
        """
        if vlm_text is None and vlm_json is None:
            raise ValueError("VLM 요약 내용이 비어 있습니다.")
        stt_data = self._load_json(stt_json, "STT 요약 JSON") if stt_json is not None else None
        vlm_data = self._load_json(vlm_json, "VLM 요약 JSON") if vlm_json is not None else None
        stt_section = self.build_stt_section(
            stt_text=stt_text, stt_json=stt_data, max_important_segments=max_important_segments,
        )
        vlm_section = self.build_vlm_section(vlm_text=vlm_text, vlm_json=vlm_data)
        if not stt_section.strip():
            raise ValueError("STT 요약 내용이 비어 있습니다.")
        # 강사 화면만 있는 강의도 있으므로 화면 자료가 걸러져 비면 오류 대신 안내 문구를 넣습니다.
        vlm_section = vlm_section.strip() or NO_VLM_CONTENT
        max_new_tokens = self._validate_max_new_tokens(max_new_tokens)
        known_times = self.collect_known_times(stt_data, vlm_data)

        prompt = (
            NOTE_PROMPT.replace("{stt_section}", stt_section)
            .replace("{vlm_section}", vlm_section)
        )
        attempts: list[dict[str, Any]] = []
        for attempt in range(2):
            current_prompt = prompt
            if attempt:
                current_prompt += NOTE_RETRY_SUFFIX.format(error=attempts[-1]["error"])
            raw = self._generate(current_prompt, max_new_tokens)
            try:
                note, warnings = normalize_lecture_note(extract_json_object(raw), known_times)
            except ValueError as error:
                attempts.append({"raw": raw, "error": str(error)})
                continue
            attempts.append({"raw": raw, "error": None})
            return {
                "lecture_note": note,
                "markdown": render_note_markdown(note),
                "format": "json",
                "attempts": attempts,
                "warnings": warnings,
            }

        fallback_prompt = (
            MARKDOWN_FALLBACK_PROMPT.replace("{stt_section}", stt_section)
            .replace("{vlm_section}", vlm_section)
        )
        return {
            "lecture_note": None,
            "markdown": self._generate(fallback_prompt, max_new_tokens).strip(),
            "format": "markdown_fallback",
            "attempts": attempts,
            "warnings": [],
        }

    def _generate(self, prompt: str, max_new_tokens: int) -> str:
        with self._generation_lock:
            return self.llm_service.loader.generate(
                prompt=prompt,
                max_new_tokens=max_new_tokens,
            )

    def build_stt_section(
        self,
        stt_text: TextInput | None = None,
        stt_json: JSONInput | None = None,
        max_important_segments: int | None = None,
    ) -> str:
        parts = []
        data = self._load_json(stt_json, "STT 요약 JSON") if stt_json is not None else None

        text = self._read_text(stt_text).strip() if stt_text is not None else ""
        if not text and isinstance(data, Mapping):
            # stt_summary(txt)가 없는 요청(JSON만 전송)에서는
            # stt_json의 summary 필드를 STT 요약 텍스트로 사용합니다.
            text = str(data.get("summary", "")).strip()
        if text:
            text = self._limit_text(text, self.max_stt_chars)
            parts.append(f"[STT 요약 텍스트]\n{text}")

        if isinstance(data, Mapping):
            important_segments = data.get("important_segments")
            if isinstance(important_segments, Sequence) and not isinstance(
                important_segments, (str, bytes, bytearray)
            ):
                normalized = self._format_important_segments(
                    important_segments, max_important_segments or MAX_IMPORTANT_SEGMENTS,
                )
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
            text = self._limit_text(text, self.max_vlm_chars)
            parts.append(f"[VLM 요약 텍스트]\n{text}")

        if vlm_json is not None:
            data = self._load_json(vlm_json, "VLM 요약 JSON")
            normalized = self._format_vlm_json(data, self.max_vlm_chars)
            if normalized:
                parts.append(f"[VLM 화면별 요약]\n{normalized}")

        return "\n\n".join(parts)

    @classmethod
    def collect_known_times(cls, stt_data: Any, vlm_data: Any) -> list[float]:
        """입력 자료에 있는 시간(초)을 모읍니다. 모델이 쓴 시간의 범위 검증에 씁니다."""
        times = []
        if isinstance(stt_data, Mapping):
            for segment in stt_data.get("important_segments") or []:
                if isinstance(segment, Mapping):
                    times += [segment.get("start"), segment.get("end")]
        for entry in cls._vlm_entries(vlm_data):
            times.append(entry.get("timestamp"))
        return [value for value in (_seconds(time) for time in times) if value is not None]

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
    def _format_important_segments(
        segments: Sequence[Any], max_items: int = MAX_IMPORTANT_SEGMENTS,
    ) -> str:
        lines = []
        for segment in FinalService._sample_items(segments, max_items):
            if not isinstance(segment, Mapping):
                continue
            topic = FinalService._limit_text(
                str(segment.get("topic", "")).strip(),
                80,
            )
            reason = str(segment.get("reason", "")).strip()
            text = str(segment.get("text", "")).strip()
            detail = FinalService._limit_text(reason or text, MAX_ITEM_TEXT_CHARS)
            time_range = _format_range(_seconds(segment.get("start")), _seconds(segment.get("end")))
            lines.append(f"- [{time_range}] {topic}: {detail}".strip())
        return "\n".join(lines)

    @staticmethod
    def _vlm_entries(data: Any) -> list[Mapping[str, Any]]:
        if isinstance(data, Mapping):
            for key in ("results", "frames", "vlm_results"):
                if key in data:
                    data = data[key]
                    break
        if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
            return []
        return [entry for entry in data if isinstance(entry, Mapping)]

    @staticmethod
    def _format_vlm_json(data: Any, max_chars: int = MAX_VLM_TEXT_CHARS) -> str:
        """강의 내용이 있는 화면만 골라 시간순 목록으로 만듭니다.

        1. 강사 화면처럼 내용이 없는 프레임을 뺍니다.
        2. 시간상 이어진 프레임의 제목이 같으면 한 항목(시간 구간)으로 합칩니다.
        3. 그래도 많으면 전체를 같은 크기로 나눠 구간마다 우선순위가 가장 높은 항목을 고릅니다.
        ``vlm_fields``가 없는 이전 결과는 ``vlm_summary`` 원문을 내용으로 씁니다.
        """
        items = [
            item
            for item in (FinalService._vlm_item(entry) for entry in FinalService._vlm_entries(data))
            if item is not None
        ]
        items.sort(key=lambda item: (item["start"] is None, item["start"] or 0.0))
        items = FinalService._select_spread(FinalService._merge_same_screens(items), MAX_VLM_ITEMS)

        blocks = []
        for item in items:
            label = item["screen_type"] or "화면"
            header = f"- [{_format_range(item['start'], item['end'])}] {label}"
            if item["title"]:
                header += f" | {item['title']}"
            lines = [header]
            if item["content"]:
                lines.append(f"  내용: {item['content']}")
            if item["formula"]:
                lines.append(f"  수식·코드·수치: {item['formula']}")
            block = "\n".join(lines)
            if len(block) > MAX_VLM_ITEM_TEXT_CHARS:
                block = block[:MAX_VLM_ITEM_TEXT_CHARS].rstrip() + "…"
            blocks.append(block)
        return FinalService._limit_text("\n".join(blocks), max_chars)

    @staticmethod
    def _vlm_item(entry: Mapping[str, Any]) -> dict[str, Any] | None:
        fields = entry.get("vlm_fields")
        if not isinstance(fields, Mapping):
            raw = str(entry.get("vlm_summary", "")).strip()
            if not raw:
                return None
            fields = parse_vlm_fields(raw)
        if not fields.get("has_content"):
            return None
        timestamp = _seconds(entry.get("timestamp"))
        return {
            "start": timestamp,
            "end": timestamp,
            "screen_type": fields.get("screen_type"),
            "title": _clean_text(fields.get("title")),
            "content": " ".join(_clean_text(fields.get("content")).split()),
            "formula": _clean_text(fields.get("formula")),
        }

    @staticmethod
    def _merge_same_screens(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        for item in items:
            key = re.sub(r"\s+", "", item["title"]).casefold()
            previous = merged[-1] if merged else None
            if previous is not None and key and key == previous["_key"]:
                previous["end"] = item["end"] if item["end"] is not None else previous["end"]
                if _screen_priority(item["screen_type"]) > _screen_priority(previous["screen_type"]):
                    previous["screen_type"] = item["screen_type"]
                for name in ("content", "formula"):
                    if len(item[name]) > len(previous[name]):
                        previous[name] = item[name]
                continue
            merged.append({**item, "_key": key})
        for item in merged:
            item.pop("_key")
        return merged

    @staticmethod
    def _select_spread(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        if len(items) <= limit:
            return items
        selected = []
        for bucket_index in range(limit):
            low = round(len(items) * bucket_index / limit)
            high = round(len(items) * (bucket_index + 1) / limit)
            bucket = items[low:high]
            if bucket:
                selected.append(max(bucket, key=_vlm_rank))
        return selected

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


def _screen_priority(screen_type: str | None) -> int:
    return SCREEN_PRIORITY.get(screen_type or "", 1)


def _vlm_rank(item: Mapping[str, Any]) -> tuple[int, int]:
    return _screen_priority(item["screen_type"]), len(item["content"]) + len(item["formula"])


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value.strip() if isinstance(value, str) else value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return round(number, 2)


def _format_seconds(value: float) -> str:
    return str(round(value, 2))


def _format_range(start: float | None, end: float | None) -> str:
    if start is None:
        return "시간 알 수 없음"
    if end is None or end == start:
        return _format_seconds(start)
    return f"{_format_seconds(start)} ~ {_format_seconds(end)}"


def _clean_text(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        return ""
    text = value.strip()
    # 모델이 프롬프트의 <설명> 자리표시를 그대로 베낀 경우는 빈 값으로 봅니다.
    return "" if PLACEHOLDER_PATTERN.match(text) else text


def extract_json_object(text: str) -> dict[str, Any]:
    """모델 출력에서 JSON 객체 하나를 꺼냅니다. 코드 블록과 끝 쉼표는 고쳐서 읽습니다."""
    cleaned = re.sub(r"<think>.*?</think>", "", str(text), flags=re.DOTALL)
    cleaned = re.sub(r"```(?:json)?", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0:
        raise ValueError("출력에서 JSON 객체를 찾을 수 없습니다.")
    if end <= start:
        raise ValueError("JSON 객체가 닫히지 않았습니다. 출력이 길이 제한으로 잘렸을 수 있습니다.")
    candidate = cleaned[start : end + 1]

    last_error = None
    for attempt in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
        try:
            data = json.loads(attempt)
        except json.JSONDecodeError as error:
            last_error = error
            continue
        if not isinstance(data, dict):
            raise ValueError("최상위 값이 JSON 객체가 아닙니다.")
        return data
    raise ValueError(f"JSON 형식 오류: {last_error.msg} (위치 {last_error.pos})")


def normalize_lecture_note(
    data: Mapping[str, Any],
    known_times: Sequence[float] = (),
) -> tuple[dict[str, Any], list[str]]:
    """모델이 만든 강의 노트를 화면에서 쓸 수 있는 형태로 검증·정리합니다.

    잘못된 시간은 ``None``으로 바꾸고, 빈 항목은 버리고, 개수 상한을 넘으면 자릅니다.
    고친 내용은 경고 목록으로 함께 반환합니다. 챕터가 하나도 남지 않으면 ``ValueError``입니다.
    """
    warnings: list[str] = []
    max_time = max(known_times) + TIME_TOLERANCE_SEC if known_times else None

    def texts(value: Any, key: str) -> list[str]:
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        items = [text for text in (_clean_text(item) for item in value) if text]
        limit = NOTE_LIMITS[key]
        if len(items) > limit:
            warnings.append(f"{key}: {len(items)}개 중 {limit}개만 사용")
        return items[:limit]

    def time_range(item: Mapping[str, Any], label: str) -> tuple[float | None, float | None]:
        values = []
        for key in ("start", "end"):
            raw = item.get(key)
            value = _seconds(raw)
            if value is not None and max_time is not None and value > max_time:
                value = None
            if raw is not None and value is None:
                warnings.append(f"{label}: {key} 값 {raw!r}을(를) 사용할 수 없어 null로 바꿈")
            values.append(value)
        start, end = values
        if start is None and end is not None:
            start, end = end, None
        if start is not None and end is not None and end < start:
            warnings.append(f"{label}: end가 start보다 앞서 end를 null로 바꿈")
            end = None
        return start, end

    def records(value: Any, key: str) -> list[Mapping[str, Any]]:
        if not isinstance(value, list):
            return []
        items = [item for item in value if isinstance(item, Mapping)]
        limit = NOTE_LIMITS[key]
        if len(items) > limit:
            warnings.append(f"{key}: {len(items)}개 중 {limit}개만 사용")
        return items[:limit]

    terms = []
    raw_terms = data.get("terms")
    if isinstance(raw_terms, list):
        raw_terms = [
            dict(zip(("term", "definition"), item.split(":", 1))) if isinstance(item, str) and ":" in item else item
            for item in raw_terms
        ]
    for item in records(raw_terms, "terms"):
        term = _clean_text(item.get("term"))
        if term:
            terms.append({"term": term, "definition": _clean_text(item.get("definition"))})

    chapters = []
    for index, item in enumerate(records(data.get("chapters"), "chapters"), start=1):
        points = texts(item.get("points"), "points")
        title = _clean_text(item.get("title"))
        if not title and not points:
            continue
        start, end = time_range(item, f"chapters[{index}]")
        screen_notes = [
            SCREEN_NOTE_PREFIX.sub("", note).strip()
            for note in texts(item.get("screen_notes"), "screen_notes")
        ]
        chapters.append({
            "title": title or f"주제 {len(chapters) + 1}",
            "start": start,
            "end": end,
            "points": points,
            "screen_notes": [note for note in screen_notes if note],
        })
    if not chapters:
        raise ValueError("chapters가 비어 있습니다.")

    visuals = []
    for index, item in enumerate(records(data.get("visuals"), "visuals"), start=1):
        title = _clean_text(item.get("title"))
        content = texts(item.get("content"), "content")
        if not title and not content:
            continue
        visual_type = _clean_text(item.get("type"))
        if visual_type not in VISUAL_TYPES:
            visual_type = normalize_screen_type(visual_type)
        if visual_type not in VISUAL_TYPES:
            warnings.append(f"visuals[{index}]: 자료 유형이 아니어서({item.get('type')!r}) 제외")
            continue
        start, end = time_range(item, f"visuals[{index}]")
        visuals.append({
            "type": visual_type,
            "title": title or visual_type,
            "start": start,
            "end": end,
            "content": content,
            "meaning": _clean_text(item.get("meaning")),
        })

    # 모델이 강조 표현을 공지로 분류해도 화면에 "공지"로 뜨지 않게 강조 사항으로 옮깁니다.
    emphasis = texts(data.get("emphasis"), "emphasis")
    notices = []
    for notice in texts(data.get("notices"), "notices"):
        if EMPHASIS_IN_NOTICE.search(notice):
            warnings.append(f"notices: 강조 표현이라 emphasis로 옮김 ({notice[:30]})")
            if notice not in emphasis:
                emphasis.append(notice)
        else:
            notices.append(notice)

    title = _clean_text(data.get("title"))
    if not title:
        warnings.append("title이 비어 있음")
    note = {
        "title": title,
        "key_points": texts(data.get("key_points"), "key_points"),
        "terms": terms,
        "chapters": chapters,
        "visuals": visuals,
        "conclusion": texts(data.get("conclusion"), "conclusion"),
        "emphasis": emphasis[: NOTE_LIMITS["emphasis"]],
        "notices": notices,
    }
    return note, warnings


def _timeline(start: float | None, end: float | None) -> str:
    if start is None:
        return "타임라인: 확인 필요"
    return f"타임라인: {_format_range(start, end)}"


def render_note_markdown(note: Mapping[str, Any]) -> str:
    """강의 노트 JSON을 앱의 기존 마크다운 파서가 읽는 형식으로 바꿉니다(txt 저장·이전 화면 호환)."""
    lines = [f"# {note.get('title') or '강의 요약'}"]

    def section(heading: str, body: list[str]) -> None:
        if body:
            lines.extend(["", f"## {heading}", *body])

    section("핵심 주제", [f"- {point}" for point in note.get("key_points", [])])
    section("주요 용어", [
        f"- '{term['term']}': {term['definition']}" if term["definition"] else f"- '{term['term']}'"
        for term in note.get("terms", [])
    ])

    chapter_lines = []
    for index, chapter in enumerate(note.get("chapters", []), start=1):
        chapter_lines += ["", f"### {index}. {chapter['title']} ({_timeline(chapter['start'], chapter['end'])})"]
        chapter_lines += [f"- {point}" for point in chapter["points"]]
        chapter_lines += [f"- VLM 요약 자료에서는 {note_text}" for note_text in chapter["screen_notes"]]
    section("주요 내용", chapter_lines)

    visual_lines = []
    for index, visual in enumerate(note.get("visuals", []), start=1):
        visual_lines += ["", f"### {index}. {visual['title']} ({_timeline(visual['start'], visual['end'])})"]
        visual_lines.append(f"- 자료 유형: {visual['type']}")
        if visual["content"]:
            visual_lines.append("- 확인된 내용:")
            visual_lines += [f"  - {content}" for content in visual["content"]]
        if visual["meaning"]:
            visual_lines.append(f"- 강의에서의 의미: {visual['meaning']}")
    section("표/차트 기반 주요 정보", visual_lines)

    section("종합 결론", [f"- {point}" for point in note.get("conclusion", [])])
    section("강조 사항", [f"- {point}" for point in note.get("emphasis", [])])
    section("공지 사항", [f"- {notice}" for notice in note.get("notices", [])])
    return "\n".join(lines).strip() + "\n"
