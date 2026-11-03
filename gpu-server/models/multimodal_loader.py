"""A single resident 4-bit checkpoint shared by text and image stages."""
import gc
import os
import re
from types import SimpleNamespace
from app.model_load_metrics import measure_model_load
from configs.local_models import get_profile, repo_path, require_downloaded

# "sdpa"로 지정하면 프로필의 최적화 attention 대신 기본 SDPA와 그에 맞는 입력 상한으로 되돌립니다.
ATTENTION_OVERRIDE_ENV = "LOCAL_MODEL_ATTENTION"

class MultimodalLoader:
    def __init__(self, model_id):
        self.profile = get_profile(model_id)
        self.config = SimpleNamespace(model_path=str(repo_path(self.profile.repos[0])))
        self.model = None
        self.processor = None

    @property
    def attn_implementation(self):
        override = os.environ.get(ATTENTION_OVERRIDE_ENV, "").strip()
        return "sdpa" if override == "sdpa" else self.profile.attn_implementation

    @property
    def max_input_tokens(self):
        if self.attn_implementation == "sdpa" and self.profile.sdpa_max_input_tokens:
            return self.profile.sdpa_max_input_tokens
        return self.profile.max_input_tokens

    def count_prompt_tokens(self, prompt):
        """텍스트 프롬프트가 generate에서 차지할 입력 토큰 수입니다(_generate와 같은 chat template)."""
        processor = self.processor if self.processor is not None else self.load_text()[1]
        inputs = processor.apply_chat_template(
            [{"role": "user", "content": [{"type": "text", "text": prompt}]}], tokenize=True,
            add_generation_prompt=True, enable_thinking=False, return_dict=True, return_tensors="pt")
        return int(inputs["input_ids"].shape[-1])

    @measure_model_load("llm", "processor")
    def load_text(self):
        return self._load()

    @measure_model_load("vlm", "processor")
    def load_vision(self):
        return self._load()

    def _load(self):
        if self.model is not None and self.processor is not None:
            return self.model, self.processor
        import torch
        import transformers
        from transformers import AutoProcessor, BitsAndBytesConfig
        require_downloaded(self.profile.id)
        if not torch.cuda.is_available():
            raise RuntimeError("로컬 모델 실행에는 CUDA GPU가 필요합니다.")
        cls = getattr(transformers, self.profile.architecture, None)
        if cls is None:
            raise RuntimeError(f"{self.profile.label} 로더가 없습니다. requirements-local.txt를 설치하세요.")
        attn_implementation = self.attn_implementation
        if attn_implementation != "sdpa":
            from models.attention import register
            register()
        try:
            processor = AutoProcessor.from_pretrained(self.config.model_path, local_files_only=True, trust_remote_code=False)
            model = cls.from_pretrained(
                self.config.model_path, local_files_only=True, trust_remote_code=False,
                dtype=torch.bfloat16, device_map={"": 0}, attn_implementation=attn_implementation,
                quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                    bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True))
            model.eval()
            torch.cuda.synchronize()
            self.model, self.processor = model, processor
            return model, processor
        except Exception:
            self.unload()
            raise

    def unload(self):
        self.model = None
        self.processor = None
        gc.collect()
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def generate(self, prompt, max_new_tokens=1024):
        model, processor = self.load_text()
        return self._generate(model, processor, prompt, None, max_new_tokens)

    def describe_image(self, image, prompt, max_new_tokens=512):
        from PIL import Image
        if not isinstance(image, Image.Image):
            with Image.open(image) as source:
                image = source.convert("RGB")
        model, processor = self.load_vision()
        return self._generate(model, processor, prompt, image.convert("RGB"), max_new_tokens)

    def _generate(self, model, processor, prompt, image, max_new_tokens):
        import torch
        content = [] if image is None else [{"type": "image", "image": image}]
        content.append({"type": "text", "text": prompt})
        with torch.inference_mode():
            inputs = processor.apply_chat_template(
                [{"role": "user", "content": content}], tokenize=True,
                add_generation_prompt=True, enable_thinking=False,
                return_dict=True, return_tensors="pt").to(model.device)
            if self.profile.id == "glm4.6v-flash":
                inputs.pop("token_type_ids", None)
            input_length = inputs["input_ids"].shape[-1]
            limit = self.max_input_tokens
            if input_length > limit:
                raise ValueError(f"입력이 너무 깁니다: {input_length} tokens ({self.profile.label} 최대 {limit}). "
                                 "더 짧은 영상으로 실행하세요.")
            try:
                result = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False, num_beams=1, use_cache=True)
            except torch.OutOfMemoryError as error:
                del inputs
                torch.cuda.empty_cache()
                raise ValueError(f"GPU 메모리가 부족합니다 (입력 토큰 {input_length}개). "
                                 f"{ATTENTION_OVERRIDE_ENV} 설정과 입력 상한을 확인하세요.") from error
            if self.profile.id == "gemma4-12b":
                raw = processor.decode(result[0][input_length:], skip_special_tokens=False)
                parsed = processor.parse_response(raw, prefix=inputs["input_ids"][0])
                text = parsed.get("content", "")
            else:
                text = processor.batch_decode(result[:, input_length:], skip_special_tokens=True)[0]
        # Non-thinking is requested above; remove a completed reasoning block if emitted.
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if not text or "<think>" in text:
            raise ValueError("모델이 최종 답변을 생성하지 못했습니다. 출력 한도/모델 호환성을 확인하세요.")
        return text
