from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_STT_MODEL_SIZE = "medium"
DEFAULT_STT_LANGUAGE = "ko"
DEFAULT_STT_DEVICE = None
DEFAULT_STT_TEMPERATURE = 0.0
DEFAULT_STT_BEAM_SIZE = None


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


def clear_model_cache() -> None:
    """테스트나 장시간 프로세스에서 로드된 Whisper 모델 캐시를 비웁니다."""
    _load_model.cache_clear()
