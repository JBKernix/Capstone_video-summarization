import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from modules.common import (  # noqa: E402
    DEFAULT_AUDIO_RELATIVE_PATH,
    DEFAULT_FRAME_METADATA_RELATIVE_PATH,
    DEFAULT_INPUT_VIDEO_RELATIVE_PATH,
    DEFAULT_RUN_DIR_RELATIVE_PATH,
    DEFAULT_STT_CONFIG_RELATIVE_PATH,
    DEFAULT_STT_JSON_RELATIVE_PATH,
    DEFAULT_STT_TEXT_RELATIVE_PATH,
    DEFAULT_VISION_RESULT_RELATIVE_PATH,
    project_path,
    resolve_path_pattern,
    run_path,
)
from modules.preprocess import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_SAMPLING_METHOD,
    DEFAULT_SCENE_THRESHOLD,
    SAMPLING_METHOD_CHOICES,
    ensure_mp4_video,
    extract_audio,
    get_video_info,
    sample_frames,
)
from modules.stt import (  # noqa: E402
    DEFAULT_STT_CHUNK_SECONDS,
    DEFAULT_STT_CHUNKED,
    DEFAULT_STT_DEVICE,
    DEFAULT_STT_LANGUAGE,
    DEFAULT_STT_MODEL_SIZE,
    DEFAULT_STT_OVERLAP_SECONDS,
)
from modules.vision import DEFAULT_OCR_LANGUAGE  # noqa: E402
from scripts.run_llm_summary import (  # noqa: E402
    DEFAULT_LLM_SUMMARY_JSON_RELATIVE_PATH,
    DEFAULT_LLM_SUMMARY_RELATIVE_PATH,
    run_llm_summary_step,
)


def _execute_stt(
    audio_path: str | Path,
    output_json: str | Path,
    output_text: str | Path,
    stt_options: dict,
) -> int:
    """Whisper STT를 실행하고 결과 파일을 저장합니다.

    Args:
        audio_path: STT를 수행할 오디오 파일 경로입니다.
        output_json: STT JSON 결과를 저장할 경로입니다.
        output_text: STT 텍스트 결과를 저장할 경로입니다.
        stt_options: STT 모델, 언어, chunk 설정을 담은 딕셔너리입니다.

    Returns:
        저장된 STT 결과의 segment 개수입니다.
    """
    from modules.stt import (
        format_chunked_stt_result,
        format_stt_result,
        run_chunked_whisper_stt,
        run_whisper_stt,
        save_stt_json,
        save_stt_text,
    )

    if stt_options["chunked"]:
        raw_result = run_chunked_whisper_stt(
            audio_path=audio_path,
            model_size=stt_options["model_size"],
            language=stt_options["language"],
            chunk_seconds=stt_options["chunk_seconds"],
            overlap_seconds=stt_options["overlap_seconds"],
            device=stt_options["device"],
        )
        stt_result = format_chunked_stt_result(raw_result)
    else:
        raw_result = run_whisper_stt(
            audio_path=audio_path,
            model_size=stt_options["model_size"],
            language=stt_options["language"],
            device=stt_options["device"],
        )
        stt_result = format_stt_result(raw_result)

    save_stt_json(stt_result, output_json)
    save_stt_text(stt_result, output_text, include_timestamps=stt_options["timestamps"])
    return int(stt_result.get("segment_count", 0))


def parse_args():
    """전체 영상 요약 파이프라인 실행에 필요한 명령줄 인자를 해석합니다."""
    parser = argparse.ArgumentParser(
        description="영상 전처리, 오디오 추출, 시각 정보 분석, STT를 순서대로 실행합니다."
    )
    parser.add_argument(
        "--video",
        default=str(project_path(PROJECT_ROOT, DEFAULT_INPUT_VIDEO_RELATIVE_PATH)),
        help=f"분석할 원본 영상 파일 경로입니다. 기본값은 {DEFAULT_INPUT_VIDEO_RELATIVE_PATH.as_posix()}입니다.",
    )
    parser.add_argument(
        "--run-dir",
        default=str(project_path(PROJECT_ROOT, DEFAULT_RUN_DIR_RELATIVE_PATH)),
        help="파이프라인 결과를 저장할 실행 디렉터리입니다.",
    )
    parser.add_argument(
        "--method",
        choices=SAMPLING_METHOD_CHOICES,
        default=DEFAULT_SAMPLING_METHOD,
        help="프레임 추출 방식입니다. interval, scene_change, interval_scene_change를 사용할 수 있습니다.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help="interval 방식에서 프레임을 추출할 시간 간격입니다. 단위는 초입니다.",
    )
    parser.add_argument(
        "--scene-threshold",
        type=float,
        default=DEFAULT_SCENE_THRESHOLD,
        help="scene_change 방식에서 사용할 장면 전환 임계값입니다.",
    )
    parser.add_argument(
        "--ocr-lang",
        default=DEFAULT_OCR_LANGUAGE,
        help="OCR 엔진에 전달할 언어 설정입니다.",
    )
    parser.add_argument(
        "--skip-vision",
        action="store_true",
        help="시각 정보 분석 단계를 건너뜁니다.",
    )
    parser.add_argument("--skip-stt", action="store_true", help="STT 단계를 건너뜁니다.")
    parser.add_argument(
        "--stt-config",
        default=str(project_path(PROJECT_ROOT, DEFAULT_STT_CONFIG_RELATIVE_PATH)),
        help="STT 설정 YAML 경로입니다.",
    )
    parser.add_argument(
        "--stt-model-size",
        help="Whisper 모델 크기입니다. 예: tiny, base, small, medium",
    )
    parser.add_argument(
        "--stt-language",
        help="STT 언어 코드입니다. 기본값은 설정 파일의 language입니다.",
    )
    parser.add_argument("--stt-device", help="STT 실행 장치입니다. 예: cpu, cuda")
    parser.add_argument("--stt-chunked", action="store_true", help="오디오를 chunk 단위로 나눠 STT를 실행합니다.")
    parser.add_argument("--stt-no-chunked", action="store_true", help="chunk 분할 없이 STT를 실행합니다.")
    parser.add_argument("--stt-chunk-seconds", type=int, help="STT chunk 길이(초)입니다.")
    parser.add_argument("--stt-overlap-seconds", type=int, help="STT chunk overlap 길이(초)입니다.")
    parser.add_argument(
        "--stt-timestamps",
        action="store_true",
        help="STT 텍스트 결과에 segment 시간 정보를 포함합니다.",
    )
    return parser.parse_args()


def load_stt_config(config_path: Path) -> dict:
    """STT 설정 파일을 읽어 딕셔너리로 반환합니다.

    Args:
        config_path: STT 설정 YAML 파일 경로입니다.

    Returns:
        설정 파일에서 읽은 STT 옵션 딕셔너리입니다. 파일이 없으면 빈 딕셔너리를 반환합니다.
    """
    if not config_path.exists():
        return {}
    text = config_path.read_text(encoding="utf-8-sig")
    try:
        import yaml
    except ImportError:
        return _parse_simple_stt_config(text)

    return yaml.safe_load(text) or {}


def _parse_simple_stt_config(text: str) -> dict:
    """단순 key-value 형태의 STT 설정 텍스트를 파싱합니다.

    Args:
        text: YAML 형식의 설정 파일 내용입니다.

    Returns:
        문자열, 정수, bool, ``None`` 값으로 구성된 설정 딕셔너리입니다.
    """
    config = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value == "":
            config[key] = None
        elif value.lower() in {"true", "false"}:
            config[key] = value.lower() == "true"
        else:
            try:
                config[key] = int(value)
            except ValueError:
                config[key] = value

    return config


def build_stt_options(args: argparse.Namespace) -> dict:
    """명령줄 인자와 설정 파일을 합쳐 STT 실행 옵션을 구성합니다.

    Args:
        args: ``parse_args``가 반환한 명령줄 인자입니다.

    Returns:
        파이프라인 STT 단계에서 사용할 옵션 딕셔너리입니다.

    Raises:
        ValueError: 서로 충돌하는 chunk 옵션을 동시에 전달했을 때 발생합니다.
    """
    config = load_stt_config(Path(args.stt_config))

    if args.stt_chunked and args.stt_no_chunked:
        raise ValueError("--stt-chunked와 --stt-no-chunked는 동시에 사용할 수 없습니다.")

    if args.stt_chunked:
        chunked = True
    elif args.stt_no_chunked:
        chunked = False
    else:
        chunked = bool(config.get("chunked", DEFAULT_STT_CHUNKED))

    return {
        "model_size": args.stt_model_size or config.get("model_size", DEFAULT_STT_MODEL_SIZE),
        "language": args.stt_language or config.get("language", DEFAULT_STT_LANGUAGE),
        "device": args.stt_device if args.stt_device is not None else config.get("device", DEFAULT_STT_DEVICE),
        "chunked": chunked,
        "chunk_seconds": args.stt_chunk_seconds or int(config.get("chunk_seconds", DEFAULT_STT_CHUNK_SECONDS)),
        "overlap_seconds": args.stt_overlap_seconds or int(
            config.get("overlap_seconds", DEFAULT_STT_OVERLAP_SECONDS)
        ),
        "timestamps": args.stt_timestamps,
    }

def resolve_video_path(video_path: Path) -> Path:
    """*.mp4 같은 glob 패턴을 실제 영상 파일 경로로 변환합니다."""
    if "*" not in video_path.name:
        return video_path

    video_files = sorted(video_path.parent.glob(video_path.name))

    if not video_files:
        raise FileNotFoundError(f"mp4 파일을 찾을 수 없습니다: {video_path}")

    if len(video_files) > 1:
        raise ValueError(
            "mp4 파일이 여러 개 있습니다. "
            f"하나만 남기거나 --video 옵션으로 직접 지정하세요: {video_files}"
        )

    return video_files[0]
    
def run_preprocess_step(
    video_path: Path,
    run_dir: Path,
    method: str,
    interval_seconds: float,
    scene_threshold: float,
    important_segments_path: Path | None = None,
) -> Path:
    """영상 정보를 확인하고 프레임 이미지와 메타데이터를 생성합니다."""
    if not video_path.exists():
        raise FileNotFoundError(f"영상 파일이 존재하지 않습니다: {video_path}")

    video_info = get_video_info(video_path)
    print(
        "영상 정보 확인 완료. "
        f"길이: {video_info.duration:.2f}초, "
        f"해상도: {video_info.width}x{video_info.height}, "
        f"FPS: {video_info.fps:.2f}"
    )

    metadata = sample_frames(
        video_path=video_path,
        run_dir=run_dir,
        method=method,
        interval_seconds=interval_seconds,
        scene_threshold=scene_threshold,
        project_root=PROJECT_ROOT,
        important_segments_path=important_segments_path,
    )

    metadata_path = run_path(run_dir, DEFAULT_FRAME_METADATA_RELATIVE_PATH)
    print(f"프레임 추출 완료: {metadata_path}")
    print(f"추출 프레임 수: {len(metadata)}")
    return metadata_path


def run_audio_step(video_path: Path, run_dir: Path) -> Path:
    """영상에서 오디오 파일을 추출합니다."""
    audio_path = run_path(run_dir, DEFAULT_AUDIO_RELATIVE_PATH)
    return extract_audio(video_path, audio_path)


def run_vision_step(metadata_path: Path, run_dir: Path, ocr_lang: str) -> Path:
    """프레임 메타데이터를 분석해 시각 정보 결과를 생성합니다.

    Args:
        metadata_path: 프레임 메타데이터 JSON 파일 경로입니다.
        run_dir: 파이프라인 실행 결과를 저장할 디렉터리입니다.
        ocr_lang: OCR 엔진에 전달할 언어 설정입니다.

    Returns:
        생성된 시각 정보 결과 JSON 파일 경로입니다.
    """
    from modules.vision import analyze_frames_metadata

    output_path = run_path(run_dir, DEFAULT_VISION_RESULT_RELATIVE_PATH)

    analyze_frames_metadata(
        metadata_path=str(metadata_path),
        output_path=str(output_path),
        lang=ocr_lang,
    )

    print(f"시각 정보 추출 완료: {output_path}")
    return output_path


def run_stt_step(
    audio_path: Path,
    run_dir: Path,
    stt_options: dict,
) -> tuple[Path, Path]:
    """오디오 파일에서 STT 결과 JSON/TXT를 생성합니다.

    Args:
        audio_path: STT를 수행할 오디오 파일 경로입니다.
        run_dir: 파이프라인 실행 결과를 저장할 디렉터리입니다.
        stt_options: STT 모델, 언어, chunk 설정을 담은 딕셔너리입니다.

    Returns:
        STT JSON 결과 경로와 텍스트 결과 경로입니다.
    """
    output_json = run_path(run_dir, DEFAULT_STT_JSON_RELATIVE_PATH)
    output_text = run_path(run_dir, DEFAULT_STT_TEXT_RELATIVE_PATH)

    segment_count = _execute_stt(audio_path, output_json, output_text, stt_options)

    print(f"STT 완료: {output_json}")
    print(f"STT 텍스트 저장: {output_text}")
    print(f"STT segment 수: {segment_count}")
    return output_json, output_text


def main():
    """구현되어 있는 파이프라인 단계를 순서대로 실행합니다."""
    args = parse_args()
    video_path = resolve_path_pattern(args.video)
    run_dir = Path(args.run_dir)
    stt_options = build_stt_options(args)
    video_path = ensure_mp4_video(video_path, run_dir / "data" / "input")

    print("[1/5] 오디오 추출을 시작합니다.")
    audio_path = run_audio_step(video_path=video_path, run_dir=run_dir)

    if args.skip_stt:
        print("[2/5] STT 단계를 건너뜁니다.")
        stt_json_path = None
        stt_text_path = None
    else:
        print("[2/5] STT를 시작합니다.")
        stt_json_path, stt_text_path = run_stt_step(
            audio_path=audio_path,
            run_dir=run_dir,
            stt_options=stt_options,
        )

    print("[3/5] STT 요약을 시작합니다.")
    if stt_json_path is None:
        llm_summary_path = None
        llm_summary_json_path = None
        print("STT JSON 결과가 없어 STT 요약을 건너뜁니다.")
    else:
        llm_summary_path, llm_summary_json_path = run_llm_summary_step(
            stt_json_path=stt_json_path,
            output_path=run_path(run_dir, DEFAULT_LLM_SUMMARY_RELATIVE_PATH),
            output_json_path=run_path(run_dir, DEFAULT_LLM_SUMMARY_JSON_RELATIVE_PATH),
        )
        print(f"STT 요약 저장(txt): {llm_summary_path}")
        print(f"STT 요약 저장(json): {llm_summary_json_path}")

    if llm_summary_json_path is None:
        print("[4/5] 중요 구간 프레임 추출을 건너뜁니다.")
        metadata_path = None
    else:
        print("[4/5] 중요 구간 프레임 추출을 시작합니다.")
        metadata_path = run_preprocess_step(
            video_path=video_path,
            run_dir=run_dir,
            method=args.method,
            interval_seconds=args.interval_seconds,
            scene_threshold=args.scene_threshold,
            important_segments_path=llm_summary_json_path,
        )

    if metadata_path is None:
        print("[5/5] 시각 정보 분석을 건너뜁니다.")
        vision_path = None
    elif args.skip_vision:
        print("[5/5] 시각 정보 분석을 건너뜁니다.")
        vision_path = None
    else:
        print("[5/5] 시각 정보 분석을 시작합니다.")
        vision_path = run_vision_step(
            metadata_path=metadata_path,
            run_dir=run_dir,
            ocr_lang=args.ocr_lang,
        )

    print("파이프라인 실행이 완료되었습니다.")
    print(f"오디오 파일: {audio_path}")
    if stt_json_path is not None:
        print(f"STT JSON 결과: {stt_json_path}")
        print(f"STT 텍스트 결과: {stt_text_path}")
    if llm_summary_path is not None:
        print(f"STT 요약 결과: {llm_summary_path}")
    if llm_summary_json_path is not None:
        print(f"STT 요약 JSON 결과: {llm_summary_json_path}")
    if metadata_path is not None:
        print(f"프레임 메타데이터: {metadata_path}")
    if vision_path is not None:
        print(f"시각 정보 결과: {vision_path}")
    
if __name__ == "__main__":
    main()
