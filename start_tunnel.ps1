# Cloudflare Tunnel로 로컬 Streamlit(기본 http://127.0.0.1:8501)만 외부에 공개합니다.
# FastAPI(8000)는 절대 터널에 연결하지 않습니다.
#
# 모드
#   - 임시 URL(Quick Tunnel, 기본): 계정 없이 https://<무작위>.trycloudflare.com 주소 발급. 실행할 때마다 주소가 바뀝니다.
#   - 고정 도메인(Named Tunnel): 환경변수 TUNNEL_NAME(로그인/터널 생성 완료 후) 또는 TUNNEL_TOKEN(대시보드 토큰)을 설정합니다.
#     공개 주소는 TUNNEL_HOSTNAME(예: summary.example.com)에 적어 두면 안내에 표시됩니다.
#
# 사용법
#   start_tunnel.bat                      # 포그라운드 실행(Ctrl+C로 종료)
#   powershell -File start_tunnel.ps1 -Detach   # 백그라운드 실행(start_all이 사용, stop_all로 종료)
param(
    [int]$Port = $(if ($env:STREAMLIT_PORT) { [int]$env:STREAMLIT_PORT } else { 8501 }),
    [switch]$Detach,
    [int]$TimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$logFile = Join-Path $root "cloudflared.log"
$urlFile = Join-Path $root "tunnel_url.txt"
$pidDir = Join-Path $root "runs\pids"
$pidFile = Join-Path $pidDir "cloudflared.pid"
$target = "http://127.0.0.1:$Port"

function Find-Cloudflared {
    $candidates = @()
    if ($env:CLOUDFLARED_EXE) { $candidates += $env:CLOUDFLARED_EXE }
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
    $candidates += @(
        "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
        "$env:ProgramFiles\cloudflared\cloudflared.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe"
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) { return (Resolve-Path $path).Path }
    }
    return $null
}

$exe = Find-Cloudflared
if (-not $exe) {
    Write-Host "[ERROR] cloudflared를 찾을 수 없습니다." -ForegroundColor Red
    Write-Host "  설치: winget install --id Cloudflare.cloudflared"
    Write-Host "  설치 후 새 터미널에서 다시 실행하거나 CLOUDFLARED_EXE 환경변수에 cloudflared.exe 경로를 지정하세요."
    exit 1
}

# 이미 실행 중인 터널이 있으면 중복 실행하지 않습니다(사용자가 띄운 터널도 종료하지 않음).
$existing = Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match "tunnel" }
if ($existing) {
    Write-Host "[INFO] 이미 실행 중인 cloudflared 터널이 있어 새로 시작하지 않습니다." -ForegroundColor Yellow
    foreach ($p in $existing) { Write-Host "  PID $($p.ProcessId)" }
    if (Test-Path $urlFile) { Write-Host "  마지막 접속 주소: $(Get-Content $urlFile -Raw)" }
    exit 0
}

# 터널 대상 Streamlit이 응답하는지 먼저 확인합니다.
try {
    Invoke-WebRequest -Uri "$target/_stcore/health" -UseBasicParsing -TimeoutSec 5 | Out-Null
} catch {
    Write-Host "[ERROR] $target 에서 Streamlit이 응답하지 않습니다. start_all.bat 또는 run_app.bat으로 먼저 실행하세요." -ForegroundColor Red
    exit 1
}

if (Test-Path $logFile) { Remove-Item $logFile -Force }
if (Test-Path $urlFile) { Remove-Item $urlFile -Force }
New-Item -ItemType Directory -Force -Path $pidDir | Out-Null

if ($env:TUNNEL_TOKEN) {
    # 토큰은 명령줄 인자가 아닌 환경변수(TUNNEL_TOKEN)로만 전달합니다(프로세스 목록 노출 방지).
    $mode = "named"
    $cfArgs = @("tunnel", "--no-autoupdate", "run")
} elseif ($env:TUNNEL_NAME) {
    $mode = "named"
    $cfArgs = @("tunnel", "--no-autoupdate", "run", "--url", $target, $env:TUNNEL_NAME)
} else {
    $mode = "quick"
    $cfArgs = @("tunnel", "--no-autoupdate", "--url", $target)
}

$startArgs = @{
    FilePath = $exe; ArgumentList = $cfArgs; PassThru = $true
    RedirectStandardError = $logFile; RedirectStandardOutput = "$logFile.out"
}
# 백그라운드 실행은 창 없이 띄워 이 콘솔을 닫아도 터널이 유지되게 합니다.
if ($Detach) { $startArgs.WindowStyle = "Hidden" } else { $startArgs.NoNewWindow = $true }
$proc = Start-Process @startArgs
Set-Content -Path $pidFile -Value $proc.Id -Encoding ascii
Write-Host "cloudflared 시작 중... (PID: $($proc.Id), 대상: $target, 모드: $mode)"

$url = $null
$connected = $false
for ($i = 0; $i -lt $TimeoutSeconds; $i++) {
    Start-Sleep -Seconds 1
    if ($proc.HasExited) { break }
    $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
    if (-not $content) { continue }
    if ($mode -eq "quick" -and $content -match '(https://[a-z0-9-]+\.trycloudflare\.com)') { $url = $matches[1] }
    if ($content -match 'Registered tunnel connection') { $connected = $true }
    if ($connected -and ($url -or $mode -eq "named")) { break }
}

if ($proc.HasExited) {
    Write-Host "[ERROR] cloudflared가 종료되었습니다 (코드 $($proc.ExitCode)). 로그: $logFile" -ForegroundColor Red
    Get-Content $logFile -Tail 15 -ErrorAction SilentlyContinue
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    exit 1
}

if ($mode -eq "named" -and $env:TUNNEL_HOSTNAME) { $url = "https://$env:TUNNEL_HOSTNAME" }
if ($url) {
    [System.IO.File]::WriteAllText($urlFile, $url)
    Write-Host "터널 URL: $url" -ForegroundColor Green
    Write-Host "URL이 저장된 파일: $urlFile"
} elseif ($connected) {
    Write-Host "터널이 연결되었습니다. Cloudflare 대시보드에 설정한 공개 호스트 이름으로 접속하세요." -ForegroundColor Green
} else {
    Write-Host "[WARN] ${TimeoutSeconds}초 내에 터널 연결을 확인하지 못했습니다. $logFile 을 확인하세요." -ForegroundColor Yellow
    Write-Host "       학교/기관 네트워크가 outbound 7844 포트(QUIC/HTTP2)를 차단하면 연결되지 않을 수 있습니다."
}

if ($Detach) { exit 0 }

Write-Host "Ctrl+C를 누르면 터널이 종료됩니다."
try {
    Wait-Process -Id $proc.Id
} finally {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}
