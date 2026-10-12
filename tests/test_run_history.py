import csv
import io
import json
import sys
from unittest.mock import patch

import pytest

from modules.common.run_history import (
    RunRecorder, finish_external, list_records, prepare_run, read_record,
    record_counts, records_csv, snapshot_result,
)


def test_runs_keep_separate_logs_and_snapshots(tmp_path):
    artifact = tmp_path / "frames.json"
    artifact.write_text('[{"frame_id": 1}]')
    first = RunRecorder(tmp_path / "history", input_name="한글영상.mp4")
    with first.capture():
        with first.stage(4, "프레임 추출"):
            print("first run")
            print("stderr retained", file=sys.stderr)
            record_counts(frames_extracted=1)
            snapshot_result(artifact, "frame_metadata.json")
    artifact.write_text("[]")
    second = RunRecorder(tmp_path / "history", input_name="다음영상.mp4")
    with second.capture():
        print("second run")
    stored = read_record(first.directory)
    assert stored["status"] == "success"
    assert stored["counts"]["frames_extracted"] == 1
    assert stored["stages"][0]["duration_seconds"] >= 0
    assert stored["duration_seconds"] >= stored["stages"][0]["duration_seconds"]
    assert json.loads((first.directory / "frame_metadata.json").read_text()) == [{"frame_id": 1}]
    log = (first.directory / "pipeline.log").read_text()
    assert "first run" in log and "stderr retained" in log and "second run" not in log
    assert read_record(second.directory)["counts"] == {}
    assert len(list_records(tmp_path / "history")) == 2


@pytest.mark.parametrize("error,status", [(RuntimeError("server offline"), "failed"), (KeyboardInterrupt(), "cancelled")])
def test_failure_or_interrupt_preserves_partial_run(tmp_path, error, status):
    recorder = RunRecorder(tmp_path)
    with pytest.raises(type(error)):
        with recorder.capture():
            with recorder.stage(2, "STT"):
                record_counts(stt_segments=9)
                raise error
    record = read_record(recorder.directory)
    assert record["status"] == record["stages"][0]["status"] == status
    assert record["counts"]["stt_segments"] == 9
    assert record["finished_at"]
    assert type(error).__name__ in (recorder.directory / "pipeline.log").read_text()


def test_external_cancel_and_startup_failure(tmp_path):
    directory = prepare_run(tmp_path)
    record = read_record(directory)
    record.update(status="running", started_at=record["created_at"])
    record["stages"] = [{"step": 2, "name": "STT", "status": "running", "started_at": record["created_at"]}]
    (directory / "metrics.json").write_text(json.dumps(record))
    finish_external(directory, "cancelled", "user stopped")
    result = read_record(directory)
    assert result["status"] == result["stages"][0]["status"] == "cancelled"
    finish_external(directory, "interrupted", "later poll")
    assert read_record(directory) == result
    queued = prepare_run(tmp_path)
    finish_external(queued, "failed", "startup failure")
    assert read_record(queued)["status"] == "failed"


def test_csv_and_corrupt_record(tmp_path):
    recorder = RunRecorder(tmp_path, input_name="=danger.mp4", settings={"summary_level": "simple"})
    with recorder.capture():
        with recorder.stage(4, "프레임") as state:
            state["status"] = "건너뜀"
    record = read_record(recorder.directory)
    assert record["stages"][0]["status"] == "skipped"
    rows = list(csv.DictReader(io.StringIO(records_csv([record]).decode("utf-8-sig"))))
    assert rows[0]["input_name"] == "'=danger.mp4"
    assert rows[0]["frames_extracted"] == ""
    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "metrics.json").write_text("{")
    assert len(list_records(tmp_path)) == 1


def test_vlm_failed_second_batch_keeps_completed_count(tmp_path):
    from modules.llm.vlm_summarizer_client import GPUVLMClient
    entries = []
    for i in range(9):
        image = tmp_path / f"{i}.jpg"
        image.write_bytes(b"jpg")
        entries.append({"image_path": str(image)})
    ocr = tmp_path / "ocr.json"
    ocr.write_text(json.dumps(entries))
    recorder = RunRecorder(tmp_path / "history")
    client = GPUVLMClient()
    with pytest.raises(RuntimeError), recorder.capture(), patch.object(
        client, "_post_vlm_files", side_effect=[[{"frame_id": i} for i in range(8)], RuntimeError("timeout")]
    ):
        client.summarize_ocr_file(ocr)
    assert read_record(recorder.directory)["counts"] == {"vlm_frames": 8, "vlm_batches": 1}


def test_ocr_partial_failure_count(tmp_path):
    from modules.ocr.ocr_formatter import analyze_frames_metadata
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps([{"frame_id": i, "image_path": "test.jpg"} for i in range(2)]))
    recorder = RunRecorder(tmp_path / "history")
    with recorder.capture(), patch("modules.ocr.ocr_formatter.OCRExtractor"), patch(
        "modules.ocr.ocr_formatter.analyze_single_frame",
        side_effect=[{"ocr_text": "example"}, RuntimeError("bad frame")],
    ):
        analyze_frames_metadata(str(metadata), str(tmp_path / "ocr.json"))
    assert read_record(recorder.directory)["counts"] == {"ocr_success": 1, "ocr_failed": 1}
