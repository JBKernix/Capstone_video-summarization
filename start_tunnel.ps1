$logFile = Join-Path $PSScriptRoot "cloudflared.log"
$urlFile = Join-Path $PSScriptRoot "tunnel_url.txt"

if (Test-Path $logFile) { Remove-Item $logFile -Force }
if (Test-Path $urlFile) { Remove-Item $urlFile -Force }

$cmdArgs = "/c cloudflared tunnel --url http://localhost:8501 --no-autoupdate > `"$logFile`" 2>&1"
$proc = Start-Process -FilePath "cmd.exe" -ArgumentList $cmdArgs -NoNewWindow -PassThru

Write-Host "cloudflared 시작 중... (PID: $($proc.Id))"

$url = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Path $logFile) {
        $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
        if ($content -match '(https://[a-z0-9-]+\.trycloudflare\.com)') {
            $url = $matches[1]
            break
        }
    }
}

if ($url) {
    [System.IO.File]::WriteAllText($urlFile, $url)
    Write-Host "터널 URL: $url"
    Write-Host "URL이 저장된 파일: $urlFile"
} else {
    Write-Host "30초 내에 URL을 찾지 못했습니다. $logFile 을 확인하세요."
}

Wait-Process -Id $proc.Id
