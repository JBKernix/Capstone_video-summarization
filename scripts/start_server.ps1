param(
    [string]$HostAddress = "10.30.2.224",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
    Write-Host "Starting Video Summarization API at http://$HostAddress`:$Port"
    Write-Host "Swagger UI: http://localhost:$Port/docs"
    Write-Host "Log file: $ProjectRoot\logs\server.log"

    # 현재 활성화된 가상 환경의 Python으로 Uvicorn을 실행합니다.
    python -m uvicorn scripts.server:app `
        --host $HostAddress `
        --port $Port `
        --workers 1
}
finally {
    Pop-Location
}
