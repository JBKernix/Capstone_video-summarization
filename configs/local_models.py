"""Allowlisted local models; no torch import or user-controlled repository/path."""
import json
import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = Path(os.environ.get("LOCAL_MODEL_DIR", PROJECT_ROOT / "models" / "hf_cache"))
DEFAULT_LOCAL_MODEL = "legacy-qwen"

@dataclass(frozen=True)
class ModelProfile:
    id: str
    label: str
    repos: tuple[str, ...]
    architecture: str = ""
    precision: str = "nf4"
    runtime: str = "transformers"

PROFILES = {
    p.id: p for p in (
        ModelProfile("legacy-qwen", "기존 Qwen3 8B + Qwen2.5-VL 7B", ("Qwen/Qwen3-8B", "Qwen/Qwen2.5-VL-7B-Instruct"), precision="fp16"),
        ModelProfile("qwen3.5-9b", "Qwen3.5 9B", ("Qwen/Qwen3.5-9B",), "Qwen3_5ForConditionalGeneration"),
        ModelProfile("qwen3-vl-8b", "Qwen3-VL 8B Instruct", ("Qwen/Qwen3-VL-8B-Instruct",), "Qwen3VLForConditionalGeneration"),
        ModelProfile("gemma4-12b", "Gemma 4 12B IT", ("google/gemma-4-12B-it",), "Gemma4UnifiedForConditionalGeneration"),
        ModelProfile("minicpm-v4.5", "MiniCPM-V 4.5", ("openbmb/MiniCPM-V-4_5",), runtime="minicpm"),
        ModelProfile("internvl3.5-8b", "InternVL3.5 8B", ("OpenGVLab/InternVL3_5-8B-HF",), "InternVLForConditionalGeneration"),
        ModelProfile("glm4.6v-flash", "GLM-4.6V-Flash 9B", ("zai-org/GLM-4.6V-Flash",), "Glm4vForConditionalGeneration"),
    )
}

def get_profile(model_id):
    if model_id not in PROFILES:
        raise ValueError(f"지원하지 않는 로컬 모델: {model_id}")
    return PROFILES[model_id]

def repo_path(repo):
    return MODEL_ROOT / repo.split("/")[-1]

def checkpoint_status(repo):
    directory = repo_path(repo)
    manifest = directory / "download-manifest.json"
    try:
        if manifest.exists():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            files = data["files"]
            ready = data.get("repo") == repo and bool(files) and all(
                (directory / name).is_file() and (directory / name).stat().st_size == size
                for name, size in files.items())
            return {"ready": ready, "revision": data.get("revision"), "source": "manifest"}
        # Preserve existing legacy downloads only; new profiles require a completed manifest.
        if repo in PROFILES[DEFAULT_LOCAL_MODEL].repos:
            index = directory / "model.safetensors.index.json"
            names = set(json.loads(index.read_text())["weight_map"].values()) if index.exists() else {"model.safetensors"}
            ready = (directory / "config.json").is_file() and (directory / "tokenizer_config.json").is_file() and all(
                (directory / name).is_file() and (directory / name).stat().st_size > 0 for name in names)
            return {"ready": ready, "revision": None, "source": "existing"}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {"ready": False, "revision": None, "source": "missing"}

def minicpm_runtime_ready():
    default = PROJECT_ROOT / ".venv-minicpm" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return Path(os.environ.get("MINICPM_PYTHON", default)).is_file()

def profile_status(model_id):
    profile = get_profile(model_id)
    checkpoints = [{"repo": r, **checkpoint_status(r)} for r in profile.repos]
    return {"id": model_id, "label": profile.label, "precision": profile.precision,
            "runtime": profile.runtime, "runtime_ready": minicpm_runtime_ready() if profile.runtime == "minicpm" else True, "ready": all(c["ready"] for c in checkpoints),
            "checkpoints": checkpoints}

def require_downloaded(model_id):
    state = profile_status(model_id)
    if not state["ready"]:
        raise ValueError(f"{state['label']} 모델 다운로드가 필요합니다. GPU 서버에서 python scripts/download_models.py --all을 실행하세요.")
    return state
