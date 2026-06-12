from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.common import (  # noqa: E402
    DEFAULT_RUN_DIR_RELATIVE_PATH,
    DEFAULT_STT_JSON_RELATIVE_PATH,
    project_path,
    run_path,
)
from modules.llm.stt_summarizer_client import GPULLMClient  # noqa: E402

DEFAULT_LLM_SUMMARY_RELATIVE_PATH = Path("llm") / "stt_summary.txt"
DEFAULT_LLM_SUMMARY_JSON_RELATIVE_PATH = Path("llm") / "stt_summary_result.json"


def run_llm_summary_step(
    stt_json_path: str | Path,
    output_path: str | Path,
    output_json_path: str | Path | None = None,
) -> tuple[Path, Path]:
    stt_json_path = Path(stt_json_path)
    output_path = Path(output_path)
    output_json_path = Path(output_json_path or output_path.with_name("stt_summary_result.json"))

    client = GPULLMClient()
    result = client.summarize_stt_file_result(stt_json_path=stt_json_path)
    stt_result = json.loads(stt_json_path.read_text(encoding="utf-8-sig"))
    result = {
        "source": {
            "language": stt_result.get("language"),
            "duration_sec": stt_result.get("duration_sec"),
            "segment_count": stt_result.get("segment_count"),
        },
        **result,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result["summary"], encoding="utf-8")

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path, output_json_path


def parse_args() -> argparse.Namespace:
    run_dir = project_path(PROJECT_ROOT, DEFAULT_RUN_DIR_RELATIVE_PATH)

    parser = argparse.ArgumentParser(description="Request STT summary from the GPU LLM server.")
    parser.add_argument(
        "--stt-json",
        default=str(run_path(run_dir, DEFAULT_STT_JSON_RELATIVE_PATH)),
        help="Path to the STT JSON file.",
    )
    parser.add_argument(
        "--output",
        default=str(run_path(run_dir, DEFAULT_LLM_SUMMARY_RELATIVE_PATH)),
        help="Path to save the LLM summary text.",
    )
    parser.add_argument(
        "--output-json",
        default=str(run_path(run_dir, DEFAULT_LLM_SUMMARY_JSON_RELATIVE_PATH)),
        help="Path to save the full LLM summary result JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path, output_json_path = run_llm_summary_step(
        stt_json_path=args.stt_json,
        output_path=args.output,
        output_json_path=args.output_json,
    )
    print(f"LLM summary saved: {output_path}")
    print(f"LLM summary JSON saved: {output_json_path}")


if __name__ == "__main__":
    main()
