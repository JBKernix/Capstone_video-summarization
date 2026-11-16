import pytest

from app import run_registry


@pytest.fixture(autouse=True)
def _isolate_run_registry(tmp_path, monkeypatch):
    """테스트가 실제 runs/jobs, 업로드 폴더, 실행 슬롯 파일을 건드리지 않게 합니다."""
    monkeypatch.setattr(run_registry, "JOBS_DIR", tmp_path / "registry" / "jobs")
    monkeypatch.setattr(run_registry, "UPLOAD_DIR", tmp_path / "registry" / "uploads")
    monkeypatch.setattr(run_registry, "ACTIVE_FILE", tmp_path / "registry" / "active.json")
    monkeypatch.setattr(run_registry, "_processes", {})
