"""Readiness and explicit download actions for the fixed model catalogue."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from fastapi import APIRouter, HTTPException
from configs.local_models import PROFILES, get_profile, profile_status
from scripts.download_models import download_profile

router = APIRouter()
_downloads = {}
_lock = Lock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-download")

def _update(model_id, **fields):
    with _lock:
        _downloads.setdefault(model_id, {}).update(fields)

def _run(model_id):
    _update(model_id, status="downloading", error=None)
    try:
        download_profile(model_id, notify=lambda **fields: _update(model_id, **fields))
        _update(model_id, status="completed")
    except Exception as error:
        _update(model_id, status="failed", error=f"{type(error).__name__}: 서버의 HF_TOKEN/모델 접근 승인, 네트워크, 디스크 공간을 확인하세요. 다시 누르면 이어받습니다.")

@router.get("/models")
def list_local_models():
    with _lock:
        downloads = {key: dict(value) for key, value in _downloads.items()}
    return {"models": [{**profile_status(key), "download": downloads.get(key)} for key in PROFILES]}

@router.post("/models/{model_id}/download", status_code=202)
def start_download(model_id: str):
    try:
        get_profile(model_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    with _lock:
        if _downloads.get(model_id, {}).get("status") in {"queued", "downloading"}:
            return {"model_id": model_id, **_downloads[model_id]}
        _downloads[model_id] = {"status": "queued"}
    _executor.submit(_run, model_id)
    return {"model_id": model_id, "status": "queued"}
