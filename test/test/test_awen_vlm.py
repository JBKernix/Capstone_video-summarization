import torch
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info

MODEL_NAME = "Qwen/Qwen2.5-VL-7B-Instruct"

model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    MODEL_NAME,
    torch_dtype = torch.bfloat16,
    device_map = "auto",
)

processor = AutoProcessor.from_pretrained(
    MODEL_NAME,
    min_pixels = 256*28*28,
    max_pixels = 1024*28*28,
)

image_path = "test.jpg"

messages = [
    {
        "role": "user",
        "content": [{"type": "image", "image": image_path},
                    {"type": "text", "text": "이 이미지를 한국어로 간단히 설명해줘."}]
    }
]

text = processor.apply_chat_template(
    messages,
    tokenize = False,
    add_generatation_prompt = True,
)

image_inputs, video_inputs = process_vision_info(messages)

inputs = processor(
    text=[text],
    images = image_inputs,
    videos = video_inputs,
    padding = True,
    return_tensors = "pt",
).to(model.device)

with torch.no_grad():generated_ids = model.generate(**inputs, max_new_tokens = 256)

generated_ids_trimmed = [out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)]

output_text = processor.batch_decode(
    generated_ids_trimmed, skip_special_tokens = True, clean_up_tokenization_spaces = False,
)

print(output_text[0])
