$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$spec = Join-Path $PSScriptRoot "CatanClient.spec"

Write-Host "[i] Building CatanClient..."
python -m PyInstaller --noconfirm --clean --distpath (Join-Path $root "dist") --workpath (Join-Path $root "build") $spec
Write-Host "[i] Done. Output: $root\dist\CatanClient\CatanClient.exe"
