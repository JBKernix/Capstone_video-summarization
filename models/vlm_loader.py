from __future__ import annotations

import gc
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

from configs.inference_config import VLM_INFERENCE_CONFIG


PROJECT_ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger(__name__)


@dataclass
class VLMConfig:
    model_path: str = str(PROJECT_ROOT / "models" / "hf_cache" / "Qwen2.5-VL-7B-Instruct")
    device: str = "cuda"
    torch_dtype: str = "float16"
    trust_remote_code: bool = True
    local_files_only: bool = True


class VLMLoader:
    def __init__(self, config: Optional[VLMConfig] = None):
        self.config = config or VLMConfig()
        self.processor = None
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
        if self.model is not None and self.processor is not None:
            return self.model, self.processor

        if self.config.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA를 사용할 수 없습니다.")

        model_path = Path(self.config.model_path)

        if not model_path.exists():
            raise FileNotFoundError(f"로컬 모델 경로를 찾을 수 없습니다: {model_path}")

        dtype = self._get_torch_dtype()

        print(f"[VLM 로드 시작] {model_path}")

        self.processor = AutoProcessor.from_pretrained(
            str(model_path),
            trust_remote_code=self.config.trust_remote_code,
            local_files_only=self.config.local_files_only,
        )

        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            str(model_path),
            torch_dtype=dtype,
            device_map="auto" if self.config.device == "cuda" else None,
            trust_remote_code=self.config.trust_remote_code,
            local_files_only=self.config.local_files_only,
        )

        if self.config.device == "cpu":
            self.model = self.model.to("cpu")

        self.model.eval()

        print("[VLM 로드 완료]")

        return self.model, self.processor

    def unload(self) -> None:
        """모델 참조를 해제하고 사용하지 않는 CUDA 메모리를 반환합니다."""
        self.model = None
        self.processor = None
        gc.collect()

        if self.config.device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    
    def _load_image(self, image: Union[str, Path, Image.Image]) -> Image.Image:
        if isinstance(image, Image.Image):
            return image.convert("RGB")

        image_path = Path(image)

        if not image_path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        return Image.open(image_path).convert("RGB")

    @torch.inference_mode()
    def describe_image(
        self,
        image: Union[str, Path, Image.Image],
        prompt: str,
        max_new_tokens: int = VLM_INFERENCE_CONFIG.default_max_new_tokens,
    ) -> str:
        model, processor = self.load()
        pil_image = self._load_image(image)

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "image": pil_image,
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ]

        text = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = processor(
            text=[text],
            images=[pil_image],
            return_tensors="pt",
        )

        device = next(model.parameters()).device

        inputs = {
            key: value.to(device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }

        input_tokens = inputs["input_ids"].shape[-1]
        logger.info(
            "VLM generate start | input_tokens=%d | max_new_tokens=%d | "
            "image_size=%dx%d",
            input_tokens,
            max_new_tokens,
            pil_image.width,
            pil_image.height,
        )
        started_at = time.perf_counter()
        try:
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=VLM_INFERENCE_CONFIG.do_sample,
                num_beams=VLM_INFERENCE_CONFIG.num_beams,
                use_cache=VLM_INFERENCE_CONFIG.use_cache,
            )
        finally:
            logger.info(
                "VLM generate end | input_tokens=%d | max_new_tokens=%d | "
                "image_size=%dx%d | elapsed_seconds=%.3f",
                input_tokens,
                max_new_tokens,
                pil_image.width,
                pil_image.height,
                time.perf_counter() - started_at,
            )

        generated_ids_trimmed = generated_ids[:, inputs["input_ids"].shape[-1]:]

        output_text = processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]

        return output_text.strip()
