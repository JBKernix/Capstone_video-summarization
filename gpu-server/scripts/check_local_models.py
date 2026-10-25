"""GPU smoke test: text and image inference, with actual load timings/results."""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configs.local_models import PROFILES, profile_status

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true")
    group.add_argument("--model", nargs="+", choices=list(PROFILES))
    parser.add_argument("--image", type=Path, required=True, help="실제 뉴스 프레임 이미지")
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error("--image 파일이 없습니다.")
    import logging
    import torch
    import transformers
    from app.inference_jobs import InferenceJobRunner
    from app.job_store import JobStore
    from app.local_model_manager import LocalModelManager
    from app.model_load_metrics import ACTIVE_LOAD_SINK
    from services.summary_service import SummaryService
    manager = LocalModelManager(InferenceJobRunner(SummaryService(), JobStore(), logging.getLogger(__name__)))
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "torch": torch.__version__,
              "transformers": transformers.__version__, "gpu": torch.cuda.get_device_name(0), "models": []}
    target = Path("logs") / ("local-model-check-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".json")
    target.parent.mkdir(parents=True, exist_ok=True)
    for model_id in PROFILES if args.all else args.model:
        record = {**profile_status(model_id), "loads": []}
        token = ACTIVE_LOAD_SINK.set(record["loads"].append)
        start = time.perf_counter()
        try:
            service = manager._runner_for(model_id).summary_service
            record["text_result"] = service.llm_service.loader.generate("다음 뉴스를 한국어 한 문장으로 요약하세요: 서울시는 내일부터 버스 10대를 추가 운행한다고 발표했습니다.", max_new_tokens=128)
            if model_id == "legacy-qwen":
                service.unload_llm()
            record["vision_result"] = service.vlm_service.loader.describe_image(args.image, "이미지에서 직접 확인할 수 있는 정보만 한국어로 설명하세요.", max_new_tokens=128)
            if not record["text_result"].strip() or not record["vision_result"].strip():
                raise ValueError("빈 답변")
            record["status"] = "passed"
        except Exception as error:
            record.update(status="failed", error=f"{type(error).__name__}: {error}")
        finally:
            ACTIVE_LOAD_SINK.reset(token)
            manager.active_runner.summary_service.unload_llm()
            manager.active_runner.summary_service.unload_vlm()
            record["seconds"] = round(time.perf_counter() - start, 3)
            report["models"].append(record)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(model_id, record["status"], record["seconds"], flush=True)
    print(target)
    return int(any(r["status"] != "passed" for r in report["models"]))

if __name__ == "__main__":
    raise SystemExit(main())
