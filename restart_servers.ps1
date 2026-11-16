# 앱 서버(React/Streamlit)와 추론 서버(FastAPI, gpu-server)만 재시작합니다.
# Cloudflare Tunnel은 건드리지 않습니다(외부 접속 주소가 그대로 유지됩니다).
# 종료 후 start_all.ps1 -NoTunnel로 다시 띄우므로 경로/포트 환경변수는 start_all과 같습니다.
param([switch]$Streamlit)

$root = $PSScriptRoot
$pidDir = Join-Path $root "runs\pids"

function Get-Port($names, [int]$default) {
    foreach ($name in $names) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrWhiteSpace($value)) { return [int]$value.Trim() }
    }
    return $default
}

$ApiPort = Get-Port @("API_PORT") 8000
$AppPort = Get-Port @("APP_PORT", "STREAMLIT_PORT") 8501

$active = Join-Path $root "runs\active_pipeline.json"
if (Test-Path $active) {
    Write-Host "[WARN] 진행 중일 수 있는 분석 작업이 있습니다. 재시작하면 함께 중단됩니다." -ForegroundColor Yellow
}

# 이름, 포트, 명령줄 패턴(다른 프로그램을 종료하지 않도록 확인용)
$targets = @(
    @{ Name = "앱 서버"; Port = $AppPort; Pattern = "app\.api\.server|streamlit"; PidFiles = @("app", "streamlit") },
    @{ Name = "추론 서버"; Port = $ApiPort; Pattern = "app\.server:app"; PidFiles = @("fastapi") }
)

Write-Host ""
Write-Host "== 1. 서버 종료" -ForegroundColor Cyan
foreach ($t in $targets) {
    $procIds = @()
    foreach ($pidName in $t.PidFiles) {
        $pidFile = Join-Path $pidDir "$pidName.pid"
        if (Test-Path $pidFile) {
            $procIds += [int](Get-Content $pidFile -Raw)
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
        }
    }
    $listeners = Get-NetTCPConnection -LocalPort $t.Port -State Listen -ErrorAction SilentlyContinue
    $procIds += @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)

    $stopped = $false
    foreach ($procId in ($procIds | Select-Object -Unique)) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        if ($proc -and $proc.CommandLine -match $t.Pattern) {
            & taskkill /PID $procId /T /F | Out-Null
            Write-Host "$($t.Name) 종료 (PID $procId, 포트 $($t.Port))"
            $stopped = $true
        } elseif ($proc) {
            Write-Host "[WARN] 포트 $($t.Port)의 PID $procId 은(는) $($t.Name)가 아니어서 종료하지 않았습니다: $($proc.Name)" -ForegroundColor Yellow
        }
    }
    if (-not $stopped) { Write-Host "$($t.Name) 은(는) 실행 중이 아닙니다." }

    # 포트가 풀릴 때까지 잠시 기다립니다.
    for ($i = 0; $i -lt 15; $i++) {
        if (-not (Get-NetTCPConnection -LocalPort $t.Port -State Listen -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Seconds 1
    }
}

Write-Host ""
Write-Host "== 2. 서버 시작 (터널 제외)" -ForegroundColor Cyan
$startArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "start_all.ps1"), "-NoTunnel")
if ($Streamlit) { $startArgs += "-Streamlit" }
& powershell @startArgs
exit $LASTEXITCODE
