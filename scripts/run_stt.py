from __future__ import annotations

from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.stt import (  # noqa: E402
    format_chunked_stt_result,
    format_stt_result,
    run_chunked_whisper_stt,
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
    parser.add_argument(
        "--audio",
        default=str(PROJECT_ROOT / "runs" / "audio" / "audio.wav"),
        help="STT를 수행할 오디오 파일 경로입니다.",
    )
    parser.add_argument(
        "--output-json",
        default=str(PROJECT_ROOT / "runs" / "stt" / "stt_result.json"),
        help="STT JSON 결과 저장 경로입니다.",
    )
    parser.add_argument(
        "--output-text",
        default=str(PROJECT_ROOT / "runs" / "stt" / "stt_result.txt"),
        help="STT 텍스트 결과 저장 경로입니다.",
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "configs" / "stt_config.yaml"),
        help="STT 설정 YAML 경로입니다.",
    )
    parser.add_argument("--model-size", help="Whisper 모델 크기입니다. 예: tiny, base, small, medium")
    parser.add_argument("--language", help="언어 코드입니다. 한국어 기본값은 ko입니다.")
    parser.add_argument("--device", help="실행 장치입니다. 예: cpu, cuda")
    parser.add_argument("--chunked", action="store_true", help="오디오를 chunk로 나누어 STT를 수행합니다.")
    parser.add_argument("--chunk-seconds", type=int, help="chunk 길이(초)입니다.")
    parser.add_argument("--overlap-seconds", type=int, help="chunk 간 overlap 길이(초)입니다.")
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="텍스트 파일에 segment 시간 정보를 함께 저장합니다.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(Path(args.config))

    model_size = args.model_size or config.get("model_size", "small")
    language = args.language or config.get("language", "ko")
    device = args.device if args.device is not None else config.get("device")
    chunked = args.chunked or bool(config.get("chunked", True))
    chunk_seconds = args.chunk_seconds or int(config.get("chunk_seconds", 30))
    overlap_seconds = args.overlap_seconds or int(config.get("overlap_seconds", 2))

    audio_path = Path(args.audio)
    if chunked:
        raw_result = run_chunked_whisper_stt(
            audio_path=audio_path,
            model_size=model_size,
            language=language,
            chunk_seconds=chunk_seconds,
            overlap_seconds=overlap_seconds,
            device=device,
        )
        stt_result = format_chunked_stt_result(raw_result)
    else:
        raw_result = run_whisper_stt(
            audio_path=audio_path,
            model_size=model_size,
            language=language,
            device=device,
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
