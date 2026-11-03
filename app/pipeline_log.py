"""파이프라인 실행 로그(process.log)를 화면용 로그와 단계별 진행 상황으로 해석합니다.

Streamlit 업로드 페이지와 FastAPI 앱 API가 함께 사용하므로 UI 라이브러리에 의존하지 않습니다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from modules.common.progress import PROGRESS_MARKER, STEP_STT

ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
# Whisper STT의 tqdm 진행률 표시줄(예: "45%|████  | 12/27 ...")을 감지하고 퍼센트를 추출합니다.
STT_TQDM_PATTERN = re.compile(r"^\s*(\d{1,3})%\|")
PATH_FRAGMENT_PATTERN = re.compile(r"([A-Za-z]:[\\/]|(?:^|\s)(?:runs|data)[\\/])")
PATH_OUTPUT_KEYWORDS = (
    "저장",
    "결과",
    "완료:",
    "파일:",
    "메타데이터:",
    "saved:",
    "complete:",
)


def clean_pipeline_log_line(line: str) -> str:
    line = ANSI_ESCAPE_PATTERN.sub("", line)
    return line.strip()


def is_progress_log_line(line: str) -> bool:
    return bool(STT_TQDM_PATTERN.search(line)) or (
        "|" in line and ("it/s" in line or "s/it" in line)
    )


def is_path_output_log_line(line: str) -> bool:
    lower_line = line.lower()
    return bool(PATH_FRAGMENT_PATTERN.search(line)) and any(
        keyword in lower_line for keyword in PATH_OUTPUT_KEYWORDS
    )


def read_raw_log_lines(log_path: str | Path) -> list[str]:
    log_path = Path(log_path)
    if not log_path.exists():
        return []

    raw_text = log_path.read_bytes()
    try:
        text = raw_text.decode("utf-8")
    except UnicodeDecodeError:
        text = raw_text.decode("cp949", errors="replace")

    return [clean_pipeline_log_line(raw_line) for raw_line in text.splitlines()]


def read_pipeline_logs(raw_lines: list[str], limit: int = 40) -> list[str]:
    """사람이 읽기 편하도록 진행률 마커/tqdm 진행바/산출물 경로 줄을 걸러낸 로그입니다."""
    lines = [
        line
        for line in raw_lines
        if line
        and not line.startswith(PROGRESS_MARKER)
        and not is_progress_log_line(line)
        and not is_path_output_log_line(line)
    ]
    return lines[-limit:]


def parse_progress_state(raw_lines: list[str]) -> dict[int, dict]:
    """로그 원본 줄에서 단계별 최신 진행 상황(퍼센트/메시지)을 추출합니다.

    같은 단계에서 퍼센트 없는 메시지가 나중에 와도 이전 퍼센트는 유지합니다(sticky).
    """
    state: dict[int, dict] = {}

    def _update(step: int, message: str | None, percent: float | None) -> None:
        entry = state.setdefault(step, {"percent": None, "message": ""})
        if message:
            entry["message"] = message
        if percent is not None:
            entry["percent"] = percent

    for line in raw_lines:
        if line.startswith(PROGRESS_MARKER):
            try:
                payload = json.loads(line[len(PROGRESS_MARKER):].strip())
            except json.JSONDecodeError:
                continue
            step = payload.get("step")
            if isinstance(step, int):
                _update(step, payload.get("message"), payload.get("percent"))
            continue

        match = STT_TQDM_PATTERN.match(line)
        if match:
            _update(STEP_STT, "음성 인식 처리 중", float(match.group(1)))

    return state


def describe_step_status(
    step: int, progress_state: dict[int, dict], has_error: bool = False
) -> dict:
    """단계 하나의 렌더링 상태(done/active-percent/active-indeterminate/error/pending)를 계산합니다."""
    if not progress_state:
        return {"state": "pending", "percent": None, "message": ""}

    current_step = max(progress_state.keys())
    if step < current_step:
        return {"state": "done", "percent": 100.0, "message": ""}
    if step > current_step:
        return {"state": "pending", "percent": None, "message": ""}

    entry = progress_state[step]
    percent = entry.get("percent")
    message = entry.get("message") or ""
    if has_error:
        return {"state": "error", "percent": percent, "message": message or "오류 발생"}
    if percent is not None:
        return {"state": "active-percent", "percent": percent, "message": message}
    return {"state": "active-indeterminate", "percent": None, "message": message}
