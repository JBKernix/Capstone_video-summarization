from dataclasses import dataclass
from typing import Literal

SummaryLevel = Literal["simple", "standard", "detailed"]


@dataclass(frozen=True)
class LLMInferenceConfig:
    default_max_new_tokens: int = 512
    max_new_tokens_limit: int = 1024
    # 24GB급 GPU에서 관측된 CUDA OOM(입력 토큰 24054개) 사례를 반영해
    # 정상 운영 범위(약 9천~14천 토큰)보다 여유를 두고 상한을 둡니다.
    max_input_tokens: int = 16000
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


@dataclass(frozen=True)
class SummaryLevelPreset:
    """간단/기본/상세 요약 프리셋 한 단계가 각 추론 단계에 적용하는 값입니다."""

    label: str
    # STT 전체 요약 생성 토큰 수 (LLM_INFERENCE_CONFIG.max_new_tokens_limit 이하)
    stt_max_new_tokens: int
    # 중요 구간 추출 생성 토큰 수 (짧은 구조화 출력이라 프리셋 간 차이를 작게 둡니다)
    important_segments_max_new_tokens: int
    # 중요 구간 추출 시 STT 세그먼트를 묶는 청크 크기(문자 수).
    # 작을수록 청크(=LLM 호출) 수가 늘어나 더 꼼꼼하지만 느려집니다.
    segment_chunk_chars: int
    # VLM 프레임 1장당 생성 토큰 수 (VLM_INFERENCE_CONFIG.max_new_tokens_limit 이하)
    vlm_max_new_tokens: int
    # 최종 통합 요약 생성 토큰 수 (services.final_service.MAX_FINAL_NEW_TOKENS_LIMIT 이하)
    final_max_new_tokens: int


SUMMARY_LEVEL_PRESETS: dict[SummaryLevel, SummaryLevelPreset] = {
    "simple": SummaryLevelPreset(
        label="간단요약",
        stt_max_new_tokens=256,
        important_segments_max_new_tokens=160,
        segment_chunk_chars=20000,
        vlm_max_new_tokens=96,
        final_max_new_tokens=1024,
    ),
    "standard": SummaryLevelPreset(
        label="기본요약",
        stt_max_new_tokens=LLM_INFERENCE_CONFIG.default_max_new_tokens,
        important_segments_max_new_tokens=256,
        segment_chunk_chars=LLM_INFERENCE_CONFIG.segment_chunk_chars,
        vlm_max_new_tokens=VLM_INFERENCE_CONFIG.default_max_new_tokens,
        final_max_new_tokens=2048,
    ),
    "detailed": SummaryLevelPreset(
        label="상세요약",
        stt_max_new_tokens=LLM_INFERENCE_CONFIG.max_new_tokens_limit,
        important_segments_max_new_tokens=256,
        segment_chunk_chars=8000,
        vlm_max_new_tokens=VLM_INFERENCE_CONFIG.max_new_tokens_limit,
        final_max_new_tokens=4096,
    ),
}

DEFAULT_SUMMARY_LEVEL: SummaryLevel = "standard"


def get_summary_level_preset(summary_level: str) -> SummaryLevelPreset:
    try:
        return SUMMARY_LEVEL_PRESETS[summary_level]
    except KeyError as error:
        allowed = ", ".join(SUMMARY_LEVEL_PRESETS)
        raise ValueError(
            f"알 수 없는 summary_level입니다: {summary_level}. 허용값: {allowed}"
        ) from error
