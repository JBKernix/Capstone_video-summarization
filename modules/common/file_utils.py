# modules/common/file_utils.py

from __future__ import annotations

from pathlib import Path
from typing import Optional


def find_existing_path(
    stored_path: str | Path,
    anchor_path: str | Path,
    project_root: str | Path,
) -> Optional[Path]:
    """메타데이터/결과 JSON에 저장된 경로를 실제 존재하는 파일 경로로 해석합니다.

    저장된 경로는 절대경로, 현재 작업 디렉터리 기준, 프로젝트 루트 기준, 또는 anchor_path가
    위치한 산출물 디렉터리 기준 상대경로일 수 있어 후보를 순서대로 확인합니다.

    Args:
        stored_path: 메타데이터/결과 JSON에 저장된 경로 문자열입니다.
        anchor_path: 상대경로 해석 기준으로 사용할 파일(예: 메타데이터 JSON) 경로입니다.
        project_root: 프로젝트 루트 경로입니다.

    Returns:
        존재가 확인된 실제 파일 경로입니다. 어떤 후보에서도 파일을 찾지 못하면 ``None``입니다.
    """
    path = Path(stored_path)
    if path.is_absolute():
        return path.resolve() if path.is_file() else None

    anchor_path = Path(anchor_path).resolve()
    project_root = Path(project_root)

    candidates = [
        Path.cwd() / path,
        project_root / path,
        anchor_path.parent / path,
        anchor_path.parent.parent / path,
    ]
    return next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
