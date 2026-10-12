"""Generate explicitly labeled UI fixtures, never benchmark results."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from modules.common.run_history import DEFAULT_HISTORY_DIR, atomic_json, prepare_run, read_record
from modules.common.progress import STEP_LABELS


def main():
    parser = argparse.ArgumentParser(description="실제 추론 없이 화면 검증용 예시 이력을 생성합니다.")
    parser.add_argument("--write-demo-data", action="store_true", required=True)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY_DIR)
    args = parser.parse_args()
    samples = [
        ("강의영상_멀티모달AI.mp4", "standard", "small", "success", [3.2, 64.7, 18.4, 12.5, 39.8, 76.2, 14.6],
         {"frames_extracted": 48, "ocr_success": 47, "ocr_failed": 1, "vlm_frames": 47, "vlm_batches": 6, "stt_segments": 186}),
        ("강의영상_멀티모달AI.mp4", "simple", "base", "success", [3.1, 31.8, 12.2, 0, 0, 0, .01], {"stt_segments": 181}),
        ("실습영상_데이터분석.mp4", "detailed", "medium", "failed", [2.8, 103.5, 24.1, 9.7, 32.4, 45.3],
         {"frames_extracted": 36, "ocr_success": 36, "ocr_failed": 0, "vlm_frames": 8, "vlm_batches": 1, "stt_segments": 152}),
    ]
    for index, (name, level, model, status, seconds, counts) in enumerate(samples):
        directory = prepare_run(args.history_dir, input_name=name, settings={"summary_level": level, "stt": {"model_size": model, "device": "cuda"}, "method": "interval", "interval_seconds": 5})
        record = read_record(directory)
        started = datetime.now(timezone.utc) - timedelta(minutes=index * 15 + 10)
        record.update(demo=True, status=status, created_at=started.isoformat(), started_at=started.isoformat(),
                      finished_at=(started + timedelta(seconds=sum(seconds) + .8)).isoformat(),
                      duration_seconds=round(sum(seconds) + .8, 3), counts=counts)
        record["input"].update(duration_seconds=1200, width=1920, height=1080, fps=30)
        cursor = started
        lines = ["[DEMO] 화면 검증용 예시입니다. 실제 추론/측정 결과가 아닙니다.", f"영상: {name}"]
        for step, elapsed in enumerate(seconds, 1):
            stage_status = "skipped" if level == "simple" and 4 <= step <= 6 else "success"
            if status == "failed" and step == len(seconds):
                stage_status = "failed"
            end = cursor + timedelta(seconds=elapsed)
            record["stages"].append({"step": step, "name": STEP_LABELS[step][0], "status": stage_status,
                                     "started_at": cursor.isoformat(), "finished_at": end.isoformat(), "duration_seconds": elapsed})
            lines.append(f"[{step}/7] {STEP_LABELS[step][0]} {stage_status} · {elapsed:.2f}초")
            cursor = end
        if status == "failed":
            record["error"] = "[예시] VLM 서버 연결 시간 초과 — 첫 번째 배치까지 저장됨"
            lines.append(record["error"])
        atomic_json(directory / "metrics.json", record)
        (directory / "pipeline.log").write_text("\n".join(lines), encoding="utf-8")
        print(directory)


if __name__ == "__main__":
    main()
