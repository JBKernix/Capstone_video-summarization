conda activate capstone_vllm

$env:CUDA_VISIBLE_DEVICES="0"

vllm serve Qwen/Qwen2.5-VL-7B-Instruct \
    --host 0.0.0.0 \
    --port 8002 \
    --dtype auto \
    --gpu-memory-utilization 0.85 \
    --max-model-len 8192