from __future__ import annotations

from pathlib import Path
from typing import Any
import json


def _to_float(value: Any, default: float = 0.0) -> float:
    """값을 float로 변환합니다.

    Args:
        value: 변환할 값입니다.
        default: 변환할 수 없을 때 반환할 기본값입니다.

    Returns:
        변환된 float 값입니다.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_text(text: Any) -> str:
    """STT 텍스트 값을 공백이 제거된 문자열로 정규화합니다.

    Args:
        text: 정규화할 텍스트 값입니다.

    Returns:
        앞뒤 공백이 제거된 문자열입니다.
    """
    return str(text or "").strip()


def _format_segment(segment_id: int, start: Any, end: Any, text: Any) -> dict[str, Any] | None:
    """Whisper segment를 프로젝트 공통 STT segment 구조로 변환합니다.

    Args:
        segment_id: 결과에 부여할 segment 식별자입니다.
        start: segment 시작 시간입니다. 단위는 초입니다.
        end: segment 종료 시간입니다. 단위는 초입니다.
        text: segment 텍스트입니다.

    Returns:
        정규화된 segment 딕셔너리입니다. 텍스트가 비어 있으면 ``None``을 반환합니다.
    """
    normalized_text = _normalize_text(text)
    if not normalized_text:
        return None

    start_sec = max(0.0, _to_float(start))
    end_sec = max(start_sec, _to_float(end, start_sec))
    return {
        "segment_id": segment_id,
        "start": round(start_sec, 2),
        "end": round(end_sec, 2),
        "text": normalized_text,
    }


def format_stt_result(raw_result: dict[str, Any]) -> dict[str, Any]:
    """Whisper 원본 결과를 프로젝트에서 쓰는 STT JSON 구조로 변환합니다.

    Args:
        raw_result: Whisper ``transcribe``가 반환한 원본 결과입니다.

    Returns:
        ``language``, ``segment_count``, ``segments``, ``full_text``를 포함한 STT 결과입니다.
    """
    segments: list[dict[str, Any]] = []

    for raw_segment in raw_result.get("segments", []):
        segment = _format_segment(
            len(segments),
            raw_segment.get("start", 0.0),
            raw_segment.get("end", 0.0),
            raw_segment.get("text", ""),
        )
        if segment is not None:
            segments.append(segment)

    full_text = " ".join(segment["text"] for segment in segments)
    return {
        "language": raw_result.get("language", "unknown"),
        "segment_count": len(segments),
        "segments": segments,
        "full_text": full_text,
    }


def save_stt_json(stt_data: dict[str, Any], output_path: str | Path) -> None:
    """구조화된 STT 결과를 JSON 파일로 저장합니다.

    Args:
        stt_data: 저장할 STT 결과 딕셔너리입니다.
        output_path: JSON 파일을 저장할 경로입니다.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(stt_data, f, ensure_ascii=False, indent=2)


def save_stt_text(stt_data: dict[str, Any], output_path: str | Path, include_timestamps: bool = False) -> None:
    """STT 결과를 TXT 파일로 저장합니다.

    Args:
        stt_data: 저장할 STT 결과 딕셔너리입니다.
        output_path: TXT 파일을 저장할 경로입니다.
        include_timestamps: 각 segment의 시작/종료 시간을 포함할지 여부입니다.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if include_timestamps:
        lines = [
            f"[{segment['start']:.2f} - {segment['end']:.2f}] {segment['text']}"
            for segment in stt_data.get("segments", [])
        ]
        text = "\n".join(lines)
    else:
        text = stt_data.get("full_text", "")

    with output_path.open("w", encoding="utf-8") as f:
        f.write(text)
