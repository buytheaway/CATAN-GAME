@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title CATAN Singleplayer
echo [i] dir: %cd%

where py >nul 2>nul
if %errorlevel%==0 (
  py -3.12 -V >nul 2>nul
  if %errorlevel%==0 (set "PYLAUNCH=py -3.12") else (set "PYLAUNCH=py -3")
) else (
  set "PYLAUNCH=python"
)

if not exist ".venv\Scripts\python.exe" (
  echo [i] Creating venv...
  %PYLAUNCH% -m venv .venv || goto :fail
)

set "PY=.venv\Scripts\python.exe"
echo [i] Python:
%PY% -V

echo [i] Installing deps...
%PY% -m pip install -U pip || goto :fail
%PY% -m pip install -r requirements.txt || goto :fail

echo [i] Launching UI...
%PY% -m app.main
goto :end

:fail
echo.
echo [!] FAILED. Scroll up for the real error.
:end
pause
endlocal
