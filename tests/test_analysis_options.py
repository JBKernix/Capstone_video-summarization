from streamlit.testing.v1 import AppTest


def test_api_settings_have_no_key_input_or_client_key_requirement(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = AppTest.from_string('''
import streamlit as st
from app.analysis_options import render_analysis_options
ready = render_analysis_options()
st.button("start", disabled=not ready)
''')
    app.session_state["claude_api_key"] = "old-session-secret"
    app.session_state["local_server_url"] = "http://old-server:8000"
    app.session_state["analysis_backend"] = "claude"
    app.run()
    assert not app.exception
    assert not app.text_input
    assert not app.button[0].disabled
    assert "claude_api_key" not in app.session_state
    assert "local_server_url" not in app.session_state
    assert any("ANTHROPIC_API_KEY 환경변수" in item.value for item in app.caption)
    app.radio(key="analysis_backend").set_value("local").run()
    assert not app.exception
    assert not app.text_input
    assert app.radio(key="summary_level").value == "standard"
