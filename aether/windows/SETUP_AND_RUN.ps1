$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
    $extra = @(
        "$env:LOCALAPPDATA\Programs\Python\Python311",
        "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts",
        "$env:ProgramFiles\nodejs",
        "$env:LOCALAPPDATA\Programs\Ollama"
    )
    foreach ($p in $extra) { if (Test-Path $p) { $env:Path = "$p;$env:Path" } }
}

function Install-WithWinget([string]$Id, [string]$Name) {
    Write-Host "`nChecking $Name..." -ForegroundColor Cyan
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Windows Package Manager (winget) is unavailable. Install/update 'App Installer' from Microsoft Store, then run this setup again."
    }
    winget install --id $Id --exact --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "winget returned exit code $LASTEXITCODE for $Name. It may already be installed; checking again."
    }
    Refresh-Path
}

Write-Host "==============================================" -ForegroundColor DarkCyan
Write-Host "       AETHER - ONE-TIME WINDOWS SETUP" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor DarkCyan
Write-Host "This setup installs missing prerequisites, Python packages, Node packages and the local AI model."
Write-Host "Internet is required for the initial setup and model download."
Write-Host ""

Refresh-Path

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Install-WithWinget "Python.Python.3.11" "Python 3.11"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Install-WithWinget "OpenJS.NodeJS.LTS" "Node.js LTS"
}
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Install-WithWinget "Ollama.Ollama" "Ollama"
}

Refresh-Path

# Validate prerequisites and give a precise recovery instruction if PATH has not refreshed.
try { py -3.11 --version } catch { throw "Python 3.11 was installed but is not visible yet. Close this window, reopen SETUP_AND_RUN.bat and retry." }
try { node --version; npm --version } catch { throw "Node.js was installed but is not visible yet. Close this window, reopen SETUP_AND_RUN.bat and retry." }
try { ollama --version } catch { throw "Ollama was installed but is not visible yet. Close this window, reopen SETUP_AND_RUN.bat and retry." }

# Create local environment and install Python requirements.
Write-Host "`n[1/4] Preparing Python environment..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "backend")
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
}
& ".venv\Scripts\python.exe" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
& ".venv\Scripts\python.exe" -m playwright install chromium
if ($LASTEXITCODE -ne 0) { Write-Warning "Could not install the Chromium browser for ChatGPT automation. Run '.venv\Scripts\python.exe -m playwright install chromium' later to enable it." }

# Install desktop dependencies.
Write-Host "`n[2/4] Preparing desktop application..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "desktop")
npm install
if ($LASTEXITCODE -ne 0) { throw "npm install failed." }

# Pull the local model once. Ollama may be installed as a background service.
Write-Host "`n[3/4] Downloading the local language model (one-time)..." -ForegroundColor Cyan
$ollamaProc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if (-not $ollamaProc) {
    $ollamaExe = (Get-Command ollama).Source
    Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 5
}
ollama pull qwen3:1.7b
if ($LASTEXITCODE -ne 0) {
    Write-Warning "The fast 1.7B model download failed. Trying the larger qwen3:4b model."
    ollama pull qwen3:4b
    if ($LASTEXITCODE -ne 0) { throw "Could not download a local model. Check internet access and rerun setup." }
    $envFile = Join-Path $ProjectRoot "backend\.env"
    (Get-Content $envFile -Raw) -replace 'AETHER_MODEL=qwen3:1\.7b','AETHER_MODEL=qwen3:4b' -replace 'AETHER_FAST_MODEL=qwen3:1\.7b','AETHER_FAST_MODEL=qwen3:4b' | Set-Content $envFile
}

Write-Host "`n[4/4] Setup complete. Starting AETHER..." -ForegroundColor Cyan
Set-Location $ProjectRoot
& (Join-Path $PSScriptRoot "START_AETHER.ps1")
