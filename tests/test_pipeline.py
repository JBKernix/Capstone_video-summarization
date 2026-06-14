from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_pipeline import (
    build_stt_options,
    run_stt_step,
    run_ocr_step,
)


class PipelineOCRProcessTests(unittest.TestCase):
    def test_run_ocr_step_runs_in_current_process(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            metadata_path = run_dir / "metadata.json"
            metadata_path.write_text("[]", encoding="utf-8")
            output_path = run_dir / "ocr" / "ocr_result.json"

            with patch("modules.ocr.analyze_frames_metadata") as analyze_frames:
                result = run_ocr_step(metadata_path, run_dir, "korean")

        self.assertEqual(result, output_path)
        analyze_frames.assert_called_once_with(
            metadata_path=str(metadata_path),
            output_path=str(output_path),
            lang="korean",
        )


class PipelineSttTests(unittest.TestCase):
    def test_build_stt_options_uses_config_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "stt_config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "model_size: tiny",
                        "language: ko",
                        "device: cpu",
                        "chunked: true",
                        "chunk_seconds: 12",
                        "overlap_seconds: 1",
                    ]
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                stt_config=str(config_path),
                stt_model_size=None,
                stt_language=None,
                stt_device=None,
                stt_chunked=False,
                stt_no_chunked=False,
                stt_chunk_seconds=None,
                stt_overlap_seconds=None,
                stt_timestamps=False,
            )

            options = build_stt_options(args)

        self.assertEqual(options["model_size"], "tiny")
        self.assertEqual(options["device"], "cpu")
        self.assertTrue(options["chunked"])
        self.assertEqual(options["chunk_seconds"], 12)

    def test_run_stt_step_runs_in_current_process(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            audio_path = run_dir / "audio.wav"
            audio_path.write_bytes(b"fake")
            output_json = run_dir / "stt" / "stt_result.json"
            output_text = run_dir / "stt" / "stt_result.txt"
            stt_options = {
                "model_size": "tiny",
                "language": "ko",
                "device": "cpu",
                "chunked": True,
                "chunk_seconds": 30,
                "overlap_seconds": 2,
                "timestamps": False,
            }

            with patch("scripts.run_pipeline._execute_stt", return_value=3) as execute_stt:
                result = run_stt_step(audio_path, run_dir, stt_options)

        self.assertEqual(result, (output_json, output_text))
        execute_stt.assert_called_once_with(audio_path, output_json, output_text, stt_options)


if __name__ == "__main__":
    unittest.main()
