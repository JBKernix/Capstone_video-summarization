# modules/preprocess/frame_sampler.py

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional

from modules.common import DEFAULT_FRAME_METADATA_RELATIVE_PATH, run_path
from modules.preprocess.ffmpeg_utils import (
    parse_showinfo_timestamps,
    remove_files,
    run_ffmpeg,
)
from modules.preprocess.video_info import get_video_info

SamplingMethod = Literal["interval", "scene_change", "interval_scene_change"]
SAMPLING_METHOD_CHOICES: tuple[str, ...] = ("interval", "scene_change", "interval_scene_change")
DEFAULT_SAMPLING_METHOD: SamplingMethod = "scene_change"
DEFAULT_INTERVAL_SECONDS = 60.0
DEFAULT_SCENE_THRESHOLD = 0.7
DEFAULT_COMBINED_MIN_GAP_SECONDS = 1.0


@dataclass(frozen=True)
class FrameMetadata:
    """추출된 프레임 하나의 메타데이터입니다.

    Args:
        frame_id: 프레임 식별자입니다.
        timestamp: 영상 내 프레임 시간입니다. 단위는 초입니다.
        image_path: 저장된 프레임 이미지 경로입니다.
        sampling_method: 프레임 추출 방식입니다.
    """

    frame_id: int
    timestamp: float
    image_path: str
    sampling_method: SamplingMethod

    def to_dict(self) -> Dict[str, object]:
        """프레임 메타데이터를 JSON 저장 가능한 딕셔너리로 변환합니다.

        Returns:
            ``frame_id``, ``timestamp``, ``image_path``, ``sampling_method``를 담은 딕셔너리입니다.
        """
        return {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "image_path": self.image_path,
            "sampling_method": self.sampling_method,
        }


def _project_relative(path: Path, project_root: Path) -> str:
    """경로를 프로젝트 루트 기준 상대 경로로 변환합니다."""
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _write_metadata(metadata: List[FrameMetadata], metadata_path: str | Path) -> None:
    """프레임 메타데이터 목록을 JSON 파일로 저장합니다."""
    metadata_path = Path(metadata_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_path.open("w", encoding="utf-8") as f:
        json.dump([item.to_dict() for item in metadata], f, ensure_ascii=False, indent=2)

    print(f"프레임 메타데이터 저장 완료: {metadata_path}")


def _reindex_metadata(metadata: List[FrameMetadata]) -> List[FrameMetadata]:
    """프레임 메타데이터의 frame_id를 시간순으로 다시 부여합니다."""
    return [
        FrameMetadata(
            frame_id=index,
            timestamp=item.timestamp,
            image_path=item.image_path,
            sampling_method=item.sampling_method,
        )
        for index, item in enumerate(sorted(metadata, key=lambda item: item.timestamp))
    ]


def _merge_frame_metadata(
    interval_metadata: List[FrameMetadata],
    scene_metadata: List[FrameMetadata],
    min_gap_seconds: float,
) -> List[FrameMetadata]:
    """interval 결과를 기본으로 scene_change 결과를 추가하고 가까운 중복을 제거합니다."""
    if min_gap_seconds < 0:
        raise ValueError("프레임 병합 최소 간격은 0 이상이어야 합니다.")

    merged: List[FrameMetadata] = []
    for item in sorted([*interval_metadata, *scene_metadata], key=lambda item: item.timestamp):
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(merged)
                if abs(existing.timestamp - item.timestamp) < min_gap_seconds
            ),
            None,
        )
        if duplicate_index is None:
            merged.append(item)
            continue

        existing = merged[duplicate_index]
        if existing.sampling_method == "interval" and item.sampling_method == "scene_change":
            merged[duplicate_index] = item

    return _reindex_metadata(merged)


def sample_interval_frames(
    video_path: str | Path,
    frames_dir: str | Path,
    metadata_path: str | Path,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    project_root: Optional[str | Path] = None,
    image_prefix: str = "frame",
) -> List[FrameMetadata]:
    """일정 시간 간격으로 프레임 이미지를 추출하고 메타데이터를 저장합니다.

    Args:
        video_path: 프레임을 추출할 영상 파일 경로입니다.
        frames_dir: 추출된 이미지 파일을 저장할 디렉터리입니다.
        metadata_path: 프레임 메타데이터 JSON을 저장할 경로입니다.
        interval_seconds: 프레임 추출 간격입니다. 단위는 초입니다.
        project_root: ``image_path``를 상대 경로로 만들 기준 디렉터리입니다.
        image_prefix: 저장할 이미지 파일명 접두사입니다.

    Returns:
        추출된 프레임 메타데이터 목록입니다.

    Raises:
        ValueError: 프레임 추출 간격이 0 이하일 때 발생합니다.
        FileNotFoundError: 영상 파일이 존재하지 않을 때 발생합니다.
    """
    if interval_seconds <= 0:
        raise ValueError("프레임 추출 간격은 0보다 커야 합니다.")

    video_path = Path(video_path)
    frames_dir = Path(frames_dir)
    project_root = Path(project_root) if project_root else Path.cwd()

    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일이 존재하지 않습니다: {video_path}")

    frames_dir.mkdir(parents=True, exist_ok=True)
    remove_files(frames_dir.glob(f"{image_prefix}_*.jpg"))

    output_pattern = frames_dir / f"{image_prefix}_%06d.jpg"
    fps_value = 1.0 / interval_seconds

    run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={fps_value}",
            "-q:v",
            "2",
            str(output_pattern),
        ]
    )

    image_paths = sorted(frames_dir.glob(f"{image_prefix}_*.jpg"))
    metadata = [
        FrameMetadata(
            frame_id=index,
            timestamp=round(index * interval_seconds, 3),
            image_path=_project_relative(image_path, project_root),
            sampling_method="interval",
        )
        for index, image_path in enumerate(image_paths)
    ]

    _write_metadata(metadata, metadata_path)
    print(f"일정 간격 프레임 추출 완료. 추출 프레임 수: {len(metadata)}")
    return metadata


def sample_interval_scene_change_frames(
    video_path: str | Path,
    frames_dir: str | Path,
    metadata_path: str | Path,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
    project_root: Optional[str | Path] = None,
    min_gap_seconds: float = DEFAULT_COMBINED_MIN_GAP_SECONDS,
) -> List[FrameMetadata]:
    """interval 프레임을 기본으로 추출하고 scene_change 프레임을 추가 보강합니다.

    Args:
        video_path: 프레임을 추출할 영상 파일 경로입니다.
        frames_dir: 추출된 이미지 파일을 저장할 디렉터리입니다.
        metadata_path: 병합된 프레임 메타데이터 JSON을 저장할 경로입니다.
        interval_seconds: 일정 간격 추출에서 사용할 시간 간격입니다.
        scene_threshold: 장면 전환 추출에서 사용할 임계값입니다.
        project_root: ``image_path``를 상대 경로로 만들 기준 디렉터리입니다.
        min_gap_seconds: 너무 가까운 interval/scene_change 프레임을 중복으로 볼 시간 간격입니다.

    Returns:
        interval과 scene_change 결과를 병합한 프레임 메타데이터 목록입니다.
    """
    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    remove_files(frames_dir.glob("frame_*.jpg"))
    remove_files(frames_dir.glob("interval_*.jpg"))
    remove_files(frames_dir.glob("scene_*.jpg"))

    interval_metadata = sample_interval_frames(
        video_path=video_path,
        frames_dir=frames_dir,
        metadata_path=metadata_path,
        interval_seconds=interval_seconds,
        project_root=project_root,
        image_prefix="interval",
    )
    scene_metadata = sample_scene_change_frames(
        video_path=video_path,
        frames_dir=frames_dir,
        metadata_path=metadata_path,
        threshold=scene_threshold,
        project_root=project_root,
        image_prefix="scene",
    )
    metadata = _merge_frame_metadata(interval_metadata, scene_metadata, min_gap_seconds)

    _write_metadata(metadata, metadata_path)
    print(
        "interval + scene_change 프레임 추출 완료. "
        f"interval: {len(interval_metadata)}, scene_change: {len(scene_metadata)}, 병합 후: {len(metadata)}"
    )
    return metadata


def sample_scene_change_frames(
    video_path: str | Path,
    frames_dir: str | Path,
    metadata_path: str | Path,
    threshold: float = DEFAULT_SCENE_THRESHOLD,
    project_root: Optional[str | Path] = None,
    image_prefix: str = "scene",
    min_scene_gap_seconds: float = 1.0,
) -> List[FrameMetadata]:
    """장면 전환으로 판단되는 프레임 이미지를 추출하고 메타데이터를 저장합니다.

    Args:
        video_path: 프레임을 추출할 영상 파일 경로입니다.
        frames_dir: 추출된 이미지 파일을 저장할 디렉터리입니다.
        metadata_path: 프레임 메타데이터 JSON을 저장할 경로입니다.
        threshold: ffmpeg scene 필터에 사용할 장면 전환 임계값입니다.
        project_root: ``image_path``를 상대 경로로 만들 기준 디렉터리입니다.
        image_prefix: 저장할 이미지 파일명 접두사입니다.
        min_scene_gap_seconds: 너무 가까운 장면 전환 프레임을 제외하기 위한 최소 시간 간격입니다.

    Returns:
        추출된 프레임 메타데이터 목록입니다.

    Raises:
        ValueError: 임계값 또는 최소 시간 간격이 올바르지 않을 때 발생합니다.
        FileNotFoundError: 영상 파일이 존재하지 않을 때 발생합니다.
    """
    if not 0 < threshold < 1:
        raise ValueError("장면 전환 임계값은 0과 1 사이여야 합니다.")
    if min_scene_gap_seconds < 0:
        raise ValueError("장면 전환 최소 간격은 0 이상이어야 합니다.")

    video_path = Path(video_path)
    frames_dir = Path(frames_dir)
    project_root = Path(project_root) if project_root else Path.cwd()

    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일이 존재하지 않습니다: {video_path}")

    frames_dir.mkdir(parents=True, exist_ok=True)
    remove_files(frames_dir.glob(f"{image_prefix}_*.jpg"))

    output_pattern = frames_dir / f"{image_prefix}_%06d.jpg"
    select_filter = (
        f"select=gt(scene\\,{threshold})"
        if min_scene_gap_seconds == 0
        else (
            f"select=gt(scene\\,{threshold})*"
            f"if(isnan(prev_selected_t)\\,1\\,gte(t-prev_selected_t\\,{min_scene_gap_seconds}))"
        )
    )

    result = run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"{select_filter},showinfo",
            "-vsync",
            "vfr",
            "-q:v",
            "2",
            str(output_pattern),
        ]
    )

    timestamps = parse_showinfo_timestamps(result.stderr)
    image_paths = sorted(frames_dir.glob(f"{image_prefix}_*.jpg"))

    metadata = [
        FrameMetadata(
            frame_id=index,
            timestamp=round(timestamps[index], 3) if index < len(timestamps) else 0.0,
            image_path=_project_relative(image_path, project_root),
            sampling_method="scene_change",
        )
        for index, image_path in enumerate(image_paths)
    ]

    _write_metadata(metadata, metadata_path)
    print(f"장면 전환 프레임 추출 완료. 추출 프레임 수: {len(metadata)}")
    return metadata


def sample_frames(
    video_path: str | Path,
    run_dir: str | Path,
    method: SamplingMethod = DEFAULT_SAMPLING_METHOD,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
    project_root: Optional[str | Path] = None,
) -> List[FrameMetadata]:
    """run 디렉터리 구조에 맞춰 프레임 이미지와 메타데이터를 생성합니다.

    Args:
        video_path: 프레임을 추출할 영상 파일 경로입니다.
        run_dir: 실행 결과를 저장할 run 디렉터리입니다.
        method: 프레임 추출 방식입니다.
        interval_seconds: 일정 간격 추출에서 사용할 시간 간격입니다.
        scene_threshold: 장면 전환 추출에서 사용할 임계값입니다.
        project_root: ``image_path``를 상대 경로로 만들 기준 디렉터리입니다.

    Returns:
        추출된 프레임 메타데이터 목록입니다.

    Raises:
        ValueError: 지원하지 않는 프레임 추출 방식이 전달될 때 발생합니다.
    """
    run_dir = Path(run_dir)
    project_root = Path(project_root) if project_root else run_dir.parent.parent
    frames_dir = run_dir / "frames"
    metadata_path = run_path(run_dir, DEFAULT_FRAME_METADATA_RELATIVE_PATH)

    if method == "interval":
        return sample_interval_frames(
            video_path=video_path,
            frames_dir=frames_dir,
            metadata_path=metadata_path,
            interval_seconds=interval_seconds,
            project_root=project_root,
            image_prefix="frame",
        )

    if method == "scene_change":
        return sample_scene_change_frames(
            video_path=video_path,
            frames_dir=frames_dir,
            metadata_path=metadata_path,
            threshold=scene_threshold,
            project_root=project_root,
            image_prefix="frame",
        )

    if method == "interval_scene_change":
        return sample_interval_scene_change_frames(
            video_path=video_path,
            frames_dir=frames_dir,
            metadata_path=metadata_path,
            interval_seconds=interval_seconds,
            scene_threshold=scene_threshold,
            project_root=project_root,
        )

    raise ValueError(f"지원하지 않는 프레임 추출 방식입니다: {method}")


def load_frame_metadata(metadata_path: str | Path) -> List[Dict[str, object]]:
    """프레임 메타데이터 JSON 파일을 읽습니다.

    Args:
        metadata_path: 프레임 메타데이터 JSON 파일 경로입니다.

    Returns:
        프레임 메타데이터 딕셔너리 목록입니다.
    """
    with Path(metadata_path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def get_sampling_summary(video_path: str | Path) -> Dict[str, object]:
    """프레임 샘플링 전에 참고할 영상 정보를 반환합니다.

    Args:
        video_path: 정보를 확인할 영상 파일 경로입니다.

    Returns:
        영상 기본 정보 딕셔너리입니다.
    """
    return get_video_info(video_path).to_dict()
