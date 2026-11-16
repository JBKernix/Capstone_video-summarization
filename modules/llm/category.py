"""강의 노트 카테고리 분류 규칙입니다.

분류는 별도 LLM 요청 없이 최종 요약(강의 노트 JSON) 응답의 ``classification`` 항목으로 함께 받습니다.
모델 출력 검증과 신뢰도 기준은 여기 한 곳에서만 처리합니다(Claude·로컬 모델 공통).
gpu-server 프롬프트(final_service.py)의 카테고리 설명도 이 기준과 같게 유지하세요.
"""
from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

CATEGORY_LABELS = {
    "SCIENCE_ENGINEERING": "과학·공학",
    "MEDICAL_HEALTH": "의학·건강",
    "HISTORY_HUMANITIES": "역사·인문",
    "CURRENT_AFFAIRS_SOCIETY": "시사·사회",
    "CULTURE_ENTERTAINMENT": "문화·엔터테인먼트",
    "OTHER": "기타·미분류",
}
CATEGORIES = tuple(CATEGORY_LABELS)
DEFAULT_CATEGORY = "OTHER"

STATUS_CLASSIFIED = "CLASSIFIED"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"
STATUS_MANUAL = "MANUALLY_CLASSIFIED"
CLASSIFICATION_STATUSES = (STATUS_CLASSIFIED, STATUS_NEEDS_REVIEW, STATUS_MANUAL)

# 이 값보다 신뢰도가 낮으면 OTHER/NEEDS_REVIEW(미분류)로 저장합니다. 환경변수로 바꿀 수 있습니다.
CONFIDENCE_THRESHOLD = float(os.environ.get("CATEGORY_CONFIDENCE_THRESHOLD") or 0.7)
MAX_TAGS = 5
MAX_TAG_LENGTH = 20
MAX_REASON_LENGTH = 200
CLASSIFICATION_FILENAME = "classification.json"

# 프롬프트에 넣는 분류 기준입니다. 단어가 아니라 콘텐츠의 성격으로 고르게 합니다.
CATEGORY_GUIDE = """[카테고리 분류]
classification에는 영상 전체 내용을 보고 아래 카테고리 중 하나를 고르세요.
- SCIENCE_ENGINEERING: 물리, 화학, 생명과학, 수학, 공학, 컴퓨터, 프로그래밍, 에너지, 우주과학
- MEDICAL_HEALTH: 실제 질병, 증상, 진단, 치료, 의학 지식, 건강관리
- HISTORY_HUMANITIES: 역사, 철학, 문학, 언어, 종교, 인문학
- CURRENT_AFFAIRS_SOCIETY: 뉴스, 정치, 경제, 국제정세, 외교, 전쟁, 사회 문제
- CULTURE_ENTERTAINMENT: 영화, 드라마, 예능, 음악, 게임, 스포츠, 작품 줄거리·명장면 요약
- OTHER: 위 다섯 분야에 속하지 않는 콘텐츠
제목의 단어 하나로 고르지 말고 영상 정보와 요약 내용 전체로 판단하세요.
의료 드라마(예: 닥터X, 낭만닥터 김사부)의 줄거리·명장면처럼 '수술', '의사' 같은 단어가 나와도
실제 의학 지식을 설명하는 내용이 아니면 MEDICAL_HEALTH가 아니라 CULTURE_ENTERTAINMENT입니다.
confidence는 0~1 사이 숫자, reason은 근거 한 문장, tags는 주제 키워드 1~5개입니다.
판단할 정보가 부족하면 OTHER와 낮은 confidence를 쓰세요."""

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["category", "confidence", "reason", "tags"],
}


def default_classification(reason: str = "") -> dict[str, Any]:
    """분류 정보가 없거나 읽을 수 없을 때의 값(미분류)입니다."""
    return {"category": DEFAULT_CATEGORY, "confidence": None, "status": STATUS_NEEDS_REVIEW,
            "reason": reason, "tags": [], "suggested_category": None}


def _confidence(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    # 일부 모델은 92처럼 백분율로 답합니다.
    if 1 < number <= 100:
        number /= 100
    return round(number, 3) if 0 <= number <= 1 else None


def _tags(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    for item in value:
        tag = item.strip().lstrip("#").strip() if isinstance(item, str) else ""
        if tag and len(tag) <= MAX_TAG_LENGTH and tag not in tags:
            tags.append(tag)
    return tags[:MAX_TAGS]


def normalize_classification(data: Any, threshold: float = CONFIDENCE_THRESHOLD) -> dict[str, Any]:
    """모델이 준 분류 결과를 검증합니다. 어떤 입력이 와도 예외 없이 저장할 수 있는 값을 돌려줍니다.

    - 허용되지 않은 카테고리·신뢰도이거나 형식이 틀리면 OTHER / NEEDS_REVIEW
    - 신뢰도가 기준 미만이면 OTHER / NEEDS_REVIEW (모델이 고른 값은 ``suggested_category``에 남김)
    - 그 밖에는 모델이 고른 카테고리 / CLASSIFIED (명확히 OTHER라고 답한 경우 포함)
    """
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            return default_classification("분류 결과를 읽을 수 없음")
    if not isinstance(data, Mapping):
        return default_classification("분류 결과 없음")

    raw_category = data.get("category")
    category = raw_category.strip().upper() if isinstance(raw_category, str) else ""
    confidence = _confidence(data.get("confidence"))
    reason = data.get("reason").strip()[:MAX_REASON_LENGTH] if isinstance(data.get("reason"), str) else ""
    tags = _tags(data.get("tags"))
    if category not in CATEGORIES or confidence is None:
        return {**default_classification(reason or "분류 결과 형식 오류"), "tags": tags}
    if confidence < threshold:
        return {"category": DEFAULT_CATEGORY, "confidence": confidence, "status": STATUS_NEEDS_REVIEW,
                "reason": reason, "tags": tags, "suggested_category": category}
    return {"category": category, "confidence": confidence, "status": STATUS_CLASSIFIED,
            "reason": reason, "tags": tags, "suggested_category": None}


def stored_classification(data: Any) -> dict[str, Any]:
    """저장된 분류 정보를 화면·API에서 쓰는 형태로 읽습니다. 없거나 깨졌으면 미분류입니다."""
    if not isinstance(data, Mapping):
        return default_classification()
    category = data.get("category")
    status = data.get("status")
    if category not in CATEGORIES or status not in CLASSIFICATION_STATUSES:
        return default_classification()
    return {
        "category": category,
        "confidence": _confidence(data.get("confidence")),
        "status": status,
        "reason": data.get("reason") if isinstance(data.get("reason"), str) else "",
        "tags": _tags(data.get("tags")),
        "suggested_category": data.get("suggested_category") if data.get("suggested_category") in CATEGORIES else None,
    }


def read_classification(folder: Path) -> dict[str, Any]:
    try:
        data = json.loads((folder / CLASSIFICATION_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    return stored_classification(data)


def _write(folder: Path, classification: Mapping[str, Any]) -> None:
    path = folder / CLASSIFICATION_FILENAME
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(dict(classification), ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def store_auto_classification(folder: Path, classification: Any) -> dict[str, Any]:
    """자동 분류 결과를 저장합니다. 사용자가 직접 고친 분류(MANUALLY_CLASSIFIED)는 덮어쓰지 않습니다."""
    current = read_classification(folder)
    if current["status"] == STATUS_MANUAL:
        return current
    value = stored_classification(classification)
    _write(folder, value)
    return value


def store_manual_classification(folder: Path, category: str) -> dict[str, Any]:
    """사용자가 고른 카테고리를 저장합니다. 이유·태그 등 자동 분류 정보는 참고용으로 남깁니다."""
    if category not in CATEGORIES:
        raise ValueError(f"지원하지 않는 카테고리입니다: {category}")
    value = {**read_classification(folder), "category": category, "status": STATUS_MANUAL,
             "suggested_category": None}
    _write(folder, value)
    return value


VIDEO_DESCRIPTION_CHARS = 500


def format_video_info(context: Mapping[str, Any] | None) -> str:
    """영상 제목·채널·설명을 최종 요약 프롬프트의 [영상 정보] 자료로 만듭니다. 없으면 빈 문자열입니다."""
    if not isinstance(context, Mapping):
        return ""
    lines = []
    for key, label in (("title", "제목"), ("channel", "채널"), ("description", "설명")):
        value = context.get(key)
        text = " ".join(value.split()) if isinstance(value, str) else ""
        if key == "description" and len(text) > VIDEO_DESCRIPTION_CHARS:
            text = text[:VIDEO_DESCRIPTION_CHARS].rstrip() + "…"
        if text:
            lines.append(f"- {label}: {text}")
    return "\n".join(lines)


VIDEO_CONTEXT_FILENAME = "video_context.json"
VIDEO_CONTEXT_KEYS = ("title", "channel", "description")


def write_video_context(run_dir: Path, context: Mapping[str, Any]) -> None:
    values = {key: context[key] for key in VIDEO_CONTEXT_KEYS if isinstance(context.get(key), str) and context[key]}
    (Path(run_dir) / VIDEO_CONTEXT_FILENAME).write_text(json.dumps(values, ensure_ascii=False), encoding="utf-8")


def load_video_context(run_dir: Path, fallback_title: str | None = None) -> dict[str, str]:
    """실행 폴더의 영상 정보를 읽습니다. 없으면 이력에 쓰는 영상 이름만 제목으로 씁니다."""
    try:
        data = json.loads((Path(run_dir) / VIDEO_CONTEXT_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    context = {key: data[key] for key in VIDEO_CONTEXT_KEYS if isinstance(data, dict) and isinstance(data.get(key), str)}
    if not context.get("title") and fallback_title:
        context["title"] = fallback_title
    return context
