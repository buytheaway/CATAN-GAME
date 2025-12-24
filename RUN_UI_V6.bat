@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title CATAN UI v6

if not exist ".venv\Scripts\python.exe" (
  echo [i] Creating venv...
  where py >nul 2>nul
  if %errorlevel%==0 (py -3 -m venv .venv) else (python -m venv .venv)
)

set "PY=.venv\Scripts\python.exe"
echo [i] Python:
"%PY%" -V

echo [i] Installing deps...
"%PY%" -m pip install -U pip
"%PY%" -m pip install -r requirements.txt

echo [i] Launching UI v6...
"%PY%" -m app.ui_v6

pause
endlocal
