import json
from pathlib import Path
from typing import Any, Dict, List

from modules.vision.ocr_extractor import OCRExtractor
from modules.vision.image_caption import generate_text_based_caption, classify_scene_type


def calculate_importance_score(ocr_text: str, scene_type: str) -> float:
    """OCR 텍스트와 장면 유형을 기반으로 프레임 중요도 점수를 계산합니다.

    Args:
        ocr_text: 프레임에서 추출한 OCR 텍스트입니다.
        scene_type: ``classify_scene_type``이 반환한 장면 유형입니다.

    Returns:
        0.0부터 1.0 사이의 중요도 점수입니다.
    """
    score = 0.3

    if ocr_text.strip():
        score += 0.3

    if len(ocr_text.strip()) > 20:
        score += 0.2

    if scene_type in ["presentation_slide", "chart_or_table"]:
        score += 0.2

    return min(score, 1.0)


def analyze_single_frame(frame_info: Dict[str, Any], ocr_extractor: OCRExtractor) -> Dict[str, Any]:
    """단일 프레임 메타데이터를 분석해 시각 정보 딕셔너리를 생성합니다.

    Args:
        frame_info: ``frame_id``, ``timestamp``, ``image_path``를 포함한 프레임 메타데이터입니다.
        ocr_extractor: OCR 추출에 사용할 ``OCRExtractor`` 인스턴스입니다.

    Returns:
        OCR 텍스트, 감지 언어, 장면 유형, 텍스트 기반 캡션, 중요도 점수를 포함한 딕셔너리입니다.
    """
    image_path = frame_info.get("image_path")

    ocr_result = ocr_extractor.extract_text_with_language(image_path)

    ocr_text = ocr_result["ocr_text"]
    detected_language = ocr_result["detected_language"]

    scene_type = classify_scene_type(ocr_text)
    image_caption = generate_text_based_caption(image_path, ocr_text)
    importance_score = calculate_importance_score(ocr_text, scene_type)

    return {
        "frame_id": frame_info.get("frame_id"),
        "timestamp": frame_info.get("timestamp"),
        "image_path": image_path,
        "ocr_text": ocr_text,
        "detected_language": detected_language,
        "scene_type": scene_type,
        "image_caption": image_caption,
        "importance_score": importance_score,
    }


def _resolve_image_path(image_path: str, metadata_path: Path) -> str:
    """프레임 메타데이터의 이미지 경로를 실제 파일 경로로 변환합니다.

    Args:
        image_path: 메타데이터에 저장된 이미지 경로입니다. 절대경로 또는 프로젝트 기준 상대경로일 수 있습니다.
        metadata_path: 이미지 경로를 해석할 때 기준으로 사용할 메타데이터 파일 경로입니다.

    Returns:
        실제 파일을 찾은 이미지 경로 문자열입니다. 후보 경로에서 파일을 찾지 못하면 첫 번째 후보 경로를 반환합니다.
    """
    path = Path(image_path)
    if path.is_absolute():
        return str(path)

    metadata_path = metadata_path.resolve()
    project_root = metadata_path.parent
    for parent in metadata_path.parents:
        if (parent / "modules").is_dir() and (parent / "scripts").is_dir():
            project_root = parent
            break

    candidates = [
        Path.cwd() / path,
        project_root / path,
        metadata_path.parent / path,
        metadata_path.parent.parent / path,
    ]

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return str(candidates[0])


def analyze_frames_metadata(metadata_path: str, output_path: str, lang: str) -> List[Dict[str, Any]]:
    """프레임 메타데이터 파일을 분석하고 시각 정보 결과 JSON을 저장합니다.

    Args:
        metadata_path: 프레임 메타데이터 JSON 파일 경로입니다.
        output_path: 분석 결과를 저장할 JSON 파일 경로입니다.
        lang: OCR 엔진에 전달할 언어 설정입니다. 예: ``korean``.

    Returns:
        프레임별 시각 정보 딕셔너리 리스트입니다.

    Raises:
        FileNotFoundError: 메타데이터 파일이 존재하지 않을 때 발생합니다.
        RuntimeError: 모든 프레임 분석에 실패했을 때 발생합니다.
    """
    metadata_path = Path(metadata_path)
    output_path = Path(output_path)

    if not metadata_path.exists():
        raise FileNotFoundError(f"프레임 메타데이터 파일이 존재하지 않습니다: {metadata_path}")

    # Windows에서 BOM이 붙은 UTF-8 JSON도 읽을 수 있도록 utf-8-sig를 사용합니다.
    with open(metadata_path, "r", encoding="utf-8-sig") as f:
        frames_metadata = json.load(f)

    # OCR 모델은 프레임마다 새로 만들지 않고 하나의 인스턴스를 재사용합니다.
    ocr_extractor = OCRExtractor(lang=lang)
    ocr_extractor.load_model()

    results = []
    failed_count = 0

    for frame_info in frames_metadata:
        frame_info = dict(frame_info)
        frame_info["image_path"] = _resolve_image_path(frame_info.get("image_path", ""), metadata_path)
        frame_id = frame_info.get("frame_id")
        try:
            result = analyze_single_frame(frame_info, ocr_extractor)
            results.append(result)

            if not result["ocr_text"].strip():
                print(f"프레임 분석 완료 (frame_id: {frame_id}) - OCR 텍스트 없음")
            else:
                print(f"프레임 분석 완료 (frame_id: {frame_id})")

        except Exception as e:
            failed_count += 1
            print(f"프레임 분석 중 오류 발생 (frame_id: {frame_id}) error={e}")

    # 일부 실패는 허용하지만, 모든 프레임이 실패하면 결과 JSON을 만들지 않습니다.
    if not results:
        raise RuntimeError(
            f"모든 프레임 분석에 실패했습니다. 실패 프레임 수: {failed_count}"
        )

    if failed_count > 0:
        print(f"일부 프레임 분석 실패: {failed_count}개")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"프레임 분석 완료. 성공: {len(results)}, 실패: {failed_count}")
    return results
