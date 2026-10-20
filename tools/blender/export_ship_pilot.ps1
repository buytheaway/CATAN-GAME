param([string]$BlenderPath, [string]$OutputRoot, [switch]$InspectOnly, [string]$SourcePath)
$ErrorActionPreference = 'Stop'
$shipRepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
if (-not $OutputRoot) { $OutputRoot = $shipRepoRoot }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$shipExporter = Join-Path $PSScriptRoot 'export_ship_pilot.py'
$shipStatusDirectory = Join-Path $shipRepoRoot '.venv/test-artifacts'
[IO.Directory]::CreateDirectory($shipStatusDirectory) | Out-Null
$shipStatusPath = Join-Path $shipStatusDirectory ('ship-export-' + [guid]::NewGuid().ToString('N') + '.json')
$shipArguments = '--background --factory-startup --python-exit-code 1 --python "' + $shipExporter + '" -- --output-root "' + $OutputRoot + '" --status-file "' + $shipStatusPath + '"'
if ($InspectOnly) {
    if (-not $SourcePath) { $SourcePath = Join-Path $shipRepoRoot 'docs/design/references/blender/ship_pilot.blend' }
    $SourcePath = (Resolve-Path -LiteralPath $SourcePath).Path
    $shipArguments += ' --inspect-source "' + $SourcePath + '"'
}
$shipStore = Get-AppxPackage 'BlenderFoundation.Blender' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $BlenderPath -and $shipStore) {
    # Standard Store app activation preserves package identity. No ACL/install changes.
    if (-not ('ShipPilotStoreLauncher' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
[ComImport, Guid("2e941141-7f97-4756-ba1d-9decde894a3d"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IShipPilotActivation {
 [PreserveSig] int ActivateApplication([MarshalAs(UnmanagedType.LPWStr)] string id, [MarshalAs(UnmanagedType.LPWStr)] string args, uint flags, out uint pid);
}
public static class ShipPilotStoreLauncher {
 public static uint Run(string id, string args) {
  var instance=Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("45BA127D-10A8-46EA-8AB7-56EA9078943C")));
  uint pid; int result=((IShipPilotActivation)instance).ActivateApplication(id,args,6,out pid);
  Marshal.ThrowExceptionForHR(result); return pid;
 }
}
'@
    }
    $shipManifest = Get-AppxPackageManifest $shipStore
    $shipAppId = ($shipManifest.Package.Applications.Application | Where-Object { $_.Executable -like '*blender*.exe' } | Select-Object -First 1).Id
    if (-not $shipAppId) { throw 'Registered Blender Store application ID not found' }
    $shipChildId = [ShipPilotStoreLauncher]::Run($shipStore.PackageFamilyName + '!' + $shipAppId, $shipArguments)
} else {
    if (-not $BlenderPath) { $BlenderPath = (Get-Command blender -ErrorAction Stop).Source }
    $shipChild = Start-Process -FilePath $BlenderPath -ArgumentList $shipArguments -WindowStyle Hidden -PassThru
    $shipChildId = $shipChild.Id
}
$shipDeadline = [DateTime]::UtcNow.AddSeconds(60)
while (-not (Test-Path -LiteralPath $shipStatusPath)) {
    if ([DateTime]::UtcNow -ge $shipDeadline) { throw "Exporter timed out; inspect Blender process $shipChildId. No data is deleted." }
    Start-Sleep -Milliseconds 150
}
$shipExportResult = Get-Content -Raw -LiteralPath $shipStatusPath | ConvertFrom-Json
if (-not $shipExportResult.success) { throw $shipExportResult.error }
$shipExportResult | ConvertTo-Json -Depth 5
