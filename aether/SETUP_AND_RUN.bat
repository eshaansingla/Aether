@echo off
title AETHER - One-time setup and launch
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\SETUP_AND_RUN.ps1"
if errorlevel 1 (
  echo.
  echo AETHER setup did not finish. Read the error above.
  pause
)
