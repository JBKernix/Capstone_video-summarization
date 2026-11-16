"""Private stdin/stdout JSON protocol; stdout is reserved for responses."""
import base64
import io
import json
import sys
from contextlib import redirect_stdout

def send(data):
    print(json.dumps(data, ensure_ascii=False), flush=True)

try:
    with redirect_stdout(sys.stderr):
        import torch
        from PIL import Image
        from transformers import AutoModel, AutoProcessor, AutoTokenizer, BitsAndBytesConfig
        path = sys.argv[1]
        tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True, local_files_only=True)
        processor = AutoProcessor.from_pretrained(path, trust_remote_code=True, local_files_only=True)
        model = AutoModel.from_pretrained(path, trust_remote_code=True, local_files_only=True,
            torch_dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="sdpa",
            quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True,
                llm_int8_skip_modules=["vpm", "resampler"])).eval()
        torch.cuda.synchronize()
    send({"ready": True})
except Exception as error:
    send({"error": f"MiniCPM 로딩 실패: {type(error).__name__}: {error}"})
    raise

for line in sys.stdin:
    try:
        request = json.loads(line)
        with redirect_stdout(sys.stderr), torch.inference_mode():
            content = []
            if request.get("image"):
                content.append(Image.open(io.BytesIO(base64.b64decode(request["image"]))).convert("RGB"))
            content.append(request["prompt"])
            if len(tokenizer.encode(request["prompt"])) > 14000:
                raise ValueError("MiniCPM 입력이 너무 깁니다 (텍스트 최대 14000 tokens).")
            text = model.chat(msgs=[{"role": "user", "content": content}], tokenizer=tokenizer,
                processor=processor, enable_thinking=False, stream=False, sampling=False,
                num_beams=1, repetition_penalty=1.0, max_new_tokens=request["max_new_tokens"])
        if not isinstance(text, str) or not text.strip():
            raise ValueError("모델이 빈 답변을 반환했습니다.")
        send({"text": text.strip()})
    except Exception as error:
        send({"error": f"MiniCPM 추론 실패: {type(error).__name__}: {error}"})
