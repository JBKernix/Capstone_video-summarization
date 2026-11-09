"""SDPA 백엔드별 지원 여부와 메모리를 합성 텐서로 확인합니다(모델 로드 없음).

Qwen3-VL 8B 텍스트 attention 모양(32 query heads, 8 KV heads, head_dim 128, bf16)을 그대로 씁니다.
실행: python benchmarks/sdpa_backend_probe.py
"""
import torch
import torch.nn.functional as F
from torch.nn.attention import SDPBackend, sdpa_kernel

BACKENDS = {
    "flash": SDPBackend.FLASH_ATTENTION,
    "efficient": SDPBackend.EFFICIENT_ATTENTION,
    "cudnn": SDPBackend.CUDNN_ATTENTION,
    "math": SDPBackend.MATH,
}


def case(length, mask_kind, gqa):
    q = torch.randn(1, 32, length, 128, device="cuda", dtype=torch.bfloat16)
    kv_heads = 8 if gqa else 32
    k = torch.randn(1, kv_heads, length, 128, device="cuda", dtype=torch.bfloat16)
    v = torch.randn_like(k)
    kwargs = {"enable_gqa": True} if gqa else {}
    if mask_kind == "is_causal":
        kwargs["is_causal"] = True
    elif mask_kind == "bool_4d":
        kwargs["attn_mask"] = torch.ones(length, length, device="cuda", dtype=torch.bool).tril()[None, None]
    return q, k, v, kwargs


def run(length, mask_kind, gqa, backend):
    q, k, v, kwargs = case(length, mask_kind, gqa)
    torch.cuda.synchronize()
    base = torch.cuda.memory_allocated()
    torch.cuda.reset_peak_memory_stats()
    try:
        with sdpa_kernel([BACKENDS[backend]]):
            F.scaled_dot_product_attention(q, k, v, **kwargs)
        torch.cuda.synchronize()
        return f"OK  extra={(torch.cuda.max_memory_allocated() - base) / 2**20:8.1f} MiB"
    except RuntimeError as error:
        return "NO  " + str(error).splitlines()[0][:90]
    finally:
        del q, k, v
        torch.cuda.empty_cache()


if __name__ == "__main__":
    print(torch.__version__, torch.cuda.get_device_name(0))
    for length in (4096, 8192):
        for gqa in (False, True):
            for mask_kind in ("is_causal", "bool_4d"):
                for backend in BACKENDS:
                    print(f"L={length:5d} gqa={gqa!s:5} mask={mask_kind:9} {backend:9} {run(length, mask_kind, gqa, backend)}")
