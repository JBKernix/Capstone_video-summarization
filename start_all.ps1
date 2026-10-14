# GPU 서버 PC 한 대에서 FastAPI(LLM/VLM) -> Streamlit -> (선택) Cloudflare Tunnel 순서로 실행합니다.
#
#   FastAPI   : 127.0.0.1:8000 (서버 PC 내부 전용, 외부 공개 안 함)
#   Streamlit : 127.0.0.1:8501 (Cloudflare Tunnel만 이 포트로 연결)
#
# 이미 실행 중인 서버는 재사용하며 종료하지 않습니다. 모델/패키지를 다시 설치하지 않습니다.
# 환경변수로 경로와 포트를 바꿀 수 있습니다(README의 "단일 서버 실행" 참고).
param(
    [switch]$Tunnel,
    [switch]$NoTunnel
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Get-Setting($name, $default) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ([string]::IsNullOrWhiteSpace($value)) { return $default } else { return $value.Trim() }
}

$condaEnvs = Join-Path $env:USERPROFILE "anaconda3\envs"
$StreamlitPython = Get-Setting "STREAMLIT_PYTHON" (Join-Path $condaEnvs "capstone\python.exe")
$ServerPython = Get-Setting "SERVER_PYTHON" (Join-Path $condaEnvs "video_summarization\python.exe")
$ServerDir = Get-Setting "SERVER_DIR" (Join-Path (Split-Path $root -Parent) "Summarization")
$ApiPort = [int](Get-Setting "API_PORT" "8000")
$StreamlitPort = [int](Get-Setting "STREAMLIT_PORT" "8501")
$ApiTimeout = [int](Get-Setting "API_START_TIMEOUT" "180")
$EnableTunnel = ($Tunnel -or (Get-Setting "ENABLE_TUNNEL" "0") -in @("1", "true", "yes", "on")) -and -not $NoTunnel

$ApiUrl = "http://127.0.0.1:$ApiPort"
$StreamlitUrl = "http://127.0.0.1:$StreamlitPort"
$logDir = Join-Path $root "logs\launcher"
$pidDir = Join-Path $root "runs\pids"
New-Item -ItemType Directory -Force -Path $logDir, $pidDir | Out-Null

function Write-Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Fail($text) {
    Write-Host "[ERROR] $text" -ForegroundColor Red
    exit 1
}

function Get-Listener([int]$port) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Test-Http($url) {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-Http($url, $proc, [int]$timeout, $errLog) {
    for ($i = 0; $i -lt $timeout; $i++) {
        if (Test-Http $url) { return $true }
        if ($proc -and $proc.HasExited) {
            Write-Host "[ERROR] 프로세스가 종료되었습니다 (코드 $($proc.ExitCode)). 마지막 로그:" -ForegroundColor Red
            Get-Content $errLog -Tail 20 -ErrorAction SilentlyContinue
            return $false
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Warn-IfPublicBind($listener, $name) {
    if ($listener.LocalAddress -in @("0.0.0.0", "::")) {
        Write-Host "[WARN] 이미 실행 중인 $name 이(가) 모든 네트워크 인터페이스($($listener.LocalAddress))에 바인딩되어 있습니다." -ForegroundColor Yellow
        Write-Host "       같은 네트워크의 다른 PC에서 직접 접근할 수 있습니다. 127.0.0.1 전용으로 바꾸려면 해당 창을 직접 종료한 뒤 start_all.bat을 다시 실행하세요."
    }
}

# ---------------------------------------------------------------------------
Write-Step "1. 실행 환경 확인"
if (-not (Test-Path $StreamlitPython)) { Fail "Streamlit용 Python을 찾을 수 없습니다: $StreamlitPython (STREAMLIT_PYTHON 환경변수로 지정)" }
if (-not (Test-Path $ServerPython)) { Fail "FastAPI용 Python을 찾을 수 없습니다: $ServerPython (SERVER_PYTHON 환경변수로 지정)" }
if (-not (Test-Path (Join-Path $ServerDir "app\server.py"))) { Fail "gpu-server 코드 폴더를 찾을 수 없습니다: $ServerDir (SERVER_DIR 환경변수로 지정)" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Host "[WARN] PATH에서 ffmpeg를 찾지 못했습니다. 영상 전처리 단계가 실패할 수 있습니다." -ForegroundColor Yellow }
Write-Host "Streamlit Python : $StreamlitPython"
Write-Host "FastAPI Python   : $ServerPython"
Write-Host "gpu-server 폴더  : $ServerDir"
$drive = (Get-Item $root).PSDrive
Write-Host ("디스크 여유 공간 : {0:N1} GB ({1}:)" -f ($drive.Free / 1GB), $drive.Name)
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    $gpu = & nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader 2>$null
    if ($gpu) { Write-Host "GPU              : $gpu" }
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# ---------------------------------------------------------------------------
Write-Step "2. FastAPI 서버 ($ApiUrl)"
$apiListener = Get-Listener $ApiPort
if ($apiListener) {
    if (Test-Http "$ApiUrl/health") {
        Write-Host "이미 실행 중인 FastAPI 서버를 재사용합니다 (PID $($apiListener.OwningProcess))." -ForegroundColor Green
        Warn-IfPublicBind $apiListener "FastAPI"
    } else {
        Fail "포트 $ApiPort 을(를) 다른 프로그램(PID $($apiListener.OwningProcess))이 사용 중이며 /health에 응답하지 않습니다. 해당 프로그램을 확인하세요."
    }
} else {
    $apiOut = Join-Path $logDir "fastapi.out.log"
    $apiErr = Join-Path $logDir "fastapi.err.log"
    $apiProc = Start-Process -FilePath $ServerPython -WorkingDirectory $ServerDir -WindowStyle Hidden -PassThru `
        -ArgumentList @("-m", "uvicorn", "app.server:app", "--host", "127.0.0.1", "--port", "$ApiPort", "--workers", "1") `
        -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr
    Set-Content -Path (Join-Path $pidDir "fastapi.pid") -Value $apiProc.Id -Encoding ascii
    Write-Host "FastAPI 시작 (PID $($apiProc.Id)). 준비 상태 확인 중... (최대 ${ApiTimeout}초)"

    # ---------------------------------------------------------------------------
    Write-Step "3. FastAPI 준비 상태 확인"
    if (-not (Wait-Http "$ApiUrl/health" $apiProc $ApiTimeout $apiErr)) {
        Fail "FastAPI가 ${ApiTimeout}초 안에 준비되지 않았습니다. 로그: $apiErr , $ServerDir\logs\server.log"
    }
    Write-Host "FastAPI 준비 완료." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
Write-Step "4. Streamlit ($StreamlitUrl)"
$env:GPU_SERVER_URL = $ApiUrl
$stListener = Get-Listener $StreamlitPort
if ($stListener) {
    if (Test-Http "$StreamlitUrl/_stcore/health") {
        Write-Host "이미 실행 중인 Streamlit을 재사용합니다 (PID $($stListener.OwningProcess))." -ForegroundColor Green
        Warn-IfPublicBind $stListener "Streamlit"
    } else {
        Fail "포트 $StreamlitPort 을(를) 다른 프로그램(PID $($stListener.OwningProcess))이 사용 중입니다."
    }
} else {
    $stOut = Join-Path $logDir "streamlit.out.log"
    $stErr = Join-Path $logDir "streamlit.err.log"
    $stProc = Start-Process -FilePath $StreamlitPython -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -ArgumentList @("-m", "streamlit", "run", "app\main.py", "--server.address", "127.0.0.1",
                        "--server.port", "$StreamlitPort", "--server.headless", "true") `
        -RedirectStandardOutput $stOut -RedirectStandardError $stErr
    Set-Content -Path (Join-Path $pidDir "streamlit.pid") -Value $stProc.Id -Encoding ascii
    Write-Host "Streamlit 시작 (PID $($stProc.Id))."

    # ---------------------------------------------------------------------------
    Write-Step "5. Streamlit 준비 상태 확인"
    if (-not (Wait-Http "$StreamlitUrl/_stcore/health" $stProc 60 $stErr)) {
        Fail "Streamlit이 60초 안에 준비되지 않았습니다. 로그: $stErr"
    }
    Write-Host "Streamlit 준비 완료." -ForegroundColor Green
}

# ---------------------------------------------------------------------------
Write-Step "6. Cloudflare Tunnel"
$publicUrl = $null
if ($EnableTunnel) {
    $secrets = Join-Path $root ".streamlit\secrets.toml"
    $hasPassword = (Test-Path $secrets) -and (Select-String -Path $secrets -Pattern '^\s*APP_PASSWORD\s*=\s*"[^"]+"' -Quiet)
    if (-not $hasPassword) {
        Write-Host "[ERROR] .streamlit\secrets.toml에 APP_PASSWORD가 없어 외부 공개를 시작하지 않습니다." -ForegroundColor Red
        Write-Host "        docs/single_server_deployment.md의 '외부 접속 비밀번호' 절차를 따른 뒤 Streamlit을 재시작하고 다시 실행하세요."
    } else {
        & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $root "start_tunnel.ps1") -Port $StreamlitPort -Detach
        $urlFile = Join-Path $root "tunnel_url.txt"
        if (Test-Path $urlFile) { $publicUrl = (Get-Content $urlFile -Raw).Trim() }
    }
} else {
    Write-Host "비활성화됨 (외부 접속이 필요하면 start_all.bat -Tunnel 또는 ENABLE_TUNNEL=1)."
}

# ---------------------------------------------------------------------------
Write-Step "7. 접속 안내"
Write-Host "서버 PC 로컬 접속 : $StreamlitUrl" -ForegroundColor Green
if ($publicUrl) { Write-Host "외부 접속 주소    : $publicUrl" -ForegroundColor Green }
Write-Host "FastAPI(내부 전용): $ApiUrl  (외부에 공개되지 않습니다)"
Write-Host "실행 로그         : $logDir , $ServerDir\logs\server.log , $root\logs\client.log"
Write-Host "종료              : stop_all.bat (이 스크립트가 시작한 프로세스만 종료)"
