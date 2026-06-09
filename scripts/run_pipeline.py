import argparse
import sys
import traceback
from multiprocessing import get_context
from pathlib import Path
from queue import Empty
from typing import Any

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


def _put_worker_error(result_queue, exc: BaseException) -> None:
    """자식 프로세스에서 발생한 예외 정보를 결과 큐에 기록합니다.

    Args:
        result_queue: 부모 프로세스로 결과를 전달할 multiprocessing 큐입니다.
        exc: 자식 프로세스에서 발생한 예외입니다.
    """
    result_queue.put(
        {
            "ok": False,
            "error": repr(exc),
            "traceback": traceback.format_exc(),
        }
    )


def _run_isolated_worker(worker_name: str, target: Any, args: tuple[Any, ...]) -> dict[str, Any]:
    """작업 함수를 spawn 자식 프로세스에서 실행하고 결과를 반환합니다.

    Args:
        worker_name: 오류 메시지에 사용할 작업 이름입니다.
        target: 자식 프로세스에서 실행할 함수입니다.
        args: ``result_queue``를 제외하고 target에 전달할 인자입니다.

    Returns:
        자식 프로세스가 큐에 넣은 결과 딕셔너리입니다.

    Raises:
        RuntimeError: 자식 프로세스가 실패했거나 결과를 반환하지 못했을 때 발생합니다.
    """
    ctx = get_context("spawn")
    result_queue = ctx.Queue()
    process = ctx.Process(target=target, args=(*args, result_queue))
    process.start()
    process.join()

    try:
        result = result_queue.get(timeout=1)
    except Empty:
        result = None

    if result is None:
        raise RuntimeError(
            f"{worker_name} failed before returning a result from the isolated process. "
            f"Child exit code: {process.exitcode}"
        )

    if not result.get("ok"):
        raise RuntimeError(
            f"{worker_name} failed in the isolated process.\n"
            f"{result.get('traceback') or result.get('error')}"
        )

    return result


def _vision_worker(metadata_path: str, output_path: str, ocr_lang: str, result_queue) -> None:
    """비전 분석을 자식 프로세스에서 실행합니다.

    Args:
        metadata_path: 프레임 메타데이터 JSON 파일 경로입니다.
        output_path: 시각 정보 결과 JSON을 저장할 경로입니다.
        ocr_lang: OCR 엔진에 전달할 언어 설정입니다.
        result_queue: 부모 프로세스로 결과를 전달할 multiprocessing 큐입니다.
    """
    try:
        from modules.vision import analyze_frames_metadata

        analyze_frames_metadata(
            metadata_path=metadata_path,
            output_path=output_path,
            lang=ocr_lang,
        )
        result_queue.put({"ok": True})
    except BaseException as exc:
        _put_worker_error(result_queue, exc)


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


def _stt_worker(audio_path: str, output_json: str, output_text: str, stt_options: dict, result_queue) -> None:
    """Whisper/PyTorch STT를 자식 프로세스에서 실행합니다.

    Args:
        audio_path: STT를 수행할 오디오 파일 경로입니다.
        output_json: STT JSON 결과를 저장할 경로입니다.
        output_text: STT 텍스트 결과를 저장할 경로입니다.
        stt_options: STT 모델, 언어, chunk 설정을 담은 딕셔너리입니다.
        result_queue: 부모 프로세스로 결과를 전달할 multiprocessing 큐입니다.
    """
    try:
        segment_count = _execute_stt(audio_path, output_json, output_text, stt_options)
        result_queue.put({"ok": True, "segment_count": segment_count})
    except BaseException as exc:
        _put_worker_error(result_queue, exc)


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
    parser.add_argument(
        "--vision-same-process",
        action="store_true",
        help="비전 단계를 별도 프로세스로 분리하지 않고 현재 프로세스에서 실행합니다.",
    )
    parser.add_argument("--skip-stt", action="store_true", help="STT 단계를 건너뜁니다.")
    parser.add_argument(
        "--stt-same-process",
        action="store_true",
        help="Whisper STT 단계를 별도 프로세스로 분리하지 않고 현재 프로세스에서 실행합니다.",
    )
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


def validate_process_isolation(args: argparse.Namespace) -> None:
    """Whisper와 OCR 엔진이 같은 프로세스에 함께 로드되는 설정을 차단합니다.

    Args:
        args: ``parse_args``가 반환한 명령줄 인자입니다.

    Raises:
        ValueError: 비전 단계와 STT 단계를 모두 same-process로 실행하려 할 때 발생합니다.
    """
    if not args.skip_vision and not args.skip_stt and args.vision_same_process and args.stt_same_process:
        raise ValueError(
            "Whisper STT와 OCR 엔진을 같은 프로세스에서 실행하면 cuDNN DLL 충돌이 발생할 수 있습니다. "
            "--vision-same-process와 --stt-same-process를 동시에 사용하지 마세요."
        )

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
    )

    metadata_path = run_path(run_dir, DEFAULT_FRAME_METADATA_RELATIVE_PATH)
    print(f"프레임 추출 완료: {metadata_path}")
    print(f"추출 프레임 수: {len(metadata)}")
    return metadata_path


def run_audio_step(video_path: Path, run_dir: Path) -> Path:
    """영상에서 오디오 파일을 추출합니다."""
    audio_path = run_path(run_dir, DEFAULT_AUDIO_RELATIVE_PATH)
    return extract_audio(video_path, audio_path)


def _run_vision_step_in_child_process(metadata_path: Path, output_path: Path, ocr_lang: str) -> None:
    """시각 정보 분석 단계를 별도 프로세스에서 실행합니다.

    Args:
        metadata_path: 프레임 메타데이터 JSON 파일 경로입니다.
        output_path: 시각 정보 결과 JSON을 저장할 경로입니다.
        ocr_lang: OCR 엔진에 전달할 언어 설정입니다.
    """
    _run_isolated_worker(
        worker_name="Vision step",
        target=_vision_worker,
        args=(str(metadata_path), str(output_path), ocr_lang),
    )


def run_vision_step(metadata_path: Path, run_dir: Path, ocr_lang: str, isolated: bool = True) -> Path:
    """프레임 메타데이터를 분석해 시각 정보 결과를 생성합니다.

    Args:
        metadata_path: 프레임 메타데이터 JSON 파일 경로입니다.
        run_dir: 파이프라인 실행 결과를 저장할 디렉터리입니다.
        ocr_lang: OCR 엔진에 전달할 언어 설정입니다.
        isolated: 별도 프로세스에서 실행할지 여부입니다.

    Returns:
        생성된 시각 정보 결과 JSON 파일 경로입니다.
    """
    output_path = run_path(run_dir, DEFAULT_VISION_RESULT_RELATIVE_PATH)

    if isolated:
        _run_vision_step_in_child_process(metadata_path, output_path, ocr_lang)
    else:
        from modules.vision import analyze_frames_metadata

        analyze_frames_metadata(
            metadata_path=str(metadata_path),
            output_path=str(output_path),
            lang=ocr_lang,
        )

    print(f"시각 정보 추출 완료: {output_path}")
    return output_path


def _run_stt_step_in_child_process(
    audio_path: Path,
    output_json: Path,
    output_text: Path,
    stt_options: dict,
) -> int:
    """STT 단계를 별도 프로세스에서 실행합니다.

    Args:
        audio_path: STT를 수행할 오디오 파일 경로입니다.
        output_json: STT JSON 결과를 저장할 경로입니다.
        output_text: STT 텍스트 결과를 저장할 경로입니다.
        stt_options: STT 모델, 언어, chunk 설정을 담은 딕셔너리입니다.

    Returns:
        저장된 STT 결과의 segment 개수입니다.
    """
    result = _run_isolated_worker(
        worker_name="STT step",
        target=_stt_worker,
        args=(str(audio_path), str(output_json), str(output_text), stt_options),
    )
    return int(result.get("segment_count", 0))


def _run_stt_step_in_current_process(
    audio_path: Path,
    output_json: Path,
    output_text: Path,
    stt_options: dict,
) -> int:
    """STT 단계를 현재 프로세스에서 실행합니다.

    Args:
        audio_path: STT를 수행할 오디오 파일 경로입니다.
        output_json: STT JSON 결과를 저장할 경로입니다.
        output_text: STT 텍스트 결과를 저장할 경로입니다.
        stt_options: STT 모델, 언어, chunk 설정을 담은 딕셔너리입니다.

    Returns:
        저장된 STT 결과의 segment 개수입니다.
    """
    return _execute_stt(audio_path, output_json, output_text, stt_options)


def run_stt_step(
    audio_path: Path,
    run_dir: Path,
    stt_options: dict,
    isolated: bool = True,
) -> tuple[Path, Path]:
    """오디오 파일에서 STT 결과 JSON/TXT를 생성합니다.

    Args:
        audio_path: STT를 수행할 오디오 파일 경로입니다.
        run_dir: 파이프라인 실행 결과를 저장할 디렉터리입니다.
        stt_options: STT 모델, 언어, chunk 설정을 담은 딕셔너리입니다.
        isolated: 별도 프로세스에서 실행할지 여부입니다.

    Returns:
        STT JSON 결과 경로와 텍스트 결과 경로입니다.
    """
    output_json = run_path(run_dir, DEFAULT_STT_JSON_RELATIVE_PATH)
    output_text = run_path(run_dir, DEFAULT_STT_TEXT_RELATIVE_PATH)

    if isolated:
        segment_count = _run_stt_step_in_child_process(audio_path, output_json, output_text, stt_options)
    else:
        segment_count = _run_stt_step_in_current_process(audio_path, output_json, output_text, stt_options)

    print(f"STT 완료: {output_json}")
    print(f"STT 텍스트 저장: {output_text}")
    print(f"STT segment 수: {segment_count}")
    return output_json, output_text


def main():
    """구현되어 있는 파이프라인 단계를 순서대로 실행합니다."""
    args = parse_args()
    validate_process_isolation(args)
    video_path = Path(args.video)
    run_dir = Path(args.run_dir)
    stt_options = build_stt_options(args)
    video_path = resolve_video_path(video_path)
    video_path = ensure_mp4_video(video_path, run_dir / "input")

    print("[1/4] 영상 전처리를 시작합니다.")
    metadata_path = run_preprocess_step(
        video_path=video_path,
        run_dir=run_dir,
        method=args.method,
        interval_seconds=args.interval_seconds,
        scene_threshold=args.scene_threshold,
    )

    print("[2/4] 오디오 추출을 시작합니다.")
    audio_path = run_audio_step(video_path=video_path, run_dir=run_dir)

    if args.skip_vision:
        print("[3/4] 시각 정보 분석을 건너뜁니다.")
        vision_path = None
    else:
        print("[3/4] 시각 정보 분석을 시작합니다.")
        vision_path = run_vision_step(
            metadata_path=metadata_path,
            run_dir=run_dir,
            ocr_lang=args.ocr_lang,
            isolated=not args.vision_same_process,
        )

    if args.skip_stt:
        print("[4/4] STT 단계를 건너뜁니다.")
        stt_json_path = None
        stt_text_path = None
    else:
        print("[4/4] STT를 시작합니다.")
        stt_json_path, stt_text_path = run_stt_step(
            audio_path=audio_path,
            run_dir=run_dir,
            stt_options=stt_options,
            isolated=not args.stt_same_process,
        )

    print("파이프라인 실행이 완료되었습니다.")
    print(f"프레임 메타데이터: {metadata_path}")
    print(f"오디오 파일: {audio_path}")
    if vision_path is not None:
        print(f"시각 정보 결과: {vision_path}")

    if stt_json_path is not None:
        print(f"STT JSON 결과: {stt_json_path}")
        print(f"STT 텍스트 결과: {stt_text_path}")


if __name__ == "__main__":
    main()
