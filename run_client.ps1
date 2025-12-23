param(
  [string]$HostIP="127.0.0.1",
  [int]$Port=8000,
  [string]$Room="room1",
  [string]$Name="Player"
)
.\.venv\Scripts\python.exe app\client_cli.py --host $HostIP --port $Port --room $Room --name $Name
