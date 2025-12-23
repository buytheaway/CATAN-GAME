@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

set VENV_PY=%CD%\.venv\Scripts\python.exe

:ensure_py
where py >nul 2>nul
if %ERRORLEVEL%==0 (set PYLAUNCH=py -3) else (set PYLAUNCH=python)

:ensure_venv
if exist "%VENV_PY%" goto :menu
echo [i] Creating venv...
%PYLAUNCH% -m venv .venv
if not exist "%VENV_PY%" (
  echo [!] Failed to create venv. Install Python 3.10+ and try again.
  pause
  exit /b 1
)

:menu
if "%~1"=="" goto :help

if /I "%~1"=="install" goto :install
if /I "%~1"=="server"  goto :server
if /I "%~1"=="client"  goto :client
if /I "%~1"=="demo"    goto :demo

goto :help

:install
echo [i] Installing deps...
"%VENV_PY%" -m pip install -U pip
"%VENV_PY%" -m pip install -r requirements.txt
echo [OK] Done.
pause
exit /b 0

:server
set PORT=%~2
if "%PORT%"=="" set PORT=8000

call :install_silent

echo [i] Starting server on 0.0.0.0:%PORT%
echo [i] Open browser: http://127.0.0.1:%PORT%/
"%VENV_PY%" -m uvicorn app.server:app --host 0.0.0.0 --port %PORT%
exit /b 0

:client
set HOST=%~2
set PORT=%~3
set ROOM=%~4
set NAME=%~5

if "%HOST%"=="" set HOST=127.0.0.1
if "%PORT%"=="" set PORT=8000
if "%ROOM%"=="" set ROOM=room1
if "%NAME%"=="" set NAME=Player

call :install_silent

echo [i] Starting client: %NAME% -> ws://%HOST%:%PORT%/ws/%ROOM%
"%VENV_PY%" app\desktop_v2.py --host %HOST% --port %PORT% --room %ROOM% --name %NAME%
exit /b 0

:demo
set PORT=%~2
if "%PORT%"=="" set PORT=8000
call :install_silent

echo [i] Demo: server + 2 clients (Alice/Bob)
start "CATAN Server" cmd /k ""%~f0" server %PORT%"
timeout /t 1 >nul
start "CATAN Alice"  cmd /k ""%~f0" client 127.0.0.1 %PORT% room1 Alice"
start "CATAN Bob"    cmd /k ""%~f0" client 127.0.0.1 %PORT% room1 Bob"
exit /b 0

:install_silent
REM install only if websockets import is missing
"%VENV_PY%" -c "import websockets" >nul 2>nul
if %ERRORLEVEL%==0 exit /b 0
echo [i] Dependencies not found -> installing...
"%VENV_PY%" -m pip install -U pip
"%VENV_PY%" -m pip install -r requirements.txt
exit /b 0

:help
echo Usage:
echo   RUN_CATAN.bat install
echo   RUN_CATAN.bat server [port]
echo   RUN_CATAN.bat client [host] [port] [room] [name]
echo   RUN_CATAN.bat demo [port]
echo Examples:
echo   RUN_CATAN.bat demo 8000
echo   RUN_CATAN.bat server 8000
echo   RUN_CATAN.bat client 127.0.0.1 8000 room1 Alice
pause
exit /b 0
