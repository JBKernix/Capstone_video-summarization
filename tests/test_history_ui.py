from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from modules.common.run_history import RunRecorder, record_counts


def app():
    at = AppTest.from_file("app/main.py")
    at.secrets["APP_PASSWORD"] = ""
    at.run()
    at.switch_page("pages/4_run_history.py")
    return at


def test_history_empty_state(tmp_path):
    with patch("modules.common.run_history.DEFAULT_HISTORY_DIR", tmp_path), patch("modules.common.run_history.list_records", return_value=[]):
        at = app().run()
    assert not at.exception
    assert "아직 저장된" in at.info[0].value


def test_history_metrics_filters_and_logs(tmp_path):
    recorder = RunRecorder(tmp_path, input_name="강의.mp4", settings={"summary_level": "standard", "stt": {"model_size": "small"}})
    with recorder.capture():
        with recorder.stage(4, "프레임 추출"):
            record_counts(frames_extracted=4)
            print("example log")
    with patch("modules.common.run_history.DEFAULT_HISTORY_DIR", tmp_path), patch("modules.common.run_history.list_records", return_value=[recorder.record]):
        at = app().run()
        assert not at.exception
        assert at.metric[0].value == "1회"
        assert at.metric[3].value == "4장"
        assert "example log" in at.code[0].value
        at.text_input[0].set_value("없음").run()
        assert not at.exception
        assert at.metric[0].value == "0회"
        at.text_input[0].set_value("").run()
        at.selectbox[0].select("실패").run()
        assert at.metric[0].value == "0회"
