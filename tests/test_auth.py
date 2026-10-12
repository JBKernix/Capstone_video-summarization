from unittest.mock import MagicMock, patch

import pytest
from streamlit.errors import StreamlitSecretNotFoundError

from app.auth import require_login


def test_missing_optional_secrets_allows_local_start(tmp_path):
    with patch("app.auth.st") as st:
        st.secrets.get.side_effect = StreamlitSecretNotFoundError("missing")
        st.get_option.return_value = [str(tmp_path / "missing.toml")]
        require_login()
        st.stop.assert_not_called()


def test_bad_existing_secret_file_does_not_bypass_login(tmp_path):
    path = tmp_path / "secrets.toml"
    path.write_text("bad toml")
    with patch("app.auth.st") as st:
        st.secrets.get.side_effect = StreamlitSecretNotFoundError("invalid")
        st.get_option.return_value = [str(path)]
        with pytest.raises(StreamlitSecretNotFoundError):
            require_login()


def test_configured_password_still_requires_login():
    with patch("app.auth.st") as st:
        st.secrets.get.return_value = "example-password"
        st.session_state = {}
        st.button.return_value = False
        require_login()
        st.stop.assert_called_once()
