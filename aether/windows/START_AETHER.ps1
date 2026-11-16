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

# AETHER calls a cloud AI API (OpenAI, Groq, or Gemini) rather than a local model — warn
# early if no key looks configured for whichever provider backend\.env selects, since a
# missing key otherwise only surfaces later as "the AI API isn't reachable" inside the app.
$envFile = Join-Path $Backend ".env"
if (Test-Path $envFile) {
    $envText = Get-Content $envFile -Raw
    $provider = if ($envText -match 'AETHER_PROVIDER\s*=\s*(\S+)') { $matches[1] } else { "groq" }
    $keyName = @{ openai = "OPENAI_API_KEY"; groq = "GROQ_API_KEY"; gemini = "GEMINI_API_KEY" }[$provider]
    if ($keyName -and -not ($envText -match "$keyName\s*=\s*\S+")) {
        Write-Warning "$keyName looks empty in backend\.env for provider '$provider'. AETHER will start, but AI replies/document generation will fail until a key is set."
    }
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
