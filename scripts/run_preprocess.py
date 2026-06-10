from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.common import (  # noqa: E402
    DEFAULT_FRAME_METADATA_RELATIVE_PATH,
    DEFAULT_INPUT_VIDEO_RELATIVE_PATH,
    DEFAULT_RUN_DIR_RELATIVE_PATH,
    project_path,
    resolve_path_pattern,
    run_path,
)
from modules.preprocess import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_SAMPLING_METHOD,
    DEFAULT_SCENE_THRESHOLD,
    SAMPLING_METHOD_CHOICES,
    ensure_mp4_video,
    get_video_info,
    sample_frames,
)


def parse_args():
    """프레임 샘플링 실행에 사용할 명령행 인자를 파싱합니다."""
    parser = argparse.ArgumentParser(description="영상에서 대표 프레임과 메타데이터를 생성합니다.")

    parser.add_argument(
        "--video",
        default=str(project_path(PROJECT_ROOT, DEFAULT_INPUT_VIDEO_RELATIVE_PATH)),
        help=f"프레임을 추출할 영상 파일 경로입니다. 기본값은 {DEFAULT_INPUT_VIDEO_RELATIVE_PATH.as_posix()}입니다.",
    )
    parser.add_argument(
        "--run-dir",
        default=str(project_path(PROJECT_ROOT, DEFAULT_RUN_DIR_RELATIVE_PATH)),
        help="프레임 이미지와 메타데이터를 저장할 실행 디렉터리입니다.",
    )
    parser.add_argument(
        "--method",
        choices=SAMPLING_METHOD_CHOICES,
        default=DEFAULT_SAMPLING_METHOD,
        help="프레임 추출 방식입니다. interval, scene_change, interval_scene_change를 사용할 수 있습니다.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help="일정 간격 추출에서 사용할 시간 간격입니다. 단위는 초입니다.",
    )
    parser.add_argument(
        "--scene-threshold",
        type=float,
        default=DEFAULT_SCENE_THRESHOLD,
        help="장면 전환 추출에서 사용할 임계값입니다.",
    )

    return parser.parse_args()


def main():
    """영상에서 프레임을 추출하고 frame_metadata.json을 생성합니다."""
    args = parse_args()

    video_path = resolve_path_pattern(args.video)
    run_dir = Path(args.run_dir)
    video_path = ensure_mp4_video(video_path, run_dir / "input")

    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일이 존재하지 않습니다: {video_path}")

    video_info = get_video_info(video_path)
    print(
        "영상 정보 확인 완료. "
        f"길이: {video_info.duration:.2f}초, "
        f"해상도: {video_info.width}x{video_info.height}, "
        f"FPS: {video_info.fps:.2f}"
    )

    metadata = sample_frames(
        video_path=video_path,
        run_dir=run_dir,
        method=args.method,
        interval_seconds=args.interval_seconds,
        scene_threshold=args.scene_threshold,
        project_root=PROJECT_ROOT,
    )

    metadata_path = run_path(run_dir, DEFAULT_FRAME_METADATA_RELATIVE_PATH)
    print(f"프레임 샘플링 완료: {metadata_path}")
    print(f"추출 프레임 수: {len(metadata)}")


if __name__ == "__main__":
    main()
