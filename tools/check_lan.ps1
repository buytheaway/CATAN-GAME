$ErrorActionPreference = "Stop"

$ports = @(8000, 5173)
$fail = $false

foreach ($port in $ports) {
  $listening = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
  if ($listening) {
    Write-Host "OK: Port $port is listening"
  } else {
    Write-Host "FAIL: Port $port is NOT listening"
    $fail = $true
  }
}

try {
  $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 2
  Write-Host "OK: HTTP response from server (status $($resp.StatusCode))"
} catch {
  if ($_.Exception.Response) {
    $status = [int]$_.Exception.Response.StatusCode
    Write-Host "OK: Server responded with status $status"
  } else {
    Write-Host "WARN: HTTP check failed ($($_.Exception.Message))"
  }
}

if ($fail) {
  exit 1
}
