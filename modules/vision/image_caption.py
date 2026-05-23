from pathlib import Path


def generate_text_based_caption(image_path: str, ocr_text: str) -> str:
    """OCR 텍스트 양에 따라 간단한 장면 설명 문장을 생성합니다.

    Args:
        image_path: 설명 대상 프레임 이미지 경로입니다.
        ocr_text: 이미지에서 추출된 OCR 텍스트입니다.

    Returns:
        OCR 텍스트 존재 여부와 길이를 기준으로 만든 설명 문장입니다.
    """
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"이미지 파일이 존재하지 않습니다: {image_path}")

    text = ocr_text.strip()

    # 현재 캡션은 이미지 자체가 아니라 OCR 텍스트 양을 기준으로 생성합니다.
    if not text:
        return "텍스트 정보가 거의 없는 장면입니다."

    if len(text) >= 30:
        return "비교적 많은 텍스트 정보가 포함된 장면입니다."

    return "텍스트 정보가 포함된 장면입니다."


def classify_scene_type(ocr_text: str) -> str:
    """OCR 텍스트 키워드를 기반으로 장면 유형을 분류합니다.

    Args:
        ocr_text: 이미지에서 추출된 OCR 텍스트입니다.

    Returns:
        ``generic_scene``, ``chart_or_table``, ``presentation_slide``,
        ``text_screen`` 중 하나의 장면 유형입니다.
    """
    text = ocr_text.strip().lower()

    if not text:
        return "generic_scene"

    # 발표 자료에서 자주 등장하는 단어를 기준으로 슬라이드형 화면을 추정합니다.
    slide_keywords = [
        "목차",
        "개요",
        "정리",
        "요약",
        "결론",
        "발표",
        "프로젝트",
        "시스템",
        "구성",
        "architecture",
        "overview",
        "summary",
        "conclusion",
        "system",
        "model",
    ]

    # 표/그래프/성능 지표 관련 단어를 기준으로 차트 또는 표 화면을 추정합니다.
    chart_keywords = [
        "표",
        "그래프",
        "차트",
        "분석",
        "결과",
        "비교",
        "평균",
        "정확도",
        "성능",
        "graph",
        "chart",
        "table",
        "result",
        "accuracy",
        "performance",
    ]

    if any(keyword in text for keyword in chart_keywords):
        return "chart_or_table"

    if any(keyword in text for keyword in slide_keywords):
        return "presentation_slide"

    return "text_screen"