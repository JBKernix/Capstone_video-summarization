from modules.preprocess import frame_sampler
from modules.preprocess.frame_sampler import FrameMetadata


def test_merge_prefers_scene_change_when_frames_are_close():
    interval_metadata = [
        FrameMetadata(0, 0.0, "runs/frames/interval_000001.jpg", "interval"),
        FrameMetadata(1, 60.0, "runs/frames/interval_000002.jpg", "interval"),
    ]
    scene_metadata = [
        FrameMetadata(0, 60.5, "runs/frames/scene_000001.jpg", "scene_change"),
        FrameMetadata(1, 90.0, "runs/frames/scene_000002.jpg", "scene_change"),
    ]

    merged = frame_sampler._merge_frame_metadata(interval_metadata, scene_metadata, min_gap_seconds=1.0)

    assert [item.frame_id for item in merged] == [0, 1, 2]
    assert [item.timestamp for item in merged] == [0.0, 60.5, 90.0]
    assert [item.sampling_method for item in merged] == ["interval", "scene_change", "scene_change"]


def test_sample_frames_uses_combined_strategy_by_default(monkeypatch, tmp_path):
    calls = []

    def fake_combined(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(frame_sampler, "sample_interval_scene_change_frames", fake_combined)

    result = frame_sampler.sample_frames(video_path=tmp_path / "input.mp4", run_dir=tmp_path)

    assert result == []
    assert calls
    assert calls[0]["frames_dir"] == tmp_path / "frames"
    assert calls[0]["metadata_path"] == tmp_path / "metadata" / "frame_metadata.json"
