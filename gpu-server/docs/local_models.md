# 로컬 모델 다운로드와 선택

## 적용 범위

클라이언트와 GPU 서버 수정본을 함께 적용한다. 기존 모델 캐시, 환경변수, 입력/출력 데이터를 삭제할 필요는 없다.
새 모델 6개와 기존 Qwen 조합을 선택한다. 새 모델은 하나의 체크포인트를 음성 텍스트 요약·프레임 분석·최종 통합에 공유한다.
Whisper base/small/medium은 이 선택과 독립적이다. 외부 API 키는 기존대로 서버 환경변수에서만 읽는다.

| 선택 ID | 공식 체크포인트 | GPU 정밀도 | 가중치 다운로드 크기(GB) |
| --- | --- | --- | ---: |
| legacy-qwen | Qwen/Qwen3-8B + Qwen/Qwen2.5-VL-7B-Instruct | FP16, 단계 종료 시 해제 | 32.99 |
| qwen3.5-9b | Qwen/Qwen3.5-9B | NF4 4비트 | 19.33 |
| qwen3-vl-8b | Qwen/Qwen3-VL-8B-Instruct | NF4 4비트 | 17.55 |
| gemma4-12b | google/gemma-4-12B-it | NF4 4비트 | 23.95 |
| minicpm-v4.5 | openbmb/MiniCPM-V-4_5 | NF4 4비트, 시각 모듈 제외 | 17.41 |
| internvl3.5-8b | OpenGVLab/InternVL3_5-8B-HF | NF4 4비트 | 17.07 |
| glm4.6v-flash | zai-org/GLM-4.6V-Flash | NF4 4비트 | 20.61 |

2026-09-29 공식 Hugging Face 파일 메타데이터 조회 기준, GB는 10억 바이트이다.
전체 약 148.91 GB, 기존 조합 제외 약 115.91 GB이다. 패키지/환경/임시 파일 공간은 별도다.
원본 safetensors를 내려받아 실행할 때 4비트로 변환한다. 따라서 GPU 메모리 절감과 다운로드/디스크 크기는 다르다.
NF4는 양자화 설정이며 정확도나 4090 메모리 적합성을 보장하지 않는다. 입력 길이에 따라 OOM이 날 수 있다.

## GPU 서버 설치 (Python 3.10 이상)

서버를 중지하고 서버가 사용하는 Python 환경에서 실행한다. 기존 CUDA용 torch와 torchvision이 서로 호환되어야 한다.
현재 환경을 유지하려면 먼저 별도 환경에 설치해 검증한다. 다음 명령은 클라이언트 PC가 아닌 GPU 서버의 프로젝트 루트에서 실행한다.

```powershell
python -m pip install -r requirements-local.txt
python scripts/setup_minicpm.py
python scripts/download_models.py --all --plan
python scripts/download_models.py --all
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000 --workers 1
```

Windows에서 기존 `start_local_server.bat`를 사용해도 된다. 이 배치는 Conda `video_summarization` 환경을 사용하므로,
위 설치 명령도 같은 환경에서 실행해야 한다. `LLM_BACKEND=local`을 유지하는 것을 권장한다.
MiniCPM을 사용하지 않으면 `setup_minicpm.py`를 생략할 수 있다. 전용 환경은 서버의 CUDA PyTorch를 상속하고
Transformers 4.51.3/tokenizers/HF Hub를 별도로 설치한다. 다른 경로라면 `MINICPM_PYTHON`에 Python 실행 파일 경로를 설정한다.
주 서버의 Transformers 5.17.0과 MiniCPM의 공식 커스텀 코드용 4.51.3을 분리한다.
MiniCPM 로딩 시 공식 저장소에서 다운로드한 Python 코드가 실행된다. 나머지 신규 모델은 trust_remote_code=False이다.

**다운로드는 모델별로도 가능하다.**

```powershell
python scripts/download_models.py --list
python scripts/download_models.py --model qwen3.5-9b qwen3-vl-8b
```

접근 승인이 필요한 모델은 Hugging Face 모델 페이지의 사용 조건에 동의하고 서버의 `HF_TOKEN` 환경변수 또는
Hugging Face 로그인 캐시로 인증한다. Streamlit에는 토큰 입력란이 없다. 다운로드 인증과 분석 API 키는 별개다.
실제 추론은 로컬 파일만 읽고 가중치를 자동 다운로드하지 않는다.

## Streamlit 사용

1. 분석 방식 → **로컬 모델 서버**.
2. **로컬 분석 모델**에서 선택.
3. **모델 설치 상태**를 열고 **설치 상태 확인 / 새로고침**.
4. 미설치라면 GPU 서버 터미널에서 `python scripts/download_models.py --all`로 일괄 다운로드한다.
5. 완료 후 상태를 새로고침하고 영상을 분석한다. MiniCPM은 전용 실행 환경도 필요하다.

Streamlit에는 다운로드 버튼을 표시하지 않는다.

모델은 다운로드 전에도 목록에 표시된다. 미완료 모델은 분석 사전 검사와 서버 API 양쪽에서 거부한다.
다운로드 완료는 파일 준비 상태이며 GPU 추론 검증 완료를 뜻하지 않는다. 라이브러리 설치는 서버 터미널에서 수행한다.
분석 중에는 모델 선택/설치 상태 확인 버튼을 잠근다. CLI 다운로드를 중단한 경우 같은 명령을 다시 실행하면 이어받는다.

## 다운로드/실행 동작

- `models/hf_cache/<repo-name>` 기본 경로. `LOCAL_MODEL_DIR`로 서버와 다운로드 CLI의 루트를 변경할 수 있다.
- 첫 다운로드에서 정확한 commit SHA를 `download-revision.json`에 고정하고 재시도에 재사용한다.
- Hugging Face의 재개 기능을 사용한다. 완료 후 파일 존재/크기를 검사하여 `download-manifest.json`을 원자적으로 저장한다.
- 완료 manifest에 없는 새 모델은 준비됨으로 처리하지 않는다. 기존 Qwen 캐시는 config/tokenizer/샤드 존재 검사로 호환한다.
- 저장소와 모델 ID는 코드의 허용 목록으로 제한한다. 임의 경로/모델 저장소를 HTTP로 받지 않는다.
- 다운로드는 별도 단일 큐, 추론은 기존 단일 큐에서 실행한다. CLI와 서버 간 같은 모델 다운로드도 파일 잠금으로 겹치지 않는다.
- 매 STT/VLM/최종 요청에 `local_model`이 들어간다. HTTP 요청 처리 스레드에서는 현재 모델을 전환하지 않는다.
- 추론 큐에서 모델을 전환할 때 이전 모델을 해제한다. 새 단일 모델은 작업 간 재사용하며, 기존 FP16 조합은 단계별로 해제한다.
- 모델 실행이 실패해도 다른 로컬 모델이나 Claude로 자동 대체하지 않는다.
- `GET /models`는 파일 준비 상태/정밀도/commit/다운로드 상태, `POST /models/{id}/download`는 다운로드 접수이다.
- `GET /health`의 `local_model_selection`은 프로파일 선택 지원 여부다. 기존 llm_model/vlm_model 필드는 구형 기본 서비스 정보이며
  실제 선택 모델은 분석 로그의 local_model/model_checkpoints를 확인한다.
- 단일 GPU 모델 수명 관리를 위해 uvicorn `--workers 1`을 유지한다.

## 로그와 비교

클라이언트 metrics.json 설정에 `local_model`, `local_model_precision`, `analysis_model`, `vision_model`,
`model_checkpoints`(commit SHA)가 기록된다. CSV에는 모델 ID와 정밀도 열을 추가했다.
신규 로더는 기존 model_loads에 모델 ID/정밀도와 함께 loaded/reused/failed 및 시간을 기록한다.
MiniCPM 로딩 시간에는 별도 프로세스 시작·라이브러리 import·GPU 로딩이 포함된다. 재사용은 0초로 기록한다.
이 시간은 각 단계 총시간에 포함되므로 총시간에 다시 더하지 않는다.

## GPU 실행 확인

이 수정본 제작 환경에는 사용자 4090 서버 접속이나 GPU가 없어 실제 가중치 설치·GPU 추론 검증은 하지 않았다.
HTTP 계약·다운로드 재개/불완전 파일 거부·모델 전환/재사용·UI는 자동 테스트로 검증했다.
아래 명령은 GPU 서버에서 텍스트와 실제 프레임을 각 모델에 넣어 로딩/생성 성공 여부와 결과를 JSON으로 저장한다.
실행 가능성 점검용이며 한국어 뉴스 정확도 벤치마크는 아니다. 모델당 텍스트/이미지 각각 최대 128토큰이다.

```powershell
python scripts/check_local_models.py --all --image path/to/news-frame.jpg
```

결과는 `logs/local-model-check-<timestamp>.json`, MiniCPM worker 출력은 `logs/minicpm-worker.log`에 저장된다.
같은 GPU를 사용하는 분석 서버는 점검 동안 중지해서 메모리 경합을 피한다.
실패 시 서버 오류 로그와 해당 환경의 패키지/CUDA를 확인한다. 실제 성능 비교 시 같은 전사/프레임/프롬프트,
양자화 설정, 콜드/웜 로딩 조건을 고정하고 모델별 실행 가능성을 먼저 확인한다.

## 공식 구현 참고

각 체크포인트 모델 카드: https://huggingface.co/<위 표의 체크포인트 ID>
- https://huggingface.co/Qwen/Qwen3.5-9B
- https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct
- https://huggingface.co/google/gemma-4-12B-it
- https://huggingface.co/openbmb/MiniCPM-V-4_5
- https://huggingface.co/OpenGVLab/InternVL3_5-8B-HF
- https://huggingface.co/zai-org/GLM-4.6V-Flash
