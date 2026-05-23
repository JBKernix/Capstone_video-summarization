from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.vision.vision_formatter import analyze_frames_metadata


def main():
    """샘플 실행 디렉터리의 프레임 메타데이터를 분석해 vision_result.json을 생성합니다."""
    run_dir = PROJECT_ROOT / "runs" / "sample"

    metadata_path = run_dir / "metadata" / "frame_metadata.json"
    output_path = run_dir / "vision" / "vision_result.json"

    analyze_frames_metadata(
        metadata_path=str(metadata_path),
        output_path=str(output_path),
        lang="korean",
    )

    print(f"시각 정보 추출 완료: {output_path}")


if __name__ == "__main__":
    main()