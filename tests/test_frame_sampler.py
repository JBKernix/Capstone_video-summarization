import json
from subprocess import CompletedProcess

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

    def fake_run_ffmpeg(args):
        captured_args.extend(args)
        frames_dir.mkdir(parents=True, exist_ok=True)
        (frames_dir / "frame_000001.jpg").write_bytes(b"frame")
        return CompletedProcess(args, 0, stderr="[Parsed_showinfo] pts_time:12.5")

    monkeypatch.setattr(frame_sampler, "run_ffmpeg", fake_run_ffmpeg)

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
