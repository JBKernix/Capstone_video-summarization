import json

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


def test_final_note_asks_for_category_and_passes_it_through():
    from threading import Lock
    from types import SimpleNamespace

    from services.final_service import FinalService

    answer = {"title": "명장면", "chapters": [CHAPTER], "classification": {
        "category": "CULTURE_ENTERTAINMENT", "confidence": 0.9, "reason": "드라마 명장면", "tags": ["드라마"]}}
    loader = FakeLoader(json.dumps(answer, ensure_ascii=False))
    service = FinalService(llm_service=SimpleNamespace(loader=loader, _generation_lock=Lock()))
    result = service.summarize_final_note(stt_text="응급 수술 장면", vlm_text="화면",
                                          video_info="- 제목: 낭만닥터 김사부 명장면")
    prompt = loader.prompts[0]
    assert "- 제목: 낭만닥터 김사부 명장면" in prompt and "CULTURE_ENTERTAINMENT" in prompt
    assert "{category_guide}" not in prompt and "{video_section}" not in prompt
    # 검증은 앱에서 하므로 서버는 모델 답을 그대로 넘깁니다. 노트 JSON에는 섞지 않습니다.
    assert result["classification"]["category"] == "CULTURE_ENTERTAINMENT"
    assert "classification" not in result["lecture_note"]


def test_final_note_without_category_still_succeeds():
    from threading import Lock
    from types import SimpleNamespace

    from services.final_service import FinalService

    loader = FakeLoader(json.dumps({"title": "강의", "chapters": [CHAPTER]}, ensure_ascii=False))
    service = FinalService(llm_service=SimpleNamespace(loader=loader, _generation_lock=Lock()))
    result = service.summarize_final_note(stt_text="강의", vlm_text="화면")
    assert result["format"] == "json" and result["classification"] is None
    assert "(영상 정보 없음)" in loader.prompts[0]
