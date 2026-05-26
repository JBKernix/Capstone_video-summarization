import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from modules.preprocess import audio_extractor


class AudioExtractorTest(unittest.TestCase):
    def test_extract_audio_builds_ffmpeg_command(self):
        with TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            video_path = temp_dir / "input.mp4"
            audio_path = temp_dir / "audio" / "output.wav"
            video_path.write_bytes(b"video")

            with patch.object(audio_extractor, "run_ffmpeg") as run_ffmpeg:
                result = audio_extractor.extract_audio(video_path, audio_path)

            self.assertEqual(result, audio_path)
            run_ffmpeg.assert_called_once_with(
                [
                    "-y",
                    "-i",
                    str(video_path),
                    "-vn",
                    "-acodec",
                    "pcm_s16le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(audio_path),
                ]
            )
            self.assertTrue(audio_path.parent.exists())

    def test_extract_audio_raises_when_video_missing(self):
        with TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)

            with self.assertRaises(FileNotFoundError):
                audio_extractor.extract_audio(
                    temp_dir / "missing.mp4",
                    temp_dir / "output.wav",
                )


if __name__ == "__main__":
    unittest.main()
