# modules/preprocess/youtube_downloader.py

from __future__ import annotations

import re
from pathlib import Path

YOUTUBE_URL_PATTERN = re.compile(
    r"^https?://(www\.)?(youtube\.com/(watch\?v=|shorts/|embed/)|youtu\.be/)",
    re.IGNORECASE,
)


def is_youtube_url(url: str) -> bool:
    """주어진 문자열이 유튜브 영상 링크 형태인지 확인합니다."""
    return bool(YOUTUBE_URL_PATTERN.match(url.strip()))


def download_youtube_video(url: str, output_path: str | Path) -> tuple[Path, str]:
    """유튜브 영상을 다운로드해 mp4 파일로 저장합니다.

    Args:
        url: 다운로드할 유튜브 영상 링크입니다.
        output_path: 저장할 파일 경로입니다. 확장자는 무시되고 항상 mp4로 저장됩니다.

    Returns:
        다운로드된 mp4 파일의 실제 경로와 영상 제목의 튜플입니다.

    Raises:
        ValueError: 유튜브 링크 형식이 아닐 때 발생합니다.
        ImportError: yt-dlp 패키지가 설치되어 있지 않을 때 발생합니다.
        RuntimeError: 다운로드에 실패했을 때 발생합니다.
    """
    if not is_youtube_url(url):
        raise ValueError(f"유효한 유튜브 링크가 아닙니다: {url}")

    try:
        import yt_dlp
    except ImportError as exc:
        raise ImportError(
            "유튜브 다운로드를 사용하려면 yt-dlp 패키지가 필요합니다. "
            "예: pip install yt-dlp"
        ) from exc

    output_path = Path(output_path).with_suffix(".mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ydl_options = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(output_path.with_suffix("")) + ".%(ext)s",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }

    with yt_dlp.YoutubeDL(ydl_options) as downloader:
        try:
            info = downloader.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            raise RuntimeError(f"유튜브 영상 다운로드에 실패했습니다: {exc}") from exc

    if not output_path.exists():
        raise RuntimeError(f"다운로드된 파일을 찾을 수 없습니다: {output_path}")

    title = str((info or {}).get("title") or "").strip()
    return output_path, title
