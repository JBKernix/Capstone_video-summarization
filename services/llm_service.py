from models.llm_loader import LLMLoader, LLMConfig


class LLMService:
    def __init__(self):
        config = LLMConfig(
            device="cuda",
            torch_dtype="float16",
        )
        self.loader = LLMLoader(config)

    def summarize_stt(self, stt_text: str) -> str:
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

        return self.loader.generate(
            prompt=prompt,
            max_new_tokens=1024,
            temperature=0.3,
            top_p=0.9,
        )

    def extract_important_segments(self, stt_text: str, stt_summary: str = "") -> str:
        prompt = f"""
다음은 영상의 STT 원문과 STT 요약입니다.

[STT 원문]
{stt_text}

[STT 요약]
{stt_summary}

위 내용을 바탕으로 OCR/VLM 분석에 사용할 중요한 영상 구간을 추출해줘.

[추출 기준]
1. 핵심 주제가 처음 등장하는 구간
2. 설명이 집중되는 구간
3. 발표 자료, 표, 화면 공유가 나올 가능성이 높은 구간
4. 결론이나 중요한 의사결정이 나오는 구간
5. 단순 잡담이나 반복 설명은 제외

[출력 형식]
반드시 JSON 배열 형식으로만 출력해줘.

[
  {{
    "start_time": "00:00:00",
    "end_time": "00:00:00",
    "topic": "구간 주제",
    "reason": "이 구간을 선택한 이유"
  }}
]
"""

        return self.loader.generate(
            prompt=prompt,
            max_new_tokens=1024,
            temperature=0.2,
            top_p=0.9,
        )