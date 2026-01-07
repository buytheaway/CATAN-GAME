$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$spec = Join-Path $PSScriptRoot "CatanServer.spec"

Write-Host "[i] Building CatanServer..."
python -m PyInstaller --noconfirm --clean --distpath (Join-Path $root "dist") --workpath (Join-Path $root "build") $spec
Write-Host "[i] Done. Output: $root\dist\CatanServer\CatanServer.exe"
