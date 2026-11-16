# Create icon shortcuts (.lnk) for the root launcher .bat files.
# .bat files cannot carry their own icon, so each gets a shortcut that points at it with assets/icons/<name>.ico.
#   powershell -ExecutionPolicy Bypass -File scripts\create_shortcuts.ps1            # shortcuts in the repo root
#   powershell -ExecutionPolicy Bypass -File scripts\create_shortcuts.ps1 -Desktop   # also on the desktop
param([switch]$Desktop)

$root = Split-Path -Parent $PSScriptRoot
$iconDir = Join-Path $root "assets\icons"
$targets = @("start_all", "stop_all", "restart_servers", "start_tunnel", "run_app")

$dirs = @($root)
if ($Desktop) { $dirs += [Environment]::GetFolderPath("Desktop") }

$shell = New-Object -ComObject WScript.Shell
foreach ($name in $targets) {
    $bat = Join-Path $root "$name.bat"
    $ico = Join-Path $iconDir "$name.ico"
    if (-not (Test-Path $bat) -or -not (Test-Path $ico)) {
        Write-Warning "skip $name (missing .bat or .ico)"
        continue
    }
    foreach ($dir in $dirs) {
        $lnkPath = Join-Path $dir "$name.lnk"
        $lnk = $shell.CreateShortcut($lnkPath)
        $lnk.TargetPath = $bat
        $lnk.WorkingDirectory = $root
        $lnk.IconLocation = "$ico,0"
        $lnk.Save()
        Write-Host "created $lnkPath"
    }
}
