# modules/preprocess/audio_extractor.py

from __future__ import annotations

from pathlib import Path
from typing import Optional

from modules.preprocess.ffmpeg_utils import run_ffmpeg


def extract_audio(
    video_path: str | Path,
    audio_path: str | Path,
    sample_rate: Optional[int] = 16000,
    channels: Optional[int] = 1,
    overwrite: bool = True,
) -> Path:
    """영상 파일에서 오디오 트랙을 추출합니다.

    Args:
        video_path: 원본 영상 파일 경로입니다.
        audio_path: 추출한 오디오를 저장할 파일 경로입니다.
        sample_rate: 출력 오디오 샘플레이트입니다. ``None``이면 원본 값을 유지합니다.
        channels: 출력 오디오 채널 수입니다. ``None``이면 원본 값을 유지합니다.
        overwrite: 출력 파일이 이미 있을 때 덮어쓸지 여부입니다.

    Returns:
        추출된 오디오 파일 경로입니다.

    Raises:
        FileNotFoundError: 원본 영상 파일이 존재하지 않을 때 발생합니다.
        subprocess.CalledProcessError: ffmpeg 실행에 실패했을 때 발생합니다.
    """
    video_path = Path(video_path)
    audio_path = Path(audio_path)

    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일이 존재하지 않습니다: {video_path}")

    audio_path.parent.mkdir(parents=True, exist_ok=True)

    args = []
    if overwrite:
        args.append("-y")

    args.extend(["-i", str(video_path), "-vn", "-acodec", "pcm_s16le"])

    if sample_rate is not None:
        args.extend(["-ar", str(sample_rate)])
    if channels is not None:
        args.extend(["-ac", str(channels)])

    args.append(str(audio_path))
    run_ffmpeg(args)

    print(f"오디오 추출 완료: {audio_path}")
    return audio_path
