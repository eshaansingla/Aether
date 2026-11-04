@echo off
title AETHER - Start
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\START_AETHER.ps1"
if errorlevel 1 (
  echo.
  echo AETHER could not start. Run SETUP_AND_RUN.bat first or read the error above.
  pause
)
