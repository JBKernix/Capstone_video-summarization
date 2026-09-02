# modules/common/config.py

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def load_yaml_config(config_path: str | Path) -> Dict[str, Any]:
    """YAML 설정 파일을 읽어 딕셔너리로 반환합니다.

    Args:
        config_path: 읽을 YAML 설정 파일 경로입니다.

    Returns:
        설정 딕셔너리입니다. 파일이 없으면 빈 딕셔너리를 반환합니다.

    Raises:
        ImportError: PyYAML 패키지가 설치되어 있지 않을 때 발생합니다.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        return {}

    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "YAML 설정 파일을 사용하려면 PyYAML 패키지가 필요합니다. "
            "예: pip install PyYAML"
        ) from exc

    with config_path.open("r", encoding="utf-8-sig") as file:
        return yaml.safe_load(file) or {}
