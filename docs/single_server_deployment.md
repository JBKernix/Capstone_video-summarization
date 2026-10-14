# 단일 서버 운영 및 Cloudflare 외부 접속 가이드

GPU 서버 PC 한 대에서 업로드 수신부터 STT·OCR·LLM/VLM·최종 요약 저장까지 모두 처리하고,
다른 PC·스마트폰은 웹브라우저로만 접속하는 구성입니다. 외부 PC에서는 어떤 모델도 실행하지 않습니다.

```text
외부 브라우저 ──HTTPS──> Cloudflare ──(outbound 터널)──> cloudflared (서버 PC)
                                                         │
                                         Streamlit 127.0.0.1:8501   (이 브랜치, C:\capstone)
                                           │  업로드 저장, run_pipeline.py 실행(FFmpeg·Whisper·EasyOCR)
                                           ▼
                                         FastAPI   127.0.0.1:8000   (gpu-server 브랜치, C:\Summarization)
                                             LLM/VLM 추론 (단일 작업 큐)
```

- 외부에 공개되는 것은 Streamlit 하나뿐입니다. FastAPI는 127.0.0.1에만 바인딩하고 터널에 연결하지 않습니다.
- cloudflared는 서버에서 Cloudflare로 나가는(outbound) 연결만 사용하므로 라우터 포트포워딩이 필요 없습니다.
- `gpu-server` 브랜치 코드는 수정하지 않았습니다. 기존처럼 별도 폴더(기본 `C:\Summarization`)에 두고 `start_all`이 그 폴더에서 uvicorn을 `--host 127.0.0.1`로 실행합니다.

## 1. 서버 PC 실행

### 통합 실행 (권장)

```bat
start_all.bat            :: FastAPI + Streamlit (로컬 전용)
start_all.bat -Tunnel    :: + Cloudflare Tunnel (외부 접속)
stop_all.bat             :: start_all이 시작한 프로세스만 종료
stop_all.bat -TunnelOnly :: 터널만 종료 (외부 접속 차단, 서버는 유지)
```

`start_all`의 동작 순서

1. Python 환경·gpu-server 폴더·ffmpeg·디스크·GPU 확인 (설치/다운로드는 하지 않음)
2. FastAPI 시작 (`127.0.0.1:8000`, `--workers 1`) — 이미 8000에서 `/health`가 응답하면 그대로 재사용
3. `/health` 응답 대기 (기본 180초)
4. Streamlit 시작 (`127.0.0.1:8501`, `GPU_SERVER_URL=http://127.0.0.1:8000`) — 이미 실행 중이면 재사용
5. `/_stcore/health` 응답 대기
6. `-Tunnel`이면 비밀번호 설정을 확인한 뒤 `start_tunnel.ps1 -Detach` 실행
7. 로컬/외부 접속 주소와 로그 위치 출력

이미 실행 중인 서버를 종료하지 않습니다. 기존 창이 `0.0.0.0`에 바인딩되어 있으면 경고만 출력하므로,
FastAPI를 외부와 완전히 분리하려면 기존 서버 창을 직접 닫고 `start_all.bat`을 다시 실행하세요.

실행 로그: `logs\launcher\*.log`(시작 스크립트), `C:\Summarization\logs\server.log`(FastAPI),
`logs\client.log`(Streamlit 접속 기록), `runs\history\<run_id>\`(실행별 파이프라인 로그·지표).

### 환경변수 (선택)

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `STREAMLIT_PYTHON` | `%USERPROFILE%\anaconda3\envs\capstone\python.exe` | Streamlit/파이프라인 Python |
| `SERVER_PYTHON` | `%USERPROFILE%\anaconda3\envs\video_summarization\python.exe` | FastAPI Python |
| `SERVER_DIR` | 이 폴더의 상위 폴더 `\Summarization` | gpu-server 브랜치 체크아웃 |
| `API_PORT` / `STREAMLIT_PORT` | `8000` / `8501` | 내부 포트 |
| `GPU_SERVER_URL` | `http://127.0.0.1:8000` | Streamlit이 호출하는 API 주소 |
| `ENABLE_TUNNEL` | `0` | `1`이면 `-Tunnel` 없이도 터널 실행 |
| `EXTERNAL_UPLOAD_LIMIT_MB` | `100` | Cloudflare 경유 업로드 한도 |
| `JOB_RETENTION_HOURS` | `72` | 업로드 영상·실행 산출물 보존 기간 (0이면 자동 정리 안 함) |
| `MIN_FREE_DISK_GB` | `5` | 업로드 시 확보할 최소 여유 공간 |
| `TUNNEL_NAME` / `TUNNEL_TOKEN` / `TUNNEL_HOSTNAME` | 없음 | 고정 도메인 터널 (아래 참고) |

LLM/VLM 서버 설정(`LLM_BACKEND`, `KEEP_LLM_LOADED`, `ANTHROPIC_API_KEY`, `HF_TOKEN` 등)은 기존 gpu-server 문서와 같습니다.
`start_all`을 실행한 창의 환경변수가 FastAPI에 그대로 전달됩니다.

### 개별 실행 (기존 방식 유지)

- FastAPI: `C:\Summarization\start_server.bat` (기존 스크립트는 `0.0.0.0` 바인딩 — 단일 서버 운영에서는 `start_all` 권장)
- Streamlit: `run_app.bat`
- 터널: `start_tunnel.bat`

## 2. 외부 접속 비밀번호 (필수)

외부 공개 전에 서버 PC에서 `.streamlit\secrets.toml`을 만듭니다(이 파일은 `.gitignore`에 포함되어 Git에 올라가지 않습니다).

```toml
APP_PASSWORD = "충분히 긴 임의의 비밀번호"
```

- 비밀번호가 없으면 Cloudflare를 거친 접속은 화면에서 차단되고, `start_all -Tunnel`도 터널을 열지 않습니다.
- 같은 IP에서 5회 연속 실패하면 60초간 로그인을 막습니다.
- 파일을 만든 뒤 Streamlit을 재시작해야 적용됩니다.

## 3. Cloudflare Tunnel 설정

먼저 서버 PC에 cloudflared를 설치합니다(관리자가 직접 실행).

```bat
winget install --id Cloudflare.cloudflared
```

### 방식 A: 임시 URL (Quick Tunnel, 계정 불필요)

```bat
start_all.bat -Tunnel
```

- `https://<무작위>.trycloudflare.com` 주소가 출력되고 `tunnel_url.txt`에 저장됩니다.
- 실행할 때마다 주소가 바뀌며, Cloudflare가 테스트·개발용으로 제공하는 방식이라 가용성 보장이 없습니다.
- 동시 요청 수 제한이 있고 Cloudflare Access(이메일 인증 등)를 붙일 수 없습니다.
- `%USERPROFILE%\.cloudflared\config.yml`(또는 `config.yaml`)이 있으면 Quick Tunnel이 동작하지 않을 수 있습니다.

### 방식 B: 고정 도메인 (Named Tunnel, Cloudflare 계정과 Cloudflare에 등록된 도메인 필요)

계정 로그인·도메인 연결은 관리자가 직접 수행합니다. 두 가지 중 하나를 선택합니다.

B-1. 명령줄로 생성 (로그인 인증서 방식)

```bat
cloudflared tunnel login
cloudflared tunnel create video-summary
cloudflared tunnel route dns video-summary summary.example.com
```

이후 실행할 때마다:

```bat
set TUNNEL_NAME=video-summary
set TUNNEL_HOSTNAME=summary.example.com
start_all.bat -Tunnel
```

B-2. 대시보드에서 생성 (토큰 방식)

1. Cloudflare Zero Trust 대시보드 → Networks → Tunnels → Create a tunnel (Cloudflared)
2. Public hostname: `summary.example.com`, Service: `HTTP` / `127.0.0.1:8501`
3. 발급된 토큰을 서버 PC의 사용자 환경변수 `TUNNEL_TOKEN`에 저장 (명령줄 인자로 넘기지 않음, Git에 기록하지 않음)
4. `set TUNNEL_HOSTNAME=summary.example.com` 후 `start_all.bat -Tunnel`

이미 Windows 서비스 등으로 cloudflared 터널이 실행 중이면 `start_tunnel`은 새 터널을 만들지 않고 기존 터널을 그대로 둡니다.

### Cloudflare Access (권장, Named Tunnel에서만)

Zero Trust → Access → Applications → Self-hosted 앱으로 `summary.example.com`을 등록하고,
허용할 이메일(또는 학교 도메인) 정책과 One-time PIN 로그인을 설정하면 Streamlit 비밀번호 앞단에서
사용자별 인증이 추가됩니다. 현재 앱 비밀번호는 모든 사용자가 공유하는 하나의 비밀번호입니다.

### 네트워크 제약

cloudflared는 Cloudflare 에지로 outbound 7844 포트(QUIC/UDP 또는 HTTP2/TCP)를 사용합니다.
학교·기관 네트워크가 이를 차단하면 연결되지 않습니다. 이 경우 보안 정책을 우회하지 말고 네트워크 관리자에게 허용 여부를 문의하세요.
연결 실패 로그는 `cloudflared.log`에 남습니다.

## 4. 다른 PC·스마트폰에서 사용

1. 관리자에게 받은 주소(`https://....trycloudflare.com` 또는 고정 도메인)로 접속
2. 비밀번호 입력 (Cloudflare Access를 쓰면 이메일 인증 먼저)
3. 업로드 페이지에서 영상 파일 업로드 또는 유튜브 링크 입력
4. 분석 방식·로컬 모델·Whisper 크기 선택 후 "영상 분석 시작"
5. 진행률 확인 → 완료 시 결과 페이지로 자동 이동 → 타임라인 클릭으로 해당 구간 재생
6. "영상과 요약 결과 저장" → "저장된 요약"·"실행 이력"에서 다시 확인

브라우저를 새로고침하거나 연결이 끊겨도 서버의 분석은 계속됩니다. 주소창의 `?run=<실행 ID>`가 붙은 주소로
다시 접속(로그인)하면 진행 중인 작업 또는 결과에 다시 연결됩니다. 주소를 잃어버렸다면 "실행 이력"에서 결과 로그를 확인할 수 있습니다.

## 5. 업로드·작업 처리 규칙

| 항목 | 동작 |
| --- | --- |
| Streamlit 한도 | `.streamlit/config.toml`의 `maxUploadSize = 500`(MB). 서버 PC에서 직접 접속할 때 적용 |
| Cloudflare 한도 | 무료/Pro 플랜은 요청 1건당 100MB. 외부 접속 시 업로더 한도를 `EXTERNAL_UPLOAD_LIMIT_MB`(100MB)로 낮춰 업로드 전에 "파일이 너무 큼" 오류를 표시 |
| 큰 영상 | 유튜브 링크(서버가 직접 다운로드) 또는 서버 PC에서 직접 업로드. 영상은 외부 저장소로 보내지 않음 |
| 저장 위치 | `data\input\uploads\<시각-무작위ID>\input.<확장자>` — 업로드마다 고유 폴더라 파일명 충돌 없음 |
| 검증 | 확장자(MP4/MOV/AVI) + ffprobe로 실제 영상인지 확인. 실패 시 파일 삭제 후 오류 표시 |
| 디스크 | 업로드 크기×2 + `MIN_FREE_DISK_GB` 여유가 없으면 저장 거부 |
| 산출물 | 실행별 `runs\jobs\<run_id>\`(audio, stt, llm, frames, ocr, vlm, final) — 사용자 간 결과가 섞이지 않음 |
| 동시 실행 | GPU 1개를 공유하므로 전체 파이프라인은 서버 전체에서 한 번에 1개. 다른 사용자는 "다른 사용자의 영상 분석이 진행 중" 안내와 함께 시작 버튼 비활성화 |
| 보존 | `JOB_RETENTION_HOURS`(72시간)가 지난 업로드·실행 폴더는 업로드 페이지 접속 시 정리. "저장"한 결과(`data\saved`)와 실행 이력은 유지 |

FastAPI의 단일 추론 큐(`max_workers=1`)와 작업 ID 폴링·타임아웃(작업당 3600초)은 그대로입니다.

## 6. 보안 점검 요약

- 외부 노출: Streamlit만 터널로 공개, FastAPI(모델 다운로드·Claude 프록시 엔드포인트 포함)는 localhost 전용
- 외부 접속인데 비밀번호 미설정이면 차단, 비밀번호 비교는 상수 시간 비교, 연속 실패 시 잠금
- `client.toolbarMode = "viewer"`, `client.showErrorDetails = "none"`: 외부 사용자에게 개발자 메뉴와 서버 경로가 담긴 예외 상세를 숨김
- 화면에 서버 절대경로를 표시하지 않음(저장 완료 메시지는 폴더명만), 영상은 Streamlit 미디어 URL로 전달
- 실행 ID·저장 폴더는 서버가 만든 목록에서만 선택하며 형식 검증으로 경로 탐색 차단
- `ANTHROPIC_API_KEY`는 FastAPI만 읽고 파이프라인 자식 프로세스에는 전달하지 않음(기존 동작). `TUNNEL_TOKEN`은 환경변수로만 전달
- `.gitignore`: `secrets.toml`, `logs/`, `*.log`, `runs/`, `data/input/`, `data/saved/`, `.cloudflared/`, `*.pem`, `.env`, `tunnel_url.txt`

한계: 비밀번호를 공유하는 모든 사용자는 같은 권한을 가지며 "저장된 요약"과 "실행 이력"을 함께 보고 삭제할 수 있습니다.
사용자별 분리가 필요하면 Cloudflare Access로 사용자를 제한하고, 앱 단 사용자 계정 기능을 추가해야 합니다.

## 7. 외부 PC에서 수행할 검증 체크리스트

- [ ] 외부 주소 접속 → 로그인 화면 → 틀린 비밀번호 거부, 올바른 비밀번호 통과
- [ ] 100MB 이하 영상 업로드 성공, 100MB 초과 영상은 업로더에서 크기 오류 표시
- [ ] 지원하지 않는 파일(예: 이름만 .mp4인 텍스트) 업로드 시 오류 표시
- [ ] 분석 시작 → 단계별 진행률 표시 → 결과 페이지 자동 이동
- [ ] 타임라인 클릭 시 영상 재생 위치 이동 (스마트폰 포함)
- [ ] 분석 중 브라우저 탭 닫기 → `?run=` 주소로 재접속 시 진행/결과 복원
- [ ] 두 번째 기기에서 동시에 분석 시작 시 "다른 사용자의 영상 분석이 진행 중" 표시
- [ ] 결과 저장 후 "저장된 요약"과 "실행 이력"에서 확인
- [ ] `stop_all.bat -TunnelOnly` 후 외부 주소 접속 불가 확인
- [ ] 외부에서 `https://<주소>:8000` 또는 `/health` 등 FastAPI 경로에 접근할 수 없음 확인
