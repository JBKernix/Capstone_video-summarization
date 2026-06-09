from __future__ import annotations

from pathlib import Path

DEFAULT_INPUT_VIDEO_RELATIVE_PATH = Path("data") / "input" / "*.mp4"
DEFAULT_RUN_DIR_RELATIVE_PATH = Path("runs")
DEFAULT_STT_CONFIG_RELATIVE_PATH = Path("configs") / "stt_config.yaml"
DEFAULT_AUDIO_RELATIVE_PATH = Path("audio") / "audio.wav"
DEFAULT_FRAME_METADATA_RELATIVE_PATH = Path("metadata") / "frame_metadata.json"
DEFAULT_STT_JSON_RELATIVE_PATH = Path("stt") / "stt_result.json"
DEFAULT_STT_TEXT_RELATIVE_PATH = Path("stt") / "stt_result.txt"
DEFAULT_VISION_RESULT_RELATIVE_PATH = Path("vision") / "vision_result.json"


def project_path(project_root: str | Path, relative_path: str | Path) -> Path:
    """프로젝트 루트 기준 기본 경로를 반환합니다."""
    return Path(project_root) / Path(relative_path)


def run_path(run_dir: str | Path, relative_path: str | Path) -> Path:
    """run 디렉터리 기준 기본 산출물 경로를 반환합니다."""
    return Path(run_dir) / Path(relative_path)
