from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.common import (  # noqa: E402
    DEFAULT_OCR_RESULT_RELATIVE_PATH,
    DEFAULT_RUN_DIR_RELATIVE_PATH,
    project_path,
    run_path,
)
from modules.llm.vlm_summarizer_client import GPUVLMClient  # noqa: E402

DEFAULT_VLM_SUMMARY_RELATIVE_PATH = Path("vlm") / "vlm_summary.txt"
DEFAULT_VLM_SUMMARY_JSON_RELATIVE_PATH = Path("vlm") / "vlm_summary_result.json"


def _format_vlm_summary_text(results: list[dict]) -> str:
    sections = []
    for index, result in enumerate(results):
        frame_id = result.get("frame_id", index)
        timestamp = result.get("timestamp")
        title = f"## Frame {frame_id}"
        if timestamp is not None:
            title += f" ({timestamp}s)"
        summary = str(result.get("vlm_summary", "")).strip()
        sections.append(f"{title}\n\n{summary}")
    return "\n\n".join(sections).strip() + "\n"


def run_vlm_summary_step(
    ocr_json_path: str | Path,
    output_path: str | Path,
    output_json_path: str | Path | None = None,
    max_new_tokens: int = 512,
) -> tuple[Path, Path]:
    ocr_json_path = Path(ocr_json_path)
    output_path = Path(output_path)
    output_json_path = Path(output_json_path or output_path.with_name("vlm_summary_result.json"))

    client = GPUVLMClient()
    results = client.summarize_ocr_file(
        ocr_json_path=ocr_json_path,
        max_new_tokens=max_new_tokens,
    )
    result_payload = {
        "source": {
            "ocr_json_path": ocr_json_path.as_posix(),
            "frame_count": len(results),
        },
        "results": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_format_vlm_summary_text(results), encoding="utf-8")

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(result_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path, output_json_path


def parse_args() -> argparse.Namespace:
    run_dir = project_path(PROJECT_ROOT, DEFAULT_RUN_DIR_RELATIVE_PATH)

    parser = argparse.ArgumentParser(description="Request frame summaries from the GPU VLM server.")
    parser.add_argument(
        "--ocr-json",
        default=str(run_path(run_dir, DEFAULT_OCR_RESULT_RELATIVE_PATH)),
        help="Path to the OCR result JSON file.",
    )
    parser.add_argument(
        "--output",
        default=str(run_path(run_dir, DEFAULT_VLM_SUMMARY_RELATIVE_PATH)),
        help="Path to save the VLM summary text.",
    )
    parser.add_argument(
        "--output-json",
        default=str(run_path(run_dir, DEFAULT_VLM_SUMMARY_JSON_RELATIVE_PATH)),
        help="Path to save the full VLM result JSON.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=512,
        help="Maximum generated tokens per frame (1-2048).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path, output_json_path = run_vlm_summary_step(
        ocr_json_path=args.ocr_json,
        output_path=args.output,
        output_json_path=args.output_json,
        max_new_tokens=args.max_new_tokens,
    )
    print(f"VLM summary saved: {output_path}")
    print(f"VLM summary JSON saved: {output_json_path}")


if __name__ == "__main__":
    main()
