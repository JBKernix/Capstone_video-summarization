from __future__ import annotations

import hmac

import streamlit as st
from pathlib import Path
from streamlit.errors import StreamlitSecretNotFoundError

from app.login_throttle import locked_out as _locked_out, record_failure as _record_failure


def _header(name: str) -> str:
    try:
        value = st.context.headers.get(name)
    except Exception:
        return ""
    return value if isinstance(value, str) else ""


def _client_ip() -> str:
    """Cloudflare Tunnel 경유 시 원 접속 IP, 아니면 직접 접속 IP입니다."""
    ip = _header("Cf-Connecting-Ip")
    if ip:
        return ip
    try:
        value = st.context.ip_address
    except Exception:
        return "-"
    return value if isinstance(value, str) and value else "-"


def require_login() -> None:
    """외부(Cloudflare Tunnel)로 노출된 앱에 비밀번호 게이트를 겁니다.

    st.secrets에 APP_PASSWORD가 없으면(로컬 전용 실행 등) 그냥 통과시킵니다.
    단, Cloudflare Tunnel을 거친 외부 접속은 비밀번호가 설정되지 않았으면 차단합니다.
    """
    try:
        password = st.secrets.get("APP_PASSWORD")
    except StreamlitSecretNotFoundError:
        # A clean local checkout has no secrets file. Preserve failure for an
        # existing but malformed configuration instead of bypassing its login.
        if any(Path(path).expanduser().exists() for path in st.get_option("secrets.files")):
            raise
        password = None
    if not password:
        if _header("Cf-Connecting-Ip"):
            st.error(
                "외부 접속용 비밀번호가 설정되지 않아 접속을 차단했습니다. "
                "서버 관리자는 .streamlit/secrets.toml에 APP_PASSWORD를 설정한 뒤 Streamlit을 재시작하세요."
            )
            st.stop()
        return

    if st.session_state.get("authenticated"):
        return

    st.title("🔒 로그인")
    entered = st.text_input("비밀번호", type="password")
    if st.button("입장", type="primary"):
        ip = _client_ip()
        remaining = _locked_out(ip)
        if remaining:
            st.error(f"로그인 시도가 너무 많습니다. {remaining:.0f}초 후 다시 시도하세요.")
        elif hmac.compare_digest(str(entered).encode("utf-8"), str(password).encode("utf-8")):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            _record_failure(ip)
            st.error("비밀번호가 올바르지 않습니다.")

    if not st.session_state.get("authenticated"):
        st.stop()
