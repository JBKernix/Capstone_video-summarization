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
    monkeypatch.setattr(server, "USER_DEFAULTS_PATH", tmp_path / "user_defaults.json")
    monkeypatch.delenv("DEV_PASSWORD", raising=False)
    monkeypatch.setattr(server, "check_free_space", lambda *_args, **_kwargs: None)
    return TestClient(server.app)


def enter_dev_mode(client):
    assert client.post("/api/dev/login", json={"password": "admin"}, headers=HEADERS).status_code == 200


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
def test_without_password_local_and_tunnel_are_allowed(client):
    assert client.get("/api/options").status_code == 200
    assert client.get("/api/options", headers=CF).status_code == 200
    assert client.get("/api/session", headers=CF).json()["authenticated"] is True
    # 앱 비밀번호가 없어도 개발자 화면은 개발자 비밀번호가 있어야 합니다.
    assert client.get("/api/history", headers=CF).status_code == 403


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


def test_developer_mode_needs_its_own_password(client):
    assert client.get("/api/session").json()["developer"] is False
    assert client.get("/api/history").status_code == 403
    assert client.post("/api/dev/login", json={"password": "wrong"}, headers=HEADERS).status_code == 401
    enter_dev_mode(client)
    assert client.get("/api/session").json()["developer"] is True
    assert client.get("/api/history").status_code == 200
    client.post("/api/dev/logout", headers=HEADERS)
    assert client.get("/api/history").status_code == 403


def test_developer_mode_still_needs_app_login(client, monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "secret")
    assert client.post("/api/dev/login", json={"password": "admin"}, headers=HEADERS).status_code == 401
    client.post("/api/login", json={"password": "secret"}, headers=HEADERS)
    enter_dev_mode(client)
    # 앱 로그아웃은 개발자 모드도 함께 끝냅니다.
    client.post("/api/logout", headers=HEADERS)
    client.post("/api/login", json={"password": "secret"}, headers=HEADERS)
    assert client.get("/api/session").json()["developer"] is False


def test_dev_password_can_be_changed_by_env(client, monkeypatch):
    monkeypatch.setenv("DEV_PASSWORD", "other")
    assert client.post("/api/dev/login", json={"password": "admin"}, headers=HEADERS).status_code == 401
    assert client.post("/api/dev/login", json={"password": "other"}, headers=HEADERS).status_code == 200


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
    # 본문을 받기 전에 크기 확인 단계에서 먼저 거절되어야 합니다.
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
    enter_dev_mode(client)
    response = client.post("/api/runs", json={"upload_id": upload["upload_id"], "summary_level": "detailed",
                                              "analysis_backend": "claude"}, headers=HEADERS)
    assert response.json() == {"run_id": "run-1"}
    assert calls["summary_level"] == "detailed" and calls["title"] == "lecture"
    assert calls["analysis_backend"] == "claude" and calls["job_info"]["upload_id"] == upload["upload_id"]
    assert log.closed


def test_user_runs_use_backend_chosen_by_developer(client, monkeypatch):
    monkeypatch.setattr(server, "get_video_info", lambda path: {"duration": 1})
    upload = client.post("/api/uploads", files={"file": ("a.mp4", b"data", "video/mp4")}, headers=HEADERS).json()
    calls = {}

    class Log:
        def close(self):
            pass

    def fake_launch(video_path, summary_level, title, **kwargs):
        calls.update(kwargs)
        return object(), Log(), run_registry.JOBS_DIR / "run-1"

    monkeypatch.setattr(server, "launch_pipeline", fake_launch)
    body = {"upload_id": upload["upload_id"], "analysis_backend": "claude"}
    # 일반 사용자가 보낸 분석 방식은 무시하고 기본값(로컬)을 씁니다.
    client.post("/api/runs", json=body, headers=HEADERS)
    assert calls["analysis_backend"] == "local"

    defaults = {"analysis_backend": "claude", "local_model": server.DEFAULT_LOCAL_MODEL}
    assert client.put("/api/dev/user-defaults", json=defaults, headers=HEADERS).status_code == 403
    enter_dev_mode(client)
    assert client.put("/api/dev/user-defaults", json=defaults, headers=HEADERS).status_code == 200
    client.post("/api/dev/logout", headers=HEADERS)
    client.post("/api/runs", json={"upload_id": upload["upload_id"]}, headers=HEADERS)
    assert calls["analysis_backend"] == "claude"
    assert client.get("/api/options").json()["user_defaults"]["analysis_backend"] == "claude"


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
    assert body["logs"] == []
    enter_dev_mode(client)
    assert client.get(f"/api/runs/{job['run_id']}").json()["logs"] == ["오디오 추출 시작"]


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
    enter_dev_mode(client)
    assert client.get("/api/history").json()["records"][0]["has_result"] is True
    assert body["blocks"][0] == {"type": "markdown", "text": "## 개요\n내용 (0:00 ~ 1:05)"}
    item = body["blocks"][1]["items"][0]
    assert item["label"] == "0:10 ~ 0:20" and item["start"] == 10.0
    assert client.get(item["image_url"]).content == b"jpg"
    assert client.get(f"/api/runs/{job['run_id']}/video").content == b"video"


def test_result_outline_for_chapter_player(client, tmp_path):
    job = make_job(tmp_path, status="success")
    run_dir = run_registry.job_dir(job["run_id"])
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpg")
    (run_dir / "final").mkdir(parents=True)
    (run_dir / "final" / "final_summary.txt").write_text(
        "# 강의 제목\n\n"
        "## 핵심 주제\n- 첫째\n- 둘째\n- 셋째\n\n"
        "## 주요 내용\n\n"
        "### 2. 뒤 챕터 (타임라인: 60 ~ 70)\n- 뒤 내용\n\n"
        "### 1. 앞 챕터 (타임라인: 10.0 ~ 20.0)\n- '스타실드' 설명\n- VLM 요약 자료에서는 화면에 표가 나온다.\n\n"
        "## 표/차트 기반 주요 정보\n### 1. 매출 (타임라인: 10.0 ~ 20.0)\n- 표 내용\n\n"
        "## 종합 결론\n- 결론 하나\n",
        encoding="utf-8")
    (run_dir / "ocr").mkdir(parents=True)
    (run_dir / "ocr" / "ocr_result.json").write_text(
        json.dumps([{"timestamp": 15, "image_path": str(frame), "scene_type": "chart_or_table"}]), encoding="utf-8")
    (run_dir / "llm").mkdir(parents=True)
    (run_dir / "llm" / "stt_summary_result.json").write_text(
        json.dumps({"important_segments": [{"topic": "스타실드 통신 문제"}, {"topic": "경유"}]}), encoding="utf-8")

    outline = client.get(f"/api/runs/{job['run_id']}/result").json()["outline"]
    assert outline["title"] == "강의 제목"
    assert outline["key_points"] == ["첫째", "둘째", "셋째"]
    # 따옴표 강조 용어가 먼저, 겹치는 중요 구간 주제("스타실드 통신 문제")는 빠집니다.
    assert outline["keywords"] == ["스타실드", "경유"]
    first, second = outline["chapters"]
    assert (first["title"], second["title"]) == ("뒤 챕터", "앞 챕터")
    assert second["points"] == ["'스타실드' 설명"]
    assert second["screen_notes"] == ["화면에 표가 나온다."]
    assert client.get(second["thumb_url"]).content == b"jpg"
    assert first["thumb_url"] is None
    assert [visual["title"] for visual in outline["visuals"]] == ["매출"]
    assert outline["conclusion"] == ["결론 하나"]
    assert outline["extras"] == []


def test_result_without_chapters_has_no_outline(client, tmp_path):
    job = make_job(tmp_path, status="success")
    final = run_registry.job_dir(job["run_id"]) / "final"
    final.mkdir(parents=True)
    (final / "final_summary.txt").write_text("## 요약\n그냥 문단입니다.", encoding="utf-8")
    body = client.get(f"/api/runs/{job['run_id']}/result").json()
    assert body["mode"] == "blocks" and body["outline"] is None


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
    enter_dev_mode(client)
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


def test_result_returns_every_distinct_frame_in_a_chapter(client, tmp_path):
    job = make_job(tmp_path, status="success")
    run_dir = run_registry.job_dir(job["run_id"])
    frames = []
    for name in ("a", "b", "c", "next"):
        frame = tmp_path / f"{name}.jpg"
        frame.write_bytes(name.encode())
        frames.append(frame)
    (run_dir / "final").mkdir(parents=True)
    (run_dir / "final" / "final_summary.txt").write_text(
        "## 주요 내용\n### 1. 슬라이드 세 장 (타임라인: 10.0 ~ 20.0)\n- 내용\n\n"
        "## 표/차트 기반 주요 정보\n### 1. 표 (타임라인: 10.0 ~ 20.0)\n- 표 내용\n",
        encoding="utf-8")
    (run_dir / "ocr").mkdir(parents=True)
    (run_dir / "ocr" / "ocr_result.json").write_text(json.dumps([
        {"timestamp": 18, "image_path": str(frames[2]), "scene_type": "chart_or_table"},
        {"timestamp": 10, "image_path": str(frames[0])},
        {"timestamp": 14, "image_path": str(frames[1]), "scene_type": "chart_or_table", "ocr_text": "표"},
        # 바로 다음 구간의 프레임은 앞뒤 1초 여유 안에 있어도 섞이지 않아야 합니다.
        {"timestamp": 20.5, "image_path": str(frames[3])},
    ]), encoding="utf-8")

    body = client.get(f"/api/runs/{job['run_id']}/result").json()
    chapter = body["outline"]["chapters"][0]
    assert [(frame["time"], frame["label"]) for frame in chapter["frames"]] == [(10, "0:10"), (14, "0:14"), (18, "0:18")]
    assert [client.get(frame["url"]).content for frame in chapter["frames"]] == [b"a", b"b", b"c"]
    # 표/차트 섹션은 표/차트로 분류된 화면만 시간순으로 보여 줍니다.
    visual = body["outline"]["visuals"][0]
    assert [frame["time"] for frame in visual["frames"]] == [14, 18]
    assert client.get(visual["image_url"]).content == b"b"


def test_result_outline_from_lecture_note_json(client, tmp_path):
    job = make_job(tmp_path, status="success")
    run_dir = run_registry.job_dir(job["run_id"])
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpg")
    note = {
        "title": "경사하강법",
        "key_points": ["가중치 갱신"],
        "terms": [{"term": "학습률", "definition": "이동 크기"}, {"term": "", "definition": "버림"}],
        "chapters": [
            {"title": "갱신식", "start": 10.0, "end": 20.0, "points": ["식 설명"], "screen_notes": ["식이 보인다"]},
            # 시간이 없는 챕터도 버리지 않습니다.
            {"title": "정리", "start": None, "end": None, "points": ["복습"], "screen_notes": []},
            {"title": "", "points": []},
        ],
        "visuals": [{"type": "수식", "title": "갱신식", "start": 15, "end": None,
                     "content": ["w ← w − η∇L"], "meaning": "갱신 규칙"},
                    {"type": "기타", "title": "판서 식", "start": None, "end": None, "content": ["Q = W + ΔU"], "meaning": ""}],
        "conclusion": ["학습률이 중요"],
        "emphasis": ["학습률 선택이 핵심"],
        # 강조 사항을 따로 받기 전 결과처럼 강조 표현이 공지에 섞여 있습니다.
        "notices": ["다음 주 퀴즈", "시험에 나온다: 부호 규칙"],
    }
    (run_dir / "final").mkdir(parents=True)
    # 마크다운은 일부러 다른 내용으로 둡니다. 화면 구조는 lecture_note에서만 만들어야 합니다.
    (run_dir / "final" / "final_summary_result.json").write_text(json.dumps({
        "summary": "# 마크다운 제목\n\n## 주요 내용\n### 1. 마크다운 챕터 (타임라인: 0.0 ~ 5.0)\n- x\n",
        "lecture_note": note,
    }), encoding="utf-8")
    (run_dir / "ocr").mkdir(parents=True)
    (run_dir / "ocr" / "ocr_result.json").write_text(
        json.dumps([{"timestamp": 15, "image_path": str(frame), "scene_type": "chart_or_table"}]), encoding="utf-8")

    body = client.get(f"/api/runs/{job['run_id']}/result").json()
    assert body["mode"] == "blocks"
    # 개발자 화면용 블록은 계속 마크다운에서 만듭니다.
    assert body["blocks"][1]["items"][0]["title"] == "마크다운 챕터"
    outline = body["outline"]
    assert outline["title"] == "경사하강법"
    assert outline["keywords"][0] == "학습률"
    assert outline["terms"] == [{"term": "학습률", "definition": "이동 크기"}]
    assert outline["notices"] == ["다음 주 퀴즈"]
    assert outline["emphasis"] == ["학습률 선택이 핵심", "시험에 나온다: 부호 규칙"]
    first, second = outline["chapters"]
    assert (first["index"], first["label"], first["screen_notes"]) == (1, "0:10 ~ 0:20", ["식이 보인다"])
    assert client.get(first["thumb_url"]).content == b"jpg"
    assert (second["start"], second["label"], second["thumb_url"], second["frames"]) == (None, "시간 정보 없음", None, [])
    visual = outline["visuals"][0]
    assert (visual["kind"], visual["label"], visual["start"]) == ("수식", "0:15", 15.0)
    assert visual["text"] == "- w ← w − η∇L\n\n**강의에서의 의미** 갱신 규칙"
    assert client.get(visual["image_url"]).content == b"jpg"
    # 유형을 알 수 없는 이전 결과의 "기타" 자료는 유형 표시 없이 보여 줍니다.
    assert (outline["visuals"][1]["kind"], outline["visuals"][1]["title"]) == ("", "판서 식")
    assert outline["conclusion"] == ["학습률이 중요"]
