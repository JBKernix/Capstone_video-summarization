import json
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace

from modules.preprocess import frame_sampler


def test_normalize_time_ranges_merges_and_filters_ranges():
    result = frame_sampler._normalize_time_ranges(
        [(-5, 5), (5, 10), (20, 15), (8, 12), (30, 40)]
    )

    assert result == [(0.0, 12.0), (30.0, 40.0)]


def test_sample_frames_uses_interval_sampling(monkeypatch, tmp_path):
    calls = []

    def fake_interval(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(frame_sampler, "sample_interval_frames", fake_interval)

    result = frame_sampler.sample_frames(
        video_path=tmp_path / "input.mp4",
        run_dir=tmp_path,
        method="interval",
        interval_seconds=15.0,
        time_ranges=[(10.0, 20.0)],
    )

    assert result == []
    assert calls[0]["frames_dir"] == tmp_path / "frames"
    assert calls[0]["metadata_path"] == tmp_path / "metadata" / "frame_metadata.json"
    assert calls[0]["interval_seconds"] == 15.0
    assert calls[0]["time_ranges"] == [(10.0, 20.0)]


def test_sample_frames_uses_scene_change_sampling(monkeypatch, tmp_path):
    calls = []

    def fake_scene_change(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(frame_sampler, "sample_scene_change_frames", fake_scene_change)

    result = frame_sampler.sample_frames(
        video_path=tmp_path / "input.mp4",
        run_dir=tmp_path,
        method="scene_change",
        scene_threshold=0.5,
        scene_min_gap_seconds=2.0,
        time_ranges=[(10.0, 20.0)],
    )

    assert result == []
    assert calls[0]["threshold"] == 0.5
    assert calls[0]["min_gap_seconds"] == 2.0
    assert calls[0]["time_ranges"] == [(10.0, 20.0)]


def test_empty_important_segments_do_not_sample_full_video(monkeypatch, tmp_path):
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({"important_segments": []}), encoding="utf-8")
    calls = []

    def fake_interval(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(frame_sampler, "sample_interval_frames", fake_interval)

    frame_sampler.sample_frames(
        video_path=tmp_path / "input.mp4",
        run_dir=tmp_path,
        method="interval",
        important_segments_path=summary_path,
    )

    assert calls[0]["time_ranges"] == []


def test_empty_time_ranges_write_empty_metadata_without_running_ffmpeg(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake")
    metadata_path = tmp_path / "metadata" / "frame_metadata.json"

    def fail_if_called(_args):
        raise AssertionError("FFmpeg should not run when there are no important segments")

    monkeypatch.setattr(frame_sampler, "run_ffmpeg", fail_if_called)

    result = frame_sampler.sample_interval_frames(
        video_path=video_path,
        frames_dir=tmp_path / "frames",
        metadata_path=metadata_path,
        time_ranges=[],
    )

    assert result == []
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == []


def test_scene_change_sampling_uses_important_ranges_and_showinfo_timestamps(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake")
    frames_dir = tmp_path / "frames"
    metadata_path = tmp_path / "metadata" / "frame_metadata.json"
    captured_args = []

    def fake_run_ffmpeg_with_progress(args, total_duration_sec, on_progress):
        captured_args.extend(args)
        frames_dir.mkdir(parents=True, exist_ok=True)
        (frames_dir / "frame_000001.jpg").write_bytes(b"frame")
        return CompletedProcess(args, 0, stderr="[Parsed_showinfo] pts_time:12.5")

    monkeypatch.setattr(frame_sampler, "run_ffmpeg_with_progress", fake_run_ffmpeg_with_progress)
    monkeypatch.setattr(
        frame_sampler, "get_video_info", lambda video_path: SimpleNamespace(duration=40.0)
    )

    result = frame_sampler.sample_scene_change_frames(
        video_path=video_path,
        frames_dir=frames_dir,
        metadata_path=metadata_path,
        threshold=0.6,
        min_gap_seconds=2.0,
        project_root=tmp_path,
        time_ranges=[(10.0, 20.0), (30.0, 40.0)],
    )

    video_filter = captured_args[captured_args.index("-vf") + 1]
    assert "gt(scene\\,0.6)" in video_filter
    assert "gte(t-prev_selected_t\\,2.0)" in video_filter
    assert "between(t\\,10.000\\,20.000)" in video_filter
    assert "between(t\\,30.000\\,40.000)" in video_filter
    assert result[0].timestamp == 12.5
    assert result[0].sampling_method == "scene_change"


def test_empty_scene_change_ranges_do_not_run_ffmpeg(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake")
    metadata_path = tmp_path / "metadata" / "frame_metadata.json"

    def fail_if_called(_args):
        raise AssertionError("FFmpeg should not run when there are no important segments")

    monkeypatch.setattr(frame_sampler, "run_ffmpeg", fail_if_called)

    result = frame_sampler.sample_scene_change_frames(
        video_path=video_path,
        frames_dir=tmp_path / "frames",
        metadata_path=metadata_path,
        time_ranges=[],
    )

    assert result == []
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == []


def test_select_evenly_keeps_first_and_last():
    assert frame_sampler._select_evenly(list(range(10)), 4) == [0, 3, 6, 9]
    assert frame_sampler._select_evenly([1, 2], 4) == [1, 2]
    assert frame_sampler._select_evenly([1, 2, 3], 1) == [1]


def test_sample_frames_defaults_to_representative(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        frame_sampler, "sample_representative_frames", lambda **kwargs: calls.append(kwargs) or []
    )

    frame_sampler.sample_frames(video_path=tmp_path / "input.mp4", run_dir=tmp_path, time_ranges=[(1.0, 2.0)])

    assert calls[0]["max_frames_per_segment"] == frame_sampler.DEFAULT_MAX_FRAMES_PER_SEGMENT
    assert calls[0]["time_ranges"] == [(1.0, 2.0)]


def test_representative_sampling_caps_frames_per_segment(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake")
    frames_dir = tmp_path / "frames"
    commands = []
    # 정렬된 구간마다 mpdecimate를 통과한 후보 수: 앞 구간(10~30초)은 화면이 그대로, 뒤 구간은 6번 바뀝니다.
    candidate_counts = iter([1, 6])

    def fake_run_ffmpeg(args):
        commands.append(args)
        count = next(candidate_counts)
        output = Path(args[-1])
        for number in range(1, count + 1):
            (output.parent / (output.name % number)).write_bytes(b"jpg")
        stderr = "\n".join(f"[Parsed_showinfo] n:{n} pts_time:{n * 2}" for n in range(count))
        return CompletedProcess(args, 0, stderr=stderr)

    monkeypatch.setattr(frame_sampler, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(frame_sampler, "get_video_info", lambda _path: SimpleNamespace(duration=100.0))

    result = frame_sampler.sample_representative_frames(
        video_path=video_path,
        frames_dir=frames_dir,
        metadata_path=tmp_path / "metadata.json",
        max_frames_per_segment=3,
        project_root=tmp_path,
        time_ranges=[(50.0, 200.0), (10.0, 30.0)],
    )

    # 구간은 시간순으로 정렬되고, 영상 길이(100초)를 넘는 끝은 잘립니다.
    assert commands[0][commands[0].index("-ss") + 1] == "10.000"
    assert commands[1][commands[1].index("-t") + 1] == "50.000"
    assert "mpdecimate" in commands[0][commands[0].index("-vf") + 1]
    assert [(item.segment_id, item.timestamp) for item in result] == [(0, 10.0), (1, 50.0), (1, 54.0), (1, 60.0)]
    assert sorted(path.name for path in frames_dir.iterdir()) == [f"frame_00000{n}.jpg" for n in range(1, 5)]
    assert result[0].to_dict()["sampling_method"] == "representative"


def test_representative_sampling_falls_back_to_middle_frame(monkeypatch, tmp_path):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake")
    commands = []

    def fake_run_ffmpeg(args):
        commands.append(args)
        if "-frames:v" in args:
            Path(args[-1]).write_bytes(b"jpg")
        return CompletedProcess(args, 0, stderr="")

    monkeypatch.setattr(frame_sampler, "run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(frame_sampler, "get_video_info", lambda _path: SimpleNamespace(duration=100.0))

    result = frame_sampler.sample_representative_frames(
        video_path=video_path,
        frames_dir=tmp_path / "frames",
        metadata_path=tmp_path / "metadata.json",
        project_root=tmp_path,
        time_ranges=[(10.0, 20.0)],
    )

    assert commands[-1][commands[-1].index("-ss") + 1] == "15.000"
    assert [(item.segment_id, item.timestamp) for item in result] == [(0, 15.0)]
