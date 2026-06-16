from __future__ import annotations

from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.common import (  # noqa: E402
    DEFAULT_AUDIO_RELATIVE_PATH,
    DEFAULT_RUN_DIR_RELATIVE_PATH,
    DEFAULT_STT_CONFIG_RELATIVE_PATH,
    DEFAULT_STT_JSON_RELATIVE_PATH,
    DEFAULT_STT_TEXT_RELATIVE_PATH,
    project_path,
    run_path,
)
from modules.stt import (  # noqa: E402
    DEFAULT_STT_DEVICE,
    DEFAULT_STT_LANGUAGE,
    DEFAULT_STT_MODEL_SIZE,
    DEFAULT_STT_TEMPERATURE,
    DEFAULT_STT_BEAM_SIZE,
    format_stt_result,
    run_whisper_stt,
    save_stt_json,
    save_stt_text,
)


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    try:
        import yaml
    except ImportError as exc:
        raise ImportError(
            "YAML 설정 파일을 사용하려면 PyYAML 패키지가 필요합니다. "
            "예: pip install PyYAML"
        ) from exc

    with config_path.open("r", encoding="utf-8-sig") as f:
        return yaml.safe_load(f) or {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="오디오 파일에서 STT 결과를 생성합니다.")
    run_dir = project_path(PROJECT_ROOT, DEFAULT_RUN_DIR_RELATIVE_PATH)
    parser.add_argument(
        "--audio",
        default=str(run_path(run_dir, DEFAULT_AUDIO_RELATIVE_PATH)),
        help="STT를 수행할 오디오 파일 경로입니다.",
    )
    parser.add_argument(
        "--output-json",
        default=str(run_path(run_dir, DEFAULT_STT_JSON_RELATIVE_PATH)),
        help="STT JSON 결과 저장 경로입니다.",
    )
    parser.add_argument(
        "--output-text",
        default=str(run_path(run_dir, DEFAULT_STT_TEXT_RELATIVE_PATH)),
        help="STT 텍스트 결과 저장 경로입니다.",
    )
    parser.add_argument(
        "--config",
        default=str(project_path(PROJECT_ROOT, DEFAULT_STT_CONFIG_RELATIVE_PATH)),
        help="STT 설정 YAML 경로입니다.",
    )
    parser.add_argument("--model-size", help="Whisper 모델 크기입니다. 예: tiny, base, small, medium")
    parser.add_argument("--language", help="언어 코드입니다. 한국어 기본값은 ko입니다.")
    parser.add_argument("--device", help="실행 장치입니다. 예: cpu, cuda")
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="텍스트 파일에 segment 시간 정보를 함께 저장합니다.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(Path(args.config))

    model_size = args.model_size or config.get("model_size", DEFAULT_STT_MODEL_SIZE)
    language = args.language or config.get("language", DEFAULT_STT_LANGUAGE)
    device = args.device if args.device is not None else config.get("device", DEFAULT_STT_DEVICE)
    temperature = float(config.get("temperature", DEFAULT_STT_TEMPERATURE))
    configured_beam_size = config.get("beam_size", DEFAULT_STT_BEAM_SIZE)
    beam_size = int(configured_beam_size) if configured_beam_size is not None else None

    audio_path = Path(args.audio)
    raw_result = run_whisper_stt(
        audio_path=audio_path,
        model_size=model_size,
        language=language,
        device=device,
        temperature=temperature,
        beam_size=beam_size,
    )
    stt_result = format_stt_result(raw_result)

    output_json = Path(args.output_json)
    output_text = Path(args.output_text)
    save_stt_json(stt_result, output_json)
    save_stt_text(stt_result, output_text, include_timestamps=args.timestamps)

    print(f"STT 완료: {output_json}")
    print(f"텍스트 저장: {output_text}")
    print(f"segment 수: {stt_result['segment_count']}")


if __name__ == "__main__":
    main()
