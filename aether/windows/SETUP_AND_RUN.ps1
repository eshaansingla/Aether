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
        "$env:ProgramFiles\nodejs"
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
Write-Host "This setup installs missing prerequisites and the Python/Node dependencies."
Write-Host "AETHER calls a cloud AI API (OpenAI, Groq, or Gemini) for generation, so you'll"
Write-Host "also need an API key for one of those - see backend\.env.example."
Write-Host ""

Refresh-Path

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Install-WithWinget "Python.Python.3.11" "Python 3.11"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Install-WithWinget "OpenJS.NodeJS.LTS" "Node.js LTS"
}

Refresh-Path

# Validate prerequisites and give a precise recovery instruction if PATH has not refreshed.
try { py -3.11 --version } catch { throw "Python 3.11 was installed but is not visible yet. Close this window, reopen SETUP_AND_RUN.bat and retry." }
try { node --version; npm --version } catch { throw "Node.js was installed but is not visible yet. Close this window, reopen SETUP_AND_RUN.bat and retry." }

# Create local environment and install Python requirements.
Write-Host "`n[1/3] Preparing Python environment..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "backend")
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.11 -m venv .venv
}
& ".venv\Scripts\python.exe" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed." }
# torch (CPU build) powers the local top-k/beam strategies and perplexity scoring. Its
# CPU wheel lives on a separate index, so it cannot go in requirements.txt.
& ".venv\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw "PyTorch installation failed." }
$envFileCreated = $false
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; $envFileCreated = $true }
& ".venv\Scripts\python.exe" -m playwright install chromium
if ($LASTEXITCODE -ne 0) { Write-Warning "Could not install the Chromium browser for ChatGPT automation. Run '.venv\Scripts\python.exe -m playwright install chromium' later to enable it." }

# Install desktop dependencies.
Write-Host "`n[2/3] Preparing desktop application..." -ForegroundColor Cyan
Set-Location (Join-Path $ProjectRoot "desktop")
npm install
if ($LASTEXITCODE -ne 0) { throw "npm install failed." }

Write-Host "`n[3/3] Setup complete." -ForegroundColor Cyan
if ($envFileCreated) {
    Write-Warning "backend\.env was just created from .env.example with no API key filled in."
    Write-Host "Open backend\.env, set AETHER_PROVIDER to openai/groq/gemini, and paste that provider's API key, then rerun this script (or START_AETHER.bat)." -ForegroundColor Yellow
    exit 0
}
Write-Host "Starting AETHER..." -ForegroundColor Cyan
Set-Location $ProjectRoot
& (Join-Path $PSScriptRoot "START_AETHER.ps1")
