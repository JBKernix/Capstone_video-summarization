import json
from pathlib import Path
from unittest.mock import patch

from modules.llm.vlm_summarizer_client import GPUVLMClient, GPUVLMClientConfig
from scripts.run_vlm_summary import run_vlm_summary_step


def test_resolve_frame_paths_uses_ocr_image_paths(tmp_path):
    frame_path = tmp_path / "frame_000001.jpg"
    frame_path.write_bytes(b"jpg")
    ocr_path = tmp_path / "ocr_result.json"
    entries = [{"frame_id": 0, "image_path": str(frame_path)}]

    result = GPUVLMClient._resolve_frame_paths(entries, ocr_path)

    assert result == [frame_path.resolve()]


def test_run_vlm_summary_step_saves_text_and_json(tmp_path):
    ocr_path = tmp_path / "ocr_result.json"
    ocr_path.write_text("[]", encoding="utf-8")
    output_path = tmp_path / "vlm" / "vlm_summary.txt"
    output_json_path = tmp_path / "vlm" / "vlm_summary_result.json"
    server_result = [
        {
            "frame_id": 3,
            "timestamp": 12.5,
            "image_path": "runs/frames/frame_000004.jpg",
            "ocr_text": "sample",
            "vlm_summary": "화면 요약입니다.",
        }
    ]

    with patch(
        "scripts.run_vlm_summary.GPUVLMClient.summarize_ocr_file",
        return_value=server_result,
    ) as summarize:
        result = run_vlm_summary_step(
            ocr_json_path=ocr_path,
            output_path=output_path,
            output_json_path=output_json_path,
            max_new_tokens=256,
        )

    assert result == (output_path, output_json_path)
    assert "## Frame 3 (12.5s)" in output_path.read_text(encoding="utf-8")
    payload = json.loads(output_json_path.read_text(encoding="utf-8"))
    assert payload["source"]["frame_count"] == 1
    assert payload["results"] == server_result
    summarize.assert_called_once_with(ocr_json_path=ocr_path, max_new_tokens=256)


def test_summarize_ocr_file_batches_more_than_server_limit(tmp_path):
    ocr_path = tmp_path / "ocr_result.json"
    entries = []
    for index in range(33):
        frame_path = tmp_path / f"frame_{index:06d}.jpg"
        frame_path.write_bytes(b"jpg")
        entries.append({"frame_id": index, "image_path": str(frame_path)})
    ocr_path.write_text(
        json.dumps(entries),
        encoding="utf-8",
    )

    client = GPUVLMClient()
    with patch.object(
        client,
        "_post_vlm_files",
        side_effect=[[{"frame_id": index} for index in range(32)], [{"frame_id": 32}]],
    ) as post_files:
        result = client.summarize_ocr_file(ocr_path, max_new_tokens=128)

    assert len(result) == 33
    assert [len(call.args[1]) for call in post_files.call_args_list] == [32, 1]


def test_client_posts_server_multipart_fields_and_polls_result(tmp_path):
    ocr_path = tmp_path / "ocr_result.json"
    frame_path = tmp_path / "frame_000001.jpg"
    ocr_path.write_text("[]", encoding="utf-8")
    frame_path.write_bytes(b"jpg")
    posted = {}

    class FakeResponse:
        text = ""

        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    def fake_post(url, files, data, timeout):
        posted["url"] = url
        posted["field_names"] = [field_name for field_name, _value in files]
        posted["filenames"] = [value[0] for _field_name, value in files]
        posted["data"] = data
        posted["timeout"] = timeout
        return FakeResponse(
            {
                "job_id": "vlm-summary-test",
                "status_url": "/vlm/jobs/vlm-summary-test",
            }
        )

    def fake_get(url, timeout):
        assert url == "http://gpu.test/vlm/jobs/vlm-summary-test"
        return FakeResponse(
            {
                "status": "completed",
                "result": [{"frame_id": 0, "vlm_summary": "summary"}],
            }
        )

    client = GPUVLMClient(
        GPUVLMClientConfig(
            server_url="http://gpu.test",
            timeout=30,
            poll_interval=0,
            job_timeout=30,
        )
    )
    with patch("modules.llm.vlm_summarizer_client.requests.post", side_effect=fake_post), patch(
        "modules.llm.vlm_summarizer_client.requests.get",
        side_effect=fake_get,
    ):
        result = client._post_vlm_files(ocr_path, [frame_path], max_new_tokens=256)

    assert result == [{"frame_id": 0, "vlm_summary": "summary"}]
    assert posted["url"] == "http://gpu.test/vlm/summarize"
    assert posted["field_names"] == ["ocr_result", "frames"]
    assert posted["filenames"] == ["ocr_result.json", "frame_000001.jpg"]
    assert posted["data"] == {"max_new_tokens": "256"}
