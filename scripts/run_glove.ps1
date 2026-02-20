$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$envFile = Join-Path $root ".env.local.ps1"
if (-not (Test-Path $envFile)) {
    throw "Missing .env.local.ps1. Run scripts/setup_windows.ps1 first."
}

. $envFile

Write-Host "Starting Glove on http://$($env:GLOVE_HOST):$($env:GLOVE_PORT)"
Push-Location $root
try {
    $exePath = Join-Path $root "dist\glove\glove.exe"
    if (Test-Path $exePath) {
        & $exePath
    }
    else {
        $venvPython = Join-Path $root ".venv\Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            throw "Missing venv. Run scripts/setup_windows.ps1 first."
        }
        & $venvPython (Join-Path $root "main.py")
    }
}
finally {
    Pop-Location
}
