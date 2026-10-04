---
tags: [catan, plan, board3d]
updated: 2026-10-04
---

# Board3D Phase 1 — Visual Foundation

[[Project State]] · [[Design System]] · [[React интерфейс]] · [[Карты и сценарии]]

Status: Completed — 2026-10-04. READY FOR CHECKPOINT. Scope authorized by the user's Board3D Phase 1 request.

## Audit before implementation

GamePage receives match.state from App/WSClient and passes the same object to BoardView. Python GameState → to_player_dict → _snapshot_state → match_state → WSClient.onMatchState → App.setMatch → GamePage is the existing data path. Commands remain GamePage/BoardView → WSClient.sendCmd → server/engine → new snapshot.

Snapshot already provides tiles with q/r, center, terrain and nullable number; size, vertices, edges, ports, occupied_v/e/ships, robber_tile/robbers and pirate_tile. Tile IDs are array indices, vertex IDs are dictionary keys and edge IDs are vertex pairs. No backend changes or graph reconstruction are required. BoardView.types.ts currently omits q/r and null from number; extend only that description, retaining compatibility with existing test fixtures.

Existing SVG BoardView also contains placement/robber/ship handlers. Preserve it intact; add a BoardRenderer selector above both renderers, defaulting to 2D. Board3D receives only snapshot geometry/occupancy and visual callbacks, without WSClient, command handlers, legal/rule calculations or a second game model.

Git baseline: clean working tree at f754457 (Docker commit), hardening-phase-1 points to 3cd8812. The user names infrastructure-phase-1, but that tag is absent locally; this task does not create it.

## Architecture and coordinates

GamePage → BoardRenderer → BoardView OR lazy-loaded Board3D → R3F/Three scene. Both renderers consume the same state. A read-only render projection computes mesh positions and bounds, not game decisions.

coordinates.ts owns conversion: server X / state.size → Three X; server Y / state.size → Three Z; visual elevation → Three Y. Server centers take priority; axial q/r can supply a missing center. Snapshot graph/IDs stay authoritative. Hex radius becomes one scene unit. Road midpoint, length and rotation derive from existing edge endpoints. Bounds include actual tiles/vertices/ports and camera framing adapts to aspect ratio; there is no fixed list of 19 positions.

## Implementation

1. Install exact compatible dependencies: @react-three/fiber 8.18.0 (React 18), Three.js 0.180.0 and matching @types/three 0.180.0. Keep React/Vite/TypeScript versions. OrbitControls comes from Three itself; no drei or external assets. The initially checked Three 0.186.1 emits deprecation warnings for Fiber 8's Clock and the selected soft-shadow API; 0.180.0 keeps this React 18 stack compatible without patching libraries.
2. Build pure coordinates/materials/render projection and behavior tests for IDs, centers, bounds, terrain and player colors.
3. Add shallow hex meshes, eight procedural terrain hints, readable number tokens and actual edge-attached port labels.
4. Add minimal owner-colored settlements/cities/roads. Small ship/robber/pirate placeholders are allowed only locally, with no command logic.
5. Add neutral fill/directional light, restrained shadows, bounded orbit/zoom, board auto-fit and Reset Camera. Use demand rendering; clean up controls/textures and let R3F dispose declarative resources.
6. Integrate 2D/3D Experimental selector with a constrained responsive canvas. Hover and click expose only the original tile index; game actions requiring map interaction stay in 2D.
7. Verify web tests, TypeScript, production build, Docker build and actual browser flow on Base Standard and Seafarers Gold Haven, including switch-back/gameplay and resizing.
8. Update Project State/Design System and existing affected UI notes; check references and scope boundaries.

## Phase 2 boundary

Build/upgrade/ship movement, robber/pirate targets and victims, port interaction, complete server-produced legal availability and controller migration are deferred. No Python, rules, map JSON, protocol/serialization/reconnect, Docker architecture, lobby/trade/development/settings redesign or persistence changes.

Clean modern digital tabletop is the visual direction. Fantasy/MMORPG/medieval tavern/gold-frame references remain historical and their decorative direction is rejected.

## Verification

Verified 2026-10-04 on Docker Desktop Linux containers and actual Chrome 154 (Windows, ANGLE/NVIDIA RTX 5050). 37 web tests passed (25 existing + 12 new); TypeScript and production build passed. Docker production build used clean npm ci and served the lazy 3D chunk through existing Nginx; final compose down removed both services/network with exit 0 for both containers. Test Compose is stopped. React/Vite/TypeScript and all existing lockfile package versions stayed unchanged.

Base Standard: two independent React browser contexts, Host/Join/Start, 2D default, all 19 hex meshes/terrain/centers/numbers/ports compared with live snapshot; click/hover on each original tile index sent no cmd and changed no tick. Orbit/zoom/reset and 1440×1000, 1280×720, 1024×768 layouts passed without horizontal overflow. Switch-back preserved 2D setup placement; eight placements plus Roll reached tick 9 on both clients. Four settlements/four roads matched the scene. Assets loaded, no page errors or console warnings.

Seafarers Gold Haven: live protocol host set the preset, React participant joined and used normal player-specific snapshots. 19 tiles, 4 sea, 2 gold, 9 ports and pirate checked; eight placements and Roll reached tick 9, return to SVG passed. No browser errors/warnings. Screenshots of both production maps were inspected visually.

Additional test snapshots were built by the unchanged Python engine, saved only outside the repository and delivered by mocked browser WebSocket: one city/ship fixture cross-checked against 2D and Three mesh IDs/positions; an offset non-preset 50-hex map fit correctly. No runtime map JSON/generator was added. These fixtures demonstrate rendering, not gameplay correctness of the test arrangements.

Demand rendering produced zero new idle frames. Typical main-pass calls: 190 for Base, 184 for Gold Haven, 352 for test 50. Twenty observed CPU render submissions for 50 hex averaged ~2.4ms (max ~4.3ms) on the verified GPU; not an FPS guarantee or low-end benchmark. Unmount returned geometry/texture counts to zero and released the WebGL context. Controls/resize/state updates do not create a continuous React animation loop.

Limitations: 3D is view-only; build/robber/pirate interaction stays in SVG. Lazy 3D chunk ~874KB (~235KB gzip) triggers Vite's existing size warning threshold. Mobile, full games and broad WebGL/device compatibility are not certified. Python pytest/scenarios were not repeated because all Python/gameplay files stayed unchanged. Existing scenario baseline remains historical 348/508.

During map switching the unchanged LobbyPage effects could revert mapId to an older room_state and send set_map after start. This happened before Board3D was imported. No lobby fix was included; protocol-configured host was used for the live Seafarers check. This remains separate work and is not hidden by weakening assertions.

No commit/tag created automatically. Proposed commit: feat: add experimental 3d board renderer; tag: board3d-phase-1.
