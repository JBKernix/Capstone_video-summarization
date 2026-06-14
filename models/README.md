# Models

Hugging Face 모델의 로드, 입력 전처리, 생성 호출과 GPU 메모리 해제를 담당하는 가장 낮은 계층입니다.

이 폴더는 프롬프트 작성이나 API 응답 형식을 알지 않습니다. 모델에 전달할 입력은 `services/`에서 준비하며, 로더는 모델 실행에 필요한 최소 기능만 제공합니다.

## 파일 구성

| 파일 | 모델 | 역할 |
| --- | --- | --- |
| `llm_loader.py` | Qwen3-8B | 토크나이저와 Causal LM 로드, 텍스트 생성 |
| `vlm_loader.py` | Qwen2.5-VL-7B-Instruct | 프로세서와 VLM 로드, 이미지 기반 텍스트 생성 |
| `hf_cache/` | 로컬 모델 파일 | Git에서 제외되는 모델 설정 및 가중치 저장소 |

## 설정 객체

각 로더는 dataclass 기반 설정을 받습니다.

```python
LLMConfig(
    model_path="models/hf_cache/Qwen3-8B",
    device="cuda",
    torch_dtype="float16",
    local_files_only=True,
)
```

```python
VLMConfig(
    model_path="models/hf_cache/Qwen2.5-VL-7B-Instruct",
    device="cuda",
    torch_dtype="float16",
    local_files_only=True,
)
```

지원 dtype은 `float16`, `bfloat16`, `float32`입니다. 기본 설정은 CUDA와 `float16`입니다.

## 지연 로딩

로더 객체를 생성해도 모델은 즉시 GPU에 올라가지 않습니다. 첫 `generate()` 또는 `describe_image()` 호출에서 `load()`가 실행됩니다.

```text
로더 생성
  -> model/tokenizer/processor = None
첫 추론
  -> 로컬 경로와 CUDA 확인
  -> 모델 로드
후속 추론
  -> 이미 로드된 모델 재사용
```

모델 경로가 없거나 CUDA를 사용할 수 없으면 추론 전에 명확한 예외를 발생시킵니다.

## LLM 입력 처리

`LLMLoader.generate()`는 사용자 프롬프트를 다음 시스템 메시지와 함께 채팅 템플릿으로 변환합니다.

```text
당신은 영상 내용을 정확하고 간결하게 요약하는 AI입니다.
```

Qwen3의 긴 내부 추론 출력을 줄이기 위해 채팅 템플릿에서 `enable_thinking=False`를 사용합니다. 생성 결과에서는 입력 토큰을 제외하고 새로 생성된 토큰만 디코딩합니다.

## VLM 입력 처리

`VLMLoader.describe_image()`는 문자열 경로, `Path`, PIL 이미지를 받을 수 있습니다.

1. 이미지를 RGB PIL 이미지로 변환
2. 이미지와 텍스트를 Qwen 채팅 메시지로 구성
3. 프로세서로 텍스트와 이미지 텐서 생성
4. 모델 파라미터가 위치한 디바이스로 입력 이동
5. 생성된 토큰만 디코딩

이미지 파일의 존재 여부와 읽기 오류는 상위 `VLMService`에서도 한 번 더 검증합니다.

## GPU 메모리 해제

두 로더의 `unload()`는 다음 작업을 수행합니다.

```python
self.model = None
self.tokenizer_or_processor = None
gc.collect()
torch.cuda.empty_cache()
torch.cuda.ipc_collect()
```

`empty_cache()`는 아직 참조 중인 텐서 메모리를 강제로 해제하지 못합니다. 따라서 모델과 프로세서 참조를 먼저 제거해야 합니다. 상위 서비스는 공용 lock을 획득한 상태에서 `unload()`를 호출합니다.

## 로컬 모델 파일

`models/hf_cache/`는 `.gitignore`에 의해 GitHub에 업로드되지 않습니다. 저장소를 새로 clone한 뒤 다음 명령으로 모델을 준비합니다.

```powershell
python scripts\download_models.py
```

`local_files_only=True`이므로 모델이 다운로드되지 않은 상태에서는 서버가 자동으로 네트워크에서 모델을 가져오지 않습니다.

## 모델 교체 시 확인 사항

1. `model_path`와 다운로드 스크립트 수정
2. Transformers 모델 클래스가 새 모델과 호환되는지 확인
3. 채팅 템플릿 지원 여부 확인
4. dtype과 GPU VRAM 요구량 확인
5. 생성 결과에서 입력 토큰을 제거하는 방식 확인
6. VLM이면 processor 입력 형식과 이미지 토큰 규칙 확인

모델별 프롬프트와 출력 파싱은 로더가 아니라 `services/`에서 변경합니다.
