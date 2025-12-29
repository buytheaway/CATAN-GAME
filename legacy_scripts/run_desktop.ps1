param(
  [string]$HostIP = "127.0.0.1",
  [int]$Port = 8000,
  [string]$Room = "room1",
  [string]$Name = "Player"
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venvPy = Join-Path $root ".\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "No .venv found. Run install.ps1 first." }
& $venvPy app\desktop_v2.py --host $HostIP --port $Port --room $Room --name $Name
