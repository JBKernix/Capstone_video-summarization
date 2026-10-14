import os

# Streamlit과 FastAPI가 같은 서버 PC에서 실행되므로 기본값은 localhost입니다.
# 다른 주소가 필요하면 GPU_SERVER_URL 환경변수로 덮어씁니다.
GPU_SERVER_URL = (os.environ.get("GPU_SERVER_URL") or "http://127.0.0.1:8000").strip().rstrip("/")
