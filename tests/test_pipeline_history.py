"""Real FFmpeg preprocessing with mocked ML inference; no external server access."""
import json
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

from modules.common.run_history import list_records
from scripts.run_pipeline import main


@pytest.fixture(autouse=True)
def local_backend_health():
    with patch("modules.llm.backends.BackendOptions.validate", return_value={"analysis_backend": "local"}):
        yield


@pytest.fixture
def video(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not installed")
    path = tmp_path / "sample.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x120:d=2",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "mpeg4", "-c:a", "aac", str(path)], check=True)
    return path


@pytest.mark.parametrize("level,skip_ocr,skip_vlm", [("simple", False, False), ("standard", False, False),
                                                       ("detailed", False, False), ("detailed", True, False), ("standard", False, True)])
def test_pipeline_archives_metrics(video, tmp_path, level, skip_ocr, skip_vlm):
    run_dir = tmp_path / "runs"
    raw_stt = {"language": "ko", "segments": [{"start": 0, "end": 1.5, "text": "테스트 문장"}]}
    llm = {"summary": "예시 음성 요약", "important_segments": [{"start": 0, "end": 1.5}]}
    argv = ["pipeline", "--video", str(video), "--run-dir", str(run_dir), "--summary-level", level]
    if skip_ocr:
        argv.append("--skip-ocr")
    if skip_vlm:
        argv.append("--skip-vlm")
    with (patch.object(sys, "argv", argv),
          patch("modules.stt.run_whisper_stt", return_value=raw_stt),
          patch("modules.llm.stt_summarizer_client.GPULLMClient._post_summary_payload", return_value=llm),
          patch("modules.ocr.ocr_formatter.OCRExtractor") as ocr_class,
          patch("modules.llm.vlm_summarizer_client.GPUVLMClient._post_vlm_files", return_value=[{"frame_id": 0, "vlm_summary": "예시"}, {"frame_id": 1, "vlm_summary": "예시"}]),
          patch("modules.llm.final_summarizer_client.GPUFinalSummaryClient._post_final_summary_files", return_value={"summary": "예시 최종 요약"})):
        ocr_class.return_value.extract_text_with_language.return_value = {"ocr_text": "example", "detected_language": "en"}
        main()
    record = list_records(run_dir / "history")[0]
    assert record["status"] == "success"
    assert len(record["stages"]) == 7
    assert record["input"]["width"] == 160
    assert record["input"]["duration_seconds"] == pytest.approx(2, abs=.1)
    assert record["counts"]["stt_segments"] == 1
    assert record["settings"]["stt"]["model_size"] == {"simple": "small", "standard": "medium", "detailed": "large"}[level]
    assert record["settings"]["preset_semantics"] == "whisper_only_v1"
    # 화면이 그대로인 단색 영상이라 대표 프레임 방식은 구간에서 1장만 남깁니다.
    assert record["counts"]["frames_extracted"] == 1
    if not skip_ocr:
        assert record["counts"]["ocr_success"] == 1
    if not skip_ocr and not skip_vlm:
        assert record["counts"]["vlm_frames"] == 2
        assert all(stage["status"] == "success" for stage in record["stages"])
    archive = run_dir / "history" / record["run_id"]
    assert (archive / "pipeline.log").is_file()
    assert (archive / "final_summary_result.json").is_file()


def test_failure_before_first_stage_is_saved(tmp_path):
    with patch.object(sys, "argv", ["pipeline", "--video", str(tmp_path / "missing.mp4"), "--run-dir", str(tmp_path / "runs")]):
        with pytest.raises(FileNotFoundError):
            main()
    record = list_records(tmp_path / "runs" / "history")[0]
    assert record["status"] == "failed"
    assert "FileNotFoundError" in record["error"]


def test_claude_pipeline_archives_all_stage_outputs(video, tmp_path, monkeypatch):
    from tests.test_analysis_backends import reply

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-secret")
    run_dir = tmp_path / "runs"
    responses = [reply({"summary": "음성 요약", "important_segment_ids": [0]}),
                 reply({"results": [{"index": 0, "summary": "파란 화면"}]}),
                 reply({"summary": "# 최종 요약\n영상의 음성과 화면을 통합했습니다."})]
    with (patch.object(sys, "argv", ["pipeline", "--video", str(video), "--run-dir", str(run_dir),
                                    "--analysis-backend", "claude"]),
          patch("modules.llm.backends.BackendOptions.validate", return_value={"analysis_backend": "claude", "analysis_model": "claude-haiku-4-5"}),
          patch("modules.stt.run_whisper_stt", return_value={"language": "ko", "segments": [{"start": 0, "end": 1.5, "text": "테스트"}]}),
          patch("modules.ocr.ocr_formatter.OCRExtractor") as ocr,
          patch("modules.llm.claude_backend.requests.post", side_effect=responses) as post):
        ocr.return_value.extract_text_with_language.return_value = {"ocr_text": "example", "detected_language": "en"}
        main()
    record = list_records(run_dir / "history")[0]
    assert record["status"] == "success"
    assert all(stage["status"] == "success" for stage in record["stages"])
    assert record["settings"]["analysis_backend"] == "claude"
    assert record["counts"]["api_calls"] == 3
    assert record["counts"]["api_input_tokens"] == 300
    assert post.call_count == 3
    archive = run_dir / "history" / record["run_id"]
    assert "최종 요약" in (archive / "final_summary_result.json").read_text()
    assert "test-only-secret" not in (archive / "metrics.json").read_text()
