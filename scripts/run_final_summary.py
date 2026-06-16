from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.common import DEFAULT_RUN_DIR_RELATIVE_PATH, project_path, run_path  # noqa: E402
from modules.llm.final_summarizer_client import GPUFinalSummaryClient  # noqa: E402
from scripts.run_llm_summary import (  # noqa: E402
    DEFAULT_LLM_SUMMARY_JSON_RELATIVE_PATH,
    DEFAULT_LLM_SUMMARY_RELATIVE_PATH,
)
from scripts.run_vlm_summary import (  # noqa: E402
    DEFAULT_VLM_SUMMARY_JSON_RELATIVE_PATH,
    DEFAULT_VLM_SUMMARY_RELATIVE_PATH,
)

DEFAULT_FINAL_SUMMARY_RELATIVE_PATH = Path("final") / "final_summary.txt"
DEFAULT_FINAL_SUMMARY_JSON_RELATIVE_PATH = Path("final") / "final_summary_result.json"


def run_final_summary_step(
    stt_summary_path: str | Path,
    stt_summary_json_path: str | Path,
    vlm_summary_path: str | Path,
    vlm_summary_json_path: str | Path,
    output_path: str | Path,
    output_json_path: str | Path | None = None,
) -> tuple[Path, Path]:
    output_path = Path(output_path)
    output_json_path = Path(output_json_path or output_path.with_name("final_summary_result.json"))

    client = GPUFinalSummaryClient()
    result = client.summarize_files_result(
        stt_summary_path=stt_summary_path,
        stt_summary_json_path=stt_summary_json_path,
        vlm_summary_path=vlm_summary_path,
        vlm_summary_json_path=vlm_summary_json_path,
    )

    result = {
        "source": {
            "stt_summary_path": Path(stt_summary_path).as_posix(),
            "stt_summary_json_path": Path(stt_summary_json_path).as_posix(),
            "vlm_summary_path": Path(vlm_summary_path).as_posix(),
            "vlm_summary_json_path": Path(vlm_summary_json_path).as_posix(),
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

    parser = argparse.ArgumentParser(
        description="Request final summary from STT and VLM summary outputs."
    )
    parser.add_argument(
        "--stt-summary",
        default=str(run_path(run_dir, DEFAULT_LLM_SUMMARY_RELATIVE_PATH)),
        help="Path to the STT summary text file.",
    )
    parser.add_argument(
        "--stt-summary-json",
        default=str(run_path(run_dir, DEFAULT_LLM_SUMMARY_JSON_RELATIVE_PATH)),
        help="Path to the STT summary result JSON file.",
    )
    parser.add_argument(
        "--vlm-summary",
        default=str(run_path(run_dir, DEFAULT_VLM_SUMMARY_RELATIVE_PATH)),
        help="Path to the VLM summary text file.",
    )
    parser.add_argument(
        "--vlm-summary-json",
        default=str(run_path(run_dir, DEFAULT_VLM_SUMMARY_JSON_RELATIVE_PATH)),
        help="Path to the VLM summary result JSON file.",
    )
    parser.add_argument(
        "--output",
        default=str(run_path(run_dir, DEFAULT_FINAL_SUMMARY_RELATIVE_PATH)),
        help="Path to save the final summary text.",
    )
    parser.add_argument(
        "--output-json",
        default=str(run_path(run_dir, DEFAULT_FINAL_SUMMARY_JSON_RELATIVE_PATH)),
        help="Path to save the full final summary result JSON.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path, output_json_path = run_final_summary_step(
        stt_summary_path=args.stt_summary,
        stt_summary_json_path=args.stt_summary_json,
        vlm_summary_path=args.vlm_summary,
        vlm_summary_json_path=args.vlm_summary_json,
        output_path=args.output,
        output_json_path=args.output_json,
    )
    print(f"Final summary saved: {output_path}")
    print(f"Final summary JSON saved: {output_json_path}")


if __name__ == "__main__":
    main()
