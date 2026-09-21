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

# simple은 프레임 추출/OCR/VLM 단계를 건너뛰고 음성(STT)만으로 요약합니다.
# standard/detailed는 음성(STT)과 영상(VLM)을 함께 분석하며 차이는 요약 길이/속도입니다.
SUMMARY_LEVEL_CAPTIONS = {
    "simple": "간단요약은 음성만으로 핵심을 간략히 요약하여 속도가 빠릅니다. (영상 분석 생략)",
    "standard": "기본요약은 음성과 영상을 균형 있게 요약합니다.",
    "detailed": "상세요약은 음성과 영상을 자세히 요약하지만 속도가 느립니다.",
}
