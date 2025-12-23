@echo off
setlocal
cd /d %~dp0

REM Create venv if missing
if not exist .venv\\Scripts\\python.exe (
  where py >nul 2>nul
  if %errorlevel%==0 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
)

REM Install deps
.venv\\Scripts\\python.exe -m pip install -U pip >nul
.venv\\Scripts\\python.exe -m pip install -r requirements.txt

REM Run
.venv\\Scripts\\python.exe app\\main.py

endlocal
