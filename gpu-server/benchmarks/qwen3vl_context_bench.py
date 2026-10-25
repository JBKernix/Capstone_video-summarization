"""Qwen3-VL 8B(NF4) 입력 길이별 GPU 메모리·시간 벤치마크.

운영 코드(MultimodalLoader)로 모델을 그대로 로드하고, SDPA 설정만 모드별로 바꿔 비교합니다.

모드
- default : 최적화 전 운영 설정(기본 SDPA)
- registered : 현재 프로필 설정 그대로(models/attention.py의 sdpa_no_gqa)
- cudnn   : SDPA 우선순위를 cuDNN → Flash → Efficient → Math로 지정
- nogqa   : transformers가 enable_gqa 대신 repeat_kv를 쓰게 해 mem-efficient 커널로 보냄
- flash   : Flash 커널만 허용(지원 여부 확인용)

안전장치
- 모드마다 별도 프로세스에서 실행해 끝나면 GPU 메모리가 반드시 반환됩니다.
- set_per_process_memory_fraction으로 남은 VRAM 안에서만 할당하게 해,
  Windows의 시스템 메모리 폴백 대신 즉시 OOM이 나도록 합니다.
- 부모 프로세스가 자식의 'GPU Process Memory\\Shared Usage'를 감시해, 기준보다 1GiB 이상
  늘면(시스템 메모리 폴백) 자식을 종료합니다.
- OOM이나 폴백이 나면 그 모드의 더 긴 입력은 건너뜁니다. 16K는 8K가 통과한 모드에서만 실행합니다.

실행(gpu-server 폴더에서):
    python benchmarks/qwen3vl_context_bench.py --modes default,cudnn,nogqa
결과는 benchmarks/results/ 아래 JSONL로 저장됩니다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

GPU_SERVER = Path(__file__).resolve().parents[1]
REPO = GPU_SERVER.parent
RESULTS = Path(__file__).resolve().parent / "results"
# 33분 강의(11,610자, 운영에서 8,424토큰으로 거부된 입력)를 앞에 두고, 길이가 모자라면 다른 강의를 잇습니다.
STT_JOBS = (
    "20261025T133520-57c5a5700e2b",
    "20261025T130633-cb49b03e32e7",
    "20261025T085857-0ed4e6a4c89b",
    "20261025T115415-331d498e1c50",
)
FRAME = REPO / "runs" / "jobs" / "20261025T085857-0ed4e6a4c89b" / "frames" / "frame_000002.jpg"
FALLBACK_LIMIT = 1 << 30  # 공유 GPU 메모리가 이만큼 늘면 시스템 메모리 폴백으로 봅니다.


# ---------------------------------------------------------------- 부모 프로세스

def shared_usage_bytes(pid: int) -> int | None:
    """Windows 성능 카운터에서 프로세스의 공유 GPU 메모리 사용량을 읽습니다."""
    command = (
        f"(Get-Counter '\\GPU Process Memory(pid_{pid}_*)\\Shared Usage' -ErrorAction SilentlyContinue)"
        ".CounterSamples | Measure-Object -Property CookedValue -Sum | ForEach-Object Sum"
    )
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", command],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return int(float(out)) if out else None
    except (subprocess.SubprocessError, ValueError):
        return None


def run_parent(args) -> None:
    RESULTS.mkdir(exist_ok=True)
    out_path = RESULTS / f"bench_{time.strftime('%Y%m%dT%H%M%S')}.jsonl"
    print(f"결과 파일: {out_path}")
    for mode in args.modes.split(","):
        command = [sys.executable, __file__, "--child", "--mode", mode, "--lengths", args.lengths,
                   "--new-tokens", str(args.new_tokens), "--out", str(out_path)]
        if args.allow_16k:
            command.append("--allow-16k")
        if args.skip_8k_gate:
            command.append("--skip-8k-gate")
        child = subprocess.Popen(command, cwd=GPU_SERVER)
        peak, baseline, stop = {"shared": 0}, {"shared": None}, threading.Event()

        def watch():
            while not stop.wait(3):
                value = shared_usage_bytes(child.pid)
                if value is None:
                    continue
                if baseline["shared"] is None:
                    baseline["shared"] = value
                peak["shared"] = max(peak["shared"], value)
                if value - baseline["shared"] > FALLBACK_LIMIT:
                    print(f"[중단] {mode}: 공유 GPU 메모리 {value / 2**30:.2f}GiB → 시스템 메모리 폴백으로 판단")
                    child.kill()
                    with out_path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps({"mode": mode, "event": "killed_sysmem_fallback",
                                            "shared_bytes": value}) + "\n")
                    return

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        code = child.wait()
        stop.set()
        watcher.join()
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"mode": mode, "event": "child_exit", "code": code,
                                "shared_baseline_bytes": baseline["shared"],
                                "shared_peak_bytes": peak["shared"]}) + "\n")
        print(f"[{mode}] 종료 코드 {code}, 공유 GPU 메모리 기준 {baseline['shared']} / 최대 {peak['shared']} bytes")


# ---------------------------------------------------------------- 자식 프로세스

def apply_mode(mode: str):
    """모드에 맞는 SDPA 설정을 적용하고, generate를 감쌀 context factory를 돌려줍니다."""
    import contextlib

    from torch.nn.attention import SDPBackend, sdpa_kernel

    # registered 외의 모드는 프로필 설정과 무관하게 기본 SDPA로 로드한 뒤 각 모드의 변경만 얹습니다.
    if mode != "registered":
        os.environ["LOCAL_MODEL_ATTENTION"] = "sdpa"
    if mode in ("default", "registered"):
        return contextlib.nullcontext
    if mode == "cudnn":
        order = [SDPBackend.CUDNN_ATTENTION, SDPBackend.FLASH_ATTENTION,
                 SDPBackend.EFFICIENT_ATTENTION, SDPBackend.MATH]
        return lambda: sdpa_kernel(order, set_priority=True)
    if mode == "nogqa":
        import transformers.integrations.sdpa_attention as sdpa_module
        sdpa_module.use_gqa_in_sdpa = lambda *args, **kwargs: False
        return contextlib.nullcontext
    if mode == "flash":
        return lambda: sdpa_kernel([SDPBackend.FLASH_ATTENTION])
    raise ValueError(mode)


def load_corpus() -> str:
    texts = []
    for job in STT_JOBS:
        data = json.loads((REPO / "runs" / "jobs" / job / "stt" / "stt_result.json").read_text(encoding="utf-8"))
        texts.append(data["full_text"].strip())
    # 고유 강의 텍스트는 약 1.85만 토큰입니다. 그보다 긴 입력의 메모리 측정에서만 반복해 늘립니다
    # (메모리·시간은 내용과 무관하고, 이때의 출력 내용은 비교에 쓰지 않습니다).
    return "\n\n".join(texts * int(os.environ.get("BENCH_REPEAT_CORPUS", "1")))


def stt_prompt(stt_text: str) -> str:
    """운영 LLMService.summarize_stt가 만드는 프롬프트를 그대로 가져옵니다."""
    from services.llm_service import LLMService

    captured = {}

    class Capture:
        def generate(self, prompt, max_new_tokens):
            captured["prompt"] = prompt
            return ""

    LLMService(loader=Capture()).summarize_stt(stt_text)
    return captured["prompt"]


def build_inputs(processor, model, prompt, image=None):
    content = [] if image is None else [{"type": "image", "image": image}]
    content.append({"type": "text", "text": prompt})
    return processor.apply_chat_template(
        [{"role": "user", "content": content}], tokenize=True, add_generation_prompt=True,
        enable_thinking=False, return_dict=True, return_tensors="pt").to(model.device)


def inputs_for_length(processor, model, corpus: str, target: int):
    """실제 토크나이저 결과가 target 토큰에 가장 가깝도록 STT 원문 길이를 이분 탐색합니다."""
    low, high, best = 1, len(corpus), None
    while low <= high:
        middle = (low + high) // 2
        inputs = build_inputs(processor, model, stt_prompt(corpus[:middle]))
        length = inputs["input_ids"].shape[-1]
        if best is None or abs(length - target) < abs(best[1] - target):
            best = (inputs, length, middle)
        if length < target:
            low = middle + 1
        elif length > target:
            high = middle - 1
        else:
            break
    if best[1] < target * 0.98:
        raise ValueError(f"말뭉치가 부족합니다: 최대 {best[1]} tokens")
    return best


class SdpaRecorder:
    """텍스트 attention의 SDPA 호출 인자(mask, enable_gqa, head 수)를 셉니다."""

    def __init__(self):
        import torch.nn.functional as F
        self.F = F
        self.original = F.scaled_dot_product_attention
        self.calls = {}

    def __enter__(self):
        def wrapped(query, key, value, attn_mask=None, *args, **kwargs):
            signature = (
                f"q_heads={query.shape[1]} kv_heads={key.shape[1]} q_len={'1' if query.shape[2] == 1 else 'N'} "
                f"mask={'None' if attn_mask is None else f'{attn_mask.dtype}{tuple(attn_mask.shape[-2:]) if attn_mask.shape[-1] < 64 else attn_mask.dim()}D'} "
                f"is_causal={kwargs.get('is_causal')} enable_gqa={kwargs.get('enable_gqa', False)} dtype={query.dtype}"
            )
            self.calls[signature] = self.calls.get(signature, 0) + 1
            return self.original(query, key, value, attn_mask, *args, **kwargs)

        self.F.scaled_dot_product_attention = wrapped
        return self

    def __exit__(self, *exc):
        self.F.scaled_dot_product_attention = self.original


def cuda_kernels(model, inputs, generate_context) -> list[tuple[str, float]]:
    """Profiler로 prefill 1회의 CUDA 커널 이름과 시간(상위 12개)을 수집합니다."""
    import torch
    from torch.profiler import ProfilerActivity, profile

    with profile(activities=[ProfilerActivity.CUDA]) as prof, generate_context(), torch.inference_mode():
        model.generate(**inputs, max_new_tokens=1, do_sample=False, num_beams=1, use_cache=True)
        torch.cuda.synchronize()
    events = [e for e in prof.key_averages() if e.device_time_total > 0]
    events.sort(key=lambda e: e.device_time_total, reverse=True)
    return [(e.key[:90], round(e.device_time_total / 1000, 2)) for e in events[:12]]


def measure(model, processor, inputs, new_tokens, generate_context) -> dict:
    import psutil
    import torch

    gib = 2 ** 30
    result = {"input_tokens": int(inputs["input_ids"].shape[-1])}
    for phase, kwargs in (("prefill", {"max_new_tokens": 1}),
                          ("generate", {"max_new_tokens": new_tokens, "min_new_tokens": new_tokens})):
        torch.cuda.empty_cache()
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()
        started = time.perf_counter()
        with generate_context(), torch.inference_mode():
            output = model.generate(**inputs, do_sample=False, num_beams=1, use_cache=True, **kwargs)
        torch.cuda.synchronize()
        result[f"{phase}_seconds"] = round(time.perf_counter() - started, 3)
        result[f"{phase}_peak_allocated_gib"] = round(torch.cuda.max_memory_allocated() / gib, 2)
        result[f"{phase}_peak_reserved_gib"] = round(torch.cuda.max_memory_reserved() / gib, 2)
        if phase == "generate":
            new_ids = output[0, inputs["input_ids"].shape[-1]:]
            result["new_tokens"] = int(new_ids.shape[-1])
            text = processor.decode(new_ids, skip_special_tokens=True)
            result["output_sha1"] = hashlib.sha1(new_ids.cpu().numpy().tobytes()).hexdigest()[:12]
            result["output_head"] = text[:120]
        del output
    result["decode_tokens_per_second"] = round(
        (new_tokens - 1) / max(result["generate_seconds"] - result["prefill_seconds"], 1e-6), 1)
    result["process_rss_gib"] = round(psutil.Process().memory_info().rss / gib, 2)
    result["system_available_gib"] = round(psutil.virtual_memory().available / gib, 1)
    return result


def run_child(args) -> None:
    sys.path.insert(0, str(GPU_SERVER))
    import torch
    from PIL import Image

    from models.multimodal_loader import MultimodalLoader
    from services.vlm_service import VLMService

    out = Path(args.out)

    def emit(record):
        record = {"mode": args.mode, **record}
        print(json.dumps(record, ensure_ascii=False), flush=True)
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    free, total = torch.cuda.mem_get_info()
    if free < 20 * 2 ** 30:
        emit({"event": "abort", "reason": f"GPU 여유 메모리 부족({free / 2**30:.1f}GiB). 다른 프로세스가 GPU를 쓰는 중"})
        return
    # 남은 VRAM - 0.5GiB 안에서만 할당합니다(넘으면 시스템 메모리로 넘기지 않고 OOM).
    fraction = (free - 0.5 * 2 ** 30) / total
    torch.cuda.set_per_process_memory_fraction(fraction)
    generate_context = apply_mode(args.mode)
    emit({"event": "env", "torch": torch.__version__, "cuda": torch.version.cuda,
          "gpu_free_gib": round(free / 2**30, 2), "gpu_total_gib": round(total / 2**30, 2),
          "memory_fraction": round(fraction, 4)})

    loader = MultimodalLoader("qwen3-vl-8b")
    started = time.perf_counter()
    model, processor = loader._load()
    torch.cuda.synchronize()
    emit({"event": "loaded", "load_seconds": round(time.perf_counter() - started, 2),
          "weights_allocated_gib": round(torch.cuda.memory_allocated() / 2**30, 2),
          "attn_implementation": model.config._attn_implementation})

    corpus = load_corpus()
    warm_inputs, warm_len, _ = inputs_for_length(processor, model, corpus, 512)
    probe_inputs, probe_len, _ = inputs_for_length(processor, model, corpus, 2000)
    try:
        started = time.perf_counter()
        with generate_context(), torch.inference_mode():
            model.generate(**warm_inputs, max_new_tokens=8, do_sample=False)
        torch.cuda.synchronize()
        emit({"event": "warmup", "input_tokens": warm_len, "seconds": round(time.perf_counter() - started, 2)})

        # 실제 실행되는 SDPA 호출 형태와 CUDA 커널(2K 입력 prefill 1회)
        with SdpaRecorder() as recorder, generate_context(), torch.inference_mode():
            model.generate(**probe_inputs, max_new_tokens=2, do_sample=False)
        emit({"event": "sdpa_calls", "input_tokens": probe_len, "calls": recorder.calls})
        emit({"event": "kernels", "input_tokens": probe_len, "top": cuda_kernels(model, probe_inputs, generate_context)})
    except RuntimeError as error:
        emit({"event": "unsupported", "error": str(error).splitlines()[0]})
        return

    # 프레임 1장(운영과 같은 960px 축소 + VLM 프롬프트)
    service = VLMService(loader=loader)
    with Image.open(FRAME) as source:
        image = service._resize_for_vlm(source.convert("RGB"))
    captured = {}

    class Capture:
        def describe_image(self, image, prompt, max_new_tokens):
            captured["prompt"] = prompt
            return ""

    VLMService(loader=Capture()).summarize_frame(image.copy(), ocr_text="경사하강법 갱신식 w = w - η∇L(w)")
    vlm_inputs = build_inputs(processor, model, captured["prompt"], image)
    image_tokens = int((vlm_inputs["input_ids"] == model.config.image_token_id).sum())
    emit({"event": "frame", "image_size": list(image.size), "image_tokens": image_tokens,
          **measure(model, processor, vlm_inputs, 64, generate_context)})

    lengths = [int(x) for x in args.lengths.split(",")]
    passed_8k = False
    for target in lengths:
        if target >= 16000 and not (args.allow_16k and (passed_8k or args.skip_8k_gate)):
            emit({"event": "skip", "target": target, "reason": "8K가 안전하게 통과하지 않았거나 --allow-16k 미지정"})
            continue
        inputs, length, chars = inputs_for_length(processor, model, corpus, target)
        try:
            emit({"event": "run", "target": target, "stt_chars": chars,
                  **measure(model, processor, inputs, args.new_tokens, generate_context)})
            if target >= 8000:
                passed_8k = True
        except torch.OutOfMemoryError as error:
            torch.cuda.empty_cache()
            emit({"event": "oom", "target": target, "input_tokens": length,
                  "error": str(error).splitlines()[0][:160]})
            break
        finally:
            del inputs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modes", default="default,cudnn,nogqa")
    parser.add_argument("--lengths", default="2000,4000,6000,7000,8000,16000")
    parser.add_argument("--new-tokens", type=int, default=128)
    parser.add_argument("--allow-16k", action="store_true")
    # 같은 모드에서 8K가 이미 통과한 것을 이전 실행으로 확인했을 때만 씁니다.
    parser.add_argument("--skip-8k-gate", action="store_true")
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--mode", default="default")
    parser.add_argument("--out")
    args = parser.parse_args()
    if args.child:
        os.chdir(GPU_SERVER)
        run_child(args)
    else:
        run_parent(args)


if __name__ == "__main__":
    main()
