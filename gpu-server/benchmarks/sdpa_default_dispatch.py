"""커널을 강제하지 않은 기본 SDPA 디스패치가 어떤 커널을 고르는지 Profiler로 확인합니다."""
import torch
import torch.nn.functional as F
from torch.profiler import ProfilerActivity, profile

from sdpa_backend_probe import case

if __name__ == "__main__":
    print("priority:", torch._C._get_sdp_priority_order() if hasattr(torch._C, "_get_sdp_priority_order") else "n/a")
    for gqa in (True, False):
        for mask_kind in ("is_causal", "bool_4d"):
            q, k, v, kwargs = case(4096, mask_kind, gqa)
            torch.cuda.synchronize()
            base = torch.cuda.memory_allocated()
            torch.cuda.reset_peak_memory_stats()
            with profile(activities=[ProfilerActivity.CUDA]) as prof:
                F.scaled_dot_product_attention(q, k, v, **kwargs)
                torch.cuda.synchronize()
            ops = sorted({e.key for e in prof.key_averages() if "attention" in e.key.lower() or "softmax" in e.key.lower() or "gemm" in e.key.lower() or "fmha" in e.key.lower() or "cudnn" in e.key.lower()})
            print(f"gqa={gqa!s:5} mask={mask_kind:9} extra={(torch.cuda.max_memory_allocated()-base)/2**20:7.0f} MiB kernels={[o[:60] for o in ops][:5]}")
            del q, k, v
            torch.cuda.empty_cache()
