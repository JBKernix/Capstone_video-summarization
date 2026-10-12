from __future__ import annotations

import logging

import streamlit as st

from modules.common.logger import configure_logging, get_logger


def _client_tag() -> str:
    """로그에 붙일 접속 세션/IP 정보를 만듭니다. Cloudflare Tunnel 경유 시 원 접속 IP를 우선합니다."""
    session_id = "-"
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        if ctx is not None:
            session_id = ctx.session_id[:8]
    except Exception:
        pass

    ip = "-"
    try:
        ip = st.context.headers.get("Cf-Connecting-Ip") or st.context.ip_address or "-"
    except Exception:
        pass

    return f"session={session_id} ip={ip}"


class _ClientTagAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        return f"[{_client_tag()}] {msg}", kwargs


def get_app_logger(name: str) -> logging.LoggerAdapter:
    """앱 화면에서 사용할 로거입니다. ``logs/client.log``와 콘솔에 기록되며 메시지 앞에 세션/IP 정보가 붙습니다."""
    configure_logging("client.log")
    return _ClientTagAdapter(get_logger(f"app.{name}"), {})
