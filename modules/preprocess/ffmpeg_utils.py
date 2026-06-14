# modules/preprocess/ffmpeg_utils.py

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, List, Sequence


SHOWINFO_TIME_PATTERN = re.compile(r"pts_time:(?P<time>[0-9]+(?:\.[0-9]+)?)")


def ensure_command(command: str) -> str:
    """외부 실행 파일이 PATH에 등록되어 있는지 확인합니다.

    Args:
        command: 확인할 실행 파일 이름입니다. 예: ``ffmpeg``, ``ffprobe``.

    Returns:
        PATH에서 찾은 실행 파일 경로입니다.

    Raises:
        RuntimeError: 실행 파일을 찾을 수 없을 때 발생합니다.
    """
    resolved = shutil.which(command)
    if resolved is None:
        raise RuntimeError(f"필수 실행 파일을 찾을 수 없습니다: {command}")
    return resolved


def run_command(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """명령어를 실행하고 표준 출력과 오류 출력을 문자열로 반환합니다.

    Args:
        args: 실행할 명령어와 인자 목록입니다.

    Returns:
        ``subprocess.CompletedProcess`` 객체입니다.

    Raises:
        ValueError: 명령어 인자 목록이 비어 있을 때 발생합니다.
        subprocess.CalledProcessError: 명령어 실행이 실패했을 때 발생합니다.
    """
    if not args:
        raise ValueError("실행할 명령어가 비어 있습니다.")

    return subprocess.run(
        list(args),
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_ffmpeg(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """ffmpeg 명령어를 실행합니다.

    Args:
        args: ``ffmpeg`` 뒤에 붙일 인자 목록입니다.

    Returns:
        ``subprocess.CompletedProcess`` 객체입니다.
    """
    return run_command([ensure_command("ffmpeg"), *args])


def ensure_mp4_video(video_path: str | Path, output_dir: str | Path) -> Path:
    """Convert input video to mp4 when its extension is not .mp4."""
    video_path = Path(video_path)
    output_dir = Path(output_dir)

    if not video_path.exists():
        raise FileNotFoundError(f"Video file does not exist: {video_path}")

    if video_path.suffix.lower() == ".mp4":
        return video_path

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_path.stem}.mp4"

    run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )

    print(f"MP4 conversion complete: {output_path}")
    return output_path


def run_ffprobe_json(args: Sequence[str]) -> dict:
    """ffprobe 명령어를 실행하고 JSON 출력을 딕셔너리로 변환합니다.

    Args:
        args: ``ffprobe`` 뒤에 붙일 인자 목록입니다.

    Returns:
        ffprobe JSON 출력을 파싱한 딕셔너리입니다.
    """
    result = run_command(
        [
            ensure_command("ffprobe"),
            "-v",
            "error",
            "-print_format",
            "json",
            *args,
        ]
    )
    return json.loads(result.stdout)


def parse_showinfo_timestamps(stderr: str) -> List[float]:
    """FFmpeg showinfo 로그에서 선택된 프레임의 timestamp를 추출합니다."""
    return [float(match.group("time")) for match in SHOWINFO_TIME_PATTERN.finditer(stderr)]


def remove_files(files: Iterable[Path]) -> None:
    """파일 목록을 받아 존재하는 파일만 삭제합니다.

    Args:
        files: 삭제할 파일 경로 목록입니다.
    """
    for file_path in files:
        if file_path.exists():
            file_path.unlink()
