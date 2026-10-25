# 분석 방식과 Whisper 설정

두 선택은 서로 독립적입니다. **분석 방식**은 LLM/VLM 실행 위치를, **간단·기본·상세**는
Whisper 음성 인식 모델 크기만 정합니다. 모든 프리셋에서 프레임 추출·OCR·화면 요약·최종 통합을 수행합니다.

| 처리 | 로컬 모델 서버 | Claude API (Haiku) |
| --- | --- | --- |
| 음성 추출·Whisper·OCR | 앱 실행 PC | 앱 실행 PC |
| 음성 요약·중요 구간 | 자가 운영 서버의 선택한 로컬 모델 | Anthropic API, `claude-haiku-4-5` |
| 프레임 분석 | 선택한 로컬 모델 (기존 조합은 Qwen2.5-VL) | Anthropic API, `claude-haiku-4-5` |
| 최종 통합 | 자가 운영 서버의 선택한 로컬 모델 | Anthropic API, `claude-haiku-4-5` |
| API 키 | 불필요 | 분석 서버의 `ANTHROPIC_API_KEY` 환경변수 |

로컬 모드는 기존 `gpu-server` 브랜치의 자체 모델 서버를 사용합니다. 같은 PC 또는
사용자가 운영하는 별도 GPU PC에서 실행할 수 있습니다. 새 서버는 `/models`에서 선택한 모델의 다운로드 완료 여부를 확인합니다.
구버전 서버는 기존 Qwen 조합만 지원하며 `/health`에서 local 백엔드인지 확인합니다.
API 모드도 지정한 분석 서버의 `/claude/messages` 경로를 사용합니다. 서버가 자기 환경변수의
키로 Anthropic을 호출합니다. 원본 동영상·오디오 대신 STT 텍스트,
OCR 텍스트와 선택된 JPG 프레임을 Anthropic으로 전송합니다. API 사용 요금이 발생합니다.

## 앱 화면 (React · Streamlit 공통)

1. 영상 업로드 화면의 **분석 방식**에서 로컬 모델 서버 또는 Claude API를 선택합니다.
   React에서는 개발자 화면(`/dev/upload`)에서만 고를 수 있습니다. 사용자 화면에서 시작한 분석은
   개발자가 분석 설정에서 **사용자 화면에 적용**을 눌러 저장한 방식(`runs/user_defaults.json`, 지정 전에는 로컬 기본 모델)을 씁니다.
2. 서버 주소는 `modules/llm/__init__.py`의 `GPU_SERVER_URL` 설정을 자동으로 사용합니다.
   서버 주소와 API 키 입력란은 화면에 표시하지 않습니다. API 키는 서버 컴퓨터의 환경변수를 사용합니다.
3. **Whisper 음성 인식**에서 아래 모델을 선택합니다.

| 표시 | 내부 옵션 | Whisper 모델 |
| --- | --- | --- |
| 간단 · small | `simple` | `small` |
| 기본 · medium | `standard` | `medium` |
| 상세 · large | `detailed` | `large` |

Whisper 선택은 요약 길이, 이미지 처리 범위, Claude 모델, 출력 토큰 예산을 바꾸지 않습니다.
인식 결과가 바뀌면 내용과 중요 구간·프레임 수는 달라질 수 있습니다.
기존 서버의 생성 프리셋에는 항상 `standard`를 전달합니다.
수동 `--skip-ocr` / `--skip-vlm` 옵션은 유지되며 Whisper 프리셋과 별개입니다.

API 키는 **FastAPI 분석 서버 프로세스의 `ANTHROPIC_API_KEY` 환경변수**에서만 읽습니다.
앱(React 앱 서버·Streamlit)의 세션·secrets·화면 입력에서는 읽지 않으며, 파이프라인 자식 프로세스에도 넘기지 않습니다.
이전 화면에 입력했던 세션 키는 삭제합니다. 브라우저·명령줄·JSON 지표·CSV·로그에는 키를 기록하지 않습니다.
분석 시작 전 `/health`의 `claude_api_proxy`와 `claude_api_configured`를 확인합니다.
이 응답에는 지원 여부·환경변수 설정 여부만 포함되며 키 값은 포함하지 않습니다.
설정 여부는 키의 유효성이나 API 사용 권한을 보증하지 않습니다.
API 오류가 나도 로컬로 자동 전환하지 않습니다. 반대 방향의 자동 전환도 없습니다.

## 공통 분석 서버 준비

같이 제공하는 `gpu-server/` 수정본을 기존 서버 환경에 적용하세요. 기존 모델 캐시는 재사용할 수 있습니다. 신규 로컬 모델은 GPU 서버의 `requirements-local.txt` 설치가 필요합니다. API 모드도 서버 수정본이 필요합니다.
서버의 `requirements.txt` 의존성을 설치한 뒤 기존 `ANTHROPIC_API_KEY` 환경변수가
전달되는 터미널/서비스에서 서버를 재시작하세요. 앱 PC에 키를 복사할 필요는 없습니다.
두 모드를 함께 쓰려면 다음과 같이 로컬 모델 경로를 설정합니다.

```powershell
$env:LLM_BACKEND = "local"
python -m uvicorn app.server:app --host 0.0.0.0 --port 8000
```

기존 Windows 배치 환경에서는 `start_local_server.bat`도 사용할 수 있습니다.
GPU 서버의 `/health`에 `llm_backend: local`, `vlm_backend: local`이 표시되어야 합니다.
선택 기능을 지원하는 새 서버에서는 명시적 로컬 모델 요청을 독립적인 로컬 로더로 처리합니다. 구버전 서버는 `LLM_BACKEND=claude`일 때 로컬 사전 검사에서 중단됩니다.
`/claude/messages` 경로는 `LLM_BACKEND`와 독립적으로 서버 환경변수의 키를 사용합니다.
`start_local_server.bat`도 해당 키를 보존하므로 한 서버에서 두 모드를 선택할 수 있습니다.

## CLI

로컬 모델 서버:

```powershell
python scripts/run_pipeline.py --video sample.mp4 --analysis-backend local --local-server-url http://127.0.0.1:8000 --summary-level standard
```

Claude API: 키가 설정된 분석 서버를 먼저 실행한 뒤 클라이언트에서 실행합니다.
`--server-url`은 `--local-server-url`의 별칭이며 두 모드에 공통으로 적용됩니다.
API 키를 명령줄 인자로 받는 옵션은 제공하지 않습니다.

```powershell
python scripts/run_pipeline.py --video sample.mp4 --analysis-backend claude --server-url http://127.0.0.1:8000 --summary-level simple
```

`--claude-model`로 API 모델 이름을 바꿀 수 있습니다. 기본값은 기존 서버의 Haiku 설정과
같은 `claude-haiku-4-5`입니다. `--stt-model-size`는 Whisper 프리셋을 덮어쓰는 명시적 옵션입니다.
`run_llm_summary.py`, `run_vlm_summary.py`, `run_final_summary.py`도 동일한 분석 방식 인자를 받습니다.
단독 요약 명령의 `--summary-level`은 호환용이며 요약 정책을 변경하지 않습니다.

## 이력 및 입력 처리

실행 이력과 CSV에 `analysis_backend`, `analysis_model`, `preset_semantics`가 기록됩니다.
새 프리셋은 `whisper_only_v1`로 표시하며, 이전 버전 기록에는 기존 의미를 안내합니다.
Claude의 응답 usage에서 입력·출력 토큰과 완료 API 응답 횟수도 누적합니다.
이 값은 성공적으로 읽은 응답 기준이며, 실패한 요청의 과금 전체를 보장하는 청구 내역은 아닙니다.

긴 STT는 기존 서버와 같은 12,000자 기준으로 구간을 묶어 부분 요약 후 통합합니다.
선정된 중요 구간의 시간은 원본 STT에서 가져오며 모델이 생성한 시간을 그대로 믿지 않습니다.
프레임은 기존 클라이언트의 최대 8장 배치를 재사용하고 Claude 전송 전에 긴 변을 최대
1,280픽셀로 줄입니다. 중요 음성 구간이 없으면 전체 영상에서 지정한 간격/장면 전환 방식으로
프레임을 추출하여 화면 분석을 계속합니다.

## 검증 범위

서버 환경변수 사용·API 요청·오류·응답·키 비전달은 모의 HTTP 응답으로 검증합니다. 실제 과금 요청은 테스트에서
발생하지 않습니다. 실제 Haiku 사용 권한·키·요금 및 로컬 GPU의 모델 추론 성능은 실행 환경에서
확인해야 합니다.

구현 시 참고한 공식 문서:
- https://platform.claude.com/docs/en/models/overview
- https://platform.claude.com/docs/en/build-with-claude/vision
- https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview

## 로컬 모델 선택과 다운로드

로컬 모드의 **로컬 분석 모델** 선택은 모든 요약 단계에 전달됩니다. 기본은 기존 Qwen 조합입니다.
Qwen3.5 9B, Qwen3-VL 8B, Gemma 4 12B, MiniCPM-V 4.5, InternVL3.5 8B, GLM-4.6V-Flash를 추가했습니다.
GPU 서버에서 `python scripts/download_models.py --all`로 가중치를 미리 일괄 다운로드합니다.
앱 업로드 화면의 **모델 설치 상태**에서는 설치 완료 여부를 확인합니다(React는 개발자 화면에서만 표시하며, 개발자 전용 앱 API `GET /api/models`가 추론 서버 `/models`를 대신 조회). 화면에 다운로드 버튼은 제공하지 않습니다.
라이브러리 설치 및 전체 다운로드 명령은 제공된 `gpu-server/docs/local_models.md`를 참고하세요.
전체 가중치는 약 149 GB이며 ZIP에는 포함되지 않습니다. 4비트 변환은 GPU에 로딩할 때 수행합니다.
MiniCPM은 `python scripts/setup_minicpm.py`로 전용 실행 환경을 설치해야 합니다.
CLI에서는 `--local-model qwen3.5-9b`처럼 지정합니다. Claude 모드에서는 이 선택을 사용하지 않습니다.
실행 로그에 선택 ID, 정밀도, 체크포인트 commit을 저장하며 CSV에 모델 ID와 정밀도 열을 제공합니다.
GPU 모델 실행은 서버에서 별도 확인해야 합니다. 다운로드 완료와 실제 추론 검증 완료는 서로 다릅니다.
