from __future__ import annotations

import streamlit as st


def require_login() -> None:
    """외부(Cloudflare Tunnel)로 노출된 앱에 비밀번호 게이트를 겁니다.

    st.secrets에 APP_PASSWORD가 없으면(로컬 전용 실행 등) 그냥 통과시킵니다.
    """
    password = st.secrets.get("APP_PASSWORD")
    if not password:
        return

    if st.session_state.get("authenticated"):
        return

    st.title("🔒 로그인")
    entered = st.text_input("비밀번호", type="password")
    if st.button("입장", type="primary"):
        if entered == password:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")

    if not st.session_state.get("authenticated"):
        st.stop()
