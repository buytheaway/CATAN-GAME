# Ship art pilot export

## Topology hardening - 2026-10-20

This regenerates the same experimental ship, not an additional model. Original
native source/GLB/exporter are preserved in Git at `986c99c` (also5A asset), before
the5B.2 correction. Use Git history for review; do not reset unrelated work.

Inspect the actual saved native source without saving or exporting:

```powershell
powershell.exe -NoProfile -File tools/blender/export_ship_pilot.ps1 -InspectOnly
# Optional: -SourcePath 'C:\path\to\original\ship_pilot.blend'
```

The same Store CLI opens the file in its disposable background process.
`ship_topology.py` reports positional-weld edge winding, boundaries, shared
non-manifold edges, degenerate triangles, unit/finite normals and closed-component
signed volume. It never welds or edits rendering geometry. Self intersections
are not certified. Open-component signed volume is not a physical volume.

Corrections: sail sidewall winding, inward pennant, rail inner wall/underside
enclosure for solid culling. The intentional separate inset deck stays open
(seven boundary edges). Opaque HullWood/PlayerColor now FrontSide; thin canvas
conservatively DoubleSide. Runtime ship ghost copies retain legacy DoubleSide,
opacity and ignored raycasts. No silhouette/palette/anchor/animation redesign.

Current export:13,216 bytes/215 triangles, three meshes/materials, no textures.
Source128 vertices; exported381 vertices reflect flat-normal splits. Manifest
includes named culling and source/import topology; both are validated before
success. Native source reopening and fresh-root repeated GLB export were verified
with Blender5.2.2 LTS. Corrected SHA256:
`0a6b103f64fd29bca195666e1e6ab97808f4812b2de6fec785b413a932294749`.
Native blend byte reproducibility is not claimed. Keep procedural default and
opt-in/fallback. Mixed measured performance is not a speedup/default-art approval.

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
