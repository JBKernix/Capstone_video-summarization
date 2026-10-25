# start_all / start_tunnel(-Detach)이 시작해 runs\pids에 기록한 프로세스만 종료합니다.
# 사용자가 직접 띄운 서버나 터널은 건드리지 않습니다.
param([switch]$TunnelOnly)

$root = $PSScriptRoot
$pidDir = Join-Path $root "runs\pids"
$expected = [ordered]@{
    "cloudflared" = "cloudflared"
    "streamlit"   = "streamlit"
    "app"         = "app\.api\.server"
    "fastapi"     = "uvicorn"
}
if ($TunnelOnly) { $expected = [ordered]@{ "cloudflared" = "cloudflared" } }

$active = Join-Path $root "runs\active_pipeline.json"
if (-not $TunnelOnly -and (Test-Path $active)) {
    Write-Host "[WARN] 진행 중일 수 있는 분석 작업이 있습니다. 앱 서버(React/Streamlit) 종료 시 함께 중단됩니다." -ForegroundColor Yellow
}

foreach ($name in $expected.Keys) {
    $pidFile = Join-Path $pidDir "$name.pid"
    if (-not (Test-Path $pidFile)) { continue }
    $procId = [int](Get-Content $pidFile -Raw)
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
    # PID가 재사용된 다른 프로그램을 종료하지 않도록 명령줄을 확인합니다.
    if ($proc -and $proc.CommandLine -match $expected[$name]) {
        & taskkill /PID $procId /T /F | Out-Null
        Write-Host "$name 종료 (PID $procId)"
    } else {
        Write-Host "$name 은(는) 이미 종료되었습니다."
    }
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}
