import json
from pathlib import Path
import tempfile
import unittest

from app.summary_result import (
    get_summary_markdown,
    has_structured_summary,
    load_final_summary,
)
from app.final_summary_view import resolve_video_path


class FinalSummaryLoaderTests(unittest.TestCase):
    def test_load_final_summary_prefers_json_result(self):
        final_dir = self.tmp_path()
        (final_dir / "final_summary.txt").write_text("# text summary", encoding="utf-8")
        (final_dir / "final_summary_result.json").write_text(
            json.dumps({"summary": "# json summary"}, ensure_ascii=False),
            encoding="utf-8",
        )

        result = load_final_summary(final_dir)

        self.assertEqual(result.mode, "json")
        self.assertEqual(result.content["summary"], "# json summary")
        self.assertEqual(result.source_path.name, "final_summary_result.json")

    def test_load_final_summary_falls_back_to_text(self):
        final_dir = self.tmp_path()
        (final_dir / "final_summary.txt").write_text("# text summary", encoding="utf-8")

        result = load_final_summary(final_dir)

        self.assertEqual(result.mode, "markdown")
        self.assertEqual(result.content, "# text summary")
        self.assertEqual(result.source_path.name, "final_summary.txt")

    def test_load_final_summary_raises_when_missing(self):
        with self.assertRaises(FileNotFoundError):
            load_final_summary(self.tmp_path())

    def test_get_summary_markdown_supports_final_summary_key(self):
        markdown = get_summary_markdown({"final_summary": "# final"})

        self.assertEqual(markdown, "# final")

    def test_has_structured_summary_detects_ui_fields(self):
        self.assertTrue(has_structured_summary({"title": "요약", "topics": []}))
        self.assertFalse(has_structured_summary({"summary": "# markdown"}))

    def test_resolve_video_path_uses_existing_explicit_video(self):
        video_path = self.tmp_path() / "sample.mp4"
        video_path.write_bytes(b"fake video")

        self.assertEqual(resolve_video_path(video_path), video_path)

    def tmp_path(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        return Path(temp_dir.name)


if __name__ == "__main__":
    unittest.main()
