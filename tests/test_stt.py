from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.stt import (  # noqa: E402
    clear_model_cache,
    format_chunked_stt_result,
    format_stt_result,
    run_chunked_whisper_stt,
    run_whisper_stt,
)


class FakeModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        return {
            "language": kwargs.get("language", "ko"),
            "segments": [
                {"start": 0.0, "end": 1.2, "text": " 안녕하세요 "},
                {"start": 1.2, "end": 2.0, "text": ""},
            ],
            "text": "안녕하세요",
        }


class SttFormatterTests(unittest.TestCase):
    def test_format_stt_result_filters_empty_segments(self):
        result = format_stt_result(
            {
                "language": "ko",
                "segments": [
                    {"start": 0, "end": 1.234, "text": " 첫 문장 "},
                    {"start": 2, "end": 3, "text": " "},
                    {"start": 3, "end": 4, "text": "둘째 문장"},
                ],
            }
        )

        self.assertEqual(result["segment_count"], 2)
        self.assertEqual(result["full_text"], "첫 문장 둘째 문장")
        self.assertEqual(result["segments"][0]["end"], 1.23)

    def test_format_chunked_stt_result_offsets_segment_times(self):
        result = format_chunked_stt_result(
            {
                "audio_path": "audio.wav",
                "language": "ko",
                "model_size": "tiny",
                "duration_sec": 12.0,
                "chunk_config": {"chunk_seconds": 10, "overlap_seconds": 1},
                "chunks": [
                    {
                        "chunk_start": 0.0,
                        "result": {"segments": [{"start": 1.0, "end": 2.0, "text": "첫 문장"}]},
                    },
                    {
                        "chunk_start": 9.0,
                        "result": {"segments": [{"start": 0.5, "end": 1.0, "text": "둘째 문장"}]},
                    },
                ],
            }
        )

        self.assertEqual(result["segment_count"], 2)
        self.assertEqual(result["segments"][1]["start"], 9.5)
        self.assertEqual(result["full_text"], "첫 문장 둘째 문장")


class WhisperSttTests(unittest.TestCase):
    def tearDown(self):
        clear_model_cache()

    def test_run_whisper_stt_loads_model_lazily(self):
        fake_model = FakeModel()
        fake_whisper = types.SimpleNamespace(load_model=lambda *args, **kwargs: fake_model)

        with patch.dict(sys.modules, {"whisper": fake_whisper}):
            result = run_whisper_stt(__file__, model_size="tiny", language="ko", device="cpu")

        self.assertEqual(result["language"], "ko")
        self.assertEqual(fake_model.calls[0][1]["language"], "ko")

    def test_run_chunked_whisper_stt_splits_audio(self):
        fake_model = FakeModel()
        fake_audio = [0.0] * 48000
        fake_whisper = types.SimpleNamespace(
            load_model=lambda *args, **kwargs: fake_model,
            load_audio=lambda path: fake_audio,
        )

        with patch.dict(sys.modules, {"whisper": fake_whisper}):
            result = run_chunked_whisper_stt(
                __file__,
                model_size="tiny",
                language="ko",
                chunk_seconds=2,
                overlap_seconds=1,
                device="cpu",
            )

        self.assertEqual(result["duration_sec"], 3.0)
        self.assertEqual(len(result["chunks"]), 3)
        self.assertEqual(fake_model.calls[0][1]["language"], "ko")


if __name__ == "__main__":
    unittest.main()
