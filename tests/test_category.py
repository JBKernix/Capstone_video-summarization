"""강의 노트 카테고리 분류 테스트입니다. 실제 LLM은 부르지 않고 응답을 고정(fixture)해 둡니다."""
import json
from unittest.mock import MagicMock, patch

import pytest

from app.result_export import save_analysis_result
from modules.llm.category import (
    CONFIDENCE_THRESHOLD,
    normalize_classification,
    read_classification,
    store_auto_classification,
    store_manual_classification,
)
from modules.llm.claude_backend import ClaudeFinalClient
from modules.llm.final_summarizer_client import GPUFinalSummaryClient
from scripts import run_final_summary
from scripts.run_final_summary import run_final_summary_step, write_stt_only_final_summary_step


def reply(result):
    response = MagicMock(status_code=200)
    response.json.return_value = {"stop_reason": "tool_use", "usage": {},
                                  "content": [{"type": "tool_use", "name": "submit_result", "input": result}]}
    return response


def note(classification, chapter="개요"):
    data = {"title": "강의", "key_points": ["핵심"], "terms": [], "visuals": [], "conclusion": [], "emphasis": [],
            "notices": [], "chapters": [{"title": chapter, "start": 0, "end": 10, "points": ["설명"], "screen_notes": []}]}
    if classification is not ...:
        data["classification"] = classification
    return data


# (영상 정보, STT 요약, 모델이 돌려준 분류) → 기대 카테고리
CASES = {
    "thermodynamics": ({"title": "열역학 제2법칙과 엔트로피"}, "열역학 제2법칙과 엔트로피 증가를 설명",
                       {"category": "SCIENCE_ENGINEERING", "confidence": 0.93, "reason": "열역학을 설명하는 물리학 강의",
                        "tags": ["물리학", "열역학", "엔트로피"]}, "SCIENCE_ENGINEERING"),
    "programming": ({"title": "파이썬 리스트 컴프리헨션", "channel": "코딩 강좌"}, "리스트 컴프리헨션 문법과 예제 코드",
                    {"category": "SCIENCE_ENGINEERING", "confidence": 0.9, "reason": "파이썬 프로그래밍 강의",
                     "tags": ["파이썬", "프로그래밍"]}, "SCIENCE_ENGINEERING"),
    "disease": ({"title": "당뇨병의 원인과 치료"}, "인슐린 저항성, 진단 기준, 약물 치료를 설명",
                {"category": "MEDICAL_HEALTH", "confidence": 0.88, "reason": "실제 질병의 원인과 치료 설명",
                 "tags": ["당뇨병", "인슐린"]}, "MEDICAL_HEALTH"),
    "korean_history": ({"title": "조선 후기 실학"}, "실학의 등장 배경과 정약용·박지원의 사상",
                       {"category": "HISTORY_HUMANITIES", "confidence": 0.91, "reason": "한국사 강의",
                        "tags": ["한국사", "조선", "실학"]}, "HISTORY_HUMANITIES"),
    "world_news": ({"title": "중동 정세 브리핑", "channel": "뉴스 채널"}, "휴전 협상과 주변국 외교 동향",
                   {"category": "CURRENT_AFFAIRS_SOCIETY", "confidence": 0.86, "reason": "국제정세 뉴스",
                    "tags": ["국제정세", "외교"]}, "CURRENT_AFFAIRS_SOCIETY"),
    "drama": ({"title": "드라마 줄거리 몰아보기 1~4화"}, "주인공들의 갈등과 명장면 정리",
              {"category": "CULTURE_ENTERTAINMENT", "confidence": 0.9, "reason": "드라마 줄거리·명장면 요약",
               "tags": ["드라마", "줄거리"]}, "CULTURE_ENTERTAINMENT"),
    "medical_drama": ({"title": "낭만닥터 김사부 명장면 - 응급 수술", "channel": "SBS 드라마",
                       "description": "닥터X를 잇는 의학 드라마 명장면 모음"},
                      "김사부가 응급 수술을 집도하며 후배 의사와 갈등하는 장면",
                      {"category": "CULTURE_ENTERTAINMENT", "confidence": 0.87,
                       "reason": "의료 드라마의 명장면으로 의학 지식 설명이 아님", "tags": ["드라마", "낭만닥터 김사부"]},
                      "CULTURE_ENTERTAINMENT"),
}


@pytest.fixture
def summary_inputs(tmp_path):
    def make(stt_text):
        stt = tmp_path / "stt_summary_result.json"
        stt.write_text(json.dumps({"summary": stt_text}, ensure_ascii=False), encoding="utf-8")
        vlm = tmp_path / "vlm_summary_result.json"
        vlm.write_text(json.dumps({"results": [{"timestamp": 1.0, "vlm_summary": "화면"}]}), encoding="utf-8")
        return stt, vlm
    return make


def run_claude_final(tmp_path, monkeypatch, stt, vlm, answer, video_context):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    monkeypatch.setattr(run_final_summary, "get_summary_client", lambda stage: ClaudeFinalClient("haiku"))
    with patch("requests.post", return_value=reply(answer)) as post:
        _, json_path = run_final_summary_step(stt, vlm, tmp_path / "final" / "final_summary.txt",
                                              video_context=video_context)
    assert post.call_count == 1  # 분류용 별도 요청 없이 강의 노트 요청 하나로 받습니다.
    return json.loads(json_path.read_text(encoding="utf-8")), post.call_args.kwargs["json"]


@pytest.mark.parametrize("case", CASES)
def test_category_comes_from_the_note_request(case, tmp_path, monkeypatch, summary_inputs):
    video, stt_text, classification, expected = CASES[case]
    result, sent = run_claude_final(tmp_path, monkeypatch, *summary_inputs(stt_text), note(classification), video)
    prompt = sent["messages"][0]["content"][0]["text"]
    assert f"- 제목: {video['title']}" in prompt and stt_text in prompt
    assert "classification" in sent["tools"][0]["input_schema"]["required"]
    assert result["classification"]["category"] == expected
    assert result["classification"]["status"] == "CLASSIFIED"
    assert result["classification"]["tags"] == classification["tags"]
    assert result["lecture_note"]["chapters"]  # 노트 자체는 그대로 만들어집니다.


def test_prompt_tells_medical_drama_is_entertainment(tmp_path, monkeypatch, summary_inputs):
    video, stt_text, classification, _ = CASES["medical_drama"]
    result, sent = run_claude_final(tmp_path, monkeypatch, *summary_inputs(stt_text), note(classification), video)
    prompt = sent["messages"][0]["content"][0]["text"]
    assert "낭만닥터 김사부" in prompt and "- 채널: SBS 드라마" in prompt
    assert "MEDICAL_HEALTH가 아니라 CULTURE_ENTERTAINMENT" in prompt
    assert result["classification"]["category"] != "MEDICAL_HEALTH"


@pytest.mark.parametrize("answer", [
    {"category": "MEDICINE", "confidence": 0.95, "reason": "", "tags": []},   # 허용되지 않은 값
    {"category": "MEDICAL_HEALTH", "confidence": "높음", "reason": "", "tags": []},  # 신뢰도 형식 오류
    {"category": "MEDICAL_HEALTH", "confidence": 3000, "reason": "", "tags": []},  # 범위 밖 신뢰도
    "category: SCIENCE",                                                        # 파싱 불가
    None,
    ...,                                                                        # 항목 자체가 없음
])
def test_invalid_answer_falls_back_without_failing_the_note(answer, tmp_path, monkeypatch, summary_inputs):
    result, _ = run_claude_final(tmp_path, monkeypatch, *summary_inputs("요약"), note(answer), {"title": "강의"})
    assert (result["classification"]["category"], result["classification"]["status"]) == ("OTHER", "NEEDS_REVIEW")
    assert result["lecture_note"]["title"] == "강의" and result["summary"]


def test_low_confidence_needs_review_and_keeps_suggestion():
    value = normalize_classification({"category": "HISTORY_HUMANITIES", "confidence": CONFIDENCE_THRESHOLD - 0.01,
                                      "reason": "애매함", "tags": ["역사"]})
    assert (value["category"], value["status"], value["suggested_category"]) == ("OTHER", "NEEDS_REVIEW",
                                                                                  "HISTORY_HUMANITIES")
    at_threshold = normalize_classification({"category": "HISTORY_HUMANITIES", "confidence": CONFIDENCE_THRESHOLD})
    assert (at_threshold["category"], at_threshold["status"]) == ("HISTORY_HUMANITIES", "CLASSIFIED")


def test_clear_other_is_classified_not_review():
    value = normalize_classification({"category": "other", "confidence": 0.9, "reason": "요리 강좌", "tags": "#요리, 레시피"})
    assert (value["category"], value["status"], value["tags"]) == ("OTHER", "CLASSIFIED", ["요리", "레시피"])


def test_percent_confidence_is_accepted():
    assert normalize_classification({"category": "MEDICAL_HEALTH", "confidence": 92})["confidence"] == 0.92


def test_local_server_path_sends_video_info_and_keeps_classification(tmp_path, monkeypatch, summary_inputs):
    stt, vlm = summary_inputs("요약")
    response = MagicMock(status_code=200)
    response.json.return_value = {"final_summary": "# 강의", "lecture_note": note(...),
                                  "classification": {"category": "SCIENCE_ENGINEERING", "confidence": 0.8}}
    monkeypatch.setattr(run_final_summary, "get_summary_client", lambda stage: GPUFinalSummaryClient())
    with patch("requests.post", return_value=response) as post:
        _, json_path = run_final_summary_step(stt, vlm, tmp_path / "final" / "final_summary.txt",
                                              video_context={"title": "회로 이론", "channel": "전자공학"})
    assert post.call_args.kwargs["data"]["video_info"] == "- 제목: 회로 이론\n- 채널: 전자공학"
    result = json.loads(json_path.read_text(encoding="utf-8"))
    assert (result["classification"]["category"], result["classification"]["status"]) == ("SCIENCE_ENGINEERING",
                                                                                          "CLASSIFIED")


def test_old_server_without_classification_is_unclassified(tmp_path, monkeypatch, summary_inputs):
    stt, vlm = summary_inputs("요약")
    response = MagicMock(status_code=200)
    response.json.return_value = {"final_summary": "# 강의", "lecture_note": None}  # 마크다운 대체 또는 이전 서버
    monkeypatch.setattr(run_final_summary, "get_summary_client", lambda stage: GPUFinalSummaryClient())
    with patch("requests.post", return_value=response):
        _, json_path = run_final_summary_step(stt, vlm, tmp_path / "final" / "final_summary.txt")
    assert json.loads(json_path.read_text(encoding="utf-8"))["classification"]["status"] == "NEEDS_REVIEW"


def test_stt_only_result_is_unclassified(tmp_path, summary_inputs):
    stt, _ = summary_inputs("요약")
    _, json_path = write_stt_only_final_summary_step(stt, tmp_path / "final" / "final_summary.txt")
    assert json.loads(json_path.read_text(encoding="utf-8"))["classification"]["category"] == "OTHER"


def test_manual_category_is_not_overwritten_by_auto_classification(tmp_path):
    folder = tmp_path / "saved"
    folder.mkdir()
    store_auto_classification(folder, normalize_classification({"category": "MEDICAL_HEALTH", "confidence": 0.8}))
    store_manual_classification(folder, "CULTURE_ENTERTAINMENT")
    kept = store_auto_classification(folder, normalize_classification({"category": "MEDICAL_HEALTH",
                                                                        "confidence": 0.99}))
    assert (kept["category"], kept["status"]) == ("CULTURE_ENTERTAINMENT", "MANUALLY_CLASSIFIED")
    assert read_classification(folder)["category"] == "CULTURE_ENTERTAINMENT"
    with pytest.raises(ValueError):
        store_manual_classification(folder, "SPORTS")


def test_save_copies_classification_and_legacy_results_are_unclassified(tmp_path):
    final_dir = tmp_path / "final"
    final_dir.mkdir()
    (final_dir / "final_summary_result.json").write_text(json.dumps({"summary": "# 강의", "classification": {
        "category": "HISTORY_HUMANITIES", "confidence": 0.9, "status": "CLASSIFIED", "reason": "한국사",
        "tags": ["조선"], "suggested_category": None}}, ensure_ascii=False), encoding="utf-8")
    saved = save_analysis_result(None, final_dir, tmp_path / "saved", title="실학")
    assert read_classification(saved)["category"] == "HISTORY_HUMANITIES"

    legacy = tmp_path / "legacy_final"
    legacy.mkdir()
    (legacy / "final_summary.txt").write_text("# 이전 결과", encoding="utf-8")
    old = save_analysis_result(None, legacy, tmp_path / "saved", title="이전")
    assert (read_classification(old)["category"], read_classification(old)["status"]) == ("OTHER", "NEEDS_REVIEW")
    (old / "classification.json").write_text("{broken", encoding="utf-8")
    assert read_classification(old)["category"] == "OTHER"
