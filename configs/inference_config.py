from dataclasses import dataclass


@dataclass(frozen=True)
class LLMInferenceConfig:
    default_max_new_tokens: int = 512
    max_new_tokens_limit: int = 1024
    segment_chunk_chars: int = 12000
    do_sample: bool = False
    num_beams: int = 1
    use_cache: bool = True


@dataclass(frozen=True)
class VLMInferenceConfig:
    default_max_new_tokens: int = 160
    max_new_tokens_limit: int = 384
    max_frame_count: int = 8
    image_max_side: int = 960
    do_sample: bool = False
    num_beams: int = 1
    use_cache: bool = True


LLM_INFERENCE_CONFIG = LLMInferenceConfig()
VLM_INFERENCE_CONFIG = VLMInferenceConfig()
