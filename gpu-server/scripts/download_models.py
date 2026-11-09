"""Resumable, revision-pinned downloads. No weights are fetched at import/startup."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.local_models import PROFILES, get_profile, repo_path

# Safetensors only: exclude duplicate bin/GGUF/AWQ exports and example media.
PATTERNS = ["*.json", "*.safetensors", "*.model", "*.txt", "*.tiktoken", "*.jinja", "*.py"]

def download_profile(model_id, *, plan=False, notify=lambda **kwargs: None):
    from fnmatch import fnmatch
    from huggingface_hub import HfApi, snapshot_download
    from filelock import FileLock
    profile = get_profile(model_id)
    results = []
    for repo in profile.repos:
        directory = repo_path(repo)
        directory.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(directory) + ".download.lock", timeout=0):
            lock_path = directory / "download-revision.json"
            # Retries stay on the same snapshot even if upstream main moves.
            revision = json.loads(lock_path.read_text())["revision"] if lock_path.exists() else "main"
            info = HfApi().model_info(repo, revision=revision, files_metadata=True)
            files = {s.rfilename: s.size for s in info.siblings
                     if any(fnmatch(s.rfilename, pattern) for pattern in PATTERNS)}
            if not files or not any(n.endswith(".safetensors") for n in files) or any(s is None for s in files.values()):
                raise ValueError(f"완전한 safetensors 파일 목록을 확인할 수 없습니다: {repo}")
            result = {"repo": repo, "revision": info.sha, "bytes": sum(files.values())}
            results.append(result)
            notify(repo=repo, total_bytes=result["bytes"], revision=info.sha)
            if plan:
                continue
            directory.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(json.dumps({"repo": repo, "revision": info.sha}), encoding="utf-8")
            snapshot_download(repo_id=repo, revision=info.sha, local_dir=str(directory), allow_patterns=PATTERNS)
            if not all((directory / name).is_file() and (directory / name).stat().st_size == size for name, size in files.items()):
                raise RuntimeError(f"다운로드 파일 검증 실패: {repo}")
            manifest = {**result, "files": files, "completed_at": datetime.now(timezone.utc).isoformat()}
            temporary = directory / "download-manifest.tmp"
            temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(directory / "download-manifest.json")
    return results

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--model", nargs="+", choices=list(PROFILES))
    group.add_argument("--list", action="store_true")
    parser.add_argument("--plan", action="store_true", help="가중치 다운로드 없이 실제 용량과 revision 조회")
    args = parser.parse_args()
    if args.list:
        for p in PROFILES.values():
            print(f"{p.id}: {p.label} ({p.precision})")
        return 0
    failed = []
    for model_id in PROFILES if args.all else args.model:
        try:
            print(model_id, json.dumps(download_profile(model_id, plan=args.plan), ensure_ascii=False), flush=True)
        except Exception as error:
            failed.append(model_id)
            print(f"실패: {model_id} ({type(error).__name__}). HF_TOKEN/접근 승인, 네트워크, 디스크 공간을 확인하세요.", file=sys.stderr)
    return 1 if failed else 0

if __name__ == "__main__":
    raise SystemExit(main())
