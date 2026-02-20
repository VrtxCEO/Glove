$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$buildVenv = Join-Path $root ".venv-build"
$buildPython = Join-Path $buildVenv "Scripts\python.exe"
$bundleRoot = Join-Path $root "dist\Glove-Windows"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is required to build bundle."
}

if (-not (Test-Path $buildPython)) {
    Write-Host "Creating build venv..."
    & python -m venv $buildVenv
}

Write-Host "Installing build dependencies..."
& $buildPython -m pip install --upgrade pip | Out-Null
& $buildPython -m pip install -r (Join-Path $root "requirements.txt")
& $buildPython -m pip install pyinstaller

Write-Host "Building glove.exe..."
& $buildPython -m PyInstaller `
  --noconfirm `
  --clean `
  --name glove `
  --onefile `
  --add-data "glove\static;glove\static" `
  (Join-Path $root "main.py")

if (Test-Path $bundleRoot) {
    Remove-Item -Recurse -Force $bundleRoot
}
New-Item -ItemType Directory -Path $bundleRoot | Out-Null
New-Item -ItemType Directory -Path (Join-Path $bundleRoot "scripts") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $bundleRoot "extensions") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $bundleRoot "dist\glove") | Out-Null

Copy-Item (Join-Path $root "dist\glove.exe") (Join-Path $bundleRoot "dist\glove\glove.exe") -Force
Copy-Item (Join-Path $root "policy.json") (Join-Path $bundleRoot "policy.json") -Force
Copy-Item (Join-Path $root "trusted_publishers.json") (Join-Path $bundleRoot "trusted_publishers.json") -Force
Copy-Item (Join-Path $root ".env.example") (Join-Path $bundleRoot ".env.example") -Force
Copy-Item (Join-Path $root "README.md") (Join-Path $bundleRoot "README.md") -Force

Copy-Item (Join-Path $root "scripts\setup_windows.ps1") (Join-Path $bundleRoot "scripts\setup_windows.ps1") -Force
Copy-Item (Join-Path $root "scripts\run_glove.ps1") (Join-Path $bundleRoot "scripts\run_glove.ps1") -Force
Copy-Item (Join-Path $root "scripts\run_openclaw_with_glove.ps1") (Join-Path $bundleRoot "scripts\run_openclaw_with_glove.ps1") -Force
Copy-Item (Join-Path $root "scripts\start_all.ps1") (Join-Path $bundleRoot "scripts\start_all.ps1") -Force

Copy-Item -Recurse -Force (Join-Path $root "extensions\README.md") (Join-Path $bundleRoot "extensions\README.md")
Copy-Item -Recurse -Force (Join-Path $root "extensions\example_console") (Join-Path $bundleRoot "extensions\example_console")

$zipPath = Join-Path $root "dist\Glove-Windows.zip"
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
Compress-Archive -Path (Join-Path $bundleRoot "*") -DestinationPath $zipPath

Write-Host "Bundle ready:"
Write-Host "  Folder: $bundleRoot"
Write-Host "  Zip:    $zipPath"
