param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venvPy = Join-Path $root ".\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "No .venv found. Run install.ps1 first." }
& $venvPy -m uvicorn app.server:app --host 0.0.0.0 --port $Port
