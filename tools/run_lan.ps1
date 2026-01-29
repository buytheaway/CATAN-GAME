$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venvActivate = Join-Path $root ".venv\\Scripts\\Activate.ps1"

function Get-LanIPv4 {
  $candidates = Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -match '^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)'
  } | Select-Object -ExpandProperty IPAddress
  if ($candidates) {
    foreach ($pref in @('^192\.168\.', '^10\.', '^172\.(1[6-9]|2[0-9]|3[0-1])\.')) {
      $match = $candidates | Where-Object { $_ -match $pref } | Select-Object -First 1
      if ($match) {
        return $match
      }
    }
  }
  $ipconfig = ipconfig 2>$null
  if ($ipconfig) {
    $matches = [regex]::Matches($ipconfig, 'IPv4[^:]*:\s*(\d+\.\d+\.\d+\.\d+)')
    foreach ($m in $matches) {
      $ip = $m.Groups[1].Value
      if ($ip -match '^192\.168\.') { return $ip }
    }
    foreach ($m in $matches) {
      $ip = $m.Groups[1].Value
      if ($ip -match '^10\.') { return $ip }
    }
    foreach ($m in $matches) {
      $ip = $m.Groups[1].Value
      if ($ip -match '^172\.(1[6-9]|2[0-9]|3[0-1])\.') { return $ip }
    }
  }
  return $null
}

$lanIp = Get-LanIPv4
if (-not $lanIp) {
  $lanIp = "127.0.0.1"
}

Write-Host "LAN IP: $lanIp"
Write-Host "Web URL: http://${lanIp}:5173"
Write-Host "WS URL: ws://${lanIp}:8000/ws"
Write-Host "If needed, set web/.env.local: VITE_WS_URL=ws://${lanIp}:8000/ws"

$serverCmd = "& { $env:CATAN_HOST='0.0.0.0'; $env:CATAN_PORT='8000'; if (Test-Path '$venvActivate') { . '$venvActivate' } ; python -m app.server_mp }"
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $serverCmd -WorkingDirectory $root | Out-Null

$webCmd = "& { Set-Location '$root\\web' ; npm run dev -- --host 0.0.0.0 --port 5173 }"
Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $webCmd -WorkingDirectory $root | Out-Null

Write-Host "Servers starting... use tools/check_lan.ps1 to verify."
