# modules/preprocess/frame_sampler.py

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence, Tuple

from modules.common import DEFAULT_FRAME_METADATA_RELATIVE_PATH, run_path
from modules.preprocess.ffmpeg_utils import parse_showinfo_timestamps, remove_files, run_ffmpeg
from modules.preprocess.video_info import get_video_info

SamplingMethod = Literal["interval", "scene_change"]
TimeRange = Tuple[float, float]
SAMPLING_METHOD_CHOICES: tuple[SamplingMethod, ...] = ("interval", "scene_change")
DEFAULT_SAMPLING_METHOD: SamplingMethod = "interval"
DEFAULT_INTERVAL_SECONDS = 5.0
DEFAULT_SCENE_THRESHOLD = 0.5
DEFAULT_SCENE_MIN_GAP_SECONDS = 1.0


@dataclass(frozen=True)
class FrameMetadata:
    """추출된 프레임 하나의 메타데이터입니다."""

    frame_id: int
    timestamp: float
    image_path: str
    sampling_method: SamplingMethod

    def to_dict(self) -> Dict[str, object]:
        """프레임 메타데이터를 JSON 저장 가능한 딕셔너리로 변환합니다."""
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
    with metadata_path.open("w", encoding="utf-8") as file:
        json.dump([item.to_dict() for item in metadata], file, ensure_ascii=False, indent=2)

    print(f"프레임 메타데이터 저장 완료: {metadata_path}")


def _normalize_time_ranges(time_ranges: Sequence[TimeRange]) -> List[TimeRange]:
    """시간 구간을 보정하고 겹치는 구간을 병합합니다."""
    normalized: List[TimeRange] = []
    for start, end in time_ranges:
        start = max(0.0, float(start))
        end = float(end)
        if end <= start:
            continue
        normalized.append((start, end))

    normalized.sort(key=lambda item: item[0])
    merged: List[TimeRange] = []
    for start, end in normalized:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))

    return merged


def load_important_time_ranges(summary_result_path: str | Path) -> List[TimeRange]:
    """LLM STT 요약 결과에서 중요 구간의 시작/종료 시점을 읽습니다."""
    summary_result_path = Path(summary_result_path)
    with summary_result_path.open("r", encoding="utf-8-sig") as file:
        summary_result = json.load(file)

    important_segments = summary_result.get("important_segments", [])
    if isinstance(important_segments, str):
        important_segments = json.loads(important_segments)

    time_ranges: List[TimeRange] = []
    for segment in important_segments:
        if not isinstance(segment, dict):
            continue
        if "start" not in segment or "end" not in segment:
            continue
        time_ranges.append((float(segment["start"]), float(segment["end"])))

    return _normalize_time_ranges(time_ranges)


def _build_interval_timestamps(time_ranges: Sequence[TimeRange], interval_seconds: float) -> List[float]:
    """각 중요 구간 안에서 일정 간격의 추출 시점을 생성합니다."""
    timestamps: List[float] = []
    for start, end in time_ranges:
        timestamp = start
        while timestamp <= end:
            timestamps.append(round(timestamp, 3))
            timestamp += interval_seconds

    return sorted(set(timestamps))


def _time_ranges_to_select_filter(time_ranges: Sequence[TimeRange]) -> str:
    """시간 구간을 FFmpeg select 필터 조건으로 변환합니다."""
    return "+".join(
        f"between(t\\,{start:.3f}\\,{end:.3f})"
        for start, end in _normalize_time_ranges(time_ranges)
    )


def _sample_interval_frames_in_ranges(
    video_path: Path,
    frames_dir: Path,
    metadata_path: str | Path,
    interval_seconds: float,
    project_root: Path,
    image_prefix: str,
    time_ranges: Sequence[TimeRange],
) -> List[FrameMetadata]:
    """지정된 시간 구간 안에서만 일정 간격으로 프레임을 추출합니다."""
    normalized_ranges = _normalize_time_ranges(time_ranges)
    timestamps = _build_interval_timestamps(normalized_ranges, interval_seconds)
    metadata: List[FrameMetadata] = []

    for index, timestamp in enumerate(timestamps):
        output_path = frames_dir / f"{image_prefix}_{index + 1:06d}.jpg"
        run_ffmpeg(
            [
                "-y",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-update",
                "1",
                str(output_path),
            ]
        )
        metadata.append(
            FrameMetadata(
                frame_id=index,
                timestamp=timestamp,
                image_path=_project_relative(output_path, project_root),
                sampling_method="interval",
            )
        )

    _write_metadata(metadata, metadata_path)
    print(f"중요 구간 프레임 추출 완료. 추출 프레임 수: {len(metadata)}")
    return metadata


def sample_interval_frames(
    video_path: str | Path,
    frames_dir: str | Path,
    metadata_path: str | Path,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    project_root: Optional[str | Path] = None,
    image_prefix: str = "frame",
    time_ranges: Optional[Sequence[TimeRange]] = None,
) -> List[FrameMetadata]:
    """전체 영상 또는 지정된 중요 구간에서 일정 간격으로 프레임을 추출합니다."""
    if interval_seconds <= 0:
        raise ValueError("프레임 추출 간격은 0보다 커야 합니다.")

    video_path = Path(video_path)
    frames_dir = Path(frames_dir)
    project_root = Path(project_root) if project_root else Path.cwd()

    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일이 존재하지 않습니다: {video_path}")

    frames_dir.mkdir(parents=True, exist_ok=True)
    remove_files(frames_dir.glob(f"{image_prefix}_*.jpg"))

    if time_ranges is not None:
        return _sample_interval_frames_in_ranges(
            video_path=video_path,
            frames_dir=frames_dir,
            metadata_path=metadata_path,
            interval_seconds=interval_seconds,
            project_root=project_root,
            image_prefix=image_prefix,
            time_ranges=time_ranges,
        )

    output_pattern = frames_dir / f"{image_prefix}_%06d.jpg"
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={1.0 / interval_seconds}",
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


def sample_scene_change_frames(
    video_path: str | Path,
    frames_dir: str | Path,
    metadata_path: str | Path,
    threshold: float = DEFAULT_SCENE_THRESHOLD,
    min_gap_seconds: float = DEFAULT_SCENE_MIN_GAP_SECONDS,
    project_root: Optional[str | Path] = None,
    image_prefix: str = "frame",
    time_ranges: Optional[Sequence[TimeRange]] = None,
) -> List[FrameMetadata]:
    """전체 영상 또는 지정된 중요 구간에서 화면 전환 프레임을 추출합니다."""
    if not 0 < threshold < 1:
        raise ValueError("화면 전환 임계값은 0과 1 사이여야 합니다.")
    if min_gap_seconds < 0:
        raise ValueError("화면 전환 최소 간격은 0 이상이어야 합니다.")

    video_path = Path(video_path)
    frames_dir = Path(frames_dir)
    project_root = Path(project_root) if project_root else Path.cwd()

    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일이 존재하지 않습니다: {video_path}")

    frames_dir.mkdir(parents=True, exist_ok=True)
    remove_files(frames_dir.glob(f"{image_prefix}_*.jpg"))

    range_filter = None
    if time_ranges is not None:
        range_filter = _time_ranges_to_select_filter(time_ranges)
        if not range_filter:
            metadata: List[FrameMetadata] = []
            _write_metadata(metadata, metadata_path)
            return metadata

    select_filter = f"gt(scene\\,{threshold})"
    if min_gap_seconds > 0:
        select_filter += (
            f"*if(isnan(prev_selected_t)\\,1\\,"
            f"gte(t-prev_selected_t\\,{min_gap_seconds}))"
        )
    if range_filter:
        select_filter += f"*({range_filter})"

    output_pattern = frames_dir / f"{image_prefix}_%06d.jpg"
    result = run_ffmpeg(
        [
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"select={select_filter},showinfo",
            "-vsync",
            "vfr",
            "-q:v",
            "2",
            str(output_pattern),
        ]
    )

    timestamps = parse_showinfo_timestamps(result.stderr)
    image_paths = sorted(frames_dir.glob(f"{image_prefix}_*.jpg"))
    if len(timestamps) != len(image_paths):
        raise RuntimeError(
            "화면 전환 프레임 수와 timestamp 수가 일치하지 않습니다: "
            f"images={len(image_paths)}, timestamps={len(timestamps)}"
        )

    metadata = [
        FrameMetadata(
            frame_id=index,
            timestamp=round(timestamp, 3),
            image_path=_project_relative(image_path, project_root),
            sampling_method="scene_change",
        )
        for index, (image_path, timestamp) in enumerate(zip(image_paths, timestamps))
    ]

    _write_metadata(metadata, metadata_path)
    print(f"화면 전환 프레임 추출 완료. 추출 프레임 수: {len(metadata)}")
    return metadata


def sample_frames(
    video_path: str | Path,
    run_dir: str | Path,
    method: SamplingMethod = DEFAULT_SAMPLING_METHOD,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
    scene_threshold: float = DEFAULT_SCENE_THRESHOLD,
    scene_min_gap_seconds: float = DEFAULT_SCENE_MIN_GAP_SECONDS,
    project_root: Optional[str | Path] = None,
    time_ranges: Optional[Sequence[TimeRange]] = None,
    important_segments_path: Optional[str | Path] = None,
) -> List[FrameMetadata]:
    """선택한 방식으로 run 디렉터리에 프레임과 메타데이터를 생성합니다."""
    run_dir = Path(run_dir)
    project_root = Path(project_root) if project_root else run_dir.parent.parent
    if important_segments_path is not None:
        time_ranges = load_important_time_ranges(important_segments_path)

    common_args = {
        "video_path": video_path,
        "frames_dir": run_dir / "frames",
        "metadata_path": run_path(run_dir, DEFAULT_FRAME_METADATA_RELATIVE_PATH),
        "project_root": project_root,
        "image_prefix": "frame",
        "time_ranges": time_ranges,
    }

    if method == "interval":
        return sample_interval_frames(interval_seconds=interval_seconds, **common_args)
    if method == "scene_change":
        return sample_scene_change_frames(
            threshold=scene_threshold,
            min_gap_seconds=scene_min_gap_seconds,
            **common_args,
        )

    raise ValueError(f"지원하지 않는 프레임 샘플링 방식입니다: {method}")


def load_frame_metadata(metadata_path: str | Path) -> List[Dict[str, object]]:
    """프레임 메타데이터 JSON 파일을 읽습니다."""
    with Path(metadata_path).open("r", encoding="utf-8-sig") as file:
        return json.load(file)


def get_sampling_summary(video_path: str | Path) -> Dict[str, object]:
    """프레임 샘플링 전에 참고할 영상 정보를 반환합니다."""
    return get_video_info(video_path).to_dict()
