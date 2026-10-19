from __future__ import annotations

# User presets control Whisper only. All summarizers use the same standard policy.
SUMMARY_LEVELS = ("simple", "standard", "detailed")
DEFAULT_SUMMARY_LEVEL = "standard"
SUMMARY_LEVEL_LABELS = {"simple": "간단", "standard": "기본", "detailed": "상세"}
SUMMARY_LEVEL_STT_MODELS = {"simple": "small", "standard": "medium", "detailed": "large"}
SUMMARY_LEVEL_CAPTIONS = {
    "simple": "Whisper small · 빠른 음성 인식. OCR·화면 분석도 함께 실행합니다.",
    "standard": "Whisper medium · 음성 인식 속도와 정확도의 균형을 고려한 선택입니다.",
    "detailed": "Whisper large · 가장 큰 음성 인식 모델을 사용합니다. 처리 시간이 늘어날 수 있습니다.",
}
