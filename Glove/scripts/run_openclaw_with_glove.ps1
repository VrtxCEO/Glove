param(
    [string]$OpenClawExePath = "..\Build_Release\OpenClaw.exe"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $root ".env.local.ps1"
if (-not (Test-Path $envFile)) {
    throw "Missing .env.local.ps1. Run scripts/setup_windows.ps1 first."
}

. $envFile

$resolvedExe = Resolve-Path (Join-Path $root $OpenClawExePath) -ErrorAction SilentlyContinue
if (-not $resolvedExe) {
    throw "OpenClaw executable not found: $OpenClawExePath"
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $resolvedExe.Path
$psi.WorkingDirectory = (Split-Path $resolvedExe.Path -Parent)
$psi.UseShellExecute = $false

$psi.EnvironmentVariables["GLOVE_BASE_URL"] = $env:GLOVE_BASE_URL
$psi.EnvironmentVariables["GLOVE_AGENT_KEY"] = $env:GLOVE_AGENT_KEY
$psi.EnvironmentVariables["GLOVE_ADMIN_KEY"] = ""
$psi.EnvironmentVariables["GLOVE_INBOUND_TOKEN"] = ""

[System.Diagnostics.Process]::Start($psi) | Out-Null
Write-Host "OpenClaw started with agent-only Glove access."
