param(
    [string]$OpenClawExePath = "..\Build_Release\OpenClaw.exe",
    [string]$AgentKey = "",
    [string]$AdminKey = ""
)

if (-not (Test-Path $OpenClawExePath)) {
    Write-Error "OpenClaw executable not found at: $OpenClawExePath"
    exit 1
}

if (-not $AgentKey) {
    $AgentKey = [Convert]::ToBase64String((1..24 | ForEach-Object {Get-Random -Maximum 256}))
}

if (-not $AdminKey) {
    $AdminKey = [Convert]::ToBase64String((1..24 | ForEach-Object {Get-Random -Maximum 256}))
}

$env:GLOVE_AGENT_KEY = $AgentKey
$env:GLOVE_ADMIN_KEY = $AdminKey

Write-Host "Starting Glove..."
Start-Process -FilePath "python" -ArgumentList "main.py" -WorkingDirectory $PSScriptRoot

Start-Sleep -Seconds 2

Write-Host "Starting OpenClaw with agent key only..."
$openClawEnv = @{
    "GLOVE_AGENT_KEY" = $AgentKey
    "GLOVE_ADMIN_KEY" = ""
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = (Resolve-Path $OpenClawExePath).Path
$psi.WorkingDirectory = (Split-Path (Resolve-Path $OpenClawExePath).Path)
$psi.UseShellExecute = $false
foreach ($entry in $openClawEnv.GetEnumerator()) {
    $psi.EnvironmentVariables[$entry.Key] = $entry.Value
}
[System.Diagnostics.Process]::Start($psi) | Out-Null

Write-Host "Glove UI: http://localhost:8088/"
Write-Host "Admin key (store safely): $AdminKey"
