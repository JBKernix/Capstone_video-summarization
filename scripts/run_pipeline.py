import argparse
import sys
import time
from contextlib import contextmanager
from datetime import datetime
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
    DEFAULT_OCR_RESULT_RELATIVE_PATH,
    project_path,
    resolve_path_pattern,
    run_path,
)
from modules.preprocess import (
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_SAMPLING_METHOD,
    DEFAULT_SCENE_MIN_GAP_SECONDS,
    DEFAULT_SCENE_THRESHOLD,
    SAMPLING_METHOD_CHOICES,
    ensure_mp4_video,
    extract_audio,
    get_video_info,
    sample_frames,
)
from modules.stt import (  # noqa: E402
    DEFAULT_STT_DEVICE,
    DEFAULT_STT_LANGUAGE,
    DEFAULT_STT_MODEL_SIZE,
    DEFAULT_STT_TEMPERATURE,
    DEFAULT_STT_BEAM_SIZE,
)
from modules.ocr import DEFAULT_OCR_LANGUAGE  # noqa: E402
from scripts.run_llm_summary import (  # noqa: E402
    DEFAULT_LLM_SUMMARY_JSON_RELATIVE_PATH,
    DEFAULT_LLM_SUMMARY_RELATIVE_PATH,
    run_llm_summary_step,
)
from scripts.run_vlm_summary import (  # noqa: E402
    DEFAULT_VLM_SUMMARY_JSON_RELATIVE_PATH,
    DEFAULT_VLM_SUMMARY_RELATIVE_PATH,
    run_vlm_summary_step,
)
from scripts.run_final_summary import (  # noqa: E402
    DEFAULT_FINAL_SUMMARY_JSON_RELATIVE_PATH,
    DEFAULT_FINAL_SUMMARY_RELATIVE_PATH,
    run_final_summary_step,
)


def _format_elapsed(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


@contextmanager
def _stage_timeline(step: str, name: str):
    started_at = time.monotonic()
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{step}] {name} 시작")
    state = {"status": "완료"}
    try:
        yield state
    except Exception:
        elapsed = _format_elapsed(time.monotonic() - started_at)
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{step}] {name} 실패 (소요 {elapsed})")
        raise
    else:
        elapsed = _format_elapsed(time.monotonic() - started_at)
        print(
            f"[{datetime.now():%Y-%m-%d %H:%M:%S}] [{step}] "
            f"{name} {state['status']} (소요 {elapsed})"
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
        format_stt_result,
        run_whisper_stt,
        save_stt_json,
        save_stt_text,
    )

    raw_result = run_whisper_stt(
        audio_path=audio_path,
        model_size=stt_options["model_size"],
        language=stt_options["language"],
        device=stt_options["device"],
        temperature=stt_options["temperature"],
        beam_size=stt_options["beam_size"],
    )
    stt_result = format_stt_result(raw_result)

    save_stt_json(stt_result, output_json)
    save_stt_text(stt_result, output_text, include_timestamps=stt_options["timestamps"])
    return int(stt_result.get("segment_count", 0))


def parse_args():
    """전체 영상 요약 파이프라인 실행에 필요한 명령줄 인자를 해석합니다."""
    parser = argparse.ArgumentParser(
        description="영상 전처리, 오디오 추출, OCR 분석, STT를 순서대로 실행합니다."
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
        help="중요 구간 프레임 샘플링 방식입니다.",
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
        help="화면 전환으로 판단할 FFmpeg scene 임계값입니다.",
    )
    parser.add_argument(
        "--scene-min-gap-seconds",
        type=float,
        default=DEFAULT_SCENE_MIN_GAP_SECONDS,
        help="연속 화면 전환 프레임 사이의 최소 간격입니다.",
    )
    parser.add_argument(
        "--ocr-lang",
        default=DEFAULT_OCR_LANGUAGE,
        help="OCR 엔진에 전달할 언어 설정입니다.",
    )
    parser.add_argument(
        "--skip-ocr",
        action="store_true",
        help="OCR 분석 단계를 건너뜁니다.",
    )
    parser.add_argument(
        "--skip-vlm",
        action="store_true",
        help="VLM 프레임 요약 단계를 건너뜁니다.",
    )
    parser.add_argument(
        "--vlm-max-new-tokens",
        type=int,
        default=384,
        help="프레임당 VLM 최대 생성 토큰 수입니다. 허용 범위는 1~384입니다.",
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

    beam_size = config.get("beam_size", DEFAULT_STT_BEAM_SIZE)

    return {
        "model_size": args.stt_model_size or config.get("model_size", DEFAULT_STT_MODEL_SIZE),
        "language": args.stt_language or config.get("language", DEFAULT_STT_LANGUAGE),
        "device": args.stt_device if args.stt_device is not None else config.get("device", DEFAULT_STT_DEVICE),
        "temperature": float(config.get("temperature", DEFAULT_STT_TEMPERATURE)),
        "beam_size": int(beam_size) if beam_size is not None else None,
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
    scene_min_gap_seconds: float,
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
        scene_min_gap_seconds=scene_min_gap_seconds,
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


def run_ocr_step(metadata_path: Path, run_dir: Path, ocr_lang: str) -> Path:
    """프레임 메타데이터를 분석해 OCR 결과를 생성합니다.

    Args:
        metadata_path: 프레임 메타데이터 JSON 파일 경로입니다.
        run_dir: 파이프라인 실행 결과를 저장할 디렉터리입니다.
        ocr_lang: OCR 엔진에 전달할 언어 설정입니다.

    Returns:
        생성된 OCR 결과 JSON 파일 경로입니다.
    """
    from modules.ocr import analyze_frames_metadata

    output_path = run_path(run_dir, DEFAULT_OCR_RESULT_RELATIVE_PATH)

    analyze_frames_metadata(
        metadata_path=str(metadata_path),
        output_path=str(output_path),
        lang=ocr_lang,
    )

    print(f"OCR 결과 저장 완료: {output_path}")
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

    with _stage_timeline("1/7", "오디오 추출"):
        audio_path = run_audio_step(video_path=video_path, run_dir=run_dir)

    with _stage_timeline("2/7", "STT") as stage:
        if args.skip_stt:
            stage["status"] = "건너뜀"
            stt_json_path = None
            stt_text_path = None
        else:
            stt_json_path, stt_text_path = run_stt_step(
                audio_path=audio_path,
                run_dir=run_dir,
                stt_options=stt_options,
            )

    with _stage_timeline("3/7", "STT 요약") as stage:
        if stt_json_path is None:
            stage["status"] = "건너뜀"
            llm_summary_path = None
            llm_summary_json_path = None
        else:
            llm_summary_path, llm_summary_json_path = run_llm_summary_step(
                stt_json_path=stt_json_path,
                output_path=run_path(run_dir, DEFAULT_LLM_SUMMARY_RELATIVE_PATH),
                output_json_path=run_path(run_dir, DEFAULT_LLM_SUMMARY_JSON_RELATIVE_PATH),
            )
            print(f"STT 요약 저장(txt): {llm_summary_path}")
            print(f"STT 요약 저장(json): {llm_summary_json_path}")

    with _stage_timeline("4/7", "중요 구간 프레임 추출") as stage:
        if llm_summary_json_path is None:
            stage["status"] = "건너뜀"
            metadata_path = None
        else:
            metadata_path = run_preprocess_step(
                video_path=video_path,
                run_dir=run_dir,
                method=args.method,
                interval_seconds=args.interval_seconds,
                scene_threshold=args.scene_threshold,
                scene_min_gap_seconds=args.scene_min_gap_seconds,
                important_segments_path=llm_summary_json_path,
            )

    with _stage_timeline("5/7", "OCR 분석") as stage:
        if metadata_path is None or args.skip_ocr:
            stage["status"] = "건너뜀"
            ocr_path = None
        else:
            ocr_path = run_ocr_step(
                metadata_path=metadata_path,
                run_dir=run_dir,
                ocr_lang=args.ocr_lang,
            )

    with _stage_timeline("6/7", "VLM 프레임 요약") as stage:
        if ocr_path is None or args.skip_vlm:
            stage["status"] = "건너뜀"
            vlm_summary_path = None
            vlm_summary_json_path = None
        else:
            vlm_summary_path, vlm_summary_json_path = run_vlm_summary_step(
                ocr_json_path=ocr_path,
                output_path=run_path(run_dir, DEFAULT_VLM_SUMMARY_RELATIVE_PATH),
                output_json_path=run_path(run_dir, DEFAULT_VLM_SUMMARY_JSON_RELATIVE_PATH),
                max_new_tokens=args.vlm_max_new_tokens,
            )
            print(f"VLM 요약 저장(txt): {vlm_summary_path}")
            print(f"VLM 요약 저장(json): {vlm_summary_json_path}")

    with _stage_timeline("7/7", "최종 통합 요약") as stage:
        if (
            llm_summary_path is None
            or llm_summary_json_path is None
            or vlm_summary_path is None
            or vlm_summary_json_path is None
        ):
            stage["status"] = "건너뜀"
            final_summary_path = None
            final_summary_json_path = None
        else:
            final_summary_path, final_summary_json_path = run_final_summary_step(
                stt_summary_path=llm_summary_path,
                stt_summary_json_path=llm_summary_json_path,
                vlm_summary_path=vlm_summary_path,
                vlm_summary_json_path=vlm_summary_json_path,
                output_path=run_path(run_dir, DEFAULT_FINAL_SUMMARY_RELATIVE_PATH),
                output_json_path=run_path(run_dir, DEFAULT_FINAL_SUMMARY_JSON_RELATIVE_PATH),
            )
            print(f"최종 요약 저장(txt): {final_summary_path}")
            print(f"최종 요약 저장(json): {final_summary_json_path}")

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
    if ocr_path is not None:
        print(f"OCR 결과: {ocr_path}")
    if vlm_summary_path is not None:
        print(f"VLM 요약 결과: {vlm_summary_path}")
    if vlm_summary_json_path is not None:
        print(f"VLM 요약 JSON 결과: {vlm_summary_json_path}")
    if final_summary_path is not None:
        print(f"최종 요약 결과: {final_summary_path}")
    if final_summary_json_path is not None:
        print(f"최종 요약 JSON 결과: {final_summary_json_path}")
    
if __name__ == "__main__":
    main()
