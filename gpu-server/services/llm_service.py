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
    ) -> str:
        prompt = f"""
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

        with self._generation_lock:
            summary = self.loader.generate(
                prompt=prompt,
                max_new_tokens=self._validate_max_new_tokens(max_new_tokens),
            )
        return strip_char_count(summary)

    def extract_important_segments(
        self,
        stt_segments: list[dict[str, Any]],
        stt_summary: str = "",
        max_new_tokens: int = LLM_INFERENCE_CONFIG.default_max_new_tokens,
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
8. 각 입력 묶음에서 가장 중요한 구간을 최대 3개만 선택

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
        max_new_tokens: int = 256,
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
            )
            try:
                important_segments.extend(
                    self._align_to_input(self._parse_important_segments(raw_result), chunk)
                )
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
