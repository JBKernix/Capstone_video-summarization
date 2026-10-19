import json

import pytest
from fastapi.testclient import TestClient

from app import login_throttle, run_registry
from app.api import auth, server
from app.saved_results import saved_folder
from modules.common.progress import PROGRESS_MARKER
from modules.common.run_history import atomic_json, prepare_run, read_record

HEADERS = {"X-Requested-With": "XMLHttpRequest"}
CF = {"Cf-Connecting-Ip": "203.0.113.7"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setattr(auth, "SECRETS_FILE", tmp_path / "missing.toml")
    monkeypatch.setattr(login_throttle, "_failures", {})
    monkeypatch.setattr(server, "SAVE_ROOT", tmp_path / "saved")
    monkeypatch.setattr(server, "DEFAULT_HISTORY_DIR", tmp_path / "history")
    monkeypatch.setattr(server, "FRONTEND_DIST", tmp_path / "dist")
    monkeypatch.setattr(server, "check_free_space", lambda *_args, **_kwargs: None)
    return TestClient(server.app)


def make_job(tmp_path, *, status="running", log_lines=(), video=True):
    history = prepare_run(tmp_path / "history", input_name="lecture")
    record = read_record(history)
    record["status"] = status
    atomic_json(history / "metrics.json", record)
    (history / "process.log").write_text("\n".join(log_lines), encoding="utf-8", newline="")
    video_path = tmp_path / "video.mp4"
    if video:
        video_path.write_bytes(b"video")
    job = {"run_id": history.name, "history_dir": str(history), "run_dir": str(run_registry.job_dir(history.name)),
           "video_path": str(video_path), "video_title": "강의"}
    run_registry.save_job(job)
    return job


# ---------------------------------------------------------------------------
# 로그인과 요청 보호
# ---------------------------------------------------------------------------
def test_without_password_local_is_allowed_and_tunnel_is_blocked(client):
    assert client.get("/api/options").status_code == 200
    assert client.get("/api/options", headers=CF).status_code == 403
    assert client.get("/api/session", headers=CF).json()["blocked"] is True


def test_password_login_sets_session_cookie(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret")
    assert client.get("/api/options").status_code == 401
    assert client.post("/api/login", json={"password": "wrong"}, headers=HEADERS).status_code == 401
    response = client.post("/api/login", json={"password": "secret"}, headers=HEADERS)
    assert response.status_code == 200
    assert client.get("/api/options").status_code == 200
    client.post("/api/logout", headers=HEADERS)
    assert client.get("/api/options").status_code == 401


def test_changing_password_invalidates_sessions(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret")
    client.post("/api/login", json={"password": "secret"}, headers=HEADERS)
    monkeypatch.setenv("APP_PASSWORD", "changed")
    assert client.get("/api/options").status_code == 401


def test_repeated_failures_lock_out_login(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret")
    for _ in range(login_throttle.MAX_FAILED_ATTEMPTS):
        client.post("/api/login", json={"password": "wrong"}, headers=HEADERS)
    response = client.post("/api/login", json={"password": "secret"}, headers=HEADERS)
    assert response.status_code == 429


def test_malformed_secrets_file_does_not_bypass_login(client, tmp_path, monkeypatch):
    path = tmp_path / "secrets.toml"
    path.write_text("bad toml = ", encoding="utf-8")
    monkeypatch.setattr(auth, "SECRETS_FILE", path)
    with pytest.raises(Exception):
        client.get("/api/options")


def test_state_changing_requests_need_csrf_header(client):
    assert client.post("/api/logout").status_code == 403
    assert client.post("/api/logout", headers=HEADERS).status_code == 200


# ---------------------------------------------------------------------------
# 업로드
# ---------------------------------------------------------------------------
def test_upload_saves_video_and_rejects_other_types(client, monkeypatch):
    monkeypatch.setattr(server, "get_video_info", lambda path: {"duration": 1})
    response = client.post("/api/uploads", files={"file": ("lecture.mp4", b"data", "video/mp4")}, headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "lecture" and body["source_key"] == "lecture.mp4_4"
    assert (run_registry.UPLOAD_DIR / body["upload_id"] / "input.mp4").read_bytes() == b"data"

    rejected = client.post("/api/uploads", files={"file": ("notes.txt", b"x", "text/plain")}, headers=HEADERS)
    assert rejected.status_code == 400


def test_unreadable_video_is_removed(client, monkeypatch):
    def broken(path):
        raise RuntimeError("bad")

    monkeypatch.setattr(server, "get_video_info", broken)
    response = client.post("/api/uploads", files={"file": ("x.mp4", b"data", "video/mp4")}, headers=HEADERS)
    assert response.status_code == 400
    assert not any(run_registry.UPLOAD_DIR.glob("*/input.mp4"))


def test_external_upload_limit_is_checked_before_reading_body(client, monkeypatch):
    monkeypatch.setattr(server, "EXTERNAL_UPLOAD_LIMIT_MB", 0)
    response = client.post("/api/uploads", files={"file": ("x.mp4", b"data", "video/mp4")},
                           headers={**HEADERS, **CF})
    # 외부 접속은 비밀번호가 없으면 차단되므로 크기 확인 단계에서 먼저 거절되어야 합니다.
    assert response.status_code == 413


def test_upload_ids_cannot_escape_upload_folder(client):
    body = {"upload_id": "../../etc", "summary_level": "standard"}
    assert client.post("/api/runs", json=body, headers=HEADERS).status_code == 404


# ---------------------------------------------------------------------------
# 분석 실행
# ---------------------------------------------------------------------------
def test_start_run_passes_upload_details_to_pipeline(client, monkeypatch):
    monkeypatch.setattr(server, "get_video_info", lambda path: {"duration": 1})
    upload = client.post("/api/uploads", files={"file": ("lecture.mp4", b"data", "video/mp4")}, headers=HEADERS).json()
    calls = {}

    class Log:
        closed = False

        def close(self):
            self.closed = True

    log = Log()

    def fake_launch(video_path, summary_level, title, **kwargs):
        calls.update(video_path=video_path, summary_level=summary_level, title=title, **kwargs)
        return object(), log, run_registry.JOBS_DIR / "run-1"

    monkeypatch.setattr(server, "launch_pipeline", fake_launch)
    response = client.post("/api/runs", json={"upload_id": upload["upload_id"], "summary_level": "detailed",
                                              "analysis_backend": "claude"}, headers=HEADERS)
    assert response.json() == {"run_id": "run-1"}
    assert calls["summary_level"] == "detailed" and calls["title"] == "lecture"
    assert calls["analysis_backend"] == "claude" and calls["job_info"]["upload_id"] == upload["upload_id"]
    assert log.closed


def test_start_run_rejects_busy_server_and_bad_options(client, monkeypatch):
    monkeypatch.setattr(server, "get_video_info", lambda path: {"duration": 1})
    upload = client.post("/api/uploads", files={"file": ("a.mp4", b"data", "video/mp4")}, headers=HEADERS).json()

    def busy(*_args, **_kwargs):
        raise run_registry.PipelineBusyError("다른 사용자의 영상 분석이 진행 중입니다.")

    monkeypatch.setattr(server, "launch_pipeline", busy)
    assert client.post("/api/runs", json={"upload_id": upload["upload_id"]}, headers=HEADERS).status_code == 409
    bad = {"upload_id": upload["upload_id"], "summary_level": "huge"}
    assert client.post("/api/runs", json=bad, headers=HEADERS).status_code == 400


def test_run_status_reports_progress_and_filtered_logs(client, tmp_path, monkeypatch):
    marker = PROGRESS_MARKER + json.dumps({"step": 2, "message": "음성 인식", "percent": 40})
    job = make_job(tmp_path, log_lines=["오디오 추출 시작", marker, "C:\\runs\\a.wav 저장"])

    class Running:
        def poll(self):
            return None

    monkeypatch.setattr(server, "handle_for", lambda _job: Running())
    body = client.get(f"/api/runs/{job['run_id']}").json()
    assert body["state"] == "running"
    assert [step["state"] for step in body["steps"][:3]] == ["done", "active-percent", "pending"]
    assert body["current"]["percent"] == 40
    assert body["logs"] == ["오디오 추출 시작"]


def test_run_that_exited_without_record_is_marked_interrupted(client, tmp_path):
    job = make_job(tmp_path)
    body = client.get(f"/api/runs/{job['run_id']}").json()
    assert body["state"] == "interrupted"
    assert read_record(job["history_dir"])["status"] == "interrupted"


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/does-not-exist").status_code == 404


# ---------------------------------------------------------------------------
# 결과와 저장
# ---------------------------------------------------------------------------
def write_result(run_dir, frame):
    (run_dir / "final").mkdir(parents=True)
    (run_dir / "final" / "final_summary.txt").write_text(
        "## 개요\n내용 (타임라인: 0.0 ~ 65.0)\n\n"
        "## 표/차트 기반 주요 정보\n### 1. 매출 추이 (타임라인: 10.0 ~ 20.0)\n매출이 늘었습니다.",
        encoding="utf-8")
    (run_dir / "ocr").mkdir(parents=True)
    entries = [{"timestamp": 1, "image_path": str(frame)},
               {"timestamp": 15, "image_path": str(frame), "scene_type": "chart_or_table", "ocr_text": "매출"}]
    (run_dir / "ocr" / "ocr_result.json").write_text(json.dumps(entries), encoding="utf-8")


def test_result_returns_timeline_blocks_with_frame_urls(client, tmp_path):
    job = make_job(tmp_path, status="success")
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpg")
    write_result(run_registry.job_dir(job["run_id"]), frame)

    body = client.get(f"/api/runs/{job['run_id']}/result").json()
    assert body["mode"] == "blocks" and body["video_url"].endswith("/video")
    assert client.get("/api/history").json()["records"][0]["has_result"] is True
    assert body["blocks"][0] == {"type": "markdown", "text": "## 개요\n내용 (0:00 ~ 1:05)"}
    item = body["blocks"][1]["items"][0]
    assert item["label"] == "0:10 ~ 0:20" and item["start"] == 10.0
    assert client.get(item["image_url"]).content == b"jpg"
    assert client.get(f"/api/runs/{job['run_id']}/video").content == b"video"


def test_structured_json_summary(client, tmp_path):
    job = make_job(tmp_path, status="success")
    final = run_registry.job_dir(job["run_id"]) / "final"
    final.mkdir(parents=True)
    (final / "final_summary_result.json").write_text(
        json.dumps({"title": "제목", "topics": ["문자열 주제"], "keywords": ["a"]}), encoding="utf-8")
    body = client.get(f"/api/runs/{job['run_id']}/result").json()
    assert body["mode"] == "structured"
    assert body["summary"]["topics"] == [{"content": "문자열 주제"}]


def test_missing_result_is_404(client, tmp_path):
    job = make_job(tmp_path, status="success")
    assert client.get(f"/api/runs/{job['run_id']}/result").status_code == 404


def test_save_then_browse_and_delete_saved_result(client, tmp_path):
    job = make_job(tmp_path, status="success")
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpg")
    write_result(run_registry.job_dir(job["run_id"]), frame)

    name = client.post(f"/api/runs/{job['run_id']}/save", headers=HEADERS).json()["name"]
    assert name.startswith("[강의] - ")
    items = client.get("/api/saved").json()["items"]
    assert [item["title"] for item in items] == ["강의"]

    detail = client.get(f"/api/saved/{name}").json()
    image_url = detail["blocks"][1]["items"][0]["image_url"]
    frame.unlink()  # 저장 결과는 원본 실행 프레임이 지워져도 자체 사본을 보여줘야 합니다.
    assert client.get(image_url).content == b"jpg"
    assert client.get(detail["video_url"]).content == b"video"

    assert client.delete(f"/api/saved/{name}", headers=HEADERS).status_code == 200
    assert client.get("/api/saved").json()["items"] == []


def test_saved_names_cannot_escape_saved_folder(client, tmp_path):
    (tmp_path / "saved").mkdir()
    (tmp_path / "history").mkdir()
    assert client.get("/api/saved/..").status_code == 404
    assert client.delete("/api/saved/..%5Chistory", headers=HEADERS).status_code == 404
    assert saved_folder("..", tmp_path / "saved") is None
    assert saved_folder("..\\history", tmp_path / "saved") is None
    assert (tmp_path / "history").exists()


# ---------------------------------------------------------------------------
# 실행 이력
# ---------------------------------------------------------------------------
def test_history_list_detail_log_and_csv(client, tmp_path):
    job = make_job(tmp_path, status="success", log_lines=["첫 줄", "둘째 줄"])
    run_id = job["run_id"]
    records = client.get("/api/history").json()["records"]
    assert [record["run_id"] for record in records] == [run_id]
    assert records[0]["has_result"] is False

    detail = client.get(f"/api/history/{run_id}").json()
    assert detail["has_log"] and detail["log_tail"] == "첫 줄\n둘째 줄"
    assert client.get(f"/api/history/{run_id}/log").text == "첫 줄\n둘째 줄"

    csv = client.post("/api/history/csv", json={"run_ids": [run_id]}, headers=HEADERS)
    assert run_id in csv.content.decode("utf-8-sig")
    assert client.get("/api/history/bad..id").status_code == 404


def test_frontend_fallback_serves_index_for_client_routes(client, tmp_path):
    assert client.get("/result/abc").status_code == 503
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    assert client.get("/result/abc").text == "<html>app</html>"
    assert client.get("/api/nope").status_code == 404
