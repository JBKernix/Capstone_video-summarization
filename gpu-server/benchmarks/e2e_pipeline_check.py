"""실제 서버 코드 경로(LocalModelManager → InferenceJobRunner → 서비스 → MultimodalLoader)로
STT 요약 → VLM 프레임 분석 → 최종 강의 노트를 실행해 결과·메모리·모델 재로딩 여부를 확인합니다.

실행 중인 API 서버와 별개인 프로세스에서 돌며, 서버 로그(logs/server.log)에 쓰지 않습니다.
남은 VRAM 안에서만 할당하도록 제한하므로(시스템 메모리 폴백 대신 OOM) 장시간 정체가 생기지 않습니다.

실행(gpu-server 폴더에서):
    python benchmarks/e2e_pipeline_check.py                       # 최적화 설정
    LOCAL_MODEL_ATTENTION=sdpa python benchmarks/e2e_pipeline_check.py --cases rollback  # 기본 SDPA·7K 상한
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

GPU_SERVER = Path(__file__).resolve().parents[1]
REPO = GPU_SERVER.parent
JOBS = REPO / "runs" / "jobs"
RESULTS = Path(__file__).resolve().parent / "results"
MODEL_ID = "qwen3-vl-8b"
LECTURES = {
    "short_13min": ["20261025T085857-0ed4e6a4c89b"],
    "lecture_33min": ["20261025T133520-57c5a5700e2b"],
    # 서로 다른 강의 4개를 시간축을 이어 붙여 약 73분 강의로 만듭니다.
    "long_73min": ["20261025T133520-57c5a5700e2b", "20261025T130633-cb49b03e32e7",
                   "20261025T085857-0ed4e6a4c89b", "20261025T115415-331d498e1c50"],
}
VLM_JOB = "20261025T130633-cb49b03e32e7"


def load_lecture(job_ids):
    segments, texts, offset = [], [], 0.0
    for job_id in job_ids:
        data = json.loads((JOBS / job_id / "stt" / "stt_result.json").read_text(encoding="utf-8"))
        for segment in data["segments"]:
            segments.append({"segment_id": len(segments), "start": round(segment["start"] + offset, 2),
                             "end": round(segment["end"] + offset, 2), "text": segment["text"]})
        texts.append(data["full_text"].strip())
        offset += float(data["duration_sec"])
    return {"segments": segments, "full_text": " ".join(texts), "duration_sec": offset}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="short_13min,lecture_33min,long_73min,vlm,final")
    parser.add_argument("--summary-level", default="standard")
    args = parser.parse_args()

    os.chdir(GPU_SERVER)
    sys.path.insert(0, str(GPU_SERVER))
    import torch

    from app.job_store import JobStore
    from app.local_model_manager import LocalModelManager

    free, total = torch.cuda.mem_get_info()
    if free < 20 * 2 ** 30:
        sys.exit(f"GPU 여유 메모리가 부족합니다({free / 2**30:.1f}GiB). 다른 프로세스가 GPU를 쓰는 중입니다.")
    torch.cuda.set_per_process_memory_fraction((free - 0.5 * 2 ** 30) / total)

    RESULTS.mkdir(exist_ok=True)
    tag = os.environ.get("LOCAL_MODEL_ATTENTION") or "optimized"
    out_dir = RESULTS / f"e2e_{tag}_{time.strftime('%Y%m%dT%H%M%S')}"
    out_dir.mkdir()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s",
                        handlers=[logging.FileHandler(out_dir / "run.log", encoding="utf-8"), logging.StreamHandler()])
    logger = logging.getLogger("e2e")

    job_store = JobStore()
    messages = {}
    original_update = job_store.update

    def update(job_id, **fields):
        if "message" in fields:
            messages.setdefault(job_id, []).append(
                f"{fields.get('current_step', '')}/{fields.get('total_steps', '')} {fields['message']}")
        return original_update(job_id, **fields)

    job_store.update = update
    unused = SimpleNamespace(unload_llm=lambda: None, unload_vlm=lambda: None)
    manager = LocalModelManager(SimpleNamespace(job_store=job_store, logger=logger, summary_service=unused))
    report = {"attention_override": os.environ.get("LOCAL_MODEL_ATTENTION"), "cases": {}}

    def run(case, method, *method_args):
        job_id = f"{case}-{int(time.time())}"
        job_store.create(job_id, "queued")
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        manager.run(MODEL_ID, method, job_id, *method_args)
        data = job_store.response_data(job_id)
        result = {
            "status": data["status"], "message": data["message"], "error": data.get("error"),
            "seconds": round(time.perf_counter() - started, 1),
            "peak_allocated_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2),
            "peak_reserved_gib": round(torch.cuda.max_memory_reserved() / 2**30, 2),
            "allocated_after_gib": round(torch.cuda.memory_allocated() / 2**30, 2),
            "model_loads": [(e.get("kind"), e.get("status"), e.get("duration_seconds"))
                            for e in data.get("model_loads") or []],
            "progress": messages.get(job_id, []),
        }
        report["cases"][case] = result
        (out_dir / f"{case}.json").write_text(json.dumps(data.get("result"), ensure_ascii=False, indent=2),
                                              encoding="utf-8")
        logger.info("%s → %s", case, json.dumps({k: v for k, v in result.items() if k != "progress"},
                                                 ensure_ascii=False))
        return data.get("result")

    stt_result = None
    for case in args.cases.split(","):
        if case in LECTURES or case == "rollback":
            lecture = load_lecture(LECTURES["lecture_33min" if case == "rollback" else case])
            request = {"local_model": MODEL_ID, "language": "ko", "segments": lecture["segments"],
                       "full_text": lecture["full_text"], "summary_level": args.summary_level}
            report.setdefault("lectures", {})[case] = {
                "duration_min": round(lecture["duration_sec"] / 60, 1), "chars": len(lecture["full_text"]),
                "segments": len(lecture["segments"]),
            }
            stt_result = run(case, "run_summary", request) or stt_result
        elif case == "vlm":
            entries = json.loads((JOBS / VLM_JOB / "ocr" / "ocr_result.json").read_text(encoding="utf-8"))[:8]
            frames = [Path(entry["image_path"]).read_bytes() for entry in entries]
            from configs.inference_config import get_summary_level_preset
            vlm_result = run("vlm", "run_vlm", entries, frames,
                             get_summary_level_preset(args.summary_level).vlm_max_new_tokens)
        elif case == "final":
            from configs.inference_config import get_summary_level_preset
            preset = get_summary_level_preset(args.summary_level)
            stt_json = json.dumps(stt_result, ensure_ascii=False).encode("utf-8")
            vlm_json = json.dumps({"results": vlm_result}, ensure_ascii=False).encode("utf-8")
            run("final", "run_final", None, stt_json, None, vlm_json,
                preset.final_max_new_tokens, preset.final_important_segments)

    loader = manager.active_runner.summary_service.llm_service.loader
    report["max_input_tokens"] = loader.max_input_tokens
    report["attn_implementation"] = loader.model.config._attn_implementation if loader.model is not None else None
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"보고서: {out_dir / 'report.json'}")


if __name__ == "__main__":
    main()
