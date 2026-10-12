"""User-facing controls; credentials are owned by the inference server."""
import streamlit as st
import requests
import importlib
from modules.llm.local_models import LOCAL_MODEL_LABELS, DEFAULT_LOCAL_MODEL

from modules.llm import GPU_SERVER_URL
from modules.llm.backends import BACKEND_LABELS, DEFAULT_CLAUDE_MODEL
from modules.llm import summary_levels as _summary_levels

# A running Streamlit session may retain the pre-update module after files are
# replaced. Refresh that module once if the new Whisper setting is missing.
_required_settings = (
    "SUMMARY_LEVELS", "SUMMARY_LEVEL_LABELS",
    "SUMMARY_LEVEL_STT_MODELS", "SUMMARY_LEVEL_CAPTIONS",
)
if any(not hasattr(_summary_levels, name) for name in _required_settings):
    importlib.invalidate_caches()
    _summary_levels = importlib.reload(_summary_levels)
    if any(not hasattr(_summary_levels, name) for name in _required_settings):
        raise RuntimeError(
            "Whisper 설정 파일이 구버전입니다. 최신 modules/llm/summary_levels.py를 "
            f"다음 경로에 덮어써주세요: {_summary_levels.__file__}"
        )

SUMMARY_LEVELS = _summary_levels.SUMMARY_LEVELS
SUMMARY_LEVEL_LABELS = _summary_levels.SUMMARY_LEVEL_LABELS
SUMMARY_LEVEL_STT_MODELS = _summary_levels.SUMMARY_LEVEL_STT_MODELS
SUMMARY_LEVEL_CAPTIONS = _summary_levels.SUMMARY_LEVEL_CAPTIONS


def render_analysis_options(disabled=False):
    # Discard a value retained by a session opened before the input was removed.
    st.session_state.pop("claude_api_key", None)
    st.session_state.pop("local_server_url", None)
    st.subheader("⚙️ 분석 설정")
    backend = st.radio("분석 방식", list(BACKEND_LABELS), format_func=BACKEND_LABELS.get,
                       key="analysis_backend", disabled=disabled)
    ready = bool(GPU_SERVER_URL.strip())
    # Preserve the selection when the local-only widget is hidden for Claude.
    st.session_state["local_model"] = st.session_state.get("local_model", DEFAULT_LOCAL_MODEL)
    if backend == "local":
        selected = st.selectbox("로컬 분석 모델", list(LOCAL_MODEL_LABELS),
            format_func=LOCAL_MODEL_LABELS.get, key="local_model", disabled=disabled)
        if selected == "legacy-qwen":
            st.caption("기존 조합 · 음성 요약 Qwen3 8B / 화면 분석 Qwen2.5-VL 7B · FP16")
        else:
            st.caption("선택한 하나의 모델로 음성 요약·화면 분석·최종 요약을 처리합니다. 4090용 NF4 4비트 설정입니다.")
        render_model_management(selected, disabled)

    else:
        st.caption(f"요약·화면 분석 모델: {DEFAULT_CLAUDE_MODEL}")
        st.caption("서버에 설정된 ANTHROPIC_API_KEY 환경변수를 자동으로 사용합니다. 분석 시작 전에 서버의 설정 여부를 확인합니다.")
        st.info("분석 서버가 인식한 음성 텍스트·OCR·추출 프레임을 Anthropic API로 전송합니다. API 사용 요금이 발생합니다.")
    st.divider()
    st.radio("Whisper 음성 인식", SUMMARY_LEVELS,
             index=SUMMARY_LEVELS.index(st.session_state.get("summary_level", "standard")),
             format_func=lambda level: f"{SUMMARY_LEVEL_LABELS[level]} · {SUMMARY_LEVEL_STT_MODELS[level]}",
             key="summary_level", horizontal=True, disabled=disabled)
    st.caption(SUMMARY_LEVEL_CAPTIONS[st.session_state["summary_level"]])
    st.caption("간단·기본·상세는 Whisper 크기만 바꿉니다. 세 옵션 모두 OCR·화면 분석·최종 통합을 수행하며 요약 생성 설정은 같습니다.")
    return ready


def render_model_management(selected, disabled):
    with st.expander("모델 설치 상태", expanded=False):
        st.caption("GPU 서버에 미리 내려받은 모델의 설치 상태를 확인합니다.")
        if st.button("설치 상태 확인 / 새로고침", disabled=disabled, use_container_width=True):
            try:
                response = requests.get(GPU_SERVER_URL.rstrip("/") + "/models", timeout=10)
                response.raise_for_status()
                st.session_state["local_model_catalogue"] = response.json()["models"]
            except (requests.RequestException, ValueError, KeyError):
                st.error("모델 목록을 가져오지 못했습니다. 서버에 수정본을 적용하고 재시작했는지 확인하세요.")
        catalogue = st.session_state.get("local_model_catalogue", [])
        if catalogue:
            statuses = {"queued": "다운로드 대기", "downloading": "다운로드 중", "failed": "다운로드 실패"}
            rows = []
            for model in catalogue:
                download = model.get("download") or {}
                state = statuses.get(download.get("status"), "다운로드 완료" if model.get("ready") else "미설치")
                if model.get("ready") and model.get("runtime_ready") is False:
                    state = "가중치 완료 · 실행 환경 필요"
                rows.append({"모델": model["label"], "정밀도": model["precision"].upper(), "상태": state})
                if model["id"] == selected and download.get("error"):
                    st.error(download["error"])
            st.dataframe(rows, hide_index=True, use_container_width=True)
        st.caption("전체 다운로드: GPU 서버에서 python scripts/download_models.py --all")
        if selected == "minicpm-v4.5":
            st.info("MiniCPM은 서버에서 python scripts/setup_minicpm.py로 전용 환경을 먼저 설치하세요.")
        if selected == "gemma4-12b":
            st.caption("접근 승인이 필요한 경우 Hugging Face에서 모델 사용 조건에 동의하고 서버 HF_TOKEN 환경변수를 설정하세요.")
