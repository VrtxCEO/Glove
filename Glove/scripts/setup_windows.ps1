param(
    [string]$OpenClawExePath = "..\Build_Release\OpenClaw.exe",
    [switch]$SkipPinSetup
)

$ErrorActionPreference = "Stop"

function New-RandomToken([int]$bytes = 24) {
    $buffer = New-Object byte[] $bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
    return [Convert]::ToBase64String($buffer).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Require-Python {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python was not found in PATH. Install Python 3.10+ and re-run."
    }
}

function Ensure-Venv([string]$root) {
    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "Creating virtual environment..."
        & python -m venv (Join-Path $root ".venv")
    }
    Write-Host "Installing dependencies..."
    & $venvPython -m pip install --upgrade pip | Out-Null
    & $venvPython -m pip install -r (Join-Path $root "requirements.txt")
    return $venvPython
}

function Resolve-GloveRunner([string]$root, [string]$venvPython) {
    $exePath = Join-Path $root "dist\glove\glove.exe"
    if (Test-Path $exePath) {
        return @{ FilePath = $exePath; Arguments = @() }
    }
    return @{ FilePath = $venvPython; Arguments = @("main.py") }
}

function Ask-Notifier {
    Write-Host ""
    Write-Host "Select notifier:"
    Write-Host "1) console (recommended to start)"
    Write-Host "2) webhook"
    Write-Host "3) smtp email"
    Write-Host "4) twilio sms"
    Write-Host "5) clawhub extensions bridge"
    Write-Host "6) multiple providers (comma list)"
    $choice = Read-Host "Choice (1-6)"
    switch ($choice) {
        "2" { return "webhook" }
        "3" { return "smtp" }
        "4" { return "twilio" }
        "5" { return "clawhub" }
        "6" { return "multi" }
        default { return "console" }
    }
}

function Write-EnvScript(
    [string]$path,
    [string]$adminKey,
    [string]$agentKey,
    [string]$inboundToken,
    [string]$notifier
) {
    $lines = @()
    $lines += '$env:GLOVE_HOST="0.0.0.0"'
    $lines += '$env:GLOVE_PORT="8088"'
    $lines += '$env:GLOVE_PUBLIC_URL="http://127.0.0.1:8088"'
    $lines += '$env:GLOVE_DB_PATH="./glove.db"'
    $lines += '$env:GLOVE_POLICY_PATH="./policy.json"'
    $lines += '$env:GLOVE_CLAWHUB_TRUST_STORE_PATH="./trusted_publishers.json"'
    $lines += '$env:GLOVE_REQUIRE_EXTENSION_SIGNATURES="true"'
    $lines += '$env:GLOVE_REQUEST_TTL_SECONDS="300"'
    $lines += '$env:GLOVE_MAX_PIN_ATTEMPTS="5"'
    $lines += '$env:GLOVE_ADMIN_KEY="' + $adminKey + '"'
    $lines += '$env:GLOVE_AGENT_KEY="' + $agentKey + '"'
    $lines += '$env:GLOVE_INBOUND_TOKEN="' + $inboundToken + '"'
    $lines += '$env:GLOVE_BASE_URL="http://127.0.0.1:8088"'
    if ($notifier -eq "multi") {
        $providers = Read-Host "GLOVE_NOTIFIER_PROVIDERS (example: console,twilio,clawhub)"
        if (-not $providers) { $providers = "console" }
        $lines += '$env:GLOVE_NOTIFIER_PROVIDER="console"'
        $lines += '$env:GLOVE_NOTIFIER_PROVIDERS="' + $providers + '"'
    }
    else {
        $lines += '$env:GLOVE_NOTIFIER_PROVIDER="' + $notifier + '"'
        $lines += '$env:GLOVE_NOTIFIER_PROVIDERS=""'
    }

    $targetSet = $notifier
    if ($notifier -eq "multi") {
        $targetSet = (Read-Host "Configure which provider now? webhook/smtp/twilio/clawhub/none")
    }

    if ($targetSet -eq "webhook") {
        $url = Read-Host "GLOVE_WEBHOOK_URL"
        $lines += '$env:GLOVE_WEBHOOK_URL="' + $url + '"'
    }
    elseif ($targetSet -eq "smtp") {
        $smtpHost = Read-Host "GLOVE_SMTP_HOST"
        $smtpPort = Read-Host "GLOVE_SMTP_PORT (default 587)"
        if (-not $smtpPort) { $smtpPort = "587" }
        $smtpUser = Read-Host "GLOVE_SMTP_USERNAME"
        $smtpPass = Read-Host "GLOVE_SMTP_PASSWORD"
        $smtpFrom = Read-Host "GLOVE_SMTP_FROM"
        $notifyTo = Read-Host "GLOVE_NOTIFY_TO"
        $lines += '$env:GLOVE_SMTP_HOST="' + $smtpHost + '"'
        $lines += '$env:GLOVE_SMTP_PORT="' + $smtpPort + '"'
        $lines += '$env:GLOVE_SMTP_USERNAME="' + $smtpUser + '"'
        $lines += '$env:GLOVE_SMTP_PASSWORD="' + $smtpPass + '"'
        $lines += '$env:GLOVE_SMTP_USE_TLS="true"'
        $lines += '$env:GLOVE_SMTP_FROM="' + $smtpFrom + '"'
        $lines += '$env:GLOVE_NOTIFY_TO="' + $notifyTo + '"'
    }
    elseif ($targetSet -eq "twilio") {
        $sid = Read-Host "GLOVE_TWILIO_ACCOUNT_SID"
        $token = Read-Host "GLOVE_TWILIO_AUTH_TOKEN"
        $from = Read-Host "GLOVE_TWILIO_FROM"
        $to = Read-Host "GLOVE_TWILIO_TO"
        $lines += '$env:GLOVE_TWILIO_ACCOUNT_SID="' + $sid + '"'
        $lines += '$env:GLOVE_TWILIO_AUTH_TOKEN="' + $token + '"'
        $lines += '$env:GLOVE_TWILIO_FROM="' + $from + '"'
        $lines += '$env:GLOVE_TWILIO_TO="' + $to + '"'
    }
    elseif ($targetSet -eq "clawhub") {
        $extDir = Read-Host "GLOVE_CLAWHUB_EXTENSIONS_DIR (default ./extensions)"
        if (-not $extDir) { $extDir = "./extensions" }
        $extList = Read-Host "GLOVE_CLAWHUB_EXTENSIONS (comma list, example: example_console)"
        $lines += '$env:GLOVE_CLAWHUB_EXTENSIONS_DIR="' + $extDir + '"'
        $lines += '$env:GLOVE_CLAWHUB_EXTENSIONS="' + $extList + '"'
        $lines += '$env:GLOVE_CLAWHUB_TIMEOUT_SECONDS="10"'
    }

    Set-Content -Path $path -Value ($lines -join "`r`n") -Encoding UTF8
}

function Setup-PinViaApi([string]$root, [string]$venvPython) {
    $pin = Read-Host "Choose Glove PIN (4+ digits/chars)"
    if ([string]::IsNullOrWhiteSpace($pin) -or $pin.Length -lt 4) {
        throw "PIN must be at least 4 characters."
    }

    Write-Host "Bootstrapping PIN via local API..."
    . (Join-Path $root ".env.local.ps1")

    $runner = Resolve-GloveRunner -root $root -venvPython $venvPython
    $proc = Start-Process -FilePath $runner.FilePath -ArgumentList $runner.Arguments -WorkingDirectory $root -PassThru
    try {
        $ready = $false
        for ($i = 0; $i -lt 20; $i++) {
            Start-Sleep -Milliseconds 500
            try {
                $null = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8088/api/v1/health"
                $ready = $true
                break
            } catch { }
        }
        if (-not $ready) {
            throw "Glove API did not start in time."
        }

        $headers = @{ "X-Glove-Admin-Key" = $env:GLOVE_ADMIN_KEY }
        $body = @{ pin = $pin } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8088/api/v1/admin/setup-pin" -Headers $headers -Body $body -ContentType "application/json" | Out-Null
        Write-Host "PIN configured."
    }
    finally {
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force
        }
    }
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Write-Host "Glove setup root: $root"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$prebuiltExe = Join-Path $root "dist\glove\glove.exe"
if (Test-Path $prebuiltExe) {
    Write-Host "Using prebuilt Glove executable."
}
else {
    Require-Python
    $venvPython = Ensure-Venv -root $root
}

if (-not (Test-Path (Join-Path $root "policy.json"))) {
    throw "policy.json is missing."
}

$notifier = Ask-Notifier
$adminKey = New-RandomToken
$agentKey = New-RandomToken
$inboundToken = New-RandomToken

$envScriptPath = Join-Path $root ".env.local.ps1"
Write-EnvScript -path $envScriptPath -adminKey $adminKey -agentKey $agentKey -inboundToken $inboundToken -notifier $notifier

if (-not $SkipPinSetup) {
    Setup-PinViaApi -root $root -venvPython $venvPython
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Admin UI: http://localhost:8088/"
Write-Host "Run Glove:   powershell -ExecutionPolicy Bypass -File .\scripts\run_glove.ps1"
Write-Host "Run game:    powershell -ExecutionPolicy Bypass -File .\scripts\run_openclaw_with_glove.ps1 -OpenClawExePath '$OpenClawExePath'"
Write-Host ""
Write-Host "Important: Keep .env.local.ps1 private. It contains admin secrets."
