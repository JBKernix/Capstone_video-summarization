from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.common import (
    DEFAULT_FRAME_METADATA_RELATIVE_PATH,
    DEFAULT_RUN_DIR_RELATIVE_PATH,
    DEFAULT_OCR_RESULT_RELATIVE_PATH,
    project_path,
    run_path,
)
from modules.ocr import DEFAULT_OCR_LANGUAGE, analyze_frames_metadata


def main():
    """샘플 실행 디렉터리의 프레임 메타데이터를 분석해 ocr_result.json을 생성합니다."""
    run_dir = project_path(PROJECT_ROOT, DEFAULT_RUN_DIR_RELATIVE_PATH)

    metadata_path = run_path(run_dir, DEFAULT_FRAME_METADATA_RELATIVE_PATH)
    output_path = run_path(run_dir, DEFAULT_OCR_RESULT_RELATIVE_PATH)

    analyze_frames_metadata(
        metadata_path=str(metadata_path),
        output_path=str(output_path),
        lang=DEFAULT_OCR_LANGUAGE,
    )

    print(f"OCR 결과 저장 완료: {output_path}")


if __name__ == "__main__":
    main()
