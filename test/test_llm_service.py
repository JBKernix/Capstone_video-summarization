import argparse
import json
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = PROJECT_ROOT / "test" / "stt_result.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "test" / "llm_service_result.json"

# test 폴더에서 직접 실행해도 services 패키지를 찾을 수 있게 합니다.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_stt_result(input_path: Path) -> dict[str, Any]:
    with input_path.open("r", encoding="utf-8") as file:
        result = json.load(file)

    full_text = str(result.get("full_text", "")).strip()
    segments = result.get("segments", [])

    if not full_text:
        full_text = " ".join(
            str(segment.get("text", "")).strip()
            for segment in segments
            if str(segment.get("text", "")).strip()
        )

    if not full_text:
        raise ValueError("STT 결과에 요약할 텍스트가 없습니다.")
    if not isinstance(segments, list):
        raise ValueError("segments는 JSON 배열이어야 합니다.")

    result["full_text"] = full_text
    return result


@contextmanager
def show_elapsed_time(task_name: str):
    """모델 생성 중 멈춘 것처럼 보이지 않도록 경과 시간을 표시합니다."""
    stop_event = threading.Event()
    started_at = time.perf_counter()

    def report() -> None:
        while not stop_event.wait(10):
            elapsed = time.perf_counter() - started_at
            print(f"[{task_name}] 생성 중... {elapsed:.0f}초 경과", flush=True)

    reporter = threading.Thread(target=report, daemon=True)
    reporter.start()
    succeeded = False
    try:
        yield
        succeeded = True
    finally:
        stop_event.set()
        reporter.join()
        elapsed = time.perf_counter() - started_at
        status = "완료" if succeeded else "중단"
        print(f"[{task_name}] {status}: {elapsed:.1f}초", flush=True)


def run_llm_service(
    stt_result: dict[str, Any],
    max_new_tokens: int,
    important_max_new_tokens: int,
    segment_chunk_chars: int,
) -> dict[str, Any]:
    # 모델 의존성은 실제 추론을 시작할 때 로드합니다.
    from services.llm_service import LLMService

    service = LLMService()
    full_text = stt_result["full_text"]
    segments = stt_result.get("segments", [])

    print(
        f"[입력] 언어={stt_result.get('language', 'unknown')}, "
        f"세그먼트={len(segments)}, 텍스트 길이={len(full_text)}"
    )

    def show_chunk_progress(task: str, index: int, total: int) -> None:
        print(f"[중요 구간] {index}/{total} 처리 시작", flush=True)

    print("[1/2] full_text 전체 요약을 생성합니다.")
    with show_elapsed_time("STT 요약"):
        summary = service.summarize_stt(
            stt_text=full_text,
            max_new_tokens=max_new_tokens,
        )

    print("[2/2] 구간 묶음별로 중요 영상 구간을 추출합니다.")
    with show_elapsed_time("중요 구간"):
        important_segments = service.extract_important_segments_in_chunks(
            stt_segments=segments,
            stt_summary=summary,
            max_new_tokens=important_max_new_tokens,
            max_chunk_chars=segment_chunk_chars,
            progress_callback=show_chunk_progress,
        )

    return {
        "source": {
            "language": stt_result.get("language", "unknown"),
            "duration_sec": stt_result.get("duration_sec"),
            "segment_count": len(segments),
        },
        "summary": summary,
        "important_segments": important_segments,
    }


def save_result(result: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="stt_result.json을 실제 LLMService로 처리합니다."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help="입력 STT JSON 경로",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="LLM 결과 JSON 저장 경로",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=256,
        choices=range(1, 4097),
        metavar="1-4096",
        help="최종 요약의 최대 생성 토큰 수",
    )
    parser.add_argument(
        "--important-max-new-tokens",
        type=int,
        default=192,
        choices=range(1, 4097),
        metavar="1-4096",
        help="구간 묶음별 중요 구간 추출의 최대 생성 토큰 수",
    )
    parser.add_argument(
        "--segment-chunk-chars",
        type=int,
        default=12000,
        help="중요 구간 추출 묶음의 최대 직렬화 문자 수",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stt_result = load_stt_result(args.input.resolve())
    result = run_llm_service(
        stt_result=stt_result,
        max_new_tokens=args.max_new_tokens,
        important_max_new_tokens=args.important_max_new_tokens,
        segment_chunk_chars=args.segment_chunk_chars,
    )
    save_result(result, args.output.resolve())

    print("\n===== STT 요약 =====")
    print(result["summary"])
    print("\n===== 중요 구간 =====")
    print(result["important_segments"])
    print(f"\n[완료] 결과 저장: {args.output.resolve()}")


if __name__ == "__main__":
    main()
