import json
import os
import re
from threading import Lock
from typing import Any, Callable

from configs.inference_config import LLM_INFERENCE_CONFIG
from models.llm_loader import LLMLoader, LLMConfig
from models.claude_llm_loader import ClaudeLLMLoader, ClaudeLLMConfig

ProgressCallback = Callable[[str, int, int], None]

# 강의용 STT 요약은 개념·정의·강조 사항까지 담아 512토큰이면 뒷부분 주제가 잘립니다.
# 서버에 반영할 때는 configs/inference_config.py의 standard 프리셋 stt_max_new_tokens도 함께 올립니다.
LECTURE_STT_MAX_NEW_TOKENS = LLM_INFERENCE_CONFIG.max_new_tokens_limit
# 긴 강의를 구간별로 요약할 때 구간 하나의 생성 토큰 수입니다(구간 요약은 600자 이내로 요청).
SECTION_MAX_NEW_TOKENS = 512
# 구간 하나에 넣을 STT 분량(토큰)입니다. 약 15분 분량으로, 입력 상한이 더 커도 이보다 크게 묶지 않습니다.
# 구간이 너무 길면 600자 요약에 담기지 못하는 내용이 늘어 통합 요약의 세부 정보가 줄어듭니다.
SECTION_TARGET_TOKENS = 6000
# 다음 구간에 문맥으로 넘기는 이전 구간 요약의 끝부분과, 참고용으로 다시 보여 주는 이전 구간 STT 끝부분(글자 수)
SECTION_CONTEXT_CHARS = 600
SECTION_OVERLAP_CHARS = 300
# 토큰 수를 셀 수 없는 로더에서 쓰는 한국어 STT 토큰/글자 비율(실측 11,610자 → 8,424토큰 ≈ 0.73에 여유를 둠)
FALLBACK_TOKENS_PER_CHAR = 0.8
# 로더가 입력 토큰 상한 초과로 거부할 때 쓰는 메시지 일부입니다.
INPUT_TOO_LONG_MARKERS = ("입력이 너무 깁니다", "입력 텍스트가 너무 깁니다")
# 분량 규칙("1200자 이내")을 의식한 모델이 끝에 덧붙이는 "(총 1198자)" 같은 줄입니다.
CHAR_COUNT_LINE = re.compile(r"^\s*[(\[（]?\s*(?:총|전체)?\s*(?:글자\s*수\s*[:：]?\s*)?\d[\d,]*\s*자\s*[)\]）]?\s*$")


def strip_char_count(text: str) -> str:
    return "\n".join(line for line in str(text).splitlines() if not CHAR_COUNT_LINE.match(line)).strip()


def _build_loader():
    """LLM_BACKEND 환경변수로 로컬 모델과 Claude API 백엔드를 전환합니다."""
    backend = os.getenv("LLM_BACKEND", "local").strip().lower()

    if backend == "claude":
        model = os.getenv("CLAUDE_LLM_MODEL", "claude-haiku-4-5")
        return ClaudeLLMLoader(ClaudeLLMConfig(model=model))

    return LLMLoader(LLMConfig(device="cuda", torch_dtype="float16"))


class LLMService:
    def __init__(self, generation_lock=None, loader=None):
        self.loader = loader if loader is not None else _build_loader()
        # 전달받은 공용 lock으로 LLM/VLM의 GPU 사용을 함께 직렬화합니다.
        self._generation_lock = generation_lock or Lock()

    def unload(self) -> None:
        with self._generation_lock:
            self.loader.unload()

    def summarize_stt(
        self,
        stt_text: str,
        max_new_tokens: int = LECTURE_STT_MAX_NEW_TOKENS,
        segments: list[dict[str, Any]] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> str:
        """STT 전체를 요약합니다.

        입력 토큰 상한 안에 들면 기존처럼 한 번에 요약하고, 넘으면 STT 세그먼트를 구간으로 나눠
        구간별로 요약한 뒤 하나로 통합합니다(map-reduce). 앞부분만 잘라 쓰지 않습니다.
        """
        max_new_tokens = self._validate_max_new_tokens(max_new_tokens)
        prompt = self._stt_prompt(stt_text)
        if self._fits(prompt):
            try:
                return strip_char_count(self._generate(prompt, max_new_tokens))
            except ValueError as error:
                # 토큰 수를 어림한 로더에서 실제로는 상한을 넘은 경우에만 구간 요약으로 넘어갑니다.
                if not self._is_input_too_long(error):
                    raise
        if not segments:
            segments = self._text_to_segments(stt_text)
        return self._summarize_stt_in_sections(segments, max_new_tokens, progress_callback)

    @staticmethod
    def _stt_prompt(stt_text: str) -> str:
        return f"""
다음은 강의 영상에서 추출한 STT 음성 인식 결과입니다.

[STT 결과]
{stt_text}

위 강의 내용을 학습자가 복습할 수 있도록 한국어로 요약해줘.

[요약 조건]
1. 강의에서 다룬 개념을 강의 순서대로 정리
2. 새로 등장한 용어는 '작은따옴표'로 표시하고 강사가 설명한 정의를 함께 적기
3. 강사가 든 예시, 비유, 예제 풀이 과정은 핵심만 남기기
4. "중요하다", "시험에 나온다", "꼭 기억하라" 등 강사가 강조한 내용은 빠뜨리지 않기
5. 출석 확인, 잡담, 마이크·장비 점검, 반복 설명은 제거
6. STT 오류로 보이는 전문 용어는 문맥상 명확할 때만 보정
7. 원문에 없는 설명, 예시, 수치는 추가하지 않기
8. 전체 1200자 이내로 작성하고, 강의가 길면 예시를 줄이더라도 다룬 주제는 끝까지 빠뜨리지 않기 (글자 수는 출력하지 않기)
9. 강조 사항과 공지를 구분하기: 공지는 과제 제출, 시험 일정, 다음 수업 안내 같은 일정·행정 안내만 해당하고,
   "시험에 나온다", "중요하다"처럼 내용을 강조한 말은 강조 사항에 적기

[출력 형식]
## 강의 요약

### 학습 주제
-

### 핵심 개념
- '용어': 설명

### 강의 흐름
-

### 강조 사항
- (강사가 강조한 내용이 없으면 "없음")

### 공지
- (과제 제출·시험 일정·다음 수업 안내가 없으면 "없음")
"""

    # ------------------------------------------------------------ 긴 강의: 구간별 요약 후 통합

    def _summarize_stt_in_sections(
        self,
        segments: list[dict[str, Any]],
        max_new_tokens: int,
        progress_callback: ProgressCallback | None,
    ) -> str:
        pending = self._split_for_sections(segments)
        sections = []
        previous_chunk, previous_summary = [], ""
        while pending:
            chunk = pending.pop(0)
            index, total = len(sections) + 1, len(sections) + 1 + len(pending)
            if progress_callback:
                progress_callback("stt_sections", index, total + 1)
            overlap = self._overlap_segments(previous_chunk) if previous_chunk else []
            prompt = self._section_prompt(chunk, overlap, previous_summary, index, total)
            try:
                summary = strip_char_count(self._generate(prompt, SECTION_MAX_NEW_TOKENS))
            except ValueError as error:
                # 토큰 수를 어림한 로더에서 구간이 실제 상한을 넘으면 그 구간만 반으로 나눠 다시 요약합니다.
                if not self._is_input_too_long(error) or not self._can_split(chunk):
                    raise
                pending[:0] = self._halves(chunk)
                continue
            sections.append({"start": chunk[0].get("start"), "end": chunk[-1].get("end"), "summary": summary})
            previous_chunk, previous_summary = chunk, summary
        if progress_callback:
            progress_callback("stt_reduce", len(sections) + 1, len(sections) + 1)
        return strip_char_count(self._reduce_sections(sections, max_new_tokens))

    def _reduce_sections(self, sections: list[dict[str, Any]], max_new_tokens: int) -> str:
        prompt = self._reduce_prompt(sections)
        if len(sections) == 1 or self._fits(prompt):
            return self._generate(prompt, max_new_tokens)
        # 구간이 많아 한 번에 통합할 수 없으면 인접 구간끼리 먼저 합친 뒤 다시 통합합니다.
        merged = []
        for group in self._pack_sections(sections):
            if len(group) == 1:
                merged.append(group[0])
                continue
            summary = strip_char_count(self._generate(self._merge_prompt(group), SECTION_MAX_NEW_TOKENS))
            merged.append({"start": group[0]["start"], "end": group[-1]["end"], "summary": summary})
        return self._reduce_sections(merged, max_new_tokens)

    def _pack_sections(self, sections: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """중간 통합 프롬프트가 입력 상한에 드는 만큼 인접 구간을 묶습니다(한 묶음에 최소 2개)."""
        groups, current = [], []
        for section in sections:
            if len(current) >= 2 and not self._fits(self._merge_prompt([*current, section])):
                groups.append(current)
                current = []
            current.append(section)
        if current:
            if len(current) == 1 and groups:
                groups[-1].append(current[0])
            else:
                groups.append(current)
        return groups

    def _split_for_sections(self, segments: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """구간 프롬프트가 입력 상한에 들도록 세그먼트를 자르지 않고 묶습니다.

        중요 구간 추출과 같은 split_segments로 먼저 묶고, 실제 토큰 수가 넘는 묶음만 반으로 더 나눕니다.
        """
        limit = self._input_limit()
        # 실제 구간 프롬프트에 붙는 문맥의 최대 크기로 검사합니다.
        worst_context = "가" * SECTION_CONTEXT_CHARS
        # 이전 구간 STT 끝부분은 본문 300자 이내지만 줄마다 [분:초]가 붙으므로 여유를 둡니다.
        worst_overlap = [{"start": 0, "text": "가" * (SECTION_OVERLAP_CHARS + 100)}]
        overhead = self._count_tokens(self._section_prompt([], worst_overlap, worst_context, 1, 1))
        budget = (limit or 16000) - overhead
        if budget < 500:
            raise ValueError(f"입력 토큰 상한({limit})이 너무 작아 구간 요약을 할 수 없습니다.")
        # split_segments는 세그먼트의 JSON 직렬화 길이로 묶으므로, 프롬프트에 들어가는 형식([분:초] 내용 줄)의
        # 토큰 수를 그 길이 기준으로 환산합니다. 짧은 세그먼트가 많으면 시각 표기만으로도 토큰이 크게 늡니다.
        sample_tokens = self._count_tokens(self._segment_lines(segments))
        json_chars = sum(len(json.dumps(segment, ensure_ascii=False)) for segment in segments)
        tokens_per_json_char = sample_tokens / max(json_chars, 1)
        chunk_chars = max(500, int(min(budget, SECTION_TARGET_TOKENS) / max(tokens_per_json_char, 0.01)))

        def fit(chunk: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
            if self._fits(self._section_prompt(chunk, worst_overlap, worst_context, 1, 1)) or not self._can_split(chunk):
                return [chunk]
            return [part for half in self._halves(chunk) for part in fit(half)]

        return [part for chunk in self.split_segments(segments, chunk_chars) for part in fit(chunk)]

    @staticmethod
    def _can_split(chunk: list[dict[str, Any]]) -> bool:
        return len(chunk) > 1 or len(str(chunk[0].get("text", ""))) >= 2

    @staticmethod
    def _halves(chunk: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """묶음을 세그먼트 단위로 반으로 나눕니다. 세그먼트 하나뿐이면 텍스트를 공백 경계에서 나눕니다."""
        if len(chunk) > 1:
            middle = len(chunk) // 2
            return [chunk[:middle], chunk[middle:]]
        segment = chunk[0]
        text = str(segment.get("text", ""))
        middle = len(text) // 2
        cut = text.rfind(" ", 0, middle)
        cut = cut if cut > 0 else middle
        return [[{**segment, "text": text[:cut]}], [{**segment, "text": text[cut:]}]]

    @staticmethod
    def _overlap_segments(previous_chunk: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """이전 구간 끝부분 세그먼트(SECTION_OVERLAP_CHARS 이내)를 경계 문맥으로 돌려줍니다."""
        overlap, chars = [], 0
        for segment in reversed(previous_chunk):
            chars += len(str(segment.get("text", "")))
            if overlap and chars > SECTION_OVERLAP_CHARS:
                break
            overlap.insert(0, segment)
        if overlap and len(str(overlap[0].get("text", ""))) > SECTION_OVERLAP_CHARS:
            text = str(overlap[0].get("text", ""))
            overlap[0] = {**overlap[0], "text": text[-SECTION_OVERLAP_CHARS:]}
        return overlap

    @staticmethod
    def _text_to_segments(text: str, piece_chars: int = 400) -> list[dict[str, Any]]:
        """세그먼트 없이 전체 텍스트만 온 요청을 공백 경계로 나눠 시간 없는 세그먼트로 만듭니다."""
        words, pieces, current = text.split(), [], ""
        for word in words:
            if current and len(current) + len(word) + 1 > piece_chars:
                pieces.append(current)
                current = ""
            current = f"{current} {word}".strip()
        if current:
            pieces.append(current)
        return [{"segment_id": index, "start": None, "end": None, "text": piece}
                for index, piece in enumerate(pieces)]

    @staticmethod
    def _format_time(seconds: Any) -> str:
        try:
            total = int(float(seconds))
        except (TypeError, ValueError):
            return "--:--"
        hours, rest = divmod(total, 3600)
        minutes, secs = divmod(rest, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"

    @classmethod
    def _segment_lines(cls, segments: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"[{cls._format_time(segment.get('start'))}] {str(segment.get('text', '')).strip()}"
            for segment in segments
        )

    @classmethod
    def _range_text(cls, start: Any, end: Any) -> str:
        return f"{cls._format_time(start)}~{cls._format_time(end)}"

    @classmethod
    def _section_prompt(
        cls,
        chunk: list[dict[str, Any]],
        overlap: list[dict[str, Any]],
        previous_summary: str,
        index: int,
        total: int,
    ) -> str:
        time_range = cls._range_text(chunk[0].get("start"), chunk[-1].get("end")) if chunk else ""
        context = previous_summary.strip()[-SECTION_CONTEXT_CHARS:] if previous_summary.strip() else "없음 (첫 구간)"
        overlap_text = cls._segment_lines(overlap) if overlap else "없음"
        return f"""
다음은 한 강의 영상의 STT를 시간 순서대로 나눈 {total}개 구간 중 {index}번째 구간({time_range})입니다.

[이전 구간 요약 끝부분 (참고용, 다시 정리하지 말 것)]
{context}

[이전 구간 STT 끝부분 (참고용, 다시 정리하지 말 것)]
{overlap_text}

[이번 구간 STT: [시작 시각] 내용]
{cls._segment_lines(chunk)}

이번 구간의 내용만 학습자가 복습할 수 있도록 한국어로 정리해줘.

[정리 조건]
1. 이번 구간에서 다룬 개념을 순서대로 적고, 각 항목 앞에 시작 시각을 [분:초] 형식으로 붙이기
2. 새로 등장한 용어는 '작은따옴표'로 표시하고 강사가 설명한 정의를 함께 적기
3. 이전 구간에서 이어지는 설명이면 "(앞 구간에서 이어짐)"이라고만 표시하고 이전 내용은 반복하지 않기
4. "중요하다", "시험에 나온다", "꼭 기억하라" 등 강사가 강조한 내용은 빠뜨리지 않기
5. 공지는 과제 제출, 시험 일정, 다음 수업 안내 같은 일정·행정 안내만 해당
6. 출석 확인, 잡담, 마이크·장비 점검, 반복 설명은 제거하고, 원문에 없는 설명·예시·수치는 추가하지 않기
7. STT 오류로 보이는 전문 용어는 문맥상 명확할 때만 보정
8. 600자 이내로 작성하기 (글자 수는 출력하지 않기)

[출력 형식]
### 주제
-

### 내용
- [분:초] '용어': 설명

### 강조 사항
- (강사가 강조한 내용이 없으면 "없음")

### 공지
- (없으면 "없음")
"""

    @classmethod
    def _sections_text(cls, sections: list[dict[str, Any]]) -> str:
        return "\n\n".join(
            f"#### 구간 {index} ({cls._range_text(section['start'], section['end'])})\n{section['summary'].strip()}"
            for index, section in enumerate(sections, start=1)
        )

    @classmethod
    def _merge_prompt(cls, sections: list[dict[str, Any]]) -> str:
        return f"""
다음은 한 강의의 연속된 구간별 요약입니다.

{cls._sections_text(sections)}

위 구간들을 하나의 구간 요약으로 합쳐줘.

[합치기 조건]
1. 시간 순서를 유지하고, 각 항목 앞의 [분:초] 시각을 그대로 두기
2. 여러 구간에 반복된 개념·설명은 처음 나온 시각 기준으로 한 번만 적기
3. 용어 정의, 강조 사항, 공지는 빠뜨리지 않기
4. 구간 요약에 없는 내용은 추가하지 않기
5. 800자 이내로 작성하기 (글자 수는 출력하지 않기)

[출력 형식]
### 주제
-

### 내용
- [분:초] '용어': 설명

### 강조 사항
- (없으면 "없음")

### 공지
- (없으면 "없음")
"""

    @classmethod
    def _reduce_prompt(cls, sections: list[dict[str, Any]]) -> str:
        return f"""
다음은 한 강의 영상의 STT를 시간 순서대로 나눠 구간별로 정리한 요약입니다.

{cls._sections_text(sections)}

위 구간별 요약을 하나의 강의 요약으로 통합해줘. 학습자가 복습할 수 있도록 한국어로 작성해.

[통합 조건]
1. 강의 순서를 유지하고, 모든 구간의 주제를 끝까지 빠뜨리지 않기
2. 여러 구간에 반복된 개념·설명은 처음 나온 시각 기준으로 한 번만 적기
3. 새로 등장한 용어는 '작은따옴표'로 표시하고 정의를 함께 적기
4. 강사가 강조한 내용은 모두 남기기
5. 강조 사항과 공지를 구분하기: 공지는 과제 제출, 시험 일정, 다음 수업 안내 같은 일정·행정 안내만 해당하고,
   "시험에 나온다", "중요하다"처럼 내용을 강조한 말은 강조 사항에 적기
6. 강의 흐름의 각 항목 앞에는 해당 내용의 시작 시각을 [분:초] 형식으로 적기
7. 구간 요약에 없는 설명, 예시, 수치는 추가하지 않기
8. 전체 1200자 이내로 작성하고, 강의가 길면 예시를 줄이더라도 다룬 주제는 끝까지 빠뜨리지 않기 (글자 수는 출력하지 않기)

[출력 형식]
## 강의 요약

### 학습 주제
-

### 핵심 개념
- '용어': 설명

### 강의 흐름
- [분:초]

### 강조 사항
- (강사가 강조한 내용이 없으면 "없음")

### 공지
- (과제 제출·시험 일정·다음 수업 안내가 없으면 "없음")
"""

    # ------------------------------------------------------------ 입력 토큰 확인

    def _input_limit(self) -> int | None:
        """로더의 입력 토큰 상한입니다. 상한이 없는 백엔드(Claude API 등)는 None입니다."""
        return getattr(self.loader, "max_input_tokens", None)

    def _count_tokens(self, prompt: str) -> int:
        counter = getattr(self.loader, "count_prompt_tokens", None)
        count = counter(prompt) if counter else None
        return count if count is not None else int(len(prompt) * FALLBACK_TOKENS_PER_CHAR)

    def _fits(self, prompt: str) -> bool:
        limit = self._input_limit()
        return limit is None or self._count_tokens(prompt) <= limit

    @staticmethod
    def _is_input_too_long(error: Exception) -> bool:
        return any(marker in str(error) for marker in INPUT_TOO_LONG_MARKERS)

    def _generate(self, prompt: str, max_new_tokens: int) -> str:
        with self._generation_lock:
            return self.loader.generate(prompt=prompt, max_new_tokens=max_new_tokens)

    def extract_important_segments(
        self,
        stt_segments: list[dict[str, Any]],
        stt_summary: str = "",
        max_new_tokens: int = LLM_INFERENCE_CONFIG.default_max_new_tokens,
        max_segments: int = 5,
    ) -> str:
        # JSON보다 짧은 행 형식으로 전달해 긴 프롬프트의 추론 비용을 줄입니다.
        segments_text = "\n".join(
            f"{segment.get('segment_id')}|{segment.get('start')}|"
            f"{segment.get('end')}|{str(segment.get('text', '')).strip()}"
            for segment in stt_segments
        )
        prompt = f"""
다음은 강의 영상의 타임스탬프가 포함된 STT 구간과 STT 요약입니다.

[STT 구간 형식: segment_id|start|end|text]
{segments_text}

[STT 요약]
{stt_summary}

위 내용을 바탕으로 강의 화면(슬라이드, 판서, 코드, 도표)을 함께 분석해야 할 중요 구간을 추출해줘.

[추출 기준]
1. 새로운 개념이나 용어가 처음 정의되는 구간
2. "여기 보시면", "이 그래프에서", "화면에", "이 식은"처럼 화면을 가리키는 말이 나오는 구간
3. 수식 유도, 코드 설명, 예제 풀이가 진행되는 구간
4. 강사가 중요하다고 강조하거나 내용을 정리·요약하는 구간
5. 출석, 잡담, 장비 점검, 단순 반복 설명은 제외
6. start와 end는 반드시 입력 구간에 존재하는 숫자 값을 사용
7. 선택한 구간을 대표하는 segment_id 하나를 사용
8. 각 입력 묶음에서 가장 중요한 구간을 최대 {max_segments}개만 선택

[출력 형식]
각 구간을 아래 형식의 한 줄로만 출력해줘. 설명, 번호, Markdown은 출력하지 마.
segment_id|start|end|topic|reason

예시:
7|12.5|18.0|경사하강법 정의|슬라이드의 갱신식을 가리키며 개념을 정의하는 구간

topic과 reason 안에는 | 문자를 사용하지 마.
"""

        with self._generation_lock:
            return self.loader.generate(
                prompt=prompt,
                max_new_tokens=self._validate_max_new_tokens(max_new_tokens),
            )

    def extract_important_segments_in_chunks(
        self,
        stt_segments: list[dict[str, Any]],
        stt_summary: str = "",
        max_new_tokens: int = 384,
        max_segments: int = 5,
        max_chunk_chars: int = LLM_INFERENCE_CONFIG.segment_chunk_chars,
        progress_callback: ProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        """STT 구간을 나눠 중요 구간을 추출하고 객체 배열로 합칩니다."""
        chunks = self.split_segments(stt_segments, max_chunk_chars)
        important_segments = []

        for index, chunk in enumerate(chunks, start=1):
            if progress_callback:
                progress_callback("important_segments", index, len(chunks))
            raw_result = self.extract_important_segments(
                stt_segments=chunk,
                stt_summary=stt_summary,
                max_new_tokens=max_new_tokens,
                max_segments=max_segments,
            )
            try:
                # 모델이 지시보다 많이 고르면 앞쪽 max_segments개만 씁니다.
                parsed = self._parse_important_segments(raw_result)[:max_segments]
                important_segments.extend(self._align_to_input(parsed, chunk))
            except ValueError as error:
                # 형식 오류가 난 묶음은 건너뛰고 나머지 정상 결과를 반환합니다.
                print(f"[중요 구간 파싱 실패] chunk={index}: {error}")

        return important_segments

    @staticmethod
    def _align_to_input(
        parsed_segments: list[dict[str, Any]],
        chunk: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """모델이 쓴 시간을 입력 구간 기준으로 바로잡습니다.

        모델은 segment_id를 시간으로 착각하는 등 없는 시간을 쓰기도 합니다.
        start·end가 모두 입력 구간의 경계값이고 대표 segment_id 구간을 포함하면 그 범위를 유지하고,
        아니면 segment_id 구간의 실제 시간으로 바꿉니다. 묶음에 없는 segment_id는 버립니다.
        """
        by_id = {}
        for segment in chunk:
            try:
                by_id[int(segment.get("segment_id"))] = segment
            except (TypeError, ValueError):
                continue
        starts = {float(segment["start"]) for segment in by_id.values()}
        ends = {float(segment["end"]) for segment in by_id.values()}

        aligned = []
        for item in parsed_segments:
            source = by_id.get(item["segment_id"])
            if source is None:
                print(f"[중요 구간 제외] 입력에 없는 segment_id={item['segment_id']}")
                continue
            source_start, source_end = float(source["start"]), float(source["end"])
            start, end = item["start"], item["end"]
            if not (start in starts and end in ends and start <= source_start and source_end <= end):
                start, end = source_start, source_end
            aligned.append({**item, "start": start, "end": end})
        return aligned

    @staticmethod
    def split_segments(
        stt_segments: list[dict[str, Any]],
        max_chunk_chars: int,
    ) -> list[list[dict[str, Any]]]:
        """세그먼트를 자르지 않고 직렬화 길이를 기준으로 묶습니다."""
        if max_chunk_chars < 1:
            raise ValueError("max_chunk_chars는 1 이상이어야 합니다.")

        chunks = []
        current_chunk = []
        current_chars = 0

        for segment in stt_segments:
            segment_chars = len(json.dumps(segment, ensure_ascii=False))
            if current_chunk and current_chars + segment_chars > max_chunk_chars:
                chunks.append(current_chunk)
                current_chunk = []
                current_chars = 0

            current_chunk.append(segment)
            current_chars += segment_chars

        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    @staticmethod
    def _parse_important_segments(raw_result: str) -> list[dict[str, Any]]:
        cleaned_result = raw_result.strip()
        if cleaned_result.startswith("```"):
            lines = cleaned_result.splitlines()
            cleaned_result = "\n".join(lines[1:-1]).strip()

        parsed_segments = []
        for line in cleaned_result.splitlines():
            line = line.strip().lstrip("- ")
            if not line or line.lower().startswith("segment_id|"):
                continue

            fields = [field.strip() for field in line.split("|", maxsplit=4)]
            if len(fields) != 5:
                continue

            try:
                segment_id = int(fields[0])
                start = float(fields[1])
                end = float(fields[2])
            except ValueError:
                continue

            parsed_segments.append(
                {
                    "segment_id": segment_id,
                    "start": start,
                    "end": end,
                    "topic": fields[3],
                    "reason": fields[4],
                }
            )

        if not parsed_segments:
            raise ValueError("중요 구간 행 형식을 해석할 수 없습니다.")
        return parsed_segments

    @staticmethod
    def _validate_max_new_tokens(max_new_tokens: int) -> int:
        if not 1 <= max_new_tokens <= LLM_INFERENCE_CONFIG.max_new_tokens_limit:
            raise ValueError(
                "max_new_tokens는 1 이상 "
                f"{LLM_INFERENCE_CONFIG.max_new_tokens_limit} 이하여야 합니다."
            )
        return max_new_tokens
