"""React 화면용 FastAPI 앱 서버입니다. Streamlit 화면과 같은 기능을 JSON API로 제공합니다.

    python -m uvicorn app.api.server:app --host 127.0.0.1 --port 8501

- /api/... : 로그인, 영상 업로드, 분석 실행/진행 상황, 결과, 저장된 요약, 실행 이력
- 실행 이력·모델 상태·분석 로그·분석 방식 선택은 개발자 모드(/api/dev/login)에서만 쓸 수 있습니다.
  사용자용 화면의 분석은 개발자가 지정한 분석 방식(USER_DEFAULTS_PATH)을 따릅니다.
- 그 외 경로: frontend/dist(React 빌드 결과)를 제공합니다.

LLM/VLM 추론 서버(GPU_SERVER_URL, 기본 127.0.0.1:8000)와는 별개의 서버입니다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.api import auth
from app.api.summary import frame_path, summary_payload
from app.pipeline_log import describe_step_status, parse_progress_state, read_pipeline_logs, read_raw_log_lines
from app.pipeline_process import launch_pipeline, stop_pipeline
from app import run_registry
from app.result_export import SUMMARY_FILENAMES, save_analysis_result
from app.run_registry import (
    EXTERNAL_UPLOAD_LIMIT_MB,
    PipelineBusyError,
    active_job,
    check_free_space,
    cleanup_expired,
    handle_for,
    job_is_running,
    load_job,
    new_upload_dir,
    remove_upload_dir,
)
from app.saved_results import (
    SAVE_ROOT,
    find_saved_video,
    list_saved_items,
    parse_saved_folder_name,
    saved_folder,
)
from modules.common.progress import STEP_LABELS, TOTAL_STEPS
from modules.common.run_history import (
    DEFAULT_HISTORY_DIR,
    TERMINAL_STATUSES,
    finish_external,
    list_records,
    model_load_rows,
    read_record,
    records_csv,
    run_directory,
)
from modules.llm import GPU_SERVER_URL
from modules.llm.backends import BACKEND_LABELS, DEFAULT_CLAUDE_MODEL
from modules.llm.local_models import DEFAULT_LOCAL_MODEL, LOCAL_MODEL_LABELS
from modules.llm.summary_levels import (
    DEFAULT_SUMMARY_LEVEL,
    SUMMARY_LEVEL_CAPTIONS,
    SUMMARY_LEVEL_LABELS,
    SUMMARY_LEVEL_STT_MODELS,
    SUMMARY_LEVELS,
)
from modules.preprocess import download_youtube_video, get_video_info, is_youtube_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST = Path(os.environ.get("FRONTEND_DIST") or PROJECT_ROOT / "frontend" / "dist")
# 기존 .streamlit/config.toml의 maxUploadSize와 같은 값입니다.
MAX_UPLOAD_MB = int(float(os.environ.get("MAX_UPLOAD_MB") or 500))
VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi")
UPLOAD_ID_PATTERN = re.compile(r"\d{8}-\d{6}-[0-9a-f]{12}")
UPLOAD_INFO_FILENAME = "upload.json"
LOG_TAIL_BYTES = 100_000
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "XMLHttpRequest"
USER_DEFAULTS_PATH = PROJECT_ROOT / "runs" / "user_defaults.json"


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    cleanup_expired()
    yield


app = FastAPI(title="영상 요약 앱 API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=_lifespan)
protected = [Depends(auth.require_auth)]
developer_only = [Depends(auth.require_developer)]


@app.middleware("http")
async def _guard_requests(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and request.method not in SAFE_METHODS:
        # 다른 사이트의 폼 전송은 이 헤더를 붙일 수 없으므로 CSRF를 막습니다(CORS는 열지 않습니다).
        if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
            return JSONResponse({"detail": "잘못된 요청입니다."}, status_code=403)
    if path == "/api/uploads" and request.method == "POST":
        # 본문을 받기 전에 크기 한도를 확인합니다(외부 접속은 Cloudflare 요청 크기 제한).
        limit = _upload_limit_mb(request) * 1024 * 1024
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > limit:
            return JSONResponse({"detail": f"파일이 너무 큽니다. 업로드 한도는 {limit // 1024 // 1024}MB입니다."},
                                status_code=413)
    return await call_next(request)


def _upload_limit_mb(request: Request) -> int:
    return min(MAX_UPLOAD_MB, EXTERNAL_UPLOAD_LIMIT_MB) if auth.is_external(request) else MAX_UPLOAD_MB


# ---------------------------------------------------------------------------
# 로그인
# ---------------------------------------------------------------------------
class LoginBody(BaseModel):
    password: str


@app.get("/api/session")
def session(request: Request) -> dict:
    return auth.auth_status(request)


@app.post("/api/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    auth.login(request, response, body.password)
    return {"authenticated": True}


@app.post("/api/logout")
def logout(response: Response) -> dict:
    auth.logout(response)
    return {"authenticated": False}


@app.post("/api/dev/login")
def dev_login(body: LoginBody, request: Request, response: Response) -> dict:
    auth.dev_login(request, response, body.password)
    return {"developer": True}


@app.post("/api/dev/logout")
def dev_logout(response: Response) -> dict:
    auth.dev_logout(response)
    return {"developer": False}


# ---------------------------------------------------------------------------
# 분석 설정
# ---------------------------------------------------------------------------
@app.get("/api/options", dependencies=protected)
def options(request: Request) -> dict:
    return {
        "summary_levels": [
            {"id": level, "label": SUMMARY_LEVEL_LABELS[level], "stt_model": SUMMARY_LEVEL_STT_MODELS[level],
             "caption": SUMMARY_LEVEL_CAPTIONS[level]}
            for level in SUMMARY_LEVELS
        ],
        "default_summary_level": DEFAULT_SUMMARY_LEVEL,
        "backends": [{"id": key, "label": label} for key, label in BACKEND_LABELS.items()],
        "local_models": [{"id": key, "label": label} for key, label in LOCAL_MODEL_LABELS.items()],
        "default_local_model": DEFAULT_LOCAL_MODEL,
        "user_defaults": _user_defaults(),
        "claude_model": DEFAULT_CLAUDE_MODEL,
        "backend_ready": bool(GPU_SERVER_URL.strip()),
        "upload_limit_mb": _upload_limit_mb(request),
        "external": auth.is_external(request),
        "video_extensions": list(VIDEO_EXTENSIONS),
        "steps": [{"step": step, "title": STEP_LABELS[step][0], "description": STEP_LABELS[step][1]}
                  for step in range(1, TOTAL_STEPS + 1)],
    }


# ---------------------------------------------------------------------------
# 사용자용 화면의 분석 방식 (개발자가 지정)
# ---------------------------------------------------------------------------
class UserDefaultsBody(BaseModel):
    analysis_backend: str
    local_model: str


def _check_backend(analysis_backend: str, local_model: str) -> None:
    if analysis_backend not in BACKEND_LABELS:
        raise HTTPException(400, "분석 방식은 local 또는 claude여야 합니다.")
    if local_model not in LOCAL_MODEL_LABELS:
        raise HTTPException(400, "지원하지 않는 로컬 모델입니다.")


def _user_defaults() -> dict:
    """사용자용 화면에서 시작한 분석에 쓰는 분석 방식입니다. 지정 전이면 로컬 기본 모델을 씁니다."""
    defaults = {"analysis_backend": "local", "local_model": DEFAULT_LOCAL_MODEL}
    try:
        stored = json.loads(USER_DEFAULTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaults
    if stored.get("analysis_backend") in BACKEND_LABELS:
        defaults["analysis_backend"] = stored["analysis_backend"]
    if stored.get("local_model") in LOCAL_MODEL_LABELS:
        defaults["local_model"] = stored["local_model"]
    return defaults


@app.put("/api/dev/user-defaults", dependencies=developer_only)
def set_user_defaults(body: UserDefaultsBody) -> dict:
    _check_backend(body.analysis_backend, body.local_model)
    USER_DEFAULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_DEFAULTS_PATH.write_text(json.dumps(body.model_dump(), ensure_ascii=False), encoding="utf-8")
    return _user_defaults()


@app.get("/api/models", dependencies=developer_only)
def models() -> dict:
    """GPU 서버에 미리 내려받은 로컬 모델의 설치 상태입니다."""
    try:
        response = requests.get(GPU_SERVER_URL.rstrip("/") + "/models", timeout=10)
        response.raise_for_status()
        return {"models": response.json()["models"]}
    except (requests.RequestException, ValueError, KeyError):
        raise HTTPException(502, "모델 목록을 가져오지 못했습니다. 서버에 수정본을 적용하고 재시작했는지 확인하세요.")


# ---------------------------------------------------------------------------
# 영상 업로드
# ---------------------------------------------------------------------------
def _upload_dir(upload_id: str) -> Path:
    if not UPLOAD_ID_PATTERN.fullmatch(upload_id or ""):
        raise HTTPException(404, "업로드한 영상을 찾을 수 없습니다.")
    directory = run_registry.UPLOAD_DIR / upload_id
    if not directory.is_dir():
        raise HTTPException(404, "업로드한 영상을 찾을 수 없습니다. 보존 기간이 지나 정리되었을 수 있습니다.")
    return directory


def _upload_video(directory: Path) -> Path:
    for candidate in sorted(directory.glob("input.*")):
        if candidate.suffix.lower() in VIDEO_EXTENSIONS:
            return candidate
    raise HTTPException(404, "업로드한 영상 파일을 찾을 수 없습니다.")


def _upload_response(directory: Path, info: dict) -> dict:
    return {"upload_id": directory.name, **info}


@app.post("/api/uploads", dependencies=protected)
def upload_video(request: Request, file: UploadFile = File(...)) -> dict:
    """업로드 영상을 업로드별 고유 폴더에 저장하고 영상 파일인지 검증합니다."""
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        raise HTTPException(400, "지원 형식은 MP4, MOV, AVI입니다.")
    limit = _upload_limit_mb(request) * 1024 * 1024
    cleanup_expired()

    upload_dir = None
    try:
        file.file.seek(0, os.SEEK_END)
        size = file.file.tell()
        file.file.seek(0)
        if size > limit:
            raise HTTPException(413, f"파일이 너무 큽니다. 업로드 한도는 {limit // 1024 // 1024}MB입니다.")
        check_free_space(size)
        upload_dir = new_upload_dir()
        save_path = upload_dir / f"input{suffix}"
        with open(save_path, "wb") as target:
            shutil.copyfileobj(file.file, target, length=1024 * 1024)
        if save_path.stat().st_size != size:
            raise ValueError(f"파일 저장 크기 불일치: 업로드={size}, 저장={save_path.stat().st_size}")
        try:
            get_video_info(save_path)
        except (OSError, RuntimeError, ValueError) as error:
            raise ValueError("영상 정보를 읽을 수 없습니다. 손상되었거나 지원하지 않는 영상 파일입니다.") from error
    except HTTPException:
        remove_upload_dir(upload_dir)
        raise
    except (OSError, ValueError) as error:
        remove_upload_dir(upload_dir)
        raise HTTPException(400, f"영상 저장에 실패했습니다: {error}")

    info = {"filename": filename, "title": Path(filename).stem, "source_key": f"{filename}_{size}"}
    (upload_dir / UPLOAD_INFO_FILENAME).write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return _upload_response(upload_dir, info)


class YoutubeBody(BaseModel):
    url: str


@app.post("/api/uploads/youtube", dependencies=protected)
def upload_youtube(body: YoutubeBody) -> dict:
    url = body.url.strip()
    if not is_youtube_url(url):
        raise HTTPException(400, "유효한 유튜브 링크가 아닙니다.")
    cleanup_expired()
    upload_dir = None
    try:
        check_free_space(0)
        upload_dir = new_upload_dir()
        save_path, video_title = download_youtube_video(url, upload_dir / "input")
    except Exception as error:
        remove_upload_dir(upload_dir)
        raise HTTPException(400, f"유튜브 영상 다운로드에 실패했습니다: {error}")

    info = {"filename": save_path.name, "title": video_title, "source_key": f"youtube_{url}"}
    (upload_dir / UPLOAD_INFO_FILENAME).write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    return _upload_response(upload_dir, info)


@app.delete("/api/uploads/{upload_id}", dependencies=protected)
def delete_upload(upload_id: str) -> dict:
    """다른 영상으로 바꿀 때 이전 업로드를 지웁니다. 실행 중인 작업의 영상은 지우지 않습니다."""
    remove_upload_dir(_upload_dir(upload_id))
    return {"deleted": True}


# ---------------------------------------------------------------------------
# 분석 실행
# ---------------------------------------------------------------------------
class RunBody(BaseModel):
    upload_id: str
    summary_level: str = DEFAULT_SUMMARY_LEVEL
    analysis_backend: str = "local"
    local_model: str = DEFAULT_LOCAL_MODEL


def _job(run_id: str) -> dict:
    try:
        job = load_job(run_id)
    except ValueError:
        job = None
    if not job:
        raise HTTPException(404, "분석 작업을 찾을 수 없습니다. 보존 기간이 지나 정리되었을 수 있습니다.")
    return job


def _record_status(job: dict) -> str | None:
    try:
        return read_record(job["history_dir"]).get("status")
    except (OSError, ValueError, KeyError):
        return None


@app.get("/api/runs/active", dependencies=protected)
def running_job() -> dict:
    job = active_job()
    return {"run_id": job["run_id"] if job else None}


@app.post("/api/runs", dependencies=protected)
def start_run(body: RunBody, request: Request) -> dict:
    if body.summary_level not in SUMMARY_LEVELS:
        raise HTTPException(400, "지원하지 않는 Whisper 설정입니다.")
    if auth.is_developer(request):
        _check_backend(body.analysis_backend, body.local_model)
    else:
        # 일반 사용자는 분석 방식(유료 API 사용 여부 등)을 고를 수 없고 개발자가 지정한 값을 씁니다.
        defaults = _user_defaults()
        body.analysis_backend, body.local_model = defaults["analysis_backend"], defaults["local_model"]

    upload_dir = _upload_dir(body.upload_id)
    video_path = _upload_video(upload_dir)
    try:
        info = json.loads((upload_dir / UPLOAD_INFO_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    title = info.get("title") or info.get("filename") or video_path.name

    try:
        _process, log_handle, directory = launch_pipeline(
            str(video_path), body.summary_level, title,
            analysis_backend=body.analysis_backend,
            local_server_url=GPU_SERVER_URL,
            local_model=body.local_model,
            job_info={
                "uploaded_filename": info.get("filename"),
                "uploaded_file_key": info.get("source_key"),
                "video_title": info.get("title"),
                "upload_id": upload_dir.name,
            },
        )
    except PipelineBusyError as error:
        raise HTTPException(409, str(error))
    # 자식 프로세스는 로그 파일 핸들을 따로 물려받았으므로 서버 쪽 핸들은 바로 닫습니다.
    log_handle.close()
    return {"run_id": directory.name}


@app.get("/api/runs/{run_id}", dependencies=protected)
def run_status(run_id: str, request: Request) -> dict:
    """분석 진행 상황입니다. 화면은 실행 중인 동안 1초마다 이 API를 호출합니다."""
    job = _job(run_id)
    returncode = handle_for(job).poll()
    if returncode is not None:
        # 정상 종료 기록 없이 프로세스가 끝났으면(강제 종료·서버 재시작 등) 중단으로 기록합니다.
        try:
            finish_external(job["history_dir"], "interrupted",
                            f"프로세스 종료 (코드 {returncode}). 정상 종료 기록이 없습니다.")
        except (OSError, ValueError):
            pass

    status = _record_status(job)
    if returncode is None:
        state = "running"
    elif status in TERMINAL_STATUSES:
        state = status
    else:
        state = "success" if returncode == 0 else "failed"

    raw_lines = read_raw_log_lines(Path(job["history_dir"]) / "process.log")
    progress = parse_progress_state(raw_lines)
    has_error = state in ("failed", "interrupted")
    steps = [
        {"step": step, "title": STEP_LABELS[step][0], "description": STEP_LABELS[step][1],
         **describe_step_status(step, progress, has_error=has_error)}
        for step in range(1, TOTAL_STEPS + 1)
    ]
    current = max(progress) if progress else None
    return {
        "run_id": run_id,
        "state": state,
        "returncode": returncode,
        "video_title": job.get("video_title") or job.get("uploaded_filename") or job.get("input_name"),
        "uploaded_filename": job.get("uploaded_filename") or job.get("input_name"),
        "upload_id": job.get("upload_id"),
        "steps": steps,
        "current": {"step": current, "title": STEP_LABELS[current][0], **progress[current]} if current else None,
        # 분석 로그는 개발자 화면에서만 보여 줍니다.
        "logs": read_pipeline_logs(raw_lines) if auth.is_developer(request) else [],
    }


@app.post("/api/runs/{run_id}/cancel", dependencies=protected)
def cancel_run(run_id: str) -> dict:
    job = _job(run_id)
    if job_is_running(job):
        stop_pipeline(handle_for(job), job["history_dir"])
    return {"cancelled": True}


@app.get("/api/runs/{run_id}/result", dependencies=protected)
def run_result(run_id: str) -> dict:
    job = _job(run_id)
    run_dir = Path(job["run_dir"])
    try:
        summary = summary_payload(run_dir / "final", run_dir / "ocr" / "ocr_result.json",
                                  f"/api/runs/{run_id}/frames", run_dir / "llm" / "stt_summary_result.json")
    except (FileNotFoundError, OSError, ValueError):
        raise HTTPException(404, "요약 결과 파일을 찾거나 읽을 수 없습니다. "
                                 "분석이 완료되지 않았거나 보존 기간이 지나 정리되었을 수 있습니다.")
    video_path = job.get("video_path")
    has_video = bool(video_path) and Path(video_path).is_file()
    return {
        "run_id": run_id,
        "title": job.get("video_title") or job.get("input_name"),
        "video_url": f"/api/runs/{run_id}/video" if has_video else None,
        **summary,
    }


@app.get("/api/runs/{run_id}/video", dependencies=protected)
def run_video(run_id: str) -> FileResponse:
    video_path = _job(run_id).get("video_path")
    if not video_path or not Path(video_path).is_file():
        raise HTTPException(404, "표시할 영상을 찾을 수 없습니다.")
    return FileResponse(video_path)


@app.get("/api/runs/{run_id}/frames/{index}", dependencies=protected)
def run_frame(run_id: str, index: int) -> FileResponse:
    path = frame_path(Path(_job(run_id)["run_dir"]) / "ocr" / "ocr_result.json", index)
    if path is None:
        raise HTTPException(404, "해당 구간 화면을 찾을 수 없습니다.")
    return FileResponse(path)


@app.post("/api/runs/{run_id}/save", dependencies=protected)
def save_run(run_id: str) -> dict:
    job = _job(run_id)
    run_dir = Path(job["run_dir"])
    video_path = job.get("video_path")
    try:
        saved_dir = save_analysis_result(
            video_path if video_path and Path(video_path).is_file() else None,
            run_dir / "final",
            SAVE_ROOT,
            title=job.get("video_title") or job.get("input_name"),
            ocr_result_path=run_dir / "ocr" / "ocr_result.json",
        )
    except FileNotFoundError as error:
        raise HTTPException(404, str(error))
    # 서버 내부 절대경로는 외부 사용자에게 노출하지 않습니다.
    return {"name": saved_dir.name}


# ---------------------------------------------------------------------------
# 저장된 요약
# ---------------------------------------------------------------------------
def _saved(name: str) -> Path:
    folder = saved_folder(name, SAVE_ROOT)
    if folder is None:
        raise HTTPException(404, "저장된 요약을 찾을 수 없습니다.")
    return folder


@app.get("/api/saved", dependencies=protected)
def saved_list() -> dict:
    return {"items": [
        {"name": item["folder"].name, "title": item["title"],
         "saved_at": item["timestamp"].isoformat() if item["timestamp"] else None}
        for item in list_saved_items(SAVE_ROOT)
    ]}


@app.get("/api/saved/{name}", dependencies=protected)
def saved_detail(name: str) -> dict:
    folder = _saved(name)
    try:
        summary = summary_payload(folder, folder / "ocr_result.json", f"/api/saved/{quote(name, safe='')}/frames")
    except (FileNotFoundError, OSError, ValueError):
        raise HTTPException(404, "선택한 저장 결과의 요약 파일을 찾거나 읽을 수 없습니다.")
    title, timestamp = parse_saved_folder_name(folder.name)
    return {
        "name": name,
        "title": title,
        "saved_at": timestamp.isoformat() if timestamp else None,
        "video_url": f"/api/saved/{quote(name, safe='')}/video" if find_saved_video(folder) else None,
        **summary,
    }


@app.get("/api/saved/{name}/video", dependencies=protected)
def saved_video(name: str) -> FileResponse:
    video = find_saved_video(_saved(name))
    if video is None:
        raise HTTPException(404, "표시할 영상을 찾을 수 없습니다.")
    return FileResponse(video)


@app.get("/api/saved/{name}/frames/{index}", dependencies=protected)
def saved_frame(name: str, index: int) -> FileResponse:
    path = frame_path(_saved(name) / "ocr_result.json", index)
    if path is None:
        raise HTTPException(404, "해당 구간 화면을 찾을 수 없습니다.")
    return FileResponse(path)


@app.delete("/api/saved/{name}", dependencies=protected)
def delete_saved(name: str) -> dict:
    shutil.rmtree(_saved(name), ignore_errors=True)
    return {"deleted": True}


# ---------------------------------------------------------------------------
# 실행 이력
# ---------------------------------------------------------------------------
def _history_dir(run_id: str) -> Path:
    try:
        directory = run_directory(DEFAULT_HISTORY_DIR, run_id)
        read_record(directory)
    except (OSError, ValueError):
        raise HTTPException(404, "실행 기록을 찾을 수 없습니다.")
    return directory


def _history_log(directory: Path) -> Path | None:
    for name in ("process.log", "pipeline.log"):
        if (directory / name).exists():
            return directory / name
    return None


@app.get("/api/history", dependencies=developer_only)
def history() -> dict:
    records = list_records(DEFAULT_HISTORY_DIR)
    for record in records:
        # 결과 화면은 실행 산출물 폴더(runs/jobs)가 보존 기간 안에 남아 있을 때만 열 수 있습니다.
        record["has_result"] = _has_result(record["run_id"])
    return {"records": records}


def _has_result(run_id: str) -> bool:
    job = load_job(run_id)
    if not job:
        return False
    final_dir = Path(job["run_dir"]) / "final"
    return any((final_dir / name).is_file() for name in SUMMARY_FILENAMES)


class CsvBody(BaseModel):
    run_ids: list[str]


@app.post("/api/history/csv", dependencies=developer_only)
def history_csv(body: CsvBody) -> Response:
    wanted = set(body.run_ids)
    records = [record for record in list_records(DEFAULT_HISTORY_DIR) if record["run_id"] in wanted]
    return Response(records_csv(records), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="run_history.csv"'})


@app.get("/api/history/{run_id}", dependencies=developer_only)
def history_detail(run_id: str) -> dict[str, Any]:
    directory = _history_dir(run_id)
    record = read_record(directory)
    log_path = _history_log(directory)
    log = log_path.read_bytes() if log_path else b""
    return {
        "record": record,
        "model_load_rows": model_load_rows(record),
        "has_log": log_path is not None,
        "log_tail": log[-LOG_TAIL_BYTES:].decode("utf-8", errors="replace"),
        "log_truncated": len(log) > LOG_TAIL_BYTES,
    }


@app.get("/api/history/{run_id}/log", dependencies=developer_only)
def history_log(run_id: str) -> FileResponse:
    log_path = _history_log(_history_dir(run_id))
    if log_path is None:
        raise HTTPException(404, "아직 기록된 로그가 없습니다.")
    return FileResponse(log_path, media_type="text/plain", filename=f"{run_id}.log")


# ---------------------------------------------------------------------------
# React 빌드 결과 제공 (마지막에 등록해야 /api 경로를 가리지 않습니다)
# ---------------------------------------------------------------------------
@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def unknown_api(path: str) -> None:
    raise HTTPException(404, "존재하지 않는 API입니다.")


if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str) -> Response:
    if path == "api" or path.startswith("api/"):
        raise HTTPException(404, "존재하지 않는 API입니다.")
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        return JSONResponse({"detail": "React 빌드 결과가 없습니다. frontend 폴더에서 npm run build를 실행하세요."},
                            status_code=503)
    candidate = (FRONTEND_DIST / path).resolve()
    if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
        return FileResponse(candidate)
    # 클라이언트 라우팅(/result/<run_id> 등)은 모두 index.html로 보냅니다.
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
