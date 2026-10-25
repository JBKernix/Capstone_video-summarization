"""GQA 모델을 메모리 효율 SDPA 커널로 실행하는 attention 구현입니다.

Windows용 PyTorch(2.12+cu130)는 Flash 커널 없이 빌드되어 있고, mem-efficient 커널은 GQA(enable_gqa)를
지원하지 않습니다. transformers 기본 "sdpa"는 mask가 없을 때 enable_gqa=True로 호출하므로, 기본 우선순위
(Flash → Efficient → Math → cuDNN)에서 Math 커널로 떨어져 입력 길이의 제곱만큼 fp32 메모리를 씁니다.

여기서는 K/V를 query head 수만큼 먼저 복제(repeat_kv)해 enable_gqa 없이 호출하므로 mem-efficient 커널이
선택됩니다. 계산식은 같고 커널만 바뀝니다. 측정 근거: benchmarks/qwen3vl_context_bench.py
"""
from transformers import AttentionInterface
from transformers.integrations.sdpa_attention import repeat_kv, sdpa_attention_forward
from transformers.masking_utils import ALL_MASK_ATTENTION_FUNCTIONS, AttentionMaskInterface

SDPA_NO_GQA = "sdpa_no_gqa"


class _WithoutGroups:
    """sdpa_attention_forward가 GQA 분기를 타지 않도록 is_causal만 전달하는 대리 객체입니다."""

    __slots__ = ("is_causal",)

    def __init__(self, module):
        self.is_causal = getattr(module, "is_causal", True)


def sdpa_without_gqa(module, query, key, value, attention_mask, **kwargs):
    groups = getattr(module, "num_key_value_groups", 1)
    if groups > 1:
        key = repeat_kv(key, groups)
        value = repeat_kv(value, groups)
        module = _WithoutGroups(module)
    return sdpa_attention_forward(module, query, key, value, attention_mask, **kwargs)


def register() -> str:
    """구현을 등록하고 from_pretrained(attn_implementation=...)에 넘길 이름을 돌려줍니다."""
    AttentionInterface.register(SDPA_NO_GQA, sdpa_without_gqa)
    # mask는 기본 sdpa와 같은 방식(가능하면 생략하고 is_causal 사용)으로 만듭니다.
    AttentionMaskInterface.register(SDPA_NO_GQA, ALL_MASK_ATTENTION_FUNCTIONS["sdpa"])
    return SDPA_NO_GQA
