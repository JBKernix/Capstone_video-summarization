import pytest

try:
    # 서비스 모듈은 모델 로더(transformers)를 함께 불러옵니다. 앱 환경처럼 없으면 건너뜁니다.
    from services.final_service import normalize_lecture_note, render_note_markdown
    from services.llm_service import LLMService, strip_char_count
except ImportError:
    LLMService = None

pytestmark = pytest.mark.skipif(LLMService is None, reason="transformers가 있는 서버 환경에서 실행")
CHAPTER = {"title": "개요", "start": 0, "end": 60, "points": ["설명"], "screen_notes": []}


class FakeLoader:
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def generate(self, prompt, max_new_tokens):
        self.prompts.append(prompt)
        return self.answer


def test_stt_summary_separates_emphasis_and_drops_char_count():
    loader = FakeLoader("## 강의 요약\n### 강조 사항\n- 시험에 나온다\n### 공지\n- 없음\n(총 1198자)")
    summary = LLMService(loader=loader).summarize_stt("강의 내용")
    assert summary.endswith("- 없음")
    assert "### 강조 사항\n" in loader.prompts[0] and "### 공지\n" in loader.prompts[0]
    assert "글자 수는 출력하지 않기" in loader.prompts[0]
    assert strip_char_count("- 100자 이내로 요약") == "- 100자 이내로 요약"


def test_visuals_keep_board_and_drop_non_material():
    note, _ = normalize_lecture_note({"chapters": [CHAPTER], "visuals": [
        {"type": "판서", "title": "제1법칙", "start": 10, "end": None, "content": ["Q = W + ΔU"], "meaning": ""},
        {"type": "기타", "title": "방송 로고", "start": 20, "end": None, "content": ["YTN"], "meaning": ""},
    ]}, known_times=[0, 60])
    assert [(v["type"], v["title"]) for v in note["visuals"]] == [("판서", "제1법칙")]


def test_emphasis_is_separated_from_notices():
    note, _ = normalize_lecture_note({"chapters": [CHAPTER], "emphasis": ["꼭 기억하라: 열은 고온→저온"],
                                      "notices": ["시험에 나온다: 부호 규칙", "중간시험은 다음 주 화요일"]})
    assert note["emphasis"] == ["꼭 기억하라: 열은 고온→저온", "시험에 나온다: 부호 규칙"]
    assert note["notices"] == ["중간시험은 다음 주 화요일"]
    assert "## 강조 사항" in render_note_markdown(note)
