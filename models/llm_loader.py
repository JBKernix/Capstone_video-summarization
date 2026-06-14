from __future__ import annotations

import gc
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from configs.inference_config import LLM_INFERENCE_CONFIG


PROJECT_ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    model_path: str = str(PROJECT_ROOT / "models" / "hf_cache" / "Qwen3-8B")
    device: str = "cuda"
    torch_dtype: str = "float16"
    trust_remote_code: bool = True
    local_files_only: bool = True



class LLMLoader:
    """
    LLM 모델 로더

    역할:
    - tokenizer 로드
    - causal LM 모델 로드
    - GPU/CPU 디바이스 설정
    - 텍스트 생성용 generate 함수 제공
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self.tokenizer = None
        self.model = None

    def _get_torch_dtype(self):
        if self.config.torch_dtype == "float16":
            return torch.float16
        if self.config.torch_dtype == "bfloat16":
            return torch.bfloat16
        if self.config.torch_dtype == "float32":
            return torch.float32

        raise ValueError(f"지원하지 않는 torch_dtype입니다: {self.config.torch_dtype}")

    def load(self):
        """
        LLM 모델과 tokenizer를 로드합니다.

        Returns:
            tuple: (model, tokenizer)
        """

        if self.model is not None and self.tokenizer is not None:
            return self.model, self.tokenizer

        if self.config.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA를 사용할 수 없습니다.")

        model_path = Path(self.config.model_path)

        if not model_path.exists():
            raise FileNotFoundError(f"로컬 모델 경로를 찾을 수 없습니다: {model_path}")

        dtype = self._get_torch_dtype()

        print(f"[LLM 로드 시작] {model_path}")

        self.tokenizer = AutoTokenizer.from_pretrained(
            str(model_path),
            trust_remote_code=self.config.trust_remote_code,
            local_files_only=self.config.local_files_only,
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            str(model_path),
            dtype=dtype,
            device_map="auto" if self.config.device == "cuda" else None,
            trust_remote_code=self.config.trust_remote_code,
            local_files_only=self.config.local_files_only,
        )

        if self.config.device == "cpu":
            self.model = self.model.to("cpu")

        self.model.eval()

        print("[LLM 로드 완료]")

        return self.model, self.tokenizer

    def unload(self) -> None:
        """Release model references and return unused CUDA memory to the driver."""
        self.model = None
        self.tokenizer = None
        gc.collect()

        if self.config.device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    
    @torch.inference_mode()
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = LLM_INFERENCE_CONFIG.default_max_new_tokens,
    ) -> str:
        model, tokenizer = self.load()

        messages = [
            {
                "role": "system",
                "content": "당신은 영상 내용을 정확하고 간결하게 요약하는 AI입니다.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ]

        if hasattr(tokenizer, "apply_chat_template"):
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                # Qwen3의 긴 추론 출력을 끄고 최종 답변 생성에 집중합니다.
                enable_thinking=False,
            )
        else:
            text = prompt

        inputs = tokenizer(
            text,
            return_tensors="pt",
        )

        inputs = {
            key: value.to(model.device)
            for key, value in inputs.items()
        }

        input_tokens = inputs["input_ids"].shape[-1]
        logger.info(
            "LLM generate start | input_tokens=%d | max_new_tokens=%d",
            input_tokens,
            max_new_tokens,
        )
        started_at = time.perf_counter()
        try:
            outputs = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=LLM_INFERENCE_CONFIG.do_sample,
                num_beams=LLM_INFERENCE_CONFIG.num_beams,
                use_cache=LLM_INFERENCE_CONFIG.use_cache,
                pad_token_id=tokenizer.eos_token_id,
            )
        finally:
            logger.info(
                "LLM generate end | input_tokens=%d | max_new_tokens=%d | "
                "elapsed_seconds=%.3f",
                input_tokens,
                max_new_tokens,
                time.perf_counter() - started_at,
            )

        generated_ids = outputs[0][inputs["input_ids"].shape[-1]:]

        result = tokenizer.decode(
            generated_ids,
            skip_special_tokens=True,
        )

        return result.strip()
    
if __name__ == "__main__":
    loader = LLMLoader()
    model, tokenizer = loader.load()

    print(f"model type: {type(model)}")
    print(f"tokenizer type: {type(tokenizer)}")
