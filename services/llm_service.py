import json
from threading import Lock
from typing import Any, Callable

from models.llm_loader import LLMLoader, LLMConfig

DEFAULT_MAX_NEW_TOKENS = 1024
MAX_NEW_TOKENS = 2048
DEFAULT_SEGMENT_CHUNK_CHARS = 12000

ProgressCallback = Callable[[str, int, int], None]


class LLMService:
    def __init__(self, generation_lock=None):
        config = LLMConfig(
            device="cuda",
            torch_dtype="float16",
        )
        self.loader = LLMLoader(config)
        # 전달받은 공용 lock으로 LLM/VLM의 GPU 사용을 함께 직렬화합니다.
        self._generation_lock = generation_lock or Lock()

    def unload(self) -> None:
        with self._generation_lock:
            self.loader.unload()

    def summarize_stt(
        self,
        stt_text: str,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    ) -> str:
        prompt = f"""
다음은 영상에서 추출한 STT 음성 인식 결과입니다.

[STT 결과]
{stt_text}

위 내용을 바탕으로 한국어로 요약해줘.

[요약 조건]
1. 핵심 내용을 주제별로 정리
2. 불필요한 반복 표현 제거
3. STT 오류로 보이는 문장은 자연스럽게 보정
4. 원문에 없는 내용은 추가하지 않기
5. 영상의 흐름을 유지해서 정리

[출력 형식]
## STT 요약

### 핵심 주제
- 

### 주요 내용
- 

### 전체 요약
-
"""

        with self._generation_lock:
            return self.loader.generate(
                prompt=prompt,
                max_new_tokens=self._validate_max_new_tokens(max_new_tokens),
                temperature=0.3,
                top_p=0.9,
            )

    def extract_important_segments(
        self,
        stt_segments: list[dict[str, Any]],
        stt_summary: str = "",
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    ) -> str:
        # JSON보다 짧은 행 형식으로 전달해 긴 프롬프트의 추론 비용을 줄입니다.
        segments_text = "\n".join(
            f"{segment.get('segment_id')}|{segment.get('start')}|"
            f"{segment.get('end')}|{str(segment.get('text', '')).strip()}"
            for segment in stt_segments
        )
        prompt = f"""
다음은 영상의 타임스탬프가 포함된 STT 구간과 STT 요약입니다.

[STT 구간 형식: segment_id|start|end|text]
{segments_text}

[STT 요약]
{stt_summary}

위 내용을 바탕으로 OCR/VLM 분석에 사용할 중요한 영상 구간을 추출해줘.

[추출 기준]
1. 핵심 주제가 처음 등장하는 구간
2. 설명이 집중되는 구간
3. 발표 자료, 표, 화면 공유가 나올 가능성이 높은 구간
4. 결론이나 중요한 의사결정이 나오는 구간
5. 단순 잡담이나 반복 설명은 제외
6. start와 end는 반드시 입력 구간에 존재하는 숫자 값을 사용
7. 선택한 구간을 대표하는 segment_id 하나를 사용
8. 각 입력 묶음에서 가장 중요한 구간을 최대 3개만 선택

[출력 형식]
각 구간을 아래 형식의 한 줄로만 출력해줘. 설명, 번호, Markdown은 출력하지 마.
segment_id|start|end|topic|reason

예시:
7|12.5|18.0|연구 결과|핵심 연구 결과가 설명되는 구간

topic과 reason 안에는 | 문자를 사용하지 마.
"""

        with self._generation_lock:
            return self.loader.generate(
                prompt=prompt,
                max_new_tokens=self._validate_max_new_tokens(max_new_tokens),
                temperature=0.2,
                top_p=0.9,
            )

    def extract_important_segments_in_chunks(
        self,
        stt_segments: list[dict[str, Any]],
        stt_summary: str = "",
        max_new_tokens: int = 256,
        max_chunk_chars: int = DEFAULT_SEGMENT_CHUNK_CHARS,
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
                    self._parse_important_segments(raw_result)
                )
            except ValueError as error:
                # 형식 오류가 난 묶음은 건너뛰고 나머지 정상 결과를 반환합니다.
                print(f"[중요 구간 파싱 실패] chunk={index}: {error}")

        return important_segments

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
        if not 1 <= max_new_tokens <= MAX_NEW_TOKENS:
            raise ValueError(
                f"max_new_tokens는 1 이상 {MAX_NEW_TOKENS} 이하여야 합니다."
            )
        return max_new_tokens
