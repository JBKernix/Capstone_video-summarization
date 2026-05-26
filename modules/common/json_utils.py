# modules/common/json_utils.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_json(json_path: str | Path) -> Dict[str, Any]:
    """JSON 파일 내용을 딕셔너리로 읽습니다.

    Args:
        json_path: 읽을 JSON 파일 경로입니다.

    Returns:
        파싱된 JSON 데이터입니다.

    Raises:
        FileNotFoundError: JSON 파일이 존재하지 않을 때 발생합니다.
        json.JSONDecodeError: JSON 파일 형식이 올바르지 않을 때 발생합니다.
    """
    json_path = Path(json_path)
    with json_path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(data: Dict[str, Any], json_path: str | Path) -> None:
    """딕셔너리 데이터를 JSON 파일로 저장합니다.

    Args:
        data: JSON으로 직렬화할 수 있는 딕셔너리입니다.
        json_path: JSON 파일을 저장할 경로입니다.
    """
    json_path = Path(json_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
