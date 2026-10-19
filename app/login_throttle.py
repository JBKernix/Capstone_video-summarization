"""같은 접속 IP에서 비밀번호를 연속으로 틀리면 잠시 로그인을 막습니다(무차별 대입 완화).

Streamlit 로그인(app/auth.py)과 FastAPI 앱 API 로그인이 함께 사용합니다.
"""
from __future__ import annotations

import threading
import time

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 60
_failures: dict[str, tuple[int, float]] = {}
_failures_lock = threading.Lock()


def locked_out(ip: str) -> float:
    """잠금이 걸려 있으면 남은 초를, 아니면 0을 반환합니다."""
    with _failures_lock:
        count, last = _failures.get(ip, (0, 0.0))
        remaining = LOCKOUT_SECONDS - (time.time() - last)
        if count >= MAX_FAILED_ATTEMPTS and remaining > 0:
            return remaining
        if count >= MAX_FAILED_ATTEMPTS:
            _failures.pop(ip, None)
        return 0.0


def record_failure(ip: str) -> None:
    with _failures_lock:
        count, _ = _failures.get(ip, (0, 0.0))
        _failures[ip] = (count + 1, time.time())


def clear_failures(ip: str) -> None:
    with _failures_lock:
        _failures.pop(ip, None)
