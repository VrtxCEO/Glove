param(
    [string]$GloveBaseUrl = "http://127.0.0.1:8088",
    [string]$GloveAgentKey = "",
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

function Require-OpenClaw {
    $cmd = Get-Command openclaw -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "openclaw CLI not found in PATH. Install it first."
    }
}

function Read-AgentKeyFromEnvFile([string]$root) {
    $envPath = Join-Path $root ".env.local.ps1"
    if (-not (Test-Path $envPath)) { return "" }
    $line = Get-Content $envPath | Where-Object { $_ -match "GLOVE_AGENT_KEY" } | Select-Object -First 1
    if (-not $line) { return "" }
    if ($line -match '"([^"]+)"') { return $matches[1] }
    return ""
}

Require-OpenClaw

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pluginSrc = Join-Path $root "openclaw-plugin\glove-guard"
$pluginDst = Join-Path $HOME ".openclaw\extensions\glove-guard"

if (-not (Test-Path $pluginSrc)) {
    throw "Plugin source not found: $pluginSrc"
}

if (-not $GloveAgentKey) {
    $GloveAgentKey = Read-AgentKeyFromEnvFile -root $root
}
if (-not $GloveAgentKey) {
    throw "Missing Glove agent key. Pass -GloveAgentKey or create Glove/.env.local.ps1 first."
}

New-Item -ItemType Directory -Force (Split-Path $pluginDst -Parent) | Out-Null
if (Test-Path $pluginDst) { Remove-Item -Recurse -Force $pluginDst }
Copy-Item -Recurse -Force $pluginSrc $pluginDst

openclaw config set plugins.load.paths[0] "$pluginDst" | Out-Null
openclaw config set plugins.entries.glove-guard.config.enabled true | Out-Null
openclaw config set plugins.entries.glove-guard.config.baseUrl "$GloveBaseUrl" | Out-Null
openclaw config set plugins.entries.glove-guard.config.agentKey "$GloveAgentKey" | Out-Null

if (-not $NoRestart) {
    openclaw daemon restart | Out-Null
}

Write-Host "Installed glove-guard plugin at: $pluginDst"
Write-Host "Configured OpenClaw to use Glove at: $GloveBaseUrl"
if ($NoRestart) {
    Write-Host "Restart skipped. Run: openclaw daemon restart"
}
else {
    Write-Host "Gateway restarted."
}
