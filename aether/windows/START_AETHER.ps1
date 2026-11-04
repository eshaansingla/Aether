$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $ProjectRoot "backend"
$Desktop = Join-Path $ProjectRoot "desktop"

# First run (or missing deps) on this machine: do the one-time setup automatically, then
# continue straight into starting AETHER, so this single file always works either way.
$needsSetup = -not (Test-Path (Join-Path $Backend ".venv\Scripts\python.exe")) -or
              -not (Test-Path (Join-Path $Desktop "node_modules"))
if ($needsSetup) {
    Write-Host "First run detected - running one-time setup first..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "SETUP_AND_RUN.ps1")
    exit $LASTEXITCODE
}

# Ensure Ollama is running.
try {
    Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
} catch {
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) { throw "Ollama is missing. Run SETUP_AND_RUN.bat." }
    Start-Process -FilePath $ollama.Source -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 4
}

# Open separate terminals so the user can see logs and stop each service.
$backendCmd = "Set-Location '$Backend'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --host 127.0.0.1 --port 8000"
$desktopCmd = "Set-Location '$Desktop'; npm run dev"
Start-Process powershell.exe -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$backendCmd)
Start-Sleep -Seconds 3
Start-Process powershell.exe -ArgumentList @("-NoExit","-ExecutionPolicy","Bypass","-Command",$desktopCmd)

Write-Host "AETHER is starting. Keep both terminal windows open." -ForegroundColor Green
Write-Host "Backend health: http://127.0.0.1:8000/health"
Write-Host "Close the two terminal windows to stop AETHER."
