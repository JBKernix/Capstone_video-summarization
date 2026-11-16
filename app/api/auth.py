"""FastAPI 앱 API의 비밀번호 로그인과 세션 쿠키입니다.

Streamlit 로그인(app/auth.py)과 같은 규칙을 따릅니다.
- 비밀번호(APP_PASSWORD)가 없으면 로컬·외부(Cloudflare Tunnel) 접속 모두 로그인 없이 통과합니다.
- 같은 IP에서 연속으로 틀리면 잠시 로그인을 막습니다(app/login_throttle.py).

비밀번호는 APP_PASSWORD 환경변수를 먼저 보고, 없으면 기존 .streamlit/secrets.toml을 읽습니다.

개발자 모드(실행 이력·모델 상태·분석 방식 선택 등 개발자용 화면)는 별도 비밀번호(DEV_PASSWORD, 기본 "admin")로
들어가며 별도 쿠키(vs_dev)를 씁니다. 일반 접속은 사용자용 화면만 사용합니다.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import tomllib
from pathlib import Path

from fastapi import HTTPException, Request, Response

from app.login_throttle import clear_failures, locked_out, record_failure

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SECRETS_FILE = PROJECT_ROOT / ".streamlit" / "secrets.toml"
SESSION_COOKIE = "vs_session"
DEV_COOKIE = "vs_dev"
DEFAULT_DEV_PASSWORD = "admin"
SESSION_SECONDS = int(float(os.environ.get("APP_SESSION_HOURS") or 12) * 3600)
# 서버를 재시작하면 기존 로그인이 풀립니다. 유지하려면 APP_SESSION_SECRET을 고정값으로 설정하세요.
_SESSION_SECRET = (os.environ.get("APP_SESSION_SECRET") or secrets.token_hex(32)).encode("utf-8")


def app_password() -> str | None:
    value = os.environ.get("APP_PASSWORD")
    if value and value.strip():
        return value
    if not SECRETS_FILE.exists():
        return None
    # 기존 설정 파일이 깨져 있으면 로그인을 건너뛰지 않고 오류를 그대로 냅니다.
    value = tomllib.loads(SECRETS_FILE.read_text(encoding="utf-8")).get("APP_PASSWORD")
    return str(value) if value else None


def dev_password() -> str:
    value = os.environ.get("DEV_PASSWORD")
    return value if value and value.strip() else DEFAULT_DEV_PASSWORD


def is_external(request: Request) -> bool:
    """Cloudflare Tunnel을 거친 요청인지 확인합니다(Cloudflare가 붙이는 헤더 기준)."""
    return bool(request.headers.get("cf-connecting-ip"))


def client_ip(request: Request) -> str:
    """Cloudflare Tunnel 경유 시 원 접속 IP, 아니면 직접 접속 IP입니다."""
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "-")


def _signature(expires: int, password: str, scope: str = "") -> str:
    # 비밀번호를 바꾸면 기존 세션이 모두 무효가 되도록 비밀번호 해시도 서명에 넣습니다.
    # scope로 일반 세션과 개발자 세션 서명을 구분해 한쪽 쿠키를 다른 쪽에 쓸 수 없게 합니다.
    password_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()
    message = f"{scope}{expires}:{password_hash}".encode("utf-8")
    return hmac.new(_SESSION_SECRET, message, hashlib.sha256).hexdigest()


def _valid_session(token: str | None, password: str, scope: str = "") -> bool:
    if not token or "." not in token:
        return False
    expires_text, signature = token.split(".", 1)
    if not expires_text.isdigit() or int(expires_text) < time.time():
        return False
    return hmac.compare_digest(signature, _signature(int(expires_text), password, scope))


def _set_session_cookie(request: Request, response: Response, name: str, password: str, scope: str = "") -> None:
    expires = int(time.time()) + SESSION_SECONDS
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https" or is_external(request)
    response.set_cookie(
        name, f"{expires}.{_signature(expires, password, scope)}",
        max_age=SESSION_SECONDS, httponly=True, samesite="lax", secure=secure, path="/",
    )


def is_developer(request: Request) -> bool:
    return _valid_session(request.cookies.get(DEV_COOKIE), dev_password(), "dev:")


def auth_status(request: Request) -> dict:
    password = app_password()
    if not password:
        status = {"required": False, "authenticated": True}
    else:
        status = {"required": True, "authenticated": _valid_session(request.cookies.get(SESSION_COOKIE), password)}
    status["developer"] = status["authenticated"] and is_developer(request)
    return status


def require_auth(request: Request) -> None:
    """로그인이 필요한 API에 거는 FastAPI 의존성입니다."""
    if not auth_status(request)["authenticated"]:
        raise HTTPException(401, "로그인이 필요합니다.")


def require_developer(request: Request) -> None:
    """개발자 모드에서만 쓰는 API에 거는 FastAPI 의존성입니다."""
    require_auth(request)
    if not is_developer(request):
        raise HTTPException(403, "개발자 모드 인증이 필요합니다.")


def login(request: Request, response: Response, entered: str) -> None:
    password = app_password()
    if not password:
        return

    ip = client_ip(request)
    remaining = locked_out(ip)
    if remaining:
        raise HTTPException(429, f"로그인 시도가 너무 많습니다. {remaining:.0f}초 후 다시 시도하세요.")
    if not hmac.compare_digest(str(entered).encode("utf-8"), password.encode("utf-8")):
        record_failure(ip)
        raise HTTPException(401, "비밀번호가 올바르지 않습니다.")

    clear_failures(ip)
    _set_session_cookie(request, response, SESSION_COOKIE, password)


def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(DEV_COOKIE, path="/")


def dev_login(request: Request, response: Response, entered: str) -> None:
    require_auth(request)
    # 일반 로그인과 실패 횟수를 따로 셉니다.
    key = f"dev:{client_ip(request)}"
    remaining = locked_out(key)
    if remaining:
        raise HTTPException(429, f"시도가 너무 많습니다. {remaining:.0f}초 후 다시 시도하세요.")
    password = dev_password()
    if not hmac.compare_digest(str(entered).encode("utf-8"), password.encode("utf-8")):
        record_failure(key)
        raise HTTPException(401, "개발자 비밀번호가 올바르지 않습니다.")
    clear_failures(key)
    _set_session_cookie(request, response, DEV_COOKIE, password, "dev:")


def dev_logout(response: Response) -> None:
    response.delete_cookie(DEV_COOKIE, path="/")
