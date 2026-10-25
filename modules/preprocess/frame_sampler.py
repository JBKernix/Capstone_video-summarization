# modules/preprocess/frame_sampler.py

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence, Tuple, TypeVar

from modules.common import DEFAULT_FRAME_METADATA_RELATIVE_PATH, load_json, run_path, save_json
from modules.common.progress import STEP_FRAME_EXTRACTION, report_progress
from modules.preprocess.ffmpeg_utils import (
    parse_showinfo_timestamps,
    remove_files,
    run_ffmpeg,
    run_ffmpeg_with_progress,
)
from modules.preprocess.video_info import get_video_info

SamplingMethod = Literal["representative", "interval", "scene_change"]
TimeRange = Tuple[float, float]
T = TypeVar("T")
SAMPLING_METHOD_CHOICES: tuple[SamplingMethod, ...] = ("representative", "interval", "scene_change")
DEFAULT_SAMPLING_METHOD: SamplingMethod = "representative"
DEFAULT_INTERVAL_SECONDS = 5.0
DEFAULT_SCENE_THRESHOLD = 0.5
DEFAULT_SCENE_MIN_GAP_SECONDS = 1.0
# representative 방식: 구간 안에서 이 간격으로 후보를 뽑고, 같은 화면이 이어지는 후보는 첫 장만 남깁니다.
DEFAULT_CANDIDATE_INTERVAL_SECONDS = 2.0
DEFAULT_MAX_FRAMES_PER_SEGMENT = 4
# 중요 구간 없이 영상 전체를 다룰 때는 이 길이로 나눈 구간마다 대표 프레임을 고릅니다.
FULL_VIDEO_WINDOW_SECONDS = 60.0


@dataclass(frozen=True)
class FrameMetadata:
    """추출된 프레임 하나의 메타데이터입니다."""

    frame_id: int
    timestamp: float
    image_path: str
    sampling_method: SamplingMethod
    # representative 방식에서 프레임이 속한 중요 구간 번호입니다(정규화된 구간 순서 기준).
    segment_id: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        """프레임 메타데이터를 JSON 저장 가능한 딕셔너리로 변환합니다."""
        data: Dict[str, object] = {
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "image_path": self.image_path,
            "sampling_method": self.sampling_method,
        }
        if self.segment_id is not None:
            data["segment_id"] = self.segment_id
        return data


def _project_relative(path: Path, project_root: Path) -> str:
    """경로를 프로젝트 루트 기준 상대 경로로 변환합니다."""
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _write_metadata(metadata: List[FrameMetadata], metadata_path: str | Path) -> None:
    """프레임 메타데이터 목록을 JSON 파일로 저장합니다."""
    save_json([item.to_dict() for item in metadata], metadata_path)
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
    summary_result = load_json(summary_result_path)

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
    total_timestamps = len(timestamps)

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
        report_progress(
            STEP_FRAME_EXTRACTION,
            f"프레임 추출 중 ({index + 1}/{total_timestamps})",
            (index + 1) / total_timestamps * 100,
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

    try:
        duration = get_video_info(video_path).duration
    except (RuntimeError, ValueError):
        duration = 0.0

    def _on_progress(percent: float) -> None:
        report_progress(STEP_FRAME_EXTRACTION, f"프레임 추출 중 ({percent:.0f}%)", percent)

    output_pattern = frames_dir / f"{image_prefix}_%06d.jpg"
    run_ffmpeg_with_progress(
        [
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"fps={1.0 / interval_seconds}",
            "-q:v",
            "2",
            str(output_pattern),
        ],
        duration,
        _on_progress,
    )
    report_progress(STEP_FRAME_EXTRACTION, "프레임 추출 완료", 100.0)

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

    try:
        duration = get_video_info(video_path).duration
    except (RuntimeError, ValueError):
        duration = 0.0

    def _on_progress(percent: float) -> None:
        report_progress(STEP_FRAME_EXTRACTION, f"화면 전환 프레임 탐색 중 ({percent:.0f}%)", percent)

    output_pattern = frames_dir / f"{image_prefix}_%06d.jpg"
    result = run_ffmpeg_with_progress(
        [
            "-y",
            "-i",
            str(video_path),
            "-vf",
            f"select={select_filter},showinfo",
            "-fps_mode",
            "vfr",
            "-q:v",
            "2",
            str(output_pattern),
        ],
        duration,
        _on_progress,
    )
    report_progress(STEP_FRAME_EXTRACTION, "프레임 추출 완료", 100.0)

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


def _select_evenly(items: Sequence[T], limit: int) -> List[T]:
    """``limit``개를 넘으면 처음과 끝을 포함해 시간상 고르게 퍼진 항목만 남깁니다."""
    if len(items) <= limit:
        return list(items)
    if limit == 1:
        return [items[0]]
    step = (len(items) - 1) / (limit - 1)
    return [items[round(position * step)] for position in range(limit)]


def _full_video_ranges(duration: float) -> List[TimeRange]:
    """영상 전체를 ``FULL_VIDEO_WINDOW_SECONDS`` 길이의 구간으로 나눕니다."""
    ranges: List[TimeRange] = []
    start = 0.0
    while start < duration:
        ranges.append((start, min(start + FULL_VIDEO_WINDOW_SECONDS, duration)))
        start += FULL_VIDEO_WINDOW_SECONDS
    return ranges


def _segment_candidates(
    video_path: Path,
    frames_dir: Path,
    segment_id: int,
    time_range: TimeRange,
    candidate_interval_seconds: float,
) -> List[Tuple[Path, float]]:
    """한 구간에서 후보 프레임을 뽑되, 직전에 남긴 후보와 거의 같은 화면(mpdecimate)은 버립니다.

    입력 위치 탐색(``-ss``)을 쓰므로 showinfo 시각은 구간 시작 기준이라 구간 시작 시각을 더합니다.
    mpdecimate는 직전에 남긴 프레임과만 비교하므로 A→B→A처럼 돌아온 화면은 다시 남습니다.
    """
    start, end = time_range
    prefix = f"_candidate_{segment_id:04d}_"
    remove_files(frames_dir.glob(f"{prefix}*.jpg"))
    result = run_ffmpeg(
        [
            "-y",
            "-ss",
            f"{start:.3f}",
            # 입력 옵션으로 둬야 필터가 구간 밖 프레임을 보지 않습니다(출력 옵션이면 끝에서 후보가 더 생깁니다).
            "-t",
            f"{end - start:.3f}",
            "-i",
            str(video_path),
            "-an",
            "-sn",
            "-vf",
            f"fps={1.0 / candidate_interval_seconds},mpdecimate,showinfo",
            "-fps_mode",
            "vfr",
            "-q:v",
            "2",
            str(frames_dir / f"{prefix}%04d.jpg"),
        ]
    )
    timestamps = parse_showinfo_timestamps(result.stderr)
    image_paths = sorted(frames_dir.glob(f"{prefix}*.jpg"))
    if len(timestamps) != len(image_paths):
        remove_files(image_paths)
        raise RuntimeError(
            "대표 프레임 후보 수와 timestamp 수가 일치하지 않습니다: "
            f"images={len(image_paths)}, timestamps={len(timestamps)}"
        )
    return [(path, round(start + timestamp, 3)) for path, timestamp in zip(image_paths, timestamps)]


def _extract_single_frame(video_path: Path, output_path: Path, timestamp: float) -> bool:
    """``timestamp`` 시점의 프레임 한 장을 저장하고, 실제로 파일이 생겼는지 돌려줍니다."""
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
    return output_path.exists()


def sample_representative_frames(
    video_path: str | Path,
    frames_dir: str | Path,
    metadata_path: str | Path,
    candidate_interval_seconds: float = DEFAULT_CANDIDATE_INTERVAL_SECONDS,
    max_frames_per_segment: int = DEFAULT_MAX_FRAMES_PER_SEGMENT,
    project_root: Optional[str | Path] = None,
    image_prefix: str = "frame",
    time_ranges: Optional[Sequence[TimeRange]] = None,
) -> List[FrameMetadata]:
    """구간마다 화면이 바뀐 만큼만 대표 프레임을 추출합니다.

    구간 안에서 ``candidate_interval_seconds`` 간격으로 후보를 뽑고, 같은 화면이 이어지는 후보는 첫 장만
    남깁니다. 그래서 화면이 그대로인 구간은 1장, 슬라이드가 여러 번 바뀐 구간은 여러 장이 됩니다.
    구간당 ``max_frames_per_segment``장을 넘으면 시간상 고르게 골라 줄이고, 후보가 하나도 없으면
    구간 가운데 시점의 한 장을 씁니다. ``time_ranges``가 없으면 영상 전체를 일정 길이로 나눠 처리합니다.
    """
    if candidate_interval_seconds <= 0:
        raise ValueError("후보 프레임 간격은 0보다 커야 합니다.")
    if max_frames_per_segment < 1:
        raise ValueError("구간당 최대 프레임 수는 1 이상이어야 합니다.")

    video_path = Path(video_path)
    frames_dir = Path(frames_dir)
    project_root = Path(project_root) if project_root else Path.cwd()

    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일이 존재하지 않습니다: {video_path}")

    frames_dir.mkdir(parents=True, exist_ok=True)
    remove_files(frames_dir.glob(f"{image_prefix}_*.jpg"))

    try:
        duration = get_video_info(video_path).duration
    except (RuntimeError, ValueError):
        duration = 0.0

    if time_ranges is None:
        if duration <= 0:
            return sample_interval_frames(
                video_path=video_path,
                frames_dir=frames_dir,
                metadata_path=metadata_path,
                project_root=project_root,
                image_prefix=image_prefix,
            )
        time_ranges = _full_video_ranges(duration)
    elif duration > 0:
        # LLM이 준 구간이 영상 길이를 넘으면 FFmpeg가 빈 출력으로 실패하므로 영상 안으로 자릅니다.
        time_ranges = [(start, min(end, duration)) for start, end in time_ranges]

    ranges = _normalize_time_ranges(time_ranges)
    metadata: List[FrameMetadata] = []

    def _add(timestamp: float, output_path: Path, segment_id: int) -> None:
        metadata.append(
            FrameMetadata(
                frame_id=len(metadata),
                timestamp=timestamp,
                image_path=_project_relative(output_path, project_root),
                sampling_method="representative",
                segment_id=segment_id,
            )
        )

    for segment_id, time_range in enumerate(ranges):
        candidates = _segment_candidates(
            video_path, frames_dir, segment_id, time_range, candidate_interval_seconds
        )
        chosen = _select_evenly(candidates, max_frames_per_segment)
        for path, timestamp in chosen:
            output_path = frames_dir / f"{image_prefix}_{len(metadata) + 1:06d}.jpg"
            path.replace(output_path)
            _add(timestamp, output_path, segment_id)
        remove_files(path for path, _ in candidates if path.exists())

        if not chosen:
            # 구간이 영상 끝을 넘는 등 후보가 없을 때의 대비입니다. 가운데 시점도 없으면 구간을 건너뜁니다.
            middle = round(sum(time_range) / 2, 3)
            output_path = frames_dir / f"{image_prefix}_{len(metadata) + 1:06d}.jpg"
            if _extract_single_frame(video_path, output_path, middle):
                _add(middle, output_path, segment_id)

        report_progress(
            STEP_FRAME_EXTRACTION,
            f"대표 프레임 추출 중 ({segment_id + 1}/{len(ranges)} 구간)",
            (segment_id + 1) / len(ranges) * 100,
        )

    _write_metadata(metadata, metadata_path)
    print(f"대표 프레임 추출 완료. 구간 수: {len(ranges)}, 추출 프레임 수: {len(metadata)}")
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
    max_frames_per_segment: int = DEFAULT_MAX_FRAMES_PER_SEGMENT,
) -> List[FrameMetadata]:
    """선택한 방식으로 run 디렉터리에 프레임과 메타데이터를 생성합니다."""
    run_dir = Path(run_dir)
    project_root = Path(project_root) if project_root else run_dir.parent
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

    if method == "representative":
        return sample_representative_frames(max_frames_per_segment=max_frames_per_segment, **common_args)
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
    return load_json(metadata_path)
