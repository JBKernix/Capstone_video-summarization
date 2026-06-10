from pathlib import Path

from huggingface_hub import snapshot_download


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = PROJECT_ROOT / "models" / "hf_cache"


def download_model(model_id: str, local_dir_name: str):
    local_dir = MODEL_DIR / local_dir_name
    local_dir.mkdir(parents=True, exist_ok=True)

    print(f"[다운로드 시작] {model_id}")
    print(f"[저장 위치] {local_dir}")

    snapshot_download(
        repo_id=model_id,
        local_dir=str(local_dir),
        local_dir_use_symlinks=False,
    )

    print(f"[다운로드 완료] {model_id}")


def main():
    download_model(
        model_id="Qwen/Qwen3-8B",
        local_dir_name="Qwen3-8B",
    )

    download_model(
        model_id="Qwen/Qwen2.5-VL-7B-Instruct",
        local_dir_name="Qwen2.5-VL-7B-Instruct",
    )


if __name__ == "__main__":
    main()