# Models

Hugging Face 모델의 로드, 입력 전처리, 생성 호출과 GPU 메모리 해제를 담당하는 가장 낮은 계층입니다.

이 폴더는 프롬프트 작성이나 API 응답 형식을 알지 않습니다. 모델에 전달할 입력은 `services/`에서 준비하며, 로더는 모델 실행에 필요한 최소 기능만 제공합니다.

## 파일 구성

| 파일 | 모델 | 역할 |
| --- | --- | --- |
| `llm_loader.py` | Qwen3-8B | 토크나이저와 Causal LM 로드, 텍스트 생성 |
| `claude_llm_loader.py` | Claude (Anthropic API) | Anthropic API 호출을 통한 텍스트 생성, `llm_loader.py`와 동일한 인터페이스 |
| `vlm_loader.py` | Qwen2.5-VL-7B-Instruct | 프로세서와 VLM 로드, 이미지 기반 텍스트 생성 |
| `multimodal_loader.py` | Qwen3.5-9B, Qwen3-VL-8B, Gemma4-12B, InternVL3.5-8B, GLM-4.6V-Flash | 4비트 양자화된 단일 체크포인트를 텍스트/이미지 단계에 공유하는 공용 로더 |
| `minicpm_loader.py` | MiniCPM-V 4.5 | `multimodal_loader.py`를 상속, 서버와 다른 Transformers 버전이 필요해 서브프로세스로 격리 실행 |
| `hf_cache/` | 로컬 모델 파일 | Git에서 제외되는 모델 설정 및 가중치 저장소 |

모델 선택 ID, 저장소 경로, 정밀도(precision)는 로더가 아니라 `configs/local_models.py`의 `PROFILES`에서 관리합니다. 설치·다운로드·검증 절차는 [로컬 모델 가이드](../docs/local_models.md)를 참고하세요.

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

토큰화 후 입력 토큰 수가 `LLM_INFERENCE_CONFIG.max_input_tokens`(기본 16000)를 초과하면 `generate()`는 모델 호출 전에 `ValueError`를 발생시킵니다. 이 상한은 24GB급 GPU에서 입력 토큰 24054개로 CUDA OOM이 발생한 사례를 반영해 정상 운영 범위(약 9천~1만4천 토큰)보다 여유를 두고 설정되어 있습니다.

## VLM 입력 처리

`VLMLoader.describe_image()`는 문자열 경로, `Path`, PIL 이미지를 받을 수 있습니다.

1. 이미지를 RGB PIL 이미지로 변환
2. 이미지와 텍스트를 Qwen 채팅 메시지로 구성
3. 프로세서로 텍스트와 이미지 텐서 생성
4. 모델 파라미터가 위치한 디바이스로 입력 이동
5. 생성된 토큰만 디코딩

이미지 파일의 존재 여부와 읽기 오류는 상위 `VLMService`에서도 한 번 더 검증합니다.

## GPU 메모리 부족(OOM) 처리

`LLMLoader.generate()`와 `VLMLoader.describe_image()`는 모델 호출을 `torch.OutOfMemoryError`에 대해 감싸고 있습니다. OOM이 발생하면 `torch.cuda.empty_cache()`로 캐시를 비운 뒤, 입력 토큰 수를 포함한 안내 메시지와 함께 `ValueError`로 다시 발생시킵니다. 이렇게 변환된 `ValueError`는 `app/inference_jobs.py`가 잡아 작업 상태의 `message`에 그대로 노출합니다.

## 신규 로컬 멀티모달 모델 (MultimodalLoader)

`multimodal_loader.py`는 `legacy-qwen`(Qwen3-8B + Qwen2.5-VL) 조합 대신 선택할 수 있는 신규 6개 프로필 중 MiniCPM을 제외한 5개(Qwen3.5, Qwen3-VL, Gemma4, InternVL3.5, GLM-4.6V)가 공통으로 사용하는 로더입니다. `LLMLoader`/`VLMLoader`처럼 모델을 두 개 따로 두지 않고, 텍스트 전용 요약과 이미지 설명 모두에 같은 4비트(NF4) 체크포인트 하나를 `load_text()`/`load_vision()`으로 재사용합니다.

- 모델 클래스는 `configs/local_models.py`의 `ModelProfile.architecture`(예: `Qwen3VLForConditionalGeneration`)로 `transformers`에서 동적으로 조회합니다. 설치된 Transformers 버전에 해당 클래스가 없으면 즉시 `RuntimeError`를 발생시킵니다.
- `BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", ...)`로 로딩 시점에 4비트 양자화하며, `trust_remote_code=False`로 고정되어 있습니다(공식 저장소의 커스텀 코드를 실행하지 않음).
- 입력 토큰이 16384개를 넘으면 `LLMLoader`의 `max_input_tokens`와 별개로 자체 `ValueError`를 발생시킵니다. `torch.OutOfMemoryError`는 별도로 잡지 않으므로, `LLMLoader`/`VLMLoader`와 달리 CUDA OOM이 사용자 메시지로 변환되지 않고 그대로 전파됩니다.
- `gemma4-12b`는 `processor.parse_response()`로 응답을 파싱하고, 그 외 모델은 `<think>...</think>` 블록(비활성화한 thinking 모드가 완료된 채 출력된 경우)을 제거한 뒤 빈 응답이면 `ValueError`를 발생시킵니다.

## MiniCPM 서브프로세스 격리 (MiniCPMLoader)

MiniCPM-V 4.5는 공식 커스텀 코드가 서버의 Transformers 5.x가 아닌 4.51.3을 요구해, `MultimodalLoader`를 상속하되 실제 모델 로딩과 추론은 별도 가상환경(`.venv-minicpm/`, `scripts/setup_minicpm.py`로 생성)의 `scripts/minicpm_worker.py` 서브프로세스에서 수행합니다.

```text
MiniCPMLoader._load()
  -> 이미 실행 중인 worker가 있으면 재사용
  -> .venv-minicpm의 Python으로 minicpm_worker.py를 subprocess로 실행
     (HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1, ANTHROPIC_API_KEY/HF_TOKEN 환경변수는 전달하지 않음)
  -> 준비 완료 응답을 stdin/stdout JSON 한 줄 프로토콜로 대기
```

`_generate()`는 프롬프트(및 있으면 PNG로 인코딩한 이미지)를 JSON 한 줄로 worker에 보내고 결과 텍스트를 받습니다. worker 응답이 없거나 타임아웃되면 `ValueError`로 변환하고 프로세스를 종료·재시작할 수 있도록 `unload()`합니다. worker 표준 에러는 `logs/minicpm-worker.log`에 남습니다. `MINICPM_PYTHON` 환경변수로 가상환경 Python 경로를 바꿀 수 있습니다.

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
python scripts\download_models.py --all
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

위 절차는 `llm_loader.py`/`vlm_loader.py`처럼 고정된 단일 모델 조합을 교체할 때 기준입니다. `multimodal_loader.py`/`minicpm_loader.py`가 다루는 신규 모델 카탈로그에 모델을 추가/교체할 때는 대신 `configs/local_models.py`의 `PROFILES`에 `ModelProfile`을 등록하고 [로컬 모델 가이드](../docs/local_models.md)의 절차를 따릅니다.

## 분석 LLM 백엔드 전환 (로컬 <-> Claude API)

`services/llm_service.py`의 `_build_loader()`가 환경변수 `LLM_BACKEND`를 읽어 로더를 선택합니다.

| 환경변수 | 기본값 | 설명 |
| --- | --- | --- |
| `LLM_BACKEND` | `local` | `claude`로 설정하면 `ClaudeLLMLoader`(Anthropic API)를 사용 |
| `ANTHROPIC_API_KEY` | (없음) | `claude` 백엔드 사용 시 필수. Anthropic API 키 |
| `CLAUDE_LLM_MODEL` | `claude-haiku-4-5` | `claude` 백엔드에서 사용할 모델 ID |

`ClaudeLLMLoader`는 `llm_loader.py`와 동일하게 `load()` / `unload()` / `generate(prompt, max_new_tokens)`를 제공하므로 `LLMService`와 `FinalService`는 백엔드가 로컬인지 API인지 알 필요가 없습니다. 다만 API 백엔드에는 GPU 자원이 없어 `unload()`는 클라이언트 참조만 제거하는 no-op이며, `KEEP_LLM_LOADED` 설정과 무관하게 동작합니다. Claude API 오류(인증 실패, 요청 한도 초과, 연결 실패, 안전 거부)는 로컬 모델의 CUDA OOM과 동일하게 `ValueError`로 변환되어 작업 상태의 `message`에 노출됩니다.

VLM(`vlm_loader.py`)은 이 전환과 무관하게 항상 로컬 모델을 사용합니다.
