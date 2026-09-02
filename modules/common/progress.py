# modules/common/progress.py

from __future__ import annotations

import json
from typing import Optional

PROGRESS_MARKER = "##PROGRESS##"

STEP_AUDIO_EXTRACTION = 1
STEP_STT = 2
STEP_STT_SUMMARY = 3
STEP_FRAME_EXTRACTION = 4
STEP_OCR = 5
STEP_VLM_SUMMARY = 6
STEP_FINAL_SUMMARY = 7

TOTAL_STEPS = 7

# 파이프라인 단계 번호별 (제목, 설명)입니다. run_pipeline.py와 앱 UI가 동일한 번호 체계를 공유합니다.
STEP_LABELS: dict[int, tuple[str, str]] = {
    STEP_AUDIO_EXTRACTION: ("오디오 추출", "영상에서 음성 분리"),
    STEP_STT: ("STT 분석", "음성을 텍스트로 변환"),
    STEP_STT_SUMMARY: ("STT 요약", "핵심 내용 및 중요 구간 요약"),
    STEP_FRAME_EXTRACTION: ("프레임 추출", "중요 구간 프레임 선택"),
    STEP_OCR: ("OCR 분석", "화면 텍스트 및 시각 정보 이해"),
    STEP_VLM_SUMMARY: ("VLM 요약 생성", "프레임별 시각 요약 생성"),
    STEP_FINAL_SUMMARY: ("최종 요약 생성", "음성/시각 요약 통합"),
}


def report_progress(step: int, message: str, percent: Optional[float] = None) -> None:
    """파이프라인 단계 진행 상황을 표준 출력에 구조화된 형태로 기록합니다.

    앱이 파이프라인 로그를 폴링하며 이 마커로 시작하는 줄을 파싱해 단계별 진행률을 표시합니다.

    Args:
        step: 진행 상황을 보고할 단계 번호입니다 (``STEP_*`` 상수 참고).
        message: 현재 진행 중인 작업을 설명하는 문구입니다.
        percent: 0~100 사이의 진행률입니다. 전체 진행률을 알 수 없는 작업이면 ``None``입니다.
    """
    payload: dict[str, object] = {"step": step, "message": message}
    if percent is not None:
        payload["percent"] = round(max(0.0, min(100.0, percent)), 1)

    print(f"{PROGRESS_MARKER} {json.dumps(payload, ensure_ascii=False)}", flush=True)
