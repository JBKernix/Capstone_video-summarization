from __future__ import annotations

# GPU 서버(gpu-server 브랜치)의 configs/inference_config.py::SUMMARY_LEVEL_PRESETS
# 키와 반드시 동일해야 합니다. 실제 토큰 수/속도 관련 값은 서버가 결정합니다.
SUMMARY_LEVELS = ("simple", "standard", "detailed")
DEFAULT_SUMMARY_LEVEL = "standard"

SUMMARY_LEVEL_LABELS = {
    "simple": "간단요약",
    "standard": "기본요약",
    "detailed": "상세요약",
}

# 세 레벨 모두 음성(STT)과 영상(VLM)을 함께 분석합니다. 차이는 요약 길이/속도입니다.
SUMMARY_LEVEL_CAPTIONS = {
    "simple": "간단요약은 음성과 영상을 핵심만 간략히 요약하여 속도가 빠릅니다.",
    "standard": "기본요약은 음성과 영상을 균형 있게 요약합니다.",
    "detailed": "상세요약은 음성과 영상을 자세히 요약하지만 속도가 느립니다.",
}
