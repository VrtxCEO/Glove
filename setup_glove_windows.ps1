$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "Glove\scripts\setup_windows.ps1"
if (-not (Test-Path $script)) {
    throw "Setup script not found: $script"
}
powershell -ExecutionPolicy Bypass -File $script
