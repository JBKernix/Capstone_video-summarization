from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FinalSummary:
    mode: str
    content: dict[str, Any] | str
    source_path: Path


def load_final_summary(final_dir: str | Path) -> FinalSummary:
    """Load the final summary from JSON first, then fall back to Markdown text."""
    final_dir = Path(final_dir)
    json_path = final_dir / "final_summary_result.json"
    txt_path = final_dir / "final_summary.txt"

    if json_path.exists():
        with json_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return FinalSummary(mode="json", content=data, source_path=json_path)

    if txt_path.exists():
        return FinalSummary(
            mode="markdown",
            content=txt_path.read_text(encoding="utf-8"),
            source_path=txt_path,
        )

    raise FileNotFoundError(
        f"Final summary file not found. Checked: {json_path} and {txt_path}"
    )


def get_summary_markdown(summary_data: dict[str, Any]) -> str:
    """Return Markdown summary text from common final-summary JSON shapes."""
    for key in ("summary", "final_summary"):
        value = summary_data.get(key)
        if isinstance(value, str) and value.strip():
            return value

    return ""


def has_structured_summary(summary_data: dict[str, Any]) -> bool:
    return any(
        summary_data.get(key)
        for key in ("title", "main_topic", "topics", "conclusion", "keywords")
    )
