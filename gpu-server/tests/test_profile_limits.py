import logging
from types import SimpleNamespace

import pytest

from app.inference_jobs import InferenceJobRunner
from app.job_store import JobStore
from configs.inference_config import get_summary_level_preset
from configs.local_models import PROFILES

try:
    # 서비스 모듈은 모델 로더(transformers)를 함께 불러옵니다. 앱 환경처럼 없으면 이 테스트만 건너뜁니다.
    from services.final_service import MAX_STT_TEXT_CHARS, FinalService
except ImportError:
    FinalService = None


def test_only_qwen3_vl_has_custom_attention_and_input_limits():
    profile = PROFILES["qwen3-vl-8b"]
    assert (profile.max_input_tokens, profile.attn_implementation, profile.sdpa_max_input_tokens) == (
        16384, "sdpa_no_gqa", 7000)
    assert profile.segment_chunk_chars == 6000
    assert (profile.final_stt_chars, profile.final_vlm_chars) == (4000, 4000)
    for other in (p for p in PROFILES.values() if p.id != "qwen3-vl-8b"):
        assert (other.max_input_tokens, other.attn_implementation, other.sdpa_max_input_tokens) == (16384, "sdpa", None)
        assert (other.segment_chunk_chars, other.final_stt_chars, other.final_vlm_chars) == (None, None, None)


def test_attention_override_restores_previous_limit(monkeypatch):
    pytest.importorskip("transformers")
    from models.multimodal_loader import ATTENTION_OVERRIDE_ENV, MultimodalLoader

    loader = MultimodalLoader("qwen3-vl-8b")
    monkeypatch.delenv(ATTENTION_OVERRIDE_ENV, raising=False)
    assert (loader.attn_implementation, loader.max_input_tokens) == ("sdpa_no_gqa", 16384)
    monkeypatch.setenv(ATTENTION_OVERRIDE_ENV, "sdpa")
    assert (loader.attn_implementation, loader.max_input_tokens) == ("sdpa", 7000)
    # 다른 프로필은 되돌려도 그대로입니다.
    assert MultimodalLoader("gemma4-12b").max_input_tokens == 16384


def test_count_prompt_tokens_matches_generate_tokenization():
    """processor 출력이 배치 형태([[...]])라 len()이 1이 되던 회귀를 막습니다(모델은 로드하지 않음)."""
    pytest.importorskip("transformers")
    from transformers import AutoProcessor

    from configs.local_models import checkpoint_status
    from models.multimodal_loader import MultimodalLoader

    loader = MultimodalLoader("qwen3-vl-8b")
    if not checkpoint_status(loader.profile.repos[0])["ready"]:
        pytest.skip("Qwen3-VL 체크포인트가 없는 환경")
    loader.processor = AutoProcessor.from_pretrained(loader.config.model_path, local_files_only=True)
    prompt = "다음은 강의 STT입니다. " + "경사하강법은 손실을 줄이는 방향으로 이동합니다. " * 200
    expected = loader.processor.apply_chat_template(
        [{"role": "user", "content": [{"type": "text", "text": prompt}]}], tokenize=True,
        add_generation_prompt=True, return_dict=True, return_tensors="pt")["input_ids"].shape[-1]
    assert loader.count_prompt_tokens(prompt) == expected > 1000


def test_sdpa_no_gqa_matches_default_sdpa_numerically():
    torch = pytest.importorskip("torch")
    from types import SimpleNamespace

    from transformers.integrations.sdpa_attention import sdpa_attention_forward

    from models.attention import sdpa_without_gqa

    module = SimpleNamespace(num_key_value_groups=4, is_causal=True)
    query = torch.randn(1, 8, 16, 32)
    key = torch.randn(1, 2, 16, 32)
    value = torch.randn(1, 2, 16, 32)
    expected, _ = sdpa_attention_forward(module, query, key, value, None)
    actual, _ = sdpa_without_gqa(module, query, key, value, None)
    assert torch.allclose(expected, actual, atol=1e-5)


@pytest.mark.skipif(FinalService is None, reason="transformers가 있는 서버 환경에서 실행")
def test_final_service_uses_profile_char_limits():
    llm = SimpleNamespace(_generation_lock=None)
    limited = FinalService(llm_service=llm, max_stt_chars=4000, max_vlm_chars=4000)
    section = limited.build_stt_section(stt_json={"summary": "가" * 4500})
    assert "가" * 4000 in section and "가" * 4001 not in section
    vlm = {"results": [{"timestamp": i, "vlm_summary": f"화면 {i} " + "나" * 280} for i in range(20)]}
    assert len(limited.build_vlm_section(vlm_json=vlm)) < 4100
    # 지정하지 않으면 기존 기본값을 씁니다.
    assert FinalService(llm_service=llm).max_stt_chars == MAX_STT_TEXT_CHARS


def test_runner_shrinks_important_segment_chunks_to_profile_limit():
    calls = []
    llm_service = SimpleNamespace(split_segments=lambda segments, max_chunk_chars: [segments])
    service = SimpleNamespace(
        llm_service=llm_service,
        summarize_stt=lambda **kwargs: "요약",
        get_important_segments_in_chunks=lambda **kwargs: calls.append(kwargs["max_chunk_chars"]) or [],
        unload_llm=lambda: None,
    )
    request = {"segments": [{"segment_id": 0, "start": 0, "end": 1, "text": "예시"}], "summary_level": "standard"}
    for limit, expected in ((6000, 6000), (None, get_summary_level_preset("standard").segment_chunk_chars)):
        store = JobStore()
        store.create("job", "queued")
        InferenceJobRunner(service, store, logging.getLogger("test"), segment_chunk_chars=limit).run_summary("job", request)
        assert store.response_data("job")["status"] == "completed"
        assert calls.pop() == expected
