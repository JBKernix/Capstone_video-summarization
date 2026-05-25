# modules/preprocess/video_info.py

from __future__ import annotations

from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, Optional

from modules.preprocess.ffmpeg_utils import run_ffprobe_json


@dataclass(frozen=True)
class VideoInfo:
    """영상 파일의 기본 메타데이터를 담는 데이터 클래스입니다.

    Args:
        path: 영상 파일 경로입니다.
        duration: 영상 길이입니다. 단위는 초입니다.
        width: 영상 가로 해상도입니다.
        height: 영상 세로 해상도입니다.
        fps: 초당 프레임 수입니다.
        frame_count: 전체 프레임 수입니다. ffprobe가 제공하지 않으면 ``None``입니다.
        codec: 영상 코덱 이름입니다.
    """

    path: str
    duration: float
    width: int
    height: int
    fps: float
    frame_count: Optional[int]
    codec: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        """영상 메타데이터를 딕셔너리로 변환합니다.

        Returns:
            영상 메타데이터 딕셔너리입니다.
        """
        return asdict(self)


def _parse_fraction(value: str | None) -> float:
    """ffprobe의 분수 형태 문자열을 실수로 변환합니다."""
    if not value or value == "0/0":
        return 0.0
    return float(Fraction(value))


def get_video_info(video_path: str | Path) -> VideoInfo:
    """영상 파일에서 길이, 해상도, FPS, 프레임 수 정보를 읽습니다.

    Args:
        video_path: 정보를 추출할 영상 파일 경로입니다.

    Returns:
        영상 기본 정보를 담은 ``VideoInfo`` 객체입니다.

    Raises:
        FileNotFoundError: 영상 파일이 존재하지 않을 때 발생합니다.
        RuntimeError: 영상 스트림을 찾을 수 없을 때 발생합니다.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일이 존재하지 않습니다: {video_path}")

    data = run_ffprobe_json(
        [
            "-show_entries",
            "format=duration:stream=index,codec_type,codec_name,width,height,avg_frame_rate,nb_frames,duration",
            "-select_streams",
            "v:0",
            str(video_path),
        ]
    )

    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError(f"영상 스트림을 찾을 수 없습니다: {video_path}")

    stream = streams[0]
    format_info = data.get("format", {})

    duration_text = format_info.get("duration") or stream.get("duration") or "0"
    frame_count_text = stream.get("nb_frames")

    return VideoInfo(
        path=str(video_path),
        duration=float(duration_text),
        width=int(stream.get("width", 0)),
        height=int(stream.get("height", 0)),
        fps=_parse_fraction(stream.get("avg_frame_rate")),
        frame_count=int(frame_count_text) if frame_count_text and frame_count_text.isdigit() else None,
        codec=stream.get("codec_name"),
    )
