# Ship art pilot export

Run from the repository root on Windows with the existing Blender installation:

```powershell
powershell.exe -NoProfile -File tools/blender/export_ship_pilot.ps1
```

The launcher uses the registered `BlenderFoundation.Blender` Store application's
standard activation API when present. This supplies the package identity needed
to run background CLI from WindowsApps; direct execution may return Access denied.
No installation, ACL, registry, system PATH or Blender GUI scene is changed. MCP
is not required. Classic/portable installations can use:

```powershell
powershell.exe -NoProfile -File tools/blender/export_ship_pilot.ps1 -BlenderPath 'D:\Tools\Blender\blender.exe'
```

The CLI runs `--background --factory-startup --python-exit-code 1 --python
tools/blender/export_ship_pilot.py`, which creates one original deterministic
ship in a disposable scene. It writes only these pilot files:

- `docs/design/references/blender/ship_pilot.blend`
- `docs/design/references/blender/ship-pilot.json`
- `web/public/models/pieces/ship-pilot.glb`

The script intentionally regenerates those outputs from source. Do not edit the
generated blend expecting re-export to preserve manual changes; amend the source
or keep an independently named art revision. Existing terrain/building sources
are never opened or modified. A unique ignored `.venv/test-artifacts/ship-export-*.json`
records CLI completion; failures/timeouts stop the launcher without deleting data.

For a reproducibility comparison, supply `-OutputRoot` pointing to a fresh temporary
directory. Compare the resulting GLB SHA-256 with the repository output. Blender
5.2.2 LTS was verified with two separate output roots: identical GLB bytes. The
exporter also reloads its GLB in the disposable process and checks triangles,
materials and world bounds. Native `.blend` binary identity across saves is not
claimed. Material/exporter changes across Blender versions can change GLB bytes;
record and review them rather than updating a hash silently.

The pilot has three opaque untextured PBR materials: `HullWood`, `CanvasIvory`
and exact `PlayerColor`. Only `PlayerColor` receives ownership colors at runtime.
Source Blender Z becomes glTF/Three Y; X remains the hull axis. Pivot is `(0,0,0)`;
Three bounds are approximately `[-.40,0,-.14]` to `[.40,.535,.14]`. ShipBody applies
only the existing edge-length X scale (`length * .88`); Ship3D keeps original
placement/yaw and ShipFleet3D keeps construction/movement/rocking. No baked
animation, embedded camera/light, external resource or texture is exported.

Normal gameplay still defaults to Procedural. Select **Ship model → GLB · pilot**
locally to compare; loading/failure uses the original procedural body. This is a
renderer preference, never a server rule, snapshot field or persistent game option.

Plan and current measured limits: [Board3D](../../docs/obsidian/plans/board3d.md).
