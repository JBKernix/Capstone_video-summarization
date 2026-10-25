"""입력 토큰 상한을 넘는 긴 강의의 STT 구간 요약(map-reduce) 테스트입니다. GPU 없이 가짜 로더로 실행합니다."""
import re

import pytest

try:
    # 서비스 모듈은 모델 로더(transformers)를 함께 불러옵니다. 앱 환경처럼 없으면 건너뜁니다.
    from services.llm_service import SECTION_MAX_NEW_TOKENS, LLMService
except ImportError:
    LLMService = None

pytestmark = pytest.mark.skipif(LLMService is None, reason="transformers가 있는 서버 환경에서 실행")


class CountingLoader:
    """글자 수를 토큰 수로 보고 상한을 강제하는 가짜 로더입니다(실제 로더처럼 넘으면 ValueError)."""

    def __init__(self, max_input_tokens, count=True):
        self.max_input_tokens = max_input_tokens
        self.calls = []
        if not count:
            self.count_prompt_tokens = lambda prompt: None

    def count_prompt_tokens(self, prompt):
        return len(prompt)

    def generate(self, prompt, max_new_tokens):
        if len(prompt) > self.max_input_tokens:
            raise ValueError(f"입력이 너무 깁니다: {len(prompt)} tokens (최대 {self.max_input_tokens}).")
        self.calls.append((prompt, max_new_tokens))
        if "구간 중" in prompt:
            first = re.search(r"\[이번 구간 STT: \[시작 시각\] 내용\]\n\[([0-9:\-]+)\] (\S+)", prompt)
            return f"### 주제\n- {first.group(2)}\n### 내용\n- [{first.group(1)}] 설명"
        if "하나의 구간 요약으로 합쳐줘" in prompt:
            return "### 주제\n- 합친 구간\n### 내용\n- [00:00] 합침"
        return "## 강의 요약\n### 학습 주제\n- 통합"


def lecture(segment_count, words_per_segment=20):
    return [
        {"segment_id": i, "start": i * 10.0, "end": i * 10.0 + 9.5,
         "text": " ".join(f"주제{i}" for _ in range(words_per_segment))}
        for i in range(segment_count)
    ]


def section_prompts(loader):
    return [prompt for prompt, _ in loader.calls if "구간 중" in prompt]


def test_short_input_keeps_single_pass_prompt():
    loader = CountingLoader(max_input_tokens=100_000)
    segments = lecture(5)
    text = " ".join(s["text"] for s in segments)
    LLMService(loader=loader).summarize_stt(text, segments=segments)
    assert len(loader.calls) == 1
    assert loader.calls[0][0] == LLMService._stt_prompt(text)


def test_long_input_is_split_by_segments_without_dropping_any():
    loader = CountingLoader(max_input_tokens=4000)
    segments = lecture(120)
    text = " ".join(s["text"] for s in segments)
    progress = []
    summary = LLMService(loader=loader).summarize_stt(
        text, segments=segments, progress_callback=lambda *args: progress.append(args))

    prompts = section_prompts(loader)
    assert len(prompts) > 1
    assert all(len(prompt) <= 4000 for prompt, _ in loader.calls)
    assert all(tokens == SECTION_MAX_NEW_TOKENS for prompt, tokens in loader.calls if "구간 중" in prompt)
    # 모든 세그먼트가 어느 한 구간의 '이번 구간' 본문에 정확히 한 번씩 들어갑니다(앞부분만 쓰지 않음).
    bodies = "\n".join(p.split("[이번 구간 STT: [시작 시각] 내용]")[1].split("이번 구간의 내용만")[0] for p in prompts)
    for segment in segments:
        assert bodies.count(f"주제{segment['segment_id']} ") >= 1
        assert bodies.count(f"[{LLMService._format_time(segment['start'])}] 주제{segment['segment_id']} ") == 1
    assert summary == "## 강의 요약\n### 학습 주제\n- 통합"
    # 진행률: 구간 1..n 다음 통합 단계
    assert [p[0] for p in progress] == ["stt_sections"] * len(prompts) + ["stt_reduce"]
    assert progress[-1][1] == progress[-1][2] == len(prompts) + 1


def test_sections_carry_previous_summary_and_boundary_overlap():
    loader = CountingLoader(max_input_tokens=4000)
    segments = lecture(60)
    LLMService(loader=loader).summarize_stt(" ".join(s["text"] for s in segments), segments=segments)
    prompts = section_prompts(loader)
    assert "없음 (첫 구간)" in prompts[0]
    second = prompts[1]
    # 이전 구간 요약(가짜 로더가 첫 세그먼트 단어를 주제로 돌려줌)과 이전 구간 끝 세그먼트가 문맥으로 들어갑니다.
    assert "- 주제0" in second.split("[이전 구간 STT 끝부분")[0]
    overlap = second.split("[이전 구간 STT 끝부분 (참고용, 다시 정리하지 말 것)]")[1].split("[이번 구간 STT")[0]
    first_body = prompts[0].split("[이번 구간 STT: [시작 시각] 내용]")[1]
    last_line = [line for line in first_body.splitlines() if re.match(r"\[\d\d:\d\d\] ", line)][-1]
    assert last_line in overlap


def test_reduce_prompt_keeps_time_ranges_and_dedup_rule():
    loader = CountingLoader(max_input_tokens=4000)
    segments = lecture(60)
    LLMService(loader=loader).summarize_stt(" ".join(s["text"] for s in segments), segments=segments)
    reduce_prompt = loader.calls[-1][0]
    assert "#### 구간 1 (00:00~" in reduce_prompt
    assert "한 번만 적기" in reduce_prompt and "## 강의 요약" in reduce_prompt


def test_many_sections_are_merged_hierarchically_until_they_fit():
    loader = CountingLoader(max_input_tokens=2600)
    segments = lecture(400, words_per_segment=10)
    LLMService(loader=loader).summarize_stt(" ".join(s["text"] for s in segments), segments=segments)
    assert any("하나의 구간 요약으로 합쳐줘" in prompt for prompt, _ in loader.calls)
    assert loader.calls[-1][0].count("#### 구간") >= 1
    assert all(len(prompt) <= 2600 for prompt, _ in loader.calls)


def test_sections_stay_near_target_size_even_with_large_limit():
    # 상한(5만)이 커도 구간 하나의 STT 본문은 SECTION_TARGET_TOKENS 근처로 묶습니다(JSON 오버헤드와 무관).
    from services.llm_service import SECTION_TARGET_TOKENS

    loader = CountingLoader(max_input_tokens=50_000)
    segments = lecture(800, words_per_segment=12)
    text = " ".join(s["text"] for s in segments)
    assert len(LLMService._stt_prompt(text)) > 50_000
    LLMService(loader=loader).summarize_stt(text, segments=segments)
    bodies = [p.split("[이번 구간 STT: [시작 시각] 내용]")[1].split("이번 구간의 내용만")[0]
              for p in section_prompts(loader)]
    assert len(bodies) >= len(text) // SECTION_TARGET_TOKENS
    assert all(len(body) <= SECTION_TARGET_TOKENS * 1.3 for body in bodies)


def test_text_without_segments_and_without_token_counter_still_succeeds():
    # count_prompt_tokens가 None이면 글자 수로 어림하고, 실제 거부가 나도 구간 요약으로 넘어갑니다.
    loader = CountingLoader(max_input_tokens=3000, count=False)
    text = " ".join(f"단어{i}" for i in range(3000))
    summary = LLMService(loader=loader).summarize_stt(text)
    assert summary.startswith("## 강의 요약")
    assert len(section_prompts(loader)) > 1
    assert "[--:--]" in section_prompts(loader)[0]


def test_single_huge_segment_is_split_instead_of_failing():
    loader = CountingLoader(max_input_tokens=3000)
    segments = [{"segment_id": 0, "start": 0.0, "end": 600.0, "text": " ".join(["긴문장"] * 2000)}]
    LLMService(loader=loader).summarize_stt(segments[0]["text"], segments=segments)
    assert len(section_prompts(loader)) > 1


def test_other_errors_are_not_swallowed():
    class Broken(CountingLoader):
        def generate(self, prompt, max_new_tokens):
            raise ValueError("GPU 메모리가 부족합니다")

    with pytest.raises(ValueError, match="GPU 메모리"):
        LLMService(loader=Broken(max_input_tokens=100_000)).summarize_stt("짧은 강의")


def test_backend_without_limit_always_uses_single_pass():
    class Unlimited:
        def __init__(self):
            self.prompts = []

        def generate(self, prompt, max_new_tokens):
            self.prompts.append(prompt)
            return "요약"

    loader = Unlimited()
    LLMService(loader=loader).summarize_stt("가 " * 50_000, segments=lecture(500))
    assert len(loader.prompts) == 1
