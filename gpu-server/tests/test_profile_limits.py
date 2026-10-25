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


def test_only_qwen3_vl_has_tighter_input_limits():
    profile = PROFILES["qwen3-vl-8b"]
    assert (profile.max_input_tokens, profile.segment_chunk_chars) == (7000, 6000)
    assert (profile.final_stt_chars, profile.final_vlm_chars) == (4000, 4000)
    for other in (p for p in PROFILES.values() if p.id != "qwen3-vl-8b"):
        assert other.max_input_tokens == 16384
        assert (other.segment_chunk_chars, other.final_stt_chars, other.final_vlm_chars) == (None, None, None)


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
