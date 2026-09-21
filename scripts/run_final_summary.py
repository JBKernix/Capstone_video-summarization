from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.common import (  # noqa: E402
    DEFAULT_RUN_DIR_RELATIVE_PATH,
    load_json,
    project_path,
    run_path,
    save_json,
)
from modules.llm.final_summarizer_client import GPUFinalSummaryClient  # noqa: E402
from modules.llm.summary_levels import (  # noqa: E402
    DEFAULT_SUMMARY_LEVEL,
    SUMMARY_LEVELS,
)
from scripts.run_llm_summary import (  # noqa: E402
    DEFAULT_LLM_SUMMARY_JSON_RELATIVE_PATH,
)
from scripts.run_vlm_summary import (  # noqa: E402
    DEFAULT_VLM_SUMMARY_JSON_RELATIVE_PATH,
)

DEFAULT_FINAL_SUMMARY_RELATIVE_PATH = Path("final") / "final_summary.txt"
DEFAULT_FINAL_SUMMARY_JSON_RELATIVE_PATH = Path("final") / "final_summary_result.json"


def run_final_summary_step(
    stt_summary_json_path: str | Path,
    vlm_summary_json_path: str | Path,
    output_path: str | Path,
    output_json_path: str | Path | None = None,
    summary_level: str = DEFAULT_SUMMARY_LEVEL,
) -> tuple[Path, Path]:
    output_path = Path(output_path)
    output_json_path = Path(output_json_path or output_path.with_name("final_summary_result.json"))

    client = GPUFinalSummaryClient()
    result = client.summarize_files_result(
        stt_summary_json_path=stt_summary_json_path,
        vlm_summary_json_path=vlm_summary_json_path,
        summary_level=summary_level,
    )

    result = {
        "source": {
            "stt_summary_json_path": Path(stt_summary_json_path).as_posix(),
            "vlm_summary_json_path": Path(vlm_summary_json_path).as_posix(),
        },
        **result,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result["summary"], encoding="utf-8")

    save_json(result, output_json_path)
    return output_path, output_json_path


def write_stt_only_final_summary_step(
    stt_summary_json_path: str | Path,
    output_path: str | Path,
    output_json_path: str | Path | None = None,
) -> tuple[Path, Path]:
    """VLM 요약을 만들지 않는 프리셋(예: 간단요약)에서 STT 요약을 최종 요약 대신 사용합니다.

    서버에 최종 요약 병합 요청을 보내지 않으므로 네트워크 호출과 LLM 생성이 줄어
    간단요약의 속도 이점을 그대로 유지합니다.
    """
    stt_summary_json_path = Path(stt_summary_json_path)
    output_path = Path(output_path)
    output_json_path = Path(output_json_path or output_path.with_name("final_summary_result.json"))

    stt_result = load_json(stt_summary_json_path)
    summary_text = str(stt_result.get("summary", "")).strip()
    if not summary_text:
        raise ValueError(f"STT 요약 내용이 비어 있습니다: {stt_summary_json_path}")

    result = {
        "source": {
            "stt_summary_json_path": stt_summary_json_path.as_posix(),
            "vlm_summary_json_path": None,
            "mode": "stt_only",
        },
        "summary": summary_text,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(summary_text, encoding="utf-8")

    save_json(result, output_json_path)
    return output_path, output_json_path


def parse_args() -> argparse.Namespace:
    run_dir = project_path(PROJECT_ROOT, DEFAULT_RUN_DIR_RELATIVE_PATH)

    parser = argparse.ArgumentParser(
        description="Request final summary from STT and VLM summary outputs."
    )
    parser.add_argument(
        "--stt-summary-json",
        default=str(run_path(run_dir, DEFAULT_LLM_SUMMARY_JSON_RELATIVE_PATH)),
        help="Path to the STT summary result JSON file.",
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
    parser.add_argument(
        "--summary-level",
        choices=SUMMARY_LEVELS,
        default=DEFAULT_SUMMARY_LEVEL,
        help="요약 크기/속도 프리셋입니다. (simple/standard/detailed)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path, output_json_path = run_final_summary_step(
        stt_summary_json_path=args.stt_summary_json,
        vlm_summary_json_path=args.vlm_summary_json,
        output_path=args.output,
        output_json_path=args.output_json,
        summary_level=args.summary_level,
    )
    print(f"Final summary saved: {output_path}")
    print(f"Final summary JSON saved: {output_json_path}")


if __name__ == "__main__":
    main()
