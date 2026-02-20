param(
    [string]$OpenClawExePath = "..\Build_Release\OpenClaw.exe"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    throw "Missing venv. Run scripts/setup_windows.ps1 first."
}

Write-Host "Starting Glove in background..."
Start-Process -FilePath "powershell" -ArgumentList @(
    "-ExecutionPolicy", "Bypass",
    "-File", (Join-Path $PSScriptRoot "run_glove.ps1")
)

Start-Sleep -Seconds 2
Write-Host "Starting OpenClaw..."
powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "run_openclaw_with_glove.ps1") -OpenClawExePath $OpenClawExePath
