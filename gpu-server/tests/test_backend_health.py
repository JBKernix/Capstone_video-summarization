"""Validate health metadata without importing GPU model dependencies."""
import ast
from pathlib import Path
from types import SimpleNamespace


def health_for(llm_type):
    source = Path(__file__).resolve().parents[1] / "app" / "server.py"
    function = next(node for node in ast.parse(source.read_text(encoding="utf-8")).body
                    if isinstance(node, ast.FunctionDef) and node.name == "health_check")
    function.decorator_list = []
    llm = type(llm_type, (), {})()
    llm.config = SimpleNamespace(model="claude-haiku-4-5") if llm_type == "ClaudeLLMLoader" else SimpleNamespace(model_path="models/hf_cache/Qwen3-8B")
    vlm = type("VLMLoader", (), {})()
    vlm.config = SimpleNamespace(model_path="models/hf_cache/Qwen2.5-VL-7B-Instruct")
    namespace = {"Path": Path, "job_store": SimpleNamespace(active_count=lambda: 0),
                 "claude_api_configured": lambda: True,
                 "summary_service": SimpleNamespace(llm_service=SimpleNamespace(loader=llm), vlm_service=SimpleNamespace(loader=vlm))}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["health_check"]()


def test_local_backend_is_reported():
    result = health_for("LLMLoader")
    assert result["llm_backend"] == result["vlm_backend"] == "local"
    assert result["llm_model"] == "Qwen3-8B"
    assert result["claude_api_configured"] is True
    assert result["claude_api_proxy"] is True


def test_claude_is_not_misreported_as_local():
    result = health_for("ClaudeLLMLoader")
    assert result["llm_backend"] == "claude"
    assert result["llm_model"] == "claude-haiku-4-5"
