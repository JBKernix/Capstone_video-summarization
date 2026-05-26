import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.preprocess import extract_audio, get_video_info, sample_frames
from modules.vision import analyze_frames_metadata


def parse_args():
    """전체 영상 요약 파이프라인 실행에 필요한 명령줄 인자를 해석합니다."""
    parser = argparse.ArgumentParser(
        description="영상 전처리, 오디오 추출, 시각 정보 분석을 순서대로 실행합니다."
    )
    parser.add_argument(
        "--video",
        default=str(PROJECT_ROOT / "data" / "input" / "input.mp4"),
        help="분석할 원본 영상 파일 경로입니다. 기본값은 data/input/input.mp4입니다.",
    )
    parser.add_argument(
        "--run-dir",
        default=str(PROJECT_ROOT / "runs" / "sample"),
        help="파이프라인 결과를 저장할 실행 디렉터리입니다.",
    )
    parser.add_argument(
        "--method",
        choices=["interval", "scene_change"],
        default="interval",
        help="프레임 추출 방식입니다. interval 또는 scene_change를 사용할 수 있습니다.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=5.0,
        help="interval 방식에서 프레임을 추출할 시간 간격입니다. 단위는 초입니다.",
    )
    parser.add_argument(
        "--scene-threshold",
        type=float,
        default=0.35,
        help="scene_change 방식에서 사용할 장면 전환 임계값입니다.",
    )
    parser.add_argument(
        "--ocr-lang",
        default="korean",
        help="PaddleOCR에 전달할 언어 코드입니다.",
    )
    parser.add_argument(
        "--skip-vision",
        action="store_true",
        help="시각 정보 분석 단계를 건너뜁니다.",
    )
    return parser.parse_args()


def run_preprocess_step(
    video_path: Path,
    run_dir: Path,
    method: str,
    interval_seconds: float,
    scene_threshold: float,
) -> Path:
    """영상 정보를 확인하고 프레임 이미지와 메타데이터를 생성합니다."""
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
        method=method,
        interval_seconds=interval_seconds,
        scene_threshold=scene_threshold,
        project_root=PROJECT_ROOT,
    )

    metadata_path = run_dir / "metadata" / "frame_metadata.json"
    print(f"프레임 추출 완료: {metadata_path}")
    print(f"추출 프레임 수: {len(metadata)}")
    return metadata_path


def run_audio_step(video_path: Path, run_dir: Path) -> Path:
    """영상에서 오디오 파일을 추출합니다."""
    audio_path = run_dir / "audio" / "audio.wav"
    return extract_audio(video_path, audio_path)


def run_vision_step(metadata_path: Path, run_dir: Path, ocr_lang: str) -> Path:
    """프레임 메타데이터를 분석해 시각 정보 결과를 생성합니다."""
    output_path = run_dir / "vision" / "vision_result.json"
    analyze_frames_metadata(
        metadata_path=str(metadata_path),
        output_path=str(output_path),
        lang=ocr_lang,
    )
    print(f"시각 정보 추출 완료: {output_path}")
    return output_path


def main():
    """구현되어 있는 파이프라인 단계를 순서대로 실행합니다."""
    args = parse_args()
    video_path = Path(args.video)
    run_dir = Path(args.run_dir)

    print("[1/3] 영상 전처리를 시작합니다.")
    metadata_path = run_preprocess_step(
        video_path=video_path,
        run_dir=run_dir,
        method=args.method,
        interval_seconds=args.interval_seconds,
        scene_threshold=args.scene_threshold,
    )

    print("[2/3] 오디오 추출을 시작합니다.")
    audio_path = run_audio_step(video_path=video_path, run_dir=run_dir)

    if args.skip_vision:
        print("[3/3] 시각 정보 분석을 건너뜁니다.")
        vision_path = None
    else:
        print("[3/3] 시각 정보 분석을 시작합니다.")
        vision_path = run_vision_step(
            metadata_path=metadata_path,
            run_dir=run_dir,
            ocr_lang=args.ocr_lang,
        )

    print("파이프라인 실행이 완료되었습니다.")
    print(f"프레임 메타데이터: {metadata_path}")
    print(f"오디오 파일: {audio_path}")
    if vision_path is not None:
        print(f"시각 정보 결과: {vision_path}")

    print("STT와 요약 단계는 현재 구현 파일이 비어 있어 자동 실행에 포함하지 않았습니다.")


if __name__ == "__main__":
    main()
