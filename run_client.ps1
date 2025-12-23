param(
  [string]$HostIP = "127.0.0.1",
  [int]$Port = 8000,
  [string]$Room = "room1",
  [string]$Name = "Player"
)

$ErrorActionPreference = "Stop"

$venvPy = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) { throw "Нет .venv. Сначала создай/установи зависимости." }

& $venvPy app\client_cli.py --host $HostIP --port $Port --room $Room --name $Name
