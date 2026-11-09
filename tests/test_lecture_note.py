from modules.llm.lecture_note import normalize_lecture_note, render_note_markdown, strip_char_count

CHAPTER = {"title": "개요", "start": 0, "end": 60, "points": ["설명"], "screen_notes": []}


def test_char_count_lines_are_removed():
    assert strip_char_count("## 강의 요약\n- 내용\n(총 1198자)\n총 1,200자") == "## 강의 요약\n- 내용"
    # 본문 속 숫자와 "자"는 지우지 않습니다.
    assert strip_char_count("- 100자 이내로 요약") == "- 100자 이내로 요약"


def test_visuals_keep_board_and_drop_non_material():
    note, warnings = normalize_lecture_note({"chapters": [CHAPTER], "visuals": [
        {"type": "판서", "title": "제1법칙", "start": 10, "end": None, "content": ["Q = W + ΔU"], "meaning": ""},
        {"type": "기타", "title": "방송 로고", "start": 20, "end": None, "content": ["YTN"], "meaning": ""},
        {"type": "차트", "title": "성능", "start": 30, "end": None, "content": ["90%"], "meaning": ""},
    ]}, known_times=[0, 60])
    assert [(v["type"], v["title"]) for v in note["visuals"]] == [("판서", "제1법칙"), ("그래프", "성능")]
    assert any("제외" in warning for warning in warnings)


def test_emphasis_is_separated_from_notices():
    note, _ = normalize_lecture_note({"chapters": [CHAPTER], "emphasis": ["꼭 기억하라: 열은 고온→저온"], "notices": [
        "시험에 나온다: 부호 규칙", "중요합니다: 엔트로피", "다음 주 퀴즈 범위는 3장", "중간시험은 다음 주 화요일"]})
    assert note["emphasis"] == ["꼭 기억하라: 열은 고온→저온", "시험에 나온다: 부호 규칙", "중요합니다: 엔트로피"]
    assert note["notices"] == ["다음 주 퀴즈 범위는 3장", "중간시험은 다음 주 화요일"]
    markdown = render_note_markdown(note)
    assert markdown.index("## 강조 사항") < markdown.index("## 공지 사항")
