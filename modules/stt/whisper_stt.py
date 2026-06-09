from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any
import math


WHISPER_SAMPLE_RATE = 16000
DEFAULT_STT_MODEL_SIZE = "medium"
DEFAULT_STT_LANGUAGE = "ko"
DEFAULT_STT_DEVICE = None
DEFAULT_STT_CHUNKED = True
DEFAULT_STT_CHUNK_SECONDS = 30
DEFAULT_STT_OVERLAP_SECONDS = 2


def _load_whisper_module():
    """Whisper 패키지를 지연 import합니다.

    Returns:
        import된 ``whisper`` 모듈입니다.

    Raises:
        ImportError: openai-whisper 패키지가 설치되어 있지 않을 때 발생합니다.
    """
    try:
        import whisper  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "Whisper STT를 사용하려면 openai-whisper 패키지가 필요합니다. "
            "예: pip install openai-whisper"
        ) from exc
    return whisper


@lru_cache(maxsize=4)
def _load_model(model_size: str, device: str | None):
    """Whisper 모델을 로드하고 캐시에 저장합니다.

    Args:
        model_size: 로드할 Whisper 모델 크기입니다. 예: ``base``, ``small``. ``medium``, ``large``
        device: 모델을 실행할 장치입니다. 예: ``cpu``, ``cuda``.

    Returns:
        로드된 Whisper 모델 인스턴스입니다.
    """
    whisper = _load_whisper_module()
    return whisper.load_model(model_size, device=device)


def _validate_audio_path(audio_path: str | Path) -> Path:
    """STT 입력 오디오 경로를 검증합니다.

    Args:
        audio_path: 검증할 오디오 파일 경로입니다.

    Returns:
        검증된 ``Path`` 객체입니다.

    Raises:
        FileNotFoundError: 오디오 파일이 존재하지 않을 때 발생합니다.
        ValueError: 오디오 경로가 파일이 아닐 때 발생합니다.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {path}")
    if not path.is_file():
        raise ValueError(f"오디오 경로가 파일이 아닙니다: {path}")
    return path


def _clean_transcribe_options(options: dict[str, Any]) -> dict[str, Any]:
    """Whisper transcribe 옵션에서 ``None`` 값을 제거합니다.

    Args:
        options: Whisper에 전달할 옵션 딕셔너리입니다.

    Returns:
        값이 ``None``인 항목을 제외한 옵션 딕셔너리입니다.
    """
    return {key: value for key, value in options.items() if value is not None}


def run_whisper_stt(
    audio_path: str | Path,
    model_size: str = DEFAULT_STT_MODEL_SIZE,
    language: str = DEFAULT_STT_LANGUAGE,
    device: str | None = DEFAULT_STT_DEVICE,
    **transcribe_options: Any,
) -> dict[str, Any]:
    """하나의 오디오 파일을 Whisper로 음성 인식합니다.

    Args:
        audio_path: STT를 수행할 오디오 파일 경로입니다.
        model_size: 사용할 Whisper 모델 크기입니다.
        language: 음성 인식 언어 코드입니다. 예: ``ko``.
        device: 모델 실행 장치입니다. ``None``이면 Whisper 기본값을 사용합니다.
        **transcribe_options: Whisper ``transcribe``에 추가로 전달할 옵션입니다.

    Returns:
        Whisper가 반환한 원본 STT 결과 딕셔너리입니다.
    """
    path = _validate_audio_path(audio_path)
    model = _load_model(model_size, device)

    options = _clean_transcribe_options(
        {
            "language": language,
            "verbose": False,
            **transcribe_options,
        }
    )
    return model.transcribe(str(path), **options)


def run_chunked_whisper_stt(
    audio_path: str | Path,
    model_size: str = DEFAULT_STT_MODEL_SIZE,
    language: str = DEFAULT_STT_LANGUAGE,
    chunk_seconds: int = DEFAULT_STT_CHUNK_SECONDS,
    overlap_seconds: int = DEFAULT_STT_OVERLAP_SECONDS,
    device: str | None = DEFAULT_STT_DEVICE,
    **transcribe_options: Any,
) -> dict[str, Any]:
    """긴 오디오를 일정 길이로 나누어 Whisper STT를 수행합니다.

    각 chunk 내부 segment 시간은 chunk 기준으로 반환되므로, 후처리는
    ``format_chunked_stt_result``에서 전체 오디오 기준 시간으로 변환합니다.

    Args:
        audio_path: STT를 수행할 오디오 파일 경로입니다.
        model_size: 사용할 Whisper 모델 크기입니다.
        language: 음성 인식 언어 코드입니다. 예: ``ko``.
        chunk_seconds: 한 번에 처리할 chunk 길이입니다. 단위는 초입니다.
        overlap_seconds: 인접 chunk 사이에 겹칠 길이입니다. 단위는 초입니다.
        device: 모델 실행 장치입니다. ``None``이면 Whisper 기본값을 사용합니다.
        **transcribe_options: Whisper ``transcribe``에 추가로 전달할 옵션입니다.

    Returns:
        chunk별 Whisper 원본 결과와 chunk 설정을 담은 딕셔너리입니다.

    Raises:
        ValueError: chunk 길이 또는 overlap 설정이 올바르지 않을 때 발생합니다.
    """
    path = _validate_audio_path(audio_path)

    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds는 0보다 커야 합니다.")
    if overlap_seconds < 0:
        raise ValueError("overlap_seconds는 0 이상이어야 합니다.")
    if chunk_seconds <= overlap_seconds:
        raise ValueError("chunk_seconds는 overlap_seconds보다 커야 합니다.")

    whisper = _load_whisper_module()
    model = _load_model(model_size, device)
    audio = whisper.load_audio(str(path))

    total_samples = len(audio)
    total_duration = total_samples / WHISPER_SAMPLE_RATE
    chunk_size = int(chunk_seconds * WHISPER_SAMPLE_RATE)
    overlap_size = int(overlap_seconds * WHISPER_SAMPLE_RATE)
    step_size = chunk_size - overlap_size
    total_chunks = max(1, math.ceil(total_samples / step_size))

    options = _clean_transcribe_options(
        {
            "language": language,
            "verbose": False,
            **transcribe_options,
        }
    )

    chunks: list[dict[str, Any]] = []
    for chunk_index in range(total_chunks):
        start_sample = chunk_index * step_size
        end_sample = min(start_sample + chunk_size, total_samples)
        if start_sample >= total_samples:
            break

        chunk_start = start_sample / WHISPER_SAMPLE_RATE
        chunk_end = end_sample / WHISPER_SAMPLE_RATE
        result = model.transcribe(audio[start_sample:end_sample], **options)

        chunks.append(
            {
                "chunk_index": chunk_index,
                "chunk_start": round(chunk_start, 2),
                "chunk_end": round(chunk_end, 2),
                "result": result,
            }
        )

    return {
        "audio_path": str(path),
        "language": language,
        "model_size": model_size,
        "duration_sec": round(total_duration, 2),
        "chunk_config": {
            "chunk_seconds": chunk_seconds,
            "overlap_seconds": overlap_seconds,
        },
        "chunks": chunks,
    }


def clear_model_cache() -> None:
    """테스트나 장시간 프로세스에서 로드된 Whisper 모델 캐시를 비웁니다."""
    _load_model.cache_clear()
