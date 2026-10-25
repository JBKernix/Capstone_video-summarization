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
    # 모델 로더가 확인하는 입력 토큰 상한입니다(transformers 런타임).
    max_input_tokens: int = 16384
    # transformers attention 구현입니다. "sdpa_no_gqa"는 models/attention.py 참고.
    attn_implementation: str = "sdpa"
    # LOCAL_MODEL_ATTENTION=sdpa로 기본 SDPA에 되돌렸을 때 쓰는 입력 토큰 상한입니다(None이면 max_input_tokens).
    sdpa_max_input_tokens: int | None = None
    # 프로필별로 더 줄일 입력 크기입니다. None이면 요약 수준 프리셋·서비스 기본값을 씁니다.
    segment_chunk_chars: int | None = None
    final_stt_chars: int | None = None
    final_vlm_chars: int | None = None

PROFILES = {
    p.id: p for p in (
        ModelProfile("legacy-qwen", "기존 Qwen3 8B + Qwen2.5-VL 7B", ("Qwen/Qwen3-8B", "Qwen/Qwen2.5-VL-7B-Instruct"), precision="fp16"),
        ModelProfile("qwen3.5-9b", "Qwen3.5 9B", ("Qwen/Qwen3.5-9B",), "Qwen3_5ForConditionalGeneration"),
        # 기본 "sdpa"는 GQA 호출이 Math 커널로 떨어져 메모리가 입력 길이의 제곱으로 늘었습니다
        # (RTX 4090: 7천 토큰 21.0GB, 8천 토큰 OOM). "sdpa_no_gqa"(mem-efficient 커널)는 1.6만 토큰 + 출력 4천 토큰에서도
        # 약 11GB라 출력·이미지 토큰과 데스크톱 VRAM 사용분을 빼고도 여유가 커서 1.6만 토큰으로 둡니다.
        # 2.4만·3.2만 토큰도 메모리는 들지만 디코딩이 12.8·10.1 tok/s로 느려져, 더 긴 강의는 구간 요약으로 처리합니다.
        # 측정: benchmarks/qwen3vl_context_bench.py, LOCAL_MODEL_ATTENTION=sdpa면 기존 설정(7천 토큰)으로 되돌립니다.
        ModelProfile("qwen3-vl-8b", "Qwen3-VL 8B Instruct", ("Qwen/Qwen3-VL-8B-Instruct",), "Qwen3VLForConditionalGeneration",
                     max_input_tokens=16384, attn_implementation="sdpa_no_gqa", sdpa_max_input_tokens=7000,
                     segment_chunk_chars=6000, final_stt_chars=4000, final_vlm_chars=4000),
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
