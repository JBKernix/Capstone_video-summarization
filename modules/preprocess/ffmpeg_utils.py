# modules/preprocess/ffmpeg_utils.py

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence


SHOWINFO_TIME_PATTERN = re.compile(r"pts_time:(?P<time>[0-9]+(?:\.[0-9]+)?)")
FFMPEG_TIME_PATTERN = re.compile(r"^(\d+):(\d{2}):(\d{2}(?:\.\d+)?)$")


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

    try:
        return subprocess.run(
            list(args),
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        command = " ".join(str(arg) for arg in exc.cmd)
        stdout = exc.stdout.strip() if exc.stdout else ""
        stderr = exc.stderr.strip() if exc.stderr else ""
        details = [
            f"Command failed with exit code {exc.returncode}: {command}",
        ]
        if stdout:
            details.append(f"stdout:\n{stdout}")
        if stderr:
            details.append(f"stderr:\n{stderr}")
        raise RuntimeError("\n".join(details)) from exc


def run_ffmpeg(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """ffmpeg 명령어를 실행합니다.

    Args:
        args: ``ffmpeg`` 뒤에 붙일 인자 목록입니다.

    Returns:
        ``subprocess.CompletedProcess`` 객체입니다.
    """
    ffmpeg_args = list(args)
    if "-nostdin" not in ffmpeg_args:
        ffmpeg_args.insert(0, "-nostdin")
    return run_command([ensure_command("ffmpeg"), *ffmpeg_args])


def _parse_ffmpeg_time(time_text: str) -> Optional[float]:
    """ffmpeg ``-progress`` 출력의 ``HH:MM:SS.ffffff`` 형식 시각을 초 단위로 변환합니다."""
    match = FFMPEG_TIME_PATTERN.match(time_text.strip())
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def run_ffmpeg_with_progress(
    args: Sequence[str],
    total_duration_sec: float,
    on_progress: Callable[[float], None],
) -> subprocess.CompletedProcess[str]:
    """ffmpeg를 실행하며 ``-progress`` 출력을 파싱해 진행률(%)을 콜백으로 전달합니다.

    Args:
        args: ``ffmpeg`` 뒤에 붙일 인자 목록입니다.
        total_duration_sec: 진행률 계산 기준이 되는 전체 길이(초)입니다. 0 이하이면 진행률을 계산하지 않습니다.
        on_progress: 0~100 사이의 진행률(%)을 전달받는 콜백입니다.

    Returns:
        ``subprocess.CompletedProcess`` 객체입니다. ``stdout``은 비어 있고 ``stderr``에 ffmpeg 로그가 담깁니다.

    Raises:
        RuntimeError: ffmpeg 실행이 실패했을 때 발생합니다.
    """
    ffmpeg_args = [arg for arg in args if arg != "-nostdin"]
    command = [
        ensure_command("ffmpeg"),
        "-nostdin",
        "-progress",
        "pipe:1",
        "-nostats",
        *ffmpeg_args,
    ]

    process = subprocess.Popen(
        command,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert process.stdout is not None
    for line in process.stdout:
        line = line.strip()
        if not line or "=" not in line:
            continue

        key, _, value = line.partition("=")
        if key == "out_time" and total_duration_sec > 0:
            seconds = _parse_ffmpeg_time(value)
            if seconds is not None:
                on_progress(min(100.0, seconds / total_duration_sec * 100))
        elif key == "progress" and value == "end":
            on_progress(100.0)

    stderr_text = process.stderr.read() if process.stderr else ""
    returncode = process.wait()

    if returncode != 0:
        details = [f"Command failed with exit code {returncode}: {' '.join(command)}"]
        if stderr_text.strip():
            details.append(f"stderr:\n{stderr_text.strip()}")
        raise RuntimeError("\n".join(details))

    return subprocess.CompletedProcess(command, returncode, stdout="", stderr=stderr_text)


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
