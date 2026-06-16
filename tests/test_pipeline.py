from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_pipeline import (
    build_stt_options,
    main,
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
                        "temperature: 0",
                        "beam_size:",
                    ]
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                stt_config=str(config_path),
                stt_model_size=None,
                stt_language=None,
                stt_device=None,
                stt_timestamps=False,
            )

            options = build_stt_options(args)

        self.assertEqual(options["model_size"], "tiny")
        self.assertEqual(options["device"], "cpu")
        self.assertEqual(options["temperature"], 0.0)
        self.assertIsNone(options["beam_size"])

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
                "timestamps": False,
            }

            with patch("scripts.run_pipeline._execute_stt", return_value=3) as execute_stt:
                result = run_stt_step(audio_path, run_dir, stt_options)

        self.assertEqual(result, (output_json, output_text))
        execute_stt.assert_called_once_with(audio_path, output_json, output_text, stt_options)


class PipelineVlmTests(unittest.TestCase):
    def test_main_requests_vlm_summary_after_ocr(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            args = SimpleNamespace(
                video="input.mp4",
                run_dir=str(run_dir),
                method="interval",
                interval_seconds=10.0,
                scene_threshold=0.3,
                scene_min_gap_seconds=1.0,
                ocr_lang="korean",
                skip_ocr=False,
                skip_vlm=False,
                vlm_max_new_tokens=256,
                skip_stt=False,
            )
            video_path = run_dir / "input.mp4"
            audio_path = run_dir / "audio" / "audio.wav"
            stt_json_path = run_dir / "stt" / "stt_result.json"
            stt_text_path = run_dir / "stt" / "stt_result.txt"
            llm_summary_path = run_dir / "llm" / "stt_summary.txt"
            llm_summary_json_path = run_dir / "llm" / "stt_summary_result.json"
            metadata_path = run_dir / "metadata" / "frame_metadata.json"
            ocr_path = run_dir / "ocr" / "ocr_result.json"
            vlm_summary_path = run_dir / "vlm" / "vlm_summary.txt"
            vlm_summary_json_path = run_dir / "vlm" / "vlm_summary_result.json"

            with patch("scripts.run_pipeline.parse_args", return_value=args), patch(
                "scripts.run_pipeline.resolve_path_pattern", return_value=video_path
            ), patch("scripts.run_pipeline.build_stt_options", return_value={}), patch(
                "scripts.run_pipeline.ensure_mp4_video", return_value=video_path
            ), patch("scripts.run_pipeline.run_audio_step", return_value=audio_path), patch(
                "scripts.run_pipeline.run_stt_step",
                return_value=(stt_json_path, stt_text_path),
            ), patch(
                "scripts.run_pipeline.run_llm_summary_step",
                return_value=(llm_summary_path, llm_summary_json_path),
            ), patch(
                "scripts.run_pipeline.run_preprocess_step", return_value=metadata_path
            ), patch("scripts.run_pipeline.run_ocr_step", return_value=ocr_path), patch(
                "scripts.run_pipeline.run_vlm_summary_step",
                return_value=(vlm_summary_path, vlm_summary_json_path),
            ) as run_vlm:
                main()

        run_vlm.assert_called_once_with(
            ocr_json_path=ocr_path,
            output_path=vlm_summary_path,
            output_json_path=vlm_summary_json_path,
            max_new_tokens=256,
        )


if __name__ == "__main__":
    unittest.main()
