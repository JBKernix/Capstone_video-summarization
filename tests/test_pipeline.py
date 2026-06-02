from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_pipeline import (
    build_stt_options,
    run_stt_step,
    run_vision_step,
    validate_process_isolation,
)


class PipelineVisionProcessTests(unittest.TestCase):
    def test_run_vision_step_uses_child_process_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            metadata_path = run_dir / "metadata.json"
            metadata_path.write_text("[]", encoding="utf-8")
            output_path = run_dir / "vision" / "vision_result.json"

            with patch("scripts.run_pipeline._run_vision_step_in_child_process") as run_child:
                result = run_vision_step(metadata_path, run_dir, "korean")

        self.assertEqual(result, output_path)
        run_child.assert_called_once_with(metadata_path, output_path, "korean")


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

    def test_run_stt_step_uses_child_process_by_default(self):
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

            with patch("scripts.run_pipeline._run_stt_step_in_child_process", return_value=3) as run_child:
                result = run_stt_step(audio_path, run_dir, stt_options)

        self.assertEqual(result, (output_json, output_text))
        run_child.assert_called_once_with(audio_path, output_json, output_text, stt_options)


class PipelineIsolationTests(unittest.TestCase):
    def test_rejects_same_process_vision_and_stt_combination(self):
        args = SimpleNamespace(
            skip_vision=False,
            skip_stt=False,
            vision_same_process=True,
            stt_same_process=True,
        )

        with self.assertRaises(ValueError):
            validate_process_isolation(args)


if __name__ == "__main__":
    unittest.main()
