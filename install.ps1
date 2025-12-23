$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# pick python: prefer py launcher if exists
$py = (Get-Command py -ErrorAction SilentlyContinue)
if ($py) {
  py -3 -m venv (Join-Path $root ".venv")
} else {
  $python = (Get-Command python -ErrorAction SilentlyContinue)
  if (-not $python) { throw "Python not found. Install Python 3.10+." }
  python -m venv (Join-Path $root ".venv")
}

$venvPy = Join-Path $root ".\.venv\Scripts\python.exe"
& $venvPy -m pip install -U pip
& $venvPy -m pip install -r (Join-Path $root "requirements.txt")
Write-Host "OK. Now run: .\run_server.ps1 -Port 8000"
