---
tags: [catan, plan, board3d]
updated: 2026-10-18
---

# Board3D

## Visual Phase 3 — construction feedback plan

**Implemented/verified; READY FOR CHECKPOINT, 2026-10-18.** Phase 2 checkpoint `f315519f0d06cf5bf131f9bc2247e82c1c3abc64` is published; exact upstream hash verified. The ship rejection assertion now compares both full personal snapshots and uses explicit property existence. Rerun: 323 frontend tests, six ship visual groups and seven real two-client ship/PostgreSQL groups passed. Phase 3 remains uncommitted/unpushed.

Affected path: existing authoritative Python executor/COMMIT/public snapshot → React GamePage → BoardRenderer → Board3D → Road3D/Settlement3D/City3D → PieceVisual → existing GLB/procedural fallback. Gameplay/controller/targets and server remain unchanged. Pre-change audit: `usePieceFeedback` ran inside the 3D mount with generic 260 ms scale feedback, without tick/fresh-object recovery fencing or a distinct city-upgrade transition. The implementation below extends this mechanism rather than adding another animation scheduler.

Implemented: existing `pieceFeedback.ts` now observes public `occupied_e`/`occupied_v` plus match key/tick/connection above the renderer toggle. Adjacent additions identify roads/settlements; same-owner1→2 identifies a city upgrade. Hydration, stale/duplicate/coalesced/ambiguous changes and first fresh reconnect frame establish quiet baselines. `PieceVisual` reuses the existing loader/material pool/fallback and finite R3F invalidation: road-axis growth450 ms, settlement emergence550 ms, city emergence700 ms plus a300 ms shrinking ghost settlement. The echo has no vertex/level/target identity and ignores raycasts. Original anchors/rotation/owner colors remain fixed. No per-frame React updates, new continuous interval, particles, model replacement or private terrain inputs. Reduced motion and **Construction effects → Motion/Still** clear feedback, consume baselines and restore final transforms without replay. Ship/Fog controls remain independent. Settled refs skip frame work, async GLB loading never restarts cue timestamps, and echo clones use pooled ghost materials/dispose=null.

The planned public-only preview extension, screenshots/video, matching committed/current A/B, lifecycle/pose tests and owning two-client construction/recovery checks are complete within the limits below. Full Python/scenarios were not required because production backend did not change. Preserve graph, accounts/data and gates; do not commit/push Phase 3.

### Construction verification and measured limits

Verified2026-10-18: **343/343 frontend tests** (323 baseline+20 building cases), TypeScript and production build pass. Three old feedback/pose assertions were migrated to the superseding public API while retaining asset/contact/material checks. Twenty new cases cover authoritative additions/upgrade, ambiguity/removal/owner change, duplicate/stale/gap, first-fresh reconnect/new match, closed public inputs and finite/static/echo transforms. Lazy Board3D is977.16 kB; existing chunk warning remains. **Three focused PostgreSQL fixture tests** pass, checking legal targets/accepted copied command/conservation/baseline ship without running gameplay during recovery. No production Python/protocol/rules/codec/schema/gates/auth/assets/dependencies changed; full Python/scenarios/Docker not rerun.

Chrome155.0.8059.80: seven real construction visual groups pass (exact/reversed edge anchor, settlement/city echo, duplicate/stale/error, simultaneous/rapid sequence, static/reduced, fresh reconnect/SVG/new epoch, ships/Fog/resources/raycast/idle/desktop). **12 final-production two-client WS/PostgreSQL groups** pass across actual Road/Settlement/City UI: both complete personal states unchanged after invalid commands with explicit property checks; accepted effects appear on both clients; receipts do not replay; refresh/native reconnect/backend restart restore exact state and no effects. Real road discovers Fog/Gold; real baseline ships remain. Six expected refusal warnings occur during deliberate restarts; no unexpected JS/console errors. Original13 SVG/Fog renderer groups and six ship visual groups pass again. These are prepared/funded fixtures, not competitive/natural full matches; live internal Fog rematch is not supported by this test capability, while presentation new-match/rematch fencing is tested with a new public epoch.

Performance primary report compares exact published `f315519f0d06cf5bf131f9bc2247e82c1c3abc64` UI blobs to current source using `git show`, never checkout/reset. One Chrome/GPU, matching public occupancy/tiles/camera/DPR/shadows/viewport; strict scene fingerprint and steady counts equal. Same1440×900 window/1186×723 Canvas/DPR1/ANGLE D3D11/RTX5050 Laptop. Before/after/after/before,12 warm renders,60 GPU-synchronous `render+finish` and30 CPU submission samples per reading. Medians below are the mean of the two medians; p95 is the worse reading. CPU submission contains driver/GPU stalls and is not isolated CPU frame time or sustained FPS.

| Scene | GPU median before→after ms | GPU p95 before→after ms | CPU submit before→after ms |
| --- | --- | --- | --- |
| 7 normal | .85→1.30 | 1.50→2.80 | 1.15→1.20 |
| 7 reduced | .90→.80 | 2.00→1.80 | 1.20→1.15 |
| 7 static | .80→.90 | 1.40→2.60 | 1.15→1.15 |
| 50 normal | 3.75→3.60 | 5.10→4.40 | 4.35→3.90 |
| 50 reduced | 3.60→3.70 | 4.20→4.60 | 3.85→3.95 |
| 50 static | 3.75→3.70 | 8.10→6.90 | 6.15→4.40 |

Counts unchanged:7 tiles/one ship =222 calls,29,310 triangles,151 geometries,6 textures;50 tiles/24 ships =1387 calls,180,310 triangles,150 geometries,17 textures. Ambient12–13 frames/s remains shared Fog/ships; reduced/all-still0. Ship-only12fps before and after finite settlement; no idle scene React commits/resource churn. A transient upgrade adds a pooled settlement clone for≤300 ms visible, unmounted when700 ms cue expires; no permanent geometry is added. **Primary small-scene normal GPU increase+.45 ms is recorded, not hidden or called an optimization.** Repeat measurement and low-end/mobile/battery limitations must be considered; 50-static CPU variance alone precludes an isolated CPU improvement claim.

One bounded full repeat used the unchanged script/source and a separate output folder, preserving the primary result. All configuration/resource/idle assertions pass again. Repeat GPU medians:7 normal **.75→.80 ms**, reduced1.15→.80, static.80→.75;50 normal **3.65→3.65 ms**, reduced3.65→3.70, static4.05→3.65. Thus the primary+.45 ms small-scene increase did not reproduce (+.05 ms repeat). Both current and baseline timings vary (including baseline7 reduced and50 CPU submission); report both runs without cherry-picking, optimization or mobile/FPS claims. Repeat evidence: `%TEMP%/catan-buildings-visual-phase3-repeat/paired-performance.json`.

Preview: `node web/e2e/buildings-visual-demo.cjs` → `http://127.0.0.1:18775/?demo=1&buildings=1`. Synthetic PUBLIC7/50 scenes with original GLBs, road/settlement/city/sequence/together/ship/Fog/reduced controls. Reset consumed targets before replay; display fixtures do not execute rules or authorize real gameplay. Existing loopback static server serves temp bundle and public assets only. [Reproduction](../../../web/e2e/README.md#visual-phase-3--construction-preview-and-verification).

Evidence outside Git: `%TEMP%/catan-buildings-visual-phase3/{before,after,paired-performance}.json`, before/after PNGs and WebM path in `after.json`; `%TEMP%/catan-buildings-phase3-live-final/report.json` (three cases/12 groups), `catan-buildings-phase3-fog-rendering/report.json`, `catan-buildings-phase3-ships/after.json`. Recording is in a separate context, excluded from timings. No trusted assignments/recipes/private manifest/seat proofs are served or committed. User graph edits, accounts, matches and database volumes remain preserved. Phase3 remains uncommitted/unpushed; no tag, Robber/Pirate animation, backend feature or next phase.

Final source was frozen before final production/live acceptance; the seven-group public visual runner also passed again after the settled-ref/userData refinements. Preview stays running independently; task-started disposable PostgreSQL is stopped afterward without removing databases or volumes. Graph remains outside the index; unrelated scale changes observed during the task are retained, with no graph edit/reset by this task.

Intended Phase 3 diff: **22 files**, excluding user graph. Runtime **+166/−75 lines**.

- Runtime (6): `web/src/board3d/{Board3D.tsx,PieceVisual.tsx,Pieces3D.tsx,pieceFeedback.ts,board3d.css}`, `web/src/components/BoardRenderer.tsx`.
- Tests/preview (10): `tests/{building_visual_support.py,test_building_visual_fixture.py}`, `web/e2e/{fog-fixture.tsx,buildings-compare.cjs,buildings-live.cjs,buildings-visual-demo.cjs,buildings-visual.cjs}`, `web/tests/{piece-assets.test.mjs,buildingVisual.test.mjs,fixtures/publicBuildings.ts}`.
- Documentation (6): this plan, `Project State.md`, `React интерфейс.md`, `Design System.md`, `Стили и визуальные границы.md`, `web/e2e/README.md`.

## Visual Phase 2 — ships, implementation plan

**Historical completed verification, 2026-10-18; published as `f315519f0d06cf5bf131f9bc2247e82c1c3abc64`.** Visual Phase 1 was checkpointed/published first as `608f14ed349f237a1ae51873864246fff40f9d6f`, normal push/exact upstream hash verified, exactly 20 intended files; only the user graph remained outside the commit. Phase 2 graphics and assertion correction were committed/pushed separately before Phase 3; no tag.

Audit: committed `occupied_ships` becomes `createRenderModel().ships` and five procedural meshes in `Ship3D`; the existing eleven GLBs contain terrain/buildings/roads, no ship asset. Original edge endpoints, owner colors and orientation are reusable. `move_ship` public events carry actor/type/tick/id but **no route or from/to IDs**. Do not add protocol fields just for animation.

Implemented: [shipFeedback.ts](../../../web/src/board/shipFeedback.ts) lives above the 2D/3D toggle. It observes public occupancy and closed event id/tick/type/actor fields, never tiles, resources, rules or commands. New adjacent live-tick additions receive **550 ms** emergence. A move requires adjacent ticks, one fresh public move event and exactly one removed/added edge of its actor. Ambiguous/coalesced changes snap safely without guessed identity. Movement uses a **350 ms** source echo and **900 ms** destination emergence (150 ms arrival lead-in), never a fabricated transit path. Echoes are presentation-only, absent from occupancy/targets/player counts. Refresh/reconnect/new match establish a baseline; cached reconnect data waits for a fresh occupancy object. Duplicates/stale/rejected frames do not animate. Static/SVG/reduced modes keep baselines current and clear cues. One expiry timer releases finite cues; no per-frame React state.

Rendering: [ShipFleet3D.tsx](../../../web/src/board3d/ShipFleet3D.tsx) accepts public render edges/topology/colors and cues, not a GameState or terrain. Original edge anchors/owner colors/lengths/orientation remain fixed; only an inner visual group bobs (±.008), pitches (±.009 rad) and rocks (±.018 rad). The source echo respects the graph's original endpoint ordering, even for reversed public tuples. All ship-body meshes ignore raycasts; legal targets/controller own interactions. The five existing procedural meshes/material pool are reused, including ghost materials for departure; no GLB/texture/dependency is added. One fleet ref update handles all pieces. **SceneMotion** shares a single **12 Hz** demand clock with Fog; finite feedback uses useFrame until its deadline. Hidden document/disconnect/reduced motion stops the clock. **Ship effects → Still** cancels finite/ambient motion and restores identity transforms; Fog's still preference remains independent. Base decorative boats and SVG stay unchanged.

### Ship visual verification and performance

Checkpoint verification, 2026-10-18: corrected the live rejection assertion to use explicit property existence (owner `0` is valid) and compare **both complete personal snapshots** before/after the rejected command. Existing ACK/tick/privacy/no-animation assertions remain. Rerun: 323 frontend tests, six ship visual groups and seven real two-client ship/PostgreSQL groups pass, including duplicate receipts and refresh/restart. No production behavior changes in this correction.

**323 frontend tests pass** (301 existing +22 new ship cases), TypeScript and production build pass; the existing large lazy Board3D warning remains (~977 kB). New cases cover accepted-only construction, event-backed movement, ties to owner/edge/tick, ambiguous/coalesced/duplicate/stale/reconnect/match fences, malformed input, no private-field access, finite/static transforms and public fixtures. **112 focused Python tests pass, exit 0, 27.93 s**: 111 existing raw WS/HTTP privacy/projection/beta-policy cases plus a new real-engine validated browser-movement fixture. Production Python/protocol/rules/codec/schema/gates/auth/deployment/assets/dependencies are unchanged; full Python/scenarios/Docker were not repeated.

Chrome **155.0.8059.80**: six ship preview groups, 13 SVG/Fog renderer groups and six Fog visual groups pass. Construction and Fog reveal coexist; ship meshes never intercept targets; move source/destination orientation is exact, including reversed edge tuples; duplicate/error/static/reduced/reconnect/SVG/refresh paths do not replay; idle has no scene React commits/resource churn; multiple effects settle correctly and desktop resize is safe. **Seven real two-client ship WS/PostgreSQL groups** pass for paid build and move: invalid command atomicity, both-client effects, actual Gold discovery, durable duplicate receipts and pending refresh/reconnect/backend restart. The original **14 live Fog groups** also pass, including setup Road, paid Ship, account Continue and normal public gate refusal. These are prepared/funded fixtures, not new natural full matches or competitive/scenario certification. Four expected WS refusals per runner occur during intentional restarts; no unexpected JS/console errors.

Performance uses the same PUBLIC 7-hex/one-ship and 50-hex/24-ship scenes, Chrome/ANGLE D3D11/RTX 5050 Laptop, viewport 1440×900/Canvas 1186×723. True pre-edit `before.json` is retained. Early standalone 50-hex timings ranged ~9.6→3.8 ms without any geometry change, so that difference is **not attributed to this code**. A controlled **before/after/after/before** comparison in one Chrome reads the `608f14e` frontend blobs with `git show` into a temporary bundle, without checkout/reset or changing the working tree. One page at a time, same assets/camera/DPR/shadows; 12 warm renders, 60 `gl.render + gl.finish()` samples and 30 CPU-submission samples per reading. Table shows the mean of two medians; p95 is the worse of the two runs. WebGL CPU submission includes driver/GPU stalls and is not isolated CPU frame time. These are diagnostic samples, not sustained FPS or an optimization claim.

| Scene | GPU median before→after ms | GPU p95 before→after ms | CPU submit before→after ms | Calls /triangles, unchanged |
| --- | --- | --- | --- | --- |
| 7, normal | .70 → .80 | 1.60 → 1.30 | 1.05 → 1.00 | 218 /27646 |
| 7, reduced | .75 → .75 | 1.60 → 1.30 | .95 → 1.15 | 218 /27646 |
| 50, normal | 3.50 → 3.50 | 5.10 → 4.40 | 3.70 → 3.70 | 1383 /178646 |
| 50, reduced | 3.55 → 3.80 | 5.00 → 5.80 | 5.30 → 3.95 | 1383 /178646 |

Paired geometry/texture counts are identical (147/6 small, 146/17 fresh large Canvas). Ambient target is 12 Hz (roughly 12–13 frames per one-second sample), shared with animated Fog rather than doubled. With only ship motion enabled, previously idle boards now render periodically; **both effects static or reduced motion: 0 idle frames**. A moving echo temporarily adds five pooled meshes for ≤350 ms; steady geometry/triangles/calls stay unchanged. Mobile/low-end GPU/battery behavior remains unverified; static mode is available.

Preview: `node web/e2e/ships-visual-demo.cjs` → `http://127.0.0.1:18773/?demo=1&ships=1`. Real Board3D, public synthetic land/sea/Fog boundary, stationary/multiple ships, Construct/Move/Reset/50 tiles/reduced-motion controls. It simulates public committed frames, not an engine/legality evaluator. Actual legality/rewards/receipts/recovery are checked separately through the owning live server. No trusted recipe/private assignment/credential endpoint or public admission is exposed. Instructions and reproducible A/B — [browser README](../../../web/e2e/README.md#visual-phase-2--ships-preview-and-verification).

Evidence: `%TEMP%/catan-ships-visual-phase2/{before,after,after-performance,paired-performance}.json`, before/after PNGs and the WebM path in `after.json` (recorded in a separate context, excluded from performance measurements); `%TEMP%/catan-ships-phase2-live-final/report.json`, `catan-ships-phase2-fog-live/report.json`, `catan-ships-fog-regression/report.json`, `catan-ships-phase2-fog-visual/after.json`; `.venv/test-artifacts/ships-web-final.log`, `ships-python.log`. Private fixture bindings stay outside served/tracked files. Remaining limits: movement without unambiguous public evidence snaps; no transit route/ship ID is invented, original placeholder art is retained, one desktop GPU measured. No production admission change, natural full-match rerun, mobile claim or next phase.

Diff scope: **31 intended files**, excluding the untouched pre-existing user graph; runtime **+257/−35 lines**.

- Runtime (10): `web/src/board/shipFeedback.ts`, `web/src/board3d/{Board3D.tsx,FogVisual.tsx,Pieces3D.tsx,SceneMotion.tsx,ShipFleet3D.tsx,board3d.css,shipMotion.ts}`, `web/src/components/{BoardRenderer.tsx,GamePage.tsx}`.
- Tests/preview (14): `tests/{fog_live_support.py,test_ship_visual_fixture.py}`, `web/e2e/{fog-fixture.tsx,fog-live.cjs,fog-preview.css,fog-rendering.cjs,fog-visual-demo.cjs,fog-visual.cjs,ships-compare.cjs,ships-live.cjs,ships-visual-demo.cjs,ships-visual.cjs}`, `web/tests/{shipVisual.test.mjs,fixtures/publicShips.ts}`.
- Documentation (7): this plan, `plans/seafarers-fog.md`, `Project State.md`, `React интерфейс.md`, `Design System.md`, `Стили и визуальные границы.md`, `web/e2e/README.md`.

Historical Phase 2 task-end note: its preview ran independently of PostgreSQL and the task-started disposable PostgreSQL was stopped without dropping databases/volume. No user services/accounts/matches/graph were reset. Phase 2 is now committed; Phase 3 above is the uncommitted task.

[[Project State]] · [[Design System]] · [[React интерфейс]] · [[Карты и сценарии]]

**S2B-2B.3A follow-up, 2026-10-12:** Board3D supports sanitized public Fog tiles, uniform procedural unknown meshes with no actual terrain asset/userData, explicit known-coast/port predicates and finite committed reveal feedback shared with SVG. Existing terrain/building GLBs, logical hit geometry/IDs/controller and camera implementation remain. Historical .3A public-fixture verification: 269 web/TS/build, 13 Chrome groups including real GLBs and 50 tiles. **Public Fog DISABLED.** Subsequent .3B (2026-10-16) verifies unchanged Board3D/SVG against actual scoped live WS/PostgreSQL/Chrome, shared discoveries and pending reward refresh/restart; no renderer redesign. This supersedes historical pre-Fog rendering scope below. Details — [[plans/seafarers-fog]], [[React интерфейс#Internal live Fog acceptance — S2B-2B.3B]].

## Product / UX / Visual Polish — Phase 3B

Authorized scope (2026-10-08): integrate the finalized settlement/city/road GLBs from Phase 3A, improve legal build previews/cancellation/feedback, without editing assets, Blender sources, Python, protocol, persistence/auth or Docker. This is a renderer integration, not a new controller.

Pre-change audit: `Pieces3D.tsx` owns all three procedural visuals. `model.ts` preserves occupied_v/occupied_e IDs; server XY maps to Three XZ. Buildings anchor at TILE_TOP=.26, roads at TILE_TOP+.06 with local X along their original edge and length scaled by the real endpoint distance. All eight finalized terrain bases share a rim top at .218333 after their existing terrain transform. Piece GLBs already have Y=0 contact: use one presentation contact offset to that rim, subtract the historical extra .06 only inside the road visual; never apply the terrain asset's +.11 source correction to pieces. Keep the anchors and independent hit meshes unchanged.

Implementation plan:

1. Cache one GLTFLoader promise per piece type; clone only scene nodes, share geometry and preserve procedural loading/error fallback. Recolor only PlayerColor via the existing Canvas resource lifetime; keep neutral source materials immutable, clone neutral opacity only for ghosts. Decorative piece meshes never raycast.
2. Lift the renderer-local target hover to Board3D so a legal City preview replaces its settlement visually. Legal lists, action/selection, setup/free-road payloads and callbacks remain controller-owned. Use the same final geometry for ghosts and confirmed pieces.
3. Detect only newly committed occupancy/upgrade changes for short finite ref-based appearance feedback. Initial mount, reconnect, rematch, color changes and 2D/3D switching do not replay historical construction. Respect reduced motion, preserve logical transforms and avoid React updates per frame.
4. Keep dock/cost UI compact. Improve build-specific disabled explanations from existing snapshot/presentation data and Escape cancellation through existing callbacks, preserving mandatory setup and choice flows.
5. Run full web tests/TS/build plus focused asset/material/transform/preview/confirmation tests. Verify the requested Base/Seafarers/refresh/rematch/Test Mode/missing-asset cases in real Chrome against the existing isolated fixture server; record fixtures and limits explicitly. Update existing Project State/UI/design notes after verification.

**Completed and verified 2026-10-08. READY FOR CHECKPOINT.** No GLB/Blender/Python/protocol/dependency/Docker edits. `pieceAssets.ts`, `PieceVisual.tsx` and `pieceFeedback.ts` implement the plan through existing Pieces3D/resources/preview/targets; GamePage and BoardRenderer pass only matchKey/connected. BoardControls adds existing-data disabled reasons and guarded Escape; existing controller, server legality, commands and ACK handling remain authoritative.

Contact verification against all eight real terrain GLBs established rim Y=.218333. Buildings/roads retain original .26/.32 roots, XZ, length/orientation and IDs; only inner visuals move to that rim. City hover keeps its settlement mounted but invisible. Procedural terrain loading/error top and the legacy coastline strip cap are also aligned to the common rim so they do not bury the lower GLB foundations. All hit meshes stay on their prior coordinates. Loading/missing pieces preserve procedural commands, ownership and contact; failed loads are bounded/warn once. Shared original materials/geometries are immutable; Canvas-owned color/ghost clones are disposed through existing resource leases.

Tests: **204/204 web tests** (187 baseline + 17 new cases), TypeScript and production build. New tests cover asset/concurrent/failing cache, six colors and neutral/ghost isolation, real raycast non-interception, GLB/contact/road/fallback transforms, legal own-city replacement/cancellation, committed/rejected/reset feedback, finite/reduced appearance, disposal and controller rejection/retry. 123 protected runtime/assets/dependency files retain pre-task SHA256; all 11 dist GLBs match source.

Browser: [building-pieces.cjs](../../../web/e2e/building-pieces.cjs) passes **10 groups/all 20 requested acceptance conditions**, 60 real command attempts/6 intentional rejections and 9 layout checks. Actual Chrome 154 + production dist + unchanged FastAPI/WS fixture server: natural Base and Gold Haven first/second settlement/roads, coastal setup, Roll/End; paid City/road/settlement; legal ghosts/Escape/text-input safeguard; Road Building two free roads before Roll; rejected coordinate/unaffordable upgrade leaves state and existing visual nodes unchanged; two colors; refresh/reconnect; orbit/zoom/reset/2D↔3D/cache reuse; host Test Mode; game_over/rematch and disconnected-host three-player pid/color remap; reduced motion; all three piece GLBs missing and all eight terrain GLBs missing. Gold verifies existing setup road next to a newly placed ship, a separate paid road, ship movement/pirate and mixed terrain contact. It does not invent a legal adjacent paid road when the current fixture's coastal target has none.

Base/Gold and missing-terrain Base are checked at 1920×1080, 1440×900 and 1280×720 with no HUD overlap/visible-piece clipping. Screenshots and `verification.json`, `baseline.json`, `performance-after.json` are outside the repository in `%TEMP%/catan-building-pieces-phase3b/`; inspected City ghost, Base/Gold 1280 and missing-terrain captures are actual browser output. No JS/WebGL errors or unexpected warnings; intentional missing-asset warnings and the fixture's existing auth DB-disabled `/api/auth/me` 503 are expected.

Approximate performance, RTX 5050 Laptop, 1920×1080, 20 warm GPU-completed renders per map:

| Map | Before → after median | Before → after draw calls | Before → after triangles |
| --- | --- | --- | --- |
| Base Standard | 3.45 → 3.55ms | 1152 → 1142 | 276,422 → 282,394 |
| Seafarers Gold Haven | 3.80 → 3.80ms | 1064 → 1054 | 233,726 → 239,698 |

Diagnostic `gl.finish()` timings use the same presets/piece types/counts but separately generated room layouts; they are not a controlled GPU benchmark or sustained FPS certification. No additional idle animation is introduced by pieces; existing capped Base ambient boats remain, Seafarers returns to demand-idle. No decimation/instancing/asset redesign. Low-end/mobile/50-hex performance remains unverified; lazy Board3D is ~947kB and retains Vite's size warning.

Limits: funded/dev/results states are prepared by the existing engine initializer, while natural setup/Roll/End run real unprepared games; this is not a full natural-match or account/PostgreSQL acceptance run. Backend pytest/scenarios/Docker were not repeated because no backend/deployment code changed. No confirmed new blocker. Audio, terrain/asset optimization, Seafarers gameplay hardening and other gameplay/UI work remain outside this completed task. Current behavior — [[Project State]] and [[React интерфейс#Building GLBs / build feedback — 2026-10-08]].

## Terrain GLB integration — visual scope

Scope: integrate the eight finalized assets in `web/public/models/terrain/`, without changing those files or their Blender sources. No rules, snapshot, controller, networking, authentication or deployment changes.

Audit: `model.ts` projects the original snapshot IDs; `coordinates.ts` converts server XY to Three XZ. `HexTile3D` currently uses its simple hex body for tile raycasting, while `TerrainHints` ignores raycasting. Vertex/edge targets are separate in `InteractionOverlay3D`; pieces use the original vertex/edge anchors. There is no board-level corrective transform. Terrain decoration and the surrounding `DecorativeOcean` are static; existing finite dice/robber/event animations are independent of terrain decoration.

Integration plan:

1. Keep the existing logical hex geometry and callbacks. Replace only its visible body/decor with a reusable `TerrainHexVisual`; visual GLB meshes never raycast.
2. Use the installed Three `GLTFLoader`, one cached load per terrain type. Clone scene nodes once per mounted hex, sharing geometry/materials; preserve procedural terrain as loading/error fallback.
3. Use one common transform: scale `1 / 1.2`, rotation Y `π / 2`, source-space Y correction `+0.11` (world offset `0.11 / 1.2`). The assets are flat-top; the logical board is pointy-top. Tile centers and game IDs stay unchanged.
4. Preserve number tokens and feedback, with the smallest shared presentation adjustment needed to keep them visible over the taller decor. Keep structures, interaction targets and decorative ocean on existing anchors.
5. Verify mappings, caching/failure fallback and common transforms; run all web tests, TypeScript and production build. In Chrome, compare Base Standard and Seafarers Gold Haven, placement/movement, hover, camera and reconnect; keep screenshots and measurements outside the repository.

Completed and verified **2026-10-07**. No dependencies added; installed Three 0.180.0/Fiber 8.18.0 remain. Source GLBs and all Blender originals/backups are unchanged. Cached assets live for the page lifetime (at most eight); primitives do not dispose shared resources on hex removal. Each Canvas retains its own renderer/GPU lifecycle.

Number-token geometry, coordinates and number/pip content are preserved. A shared depth-independent badge layer prevents Mountains/Fields from hiding the tokens; no arbitrary terrain-specific token heights or GLB material edits. Tile feedback uses a thin hex ring over the original logical footprint. Vertex/edge targets, pieces and robber/pirate anchors/animations are unchanged. Only conservative visual camera heights increased where GLB relief exceeds the old procedural hints.

Validation: 169/169 web tests, TypeScript and production build; the eight production GLB copies match source hashes. Seven added tests cover canonical/resource aliases, unknown fallback, concurrent/repeated load reuse, failed/synchronous loader fallback, clone/resource/raycast isolation, all eight real GLB base transforms and overlay depth safety. No brittle full-scene snapshots.

Chrome 154, production frontend + unchanged fixture server: 11 acceptance groups passed, including natural Base setup/Roll, paid settlement/city/road, Road Building, Knight/victims/robber, Gold Haven ships/move/pirate, dice, production/theft flights and a robber placed on Mountains. Hover covered all eight terrains; snapshot nodes remained stable, 2D/3D reused downloads, reconnect/refresh had exactly one terrain per original tile, and idle rendering stopped. Intentional missing Mountains produced one warning per page and local procedural fallback; city/hover still worked. Gold Haven 1920×1080/1440×900/1280×720 fit without HUD overlap. Screenshots inspected and kept in `%TEMP%/catan-terrain-integration/`.

Performance, RTX 5050 Laptop, 1920×1080, 20 warm GPU-complete renders per 19-tile map:

| Map | Before → after median | Before → after draw calls | Before → after triangles |
| --- | --- | --- | --- |
| Base Standard | 2.2 → 10.2ms | 792 → 1151 | 22,020 → 275,562 |
| Seafarers Gold Haven | 1.9 → 10.3ms | 698 → 1071 | 19,658 → 233,010 |

These are diagnostic timings with `gl.finish()`, not measured sustained FPS. Fields remains ~2.74MB/~44k triangles per tile and accounts for most Base triangles; no decimation/instancing/asset redesign was performed. Low-end/mobile/50-hex GLB performance remains unverified. The lazy Board3D production chunk is ~939kB and retains Vite's size warning.

Testing limits: fixture auth DB was disabled (pre-existing /api/auth/me 503 are outside renderer checks). Existing browser helper's old manual Join after refresh was adapted only in a temporary copy to permit the current automatic reconnect; repository E2E scripts and authentication were not changed. Backend pytest/scenarios/Docker were not rerun because no backend/deployment code changed.

## Phase 1 — Visual Foundation

Historical checkpoint, completed 2026-10-04. The behavior and test counts below describe Phase 1; current interaction is in Phase 2 below.

Status: Completed — 2026-10-04. READY FOR CHECKPOINT. Scope authorized by the user's Board3D Phase 1 request.

### Audit before implementation

GamePage receives match.state from App/WSClient and passes the same object to BoardView. Python GameState → to_player_dict → _snapshot_state → match_state → WSClient.onMatchState → App.setMatch → GamePage is the existing data path. Commands remain GamePage/BoardView → WSClient.sendCmd → server/engine → new snapshot.

Snapshot already provides tiles with q/r, center, terrain and nullable number; size, vertices, edges, ports, occupied_v/e/ships, robber_tile/robbers and pirate_tile. Tile IDs are array indices, vertex IDs are dictionary keys and edge IDs are vertex pairs. No backend changes or graph reconstruction are required. BoardView.types.ts currently omits q/r and null from number; extend only that description, retaining compatibility with existing test fixtures.

Existing SVG BoardView also contains placement/robber/ship handlers. Preserve it intact; add a BoardRenderer selector above both renderers, defaulting to 2D. Board3D receives only snapshot geometry/occupancy and visual callbacks, without WSClient, command handlers, legal/rule calculations or a second game model.

Git baseline: clean working tree at f754457 (Docker commit), hardening-phase-1 points to 3cd8812. The user names infrastructure-phase-1, but that tag is absent locally; this task does not create it.

### Architecture and coordinates

GamePage → BoardRenderer → BoardView OR lazy-loaded Board3D → R3F/Three scene. Both renderers consume the same state. A read-only render projection computes mesh positions and bounds, not game decisions.

coordinates.ts owns conversion: server X / state.size → Three X; server Y / state.size → Three Z; visual elevation → Three Y. Server centers take priority; axial q/r can supply a missing center. Snapshot graph/IDs stay authoritative. Hex radius becomes one scene unit. Road midpoint, length and rotation derive from existing edge endpoints. Bounds include actual tiles/vertices/ports and camera framing adapts to aspect ratio; there is no fixed list of 19 positions.

### Implementation

1. Install exact compatible dependencies: @react-three/fiber 8.18.0 (React 18), Three.js 0.180.0 and matching @types/three 0.180.0. Keep React/Vite/TypeScript versions. OrbitControls comes from Three itself; no drei or external assets. The initially checked Three 0.186.1 emits deprecation warnings for Fiber 8's Clock and the selected soft-shadow API; 0.180.0 keeps this React 18 stack compatible without patching libraries.
2. Build pure coordinates/materials/render projection and behavior tests for IDs, centers, bounds, terrain and player colors.
3. Add shallow hex meshes, eight procedural terrain hints, readable number tokens and actual edge-attached port labels.
4. Add minimal owner-colored settlements/cities/roads. Small ship/robber/pirate placeholders are allowed only locally, with no command logic.
5. Add neutral fill/directional light, restrained shadows, bounded orbit/zoom, board auto-fit and Reset Camera. Use demand rendering; clean up controls/textures and let R3F dispose declarative resources.
6. Integrate 2D/3D Experimental selector with a constrained responsive canvas. Hover and click expose only the original tile index; game actions requiring map interaction stay in 2D.
7. Verify web tests, TypeScript, production build, Docker build and actual browser flow on Base Standard and Seafarers Gold Haven, including switch-back/gameplay and resizing.
8. Update Project State/Design System and existing affected UI notes; check references and scope boundaries.

### Phase 2 boundary

Build/upgrade/ship movement, robber/pirate targets and victims, port interaction, complete server-produced legal availability and controller migration are deferred. No Python, rules, map JSON, protocol/serialization/reconnect, Docker architecture, lobby/trade/development/settings redesign or persistence changes.

Clean modern digital tabletop is the visual direction. Fantasy/MMORPG/medieval tavern/gold-frame references remain historical and their decorative direction is rejected.

### Verification

Verified 2026-10-04 on Docker Desktop Linux containers and actual Chrome 154 (Windows, ANGLE/NVIDIA RTX 5050). 37 web tests passed (25 existing + 12 new); TypeScript and production build passed. Docker production build used clean npm ci and served the lazy 3D chunk through existing Nginx; final compose down removed both services/network with exit 0 for both containers. Test Compose is stopped. React/Vite/TypeScript and all existing lockfile package versions stayed unchanged.

Base Standard: two independent React browser contexts, Host/Join/Start, 2D default, all 19 hex meshes/terrain/centers/numbers/ports compared with live snapshot; click/hover on each original tile index sent no cmd and changed no tick. Orbit/zoom/reset and 1440×1000, 1280×720, 1024×768 layouts passed without horizontal overflow. Switch-back preserved 2D setup placement; eight placements plus Roll reached tick 9 on both clients. Four settlements/four roads matched the scene. Assets loaded, no page errors or console warnings.

Seafarers Gold Haven: live protocol host set the preset, React participant joined and used normal player-specific snapshots. 19 tiles, 4 sea, 2 gold, 9 ports and pirate checked; eight placements and Roll reached tick 9, return to SVG passed. No browser errors/warnings. Screenshots of both production maps were inspected visually.

Additional test snapshots were built by the unchanged Python engine, saved only outside the repository and delivered by mocked browser WebSocket: one city/ship fixture cross-checked against 2D and Three mesh IDs/positions; an offset non-preset 50-hex map fit correctly. No runtime map JSON/generator was added. These fixtures demonstrate rendering, not gameplay correctness of the test arrangements.

Demand rendering produced zero new idle frames. Typical main-pass calls: 190 for Base, 184 for Gold Haven, 352 for test 50. Twenty observed CPU render submissions for 50 hex averaged ~2.4ms (max ~4.3ms) on the verified GPU; not an FPS guarantee or low-end benchmark. Unmount returned geometry/texture counts to zero and released the WebGL context. Controls/resize/state updates do not create a continuous React animation loop.

Limitations: 3D is view-only; build/robber/pirate interaction stays in SVG. Lazy 3D chunk ~874KB (~235KB gzip) triggers Vite's existing size warning threshold. Mobile, full games and broad WebGL/device compatibility are not certified. Python pytest/scenarios were not repeated because all Python/gameplay files stayed unchanged. Existing scenario baseline remains historical 348/508.

During the original Phase 1 verification, unchanged LobbyPage effects could revert mapId to an older room_state and send set_map after start. This happened before Board3D was imported; protocol-configured host was used for that original live Seafarers check. No lobby fix was included in the renderer implementation.

Resolved separately 2026-10-04: delayed Gold Haven confirmation reproduced the selector returning to Base and sending Base back. Narrow LobbyPage/WSClient/Room/room_state changes removed effect-driven sends and added map_revision ordering plus one in-flight/last queued choice. Full 160 pytest, 48 web tests, TypeScript, production build and Docker build passed. Two production React browser clients now select Gold Haven through normal UI, survive delayed/stale room_state and token reconnect, then Start uses the confirmed Seafarers map. Both actual Three scenes match 19 hex/4 sea/2 gold/9 ports/pirate; switch-back → eight setup placements → Roll reaches tick 9. Custom JSON, rejection and fresh-room defaults also passed. Board3D/BoardView, engine, maps and deployment architecture stayed unchanged. This lobby blocker is closed; Phase 2 is not started. Current flow and verification limits — [[React интерфейс]], [[Сервер и протокол]], [[Project State]].

Test Compose was stopped after the separate lobby verification. No commit/tag created automatically. Original renderer checkpoint proposal: feat: add experimental 3d board renderer; tag: board3d-phase-1.

## Phase 2 — Interaction

Status: Completed — 2026-10-05. READY FOR CHECKPOINT within the verified scope. Authorized by the separate Phase 2 request; baseline clean commit 5ff920a after the lobby map_revision fix. No automatic commit/tag or Phase 3.

### Interaction audit and resulting architecture

Before: GamePage held selectedAction, SVG BoardView embedded canPlace* fallbacks, command construction, local moveFrom and tools. Board3D only inspected tiles. Server legal projected geometric availability for g.turn and missed affordability/pieces/free road/movement/victims. Existing apply_cmd already validated these commands; move_robber/move_pirate already accepted a victim in the same payload.

After: GamePage.useBoardInteraction → renderer-neutral createBoardInteraction/interactionTargets → BoardRenderer → SVG BoardView or Board3D + shared BoardControls. Both get state, action, targets, selection and the same callbacks. Source ship, victim choice and waiting feedback are UI state; rule legality and final pieces remain server state. No Redux/new dependencies. Shared PLAYER_COLORS and canonical edgeId are in board/constants.ts; Three imports no SVG helpers, SVG imports no Three code.

Click → shared callback → existing WSClient.sendCmd → server._apply_cmd → unchanged engine.apply_cmd → player-specific snapshot/legal → App/GamePage → renderer. Setup automatically follows setup_need. Free roads use server road_free metadata. Move ship is source → server destinations → existing move_ship. Multiple victims open an explicit chooser; one victim is sent explicitly, zero omits the field. No optimistic permanent figures.

Tool/source/victim survive renderer switching. New room+match resets selection; a fresh snapshot reconciles source/victim; rejection clears waiting/source/victim and uses existing error feedback. Missing personal legal gives no targets or commands. Temporary hover remains renderer-local. Coordinate mapping and original IDs from Phase 1 stay unchanged.

### Personal legal contract and scope

engine/legal.py probes the unchanged executor on isolated copies. Existing pid/settlements/roads/cities/ships stay; new road_free, robber/pirate_tiles, per-tile victim pid dictionaries and move_ship.sources/targets cover the seven board commands. legal.pid is the recipient; other recipients get empty targets and no private affordability hints. Read-only geometry is reused only inside the already isolated copy; mutable hands/bank/occupancy/flags are copied for every probe. Projection must leave the entire live GameState unchanged. Server execution revalidates every command; hints are not a security boundary.

VERSION, command payload/envelope/ACK, serialization privacy, room lifecycle, reconnect, map_revision, rules.py, map data/generator and deployment architecture are unchanged. New web board interaction needs the expanded legal from the matching backend; there is no client geometry fallback. Desktop ignores legal and keeps its existing flow. Known ship movement adjacency/mixed-route limitations are faithfully projected, not corrected.

Three adds vertex rings, edge prisms and tile outlines; hover/selected colors are modest tabletop accents. Source hit geometry sits above the ship, upgrade marker above the house. Camera, terrain and placeholder figures retain Phase 1 design. Build tools/victim panel use existing button/card styles. Trade/development/HUD/mobile/redesign are outside this phase.

### Verification and limits

Verified 2026-10-05 (checks spanning October 4–5): 186 pytest passed without skips (160 prior + 26 new legal cases), 57 web passed (48 prior + 9 shared-controller cases), TypeScript and production build passed. One old WS setup test now reads the active recipient snapshot, preserving setup assertions and additionally checking the inactive legal is empty. Full suite retains privacy/reconnect/ownership/map_revision regressions. Differential legal tests compare every build coordinate and ship destination against actual executor acceptance; complete-state equality checks prove projection immutability. Explicit robber/pirate victim tests prove only the selected opponent loses one resource.

Docker production build/up passed with the new engine/legal.py included; frontend dependency versions and deployment files unchanged. Chrome 154 / ANGLE / NVIDIA RTX 5050 on Windows ran two independent React clients through normal Host/Join/map/Start. Base Standard: all eight setup actions through actual 3D raycasts, Roll, main road build, End Turn, tick 11. Gold Haven: all eight 3D setup actions, pending pirate movement after a natural 7, main ship build and move [6,9]→[9,12], two normal turns, tick 15. Both clients agree on public geometry/occupancy/turn/pending state. Pieces and original IDs matched the scene and survived 2D↔3D. Normal turn/build/setup switching and 1440×1000, 1280×720, 1024×768 layouts passed without horizontal overflow, page errors or console warnings. Screenshots inspected visually.

Separate controlled fixtures were built by unchanged Python setup/build/card commands with trusted funding outside the repository, delivered via mocked browser WS on the Docker-served React app. Subsequent clicks called the real _apply_cmd/executor and returned personal snapshots. Both SVG and Three passed settlement/city/road/ship, move ship [38,39]→[38,42], source cancellation and switch preservation, robber/pirate selecting the second of two eligible victims, two free roads before Roll, and rejection after stale affordability without phantom pieces. SVG completed all eight setup clicks. These fixtures validate interaction with prepared states, not natural reachability or a full production match. Temporary harness files/screenshots stayed outside the repository; no runtime debug API was added.

Performance: frameloop=demand preserved; production scenes produced zero new idle frames after controls settled. The final build also passed hover settling and unmount cleanup: geometry/texture counts returned to zero and the WebGL context was released. Observed final main-pass draw calls 191 Base / 186 Gold Haven; highlights are small meshes updated only on snapshots/selection/pointer events, no React updates per frame. Main bundle 172.26 KB / 55.04 KB gzip, lazy Three 876.54 KB / 235.24 KB gzip; prior Vite size warning remains. 100 isolated legal projections each: Base mean ~1.62ms, Gold mean ~1.90ms on this machine. This is a small-board observation, not a load/50-hex/low-end benchmark.

rules.py did not change, so scenario suite was not repeated; 348/508 remains historical. Full games, mobile, broad GPU compatibility and multiplayer load are not certified. No newly confirmed gameplay bugs in the checked paths; existing deterministic theft, mixed routes/Longest Trade Route/ship movement, achievements/victory and save/load remain separate P1 backlog. No confirmed new P0 or blocker regression.

### Phase 3 boundary

Only visual polish and UX: improve placeholder pieces, target readability/hit areas, contrast and feedback, accessibility and camera onboarding. No automatic Phase 3. Engine P1 and trade/development/lobby redesign require separate tasks.

Checkpoint proposal: commit `feat: add interactive 3d board gameplay`; tag `board3d-phase-2`. Neither is created automatically.

Test Compose was stopped after verification, restoring its initial stopped state. Temporary browser fixtures/harnesses stayed outside the repository.

## Phase 3 — Visual Polish (completed, 2026-10-05)

Pre-change audit, 2026-10-05: Chrome opened Base Standard, Gold Haven and a generated 50-hex fixture on the unchanged Phase 2 production build. Original coordinates, terrain differentiation, ownership and whole-board fit work. The board occupies too little of the canvas; the large pale rectangular plane competes with it. Number and port labels are small; city/settlement silhouettes are similar; road/ship/port geometry looks provisional. Pale lighting flattens terrain and sea; gold and wheat need stronger shape separation. Legal markers need clearer, restrained feedback.

- Good: original topology/IDs, whole-board fit, restrained terrain decoration and ownership colors.
- Placeholder: box roads/ships, overlapping house blocks for cities, flat port markers.
- Poor readability: small number/resource labels, detached small markers and excessive empty space.
- Noise: the large tilted rectangular stage competes with the actual island; no particle/decor overload.
- Flat: pale fill weakens shadows, bevels and separation of sea/background.
- Prototype feel: primitive pieces, indistinct city silhouette and sparse decor clustered behind tokens.

Scope: shared visual palette and reusable Three resources, bevelled hexes, stylized terrain and pieces, larger labels, renderer-local legal-target ghost previews, camera limits and neutral lighting/background. Keep server coordinates/IDs, shared interaction controller, SVG, engine, maps, protocol and dependencies unchanged. No animation loop, full HUD redesign or gameplay fixes. Verify existing controller tests, production/Docker builds, live two-client Chrome flows and prepared build/movement/50-hex fixtures; save only final visual evidence in the repository.

### Implemented architecture and visuals

GamePage → unchanged useBoardInteraction → BoardRenderer → lazy Board3D → R3F. The snapshot and shared targets/callbacks are unchanged. Renderer-only additions: preview.ts projects a hovered target into the same RenderBuilding/RenderEdge used for permanent pieces; resources.ts and VisualResources.tsx own a small per-scene cache of geometries/materials. Resources are reused across tiles/pieces and disposed on unmount; deferred lease cleanup tolerates React 18 StrictMode effect replay. Label textures remain declaratively owned/disposed by R3F. No new dependencies, server hooks or alternative GameState.

Coordinate mapping stays server X→Three X, server Y→Three Z, visual elevation→Three Y. TILE_TOP remains 0.26; toScenePosition, tilePosition, edgePlacement, boardBounds and model.ts are unchanged. Only visual camera fitting in coordinates.ts changed: cameraFootprint uses six original hex-rim positions and port-label extents, without empty rectangle corners. A stable serialized footprint prevents ordinary snapshots resetting orbit; resize/reset/new footprint recomputes fit. Perspective view is higher, polar angles limited to 21.6–52.2°, azimuth ±45°, zoom 0.68–1.25 times fitted distance, pan off.

Hex geometry is procedural bevelled extrusion shared by all tiles. Terrain colors and silhouette accents live in materials.ts; trees, wheat rows, sheep, hills, snowy peaks, dunes, gold nuggets and static curved waves stay simple. Number tokens and resource-port labels are larger/high contrast; 6/8 and printed dots are restrained. Gabled settlement, asymmetric city/tower, bevelled road, shaped ship hull/low sail, dark pawn and pirate flag/hull replace placeholders. Existing player colors and IDs are preserved. Navy background, neutral ambient/hemisphere fill and directional soft shadows replace the visible pale stage.

Legal tile outline, vertex ring and fine edge rails use pale accents; hover is brighter white; selected is amber with brackets/thicker outline. Ghost settlement/city/road/ship previews use the permanent mesh geometry with translucent owner materials, depthWrite=false and disabled raycasting. No hover command, occupancy mutation, rule checks or full-field green fill. Leave/changed targets/waiting/victim selection hide previews. No animations added; frameloop=demand remains.

### Verification and limits

2026-10-05: web 65/65 (57 previous + 8 tests covering preview projection/gating/immutability, selected feedback, actual-footprint camera fit, shared resources, disposal/StrictMode and bevel height), TypeScript, production build and Docker production build/up pass. Python runtime, gameplay/controller, SVG, snapshots/protocol, map data/generator, dependency lockfile and Docker architecture are unchanged. pytest/scenario suite not rerun; 186/186 Phase 2 pytest and 348/508 scenario baseline are historical, not new evidence.

Chrome 154, Windows / ANGLE / NVIDIA RTX 5050: two independent React clients used normal Host/Join/map/Start. Base Standard: eight setup actions, main road, robber, 13 natural rolls/turns, final tick 37. Gold Haven: eight setup actions, main ship, pirate, five natural rolls/turns, final tick 20. Public snapshots/occupancy matched, switching SVG/Three sent no commands or changed state. Natural Gold run did not execute move_ship; a separate real-engine controlled fixture verified source/cancel/destination [38,39]→[38,42] in both renderers. No claim of a fully completed match.

Controlled browser fixtures use the unchanged engine/server snapshot, trusted funding outside the repository and mocked browser WS; actions run through the existing executor. Both renderers passed settlement/city/road/ship, ship movement, explicit second robber/pirate victim, two free roads before Roll, stale-affordability rejection without phantom pieces and SVG setup. Separate pointer checks proved all four ghost previews appear only at the server-listed original IDs, send zero commands, leave occupancy untouched and disappear on leave. Orbit/zoom/reset work; a repeated personal snapshot keeps the camera; 1440×1000, 1280×720 and 1024×768 resize has no horizontal overflow. Engine-built 50-hex offset fixture includes all eight terrains and fits the camera. No console errors/warnings in checked paths.

Performance observations on this GPU: normal main pass Base 293 calls / 11,172 triangles, Gold 267 / 10,230, 50 hex 505 / 20,094. Extra calls versus Phase 2 buy static silhouette/label detail; no per-frame React updates or instancing platform. 19/50 hex each reuse one hex geometry; settled idle over 700ms produced zero new frames. Whole-scene loaded geometries: 15 Base with city markers, 13 on 50 hex; textures 28/39 including labels/shadow map. Switch to 2D returned geometry/texture counts to zero and released WebGL context. An isolated 25-render browser sample had median CPU render-submission ~2.1ms Base and ~1.3ms 50, P95 ~2.5/3.1ms. This is a small local CPU submission sample, not GPU frame time, an FPS guarantee or a low-end benchmark.

Main bundle 172.26 KB / 55.04 KB gzip; lazy Three 881.25 KB / 237.40 KB gzip (Phase 2 876.54 / 235.24). Existing Vite size warning remains. No new downloaded assets/fonts. Deuteranopia screenshots were inspected: terrain silhouettes, number contrast and marker shapes survive; full six-owner non-color encodings, formal accessibility, mobile/low-end, full-match and load verification remain separate work. No confirmed new blocker/gameplay regression in checked scope; existing engine P1 remains untouched. No camera/hover animation was added.

Eight final screenshots are stored in docs/design/references/board3d-phase3/ and linked in [[Design System#Phase 3 visual evidence]]. They show implemented prepared states, not final HUD concepts. Temporary test harnesses, snapshots and raw screenshots remain outside the repository. Only Project State, Design System and this existing plan are updated.

Verdict: **READY FOR CHECKPOINT**. Proposal: commit `feat: polish 3d board visuals`, tag `board3d-phase-3`. Neither is created automatically. No automatic UI redesign, engine P1 or next graphics phase.

Test Compose was stopped after Phase 3 verification, restoring its initial stopped state.

## Game UI / Board3D Polish 1.1

**Completed / READY FOR CHECKPOINT — verified 2026-10-05.** Narrow renderer polish after current Game UI Phase 1; no new redesign or next phase. Principle remains renderer, not rules engine: GamePage/shared controller → BoardRenderer → Board3D receives the same snapshot/targets/callbacks. Python, gameplay, network semantics, map data/generator, legal/controller, HUD/CSS, lobby and dependencies are untouched.

Root cause: HexTile3D added a six-segment RingGeometry above the tile. Its orientation differed by 30° from the extruded pointy-top hex. It is removed. Feedback now uses finite cached emissive top-material variants (legal 0.045, hover 0.12, selected amber 0.22); neutral/shared materials stay immutable. Invisible vertex discs/edge prisms retain raycasting and IDs. Terrain decorative meshes explicitly skip raycasting: they previously could intercept a legal edge at its midpoint. Only the actual tile and existing controller targets handle these hits; no new membership checks or commands.

CameraRig removes only azimuth min/max; 360° horizontal orbit is available. Existing 21.6–52.2° polar limits, no pan, zoom 0.68–1.25 fitted distance, Reset and numeric footprint fitting remain. Original server X→Three X, server Y→Three Z mapping/IDs are unchanged. Hex extrusion 0.19 with bevel 0.03 keeps top at TILE_TOP=0.26; gaps remain. terrainVariation uses only tileIndex for small deterministic rotation/scale/offset/height, with no game seed, randomness or animation. Forest/wheat/sheep/clay/peaks/dunes/nuggets receive modest variety; sea geometry stays static. Rear windows, a clearer robber collar and two-sided pirate flag improve the opposite view; road/ship main shapes and ownership palette remain. Ports are compact bevelled rectangular placards with resource rims/dark face and a small plank dock, oriented using supplied edge rotation; existing visual inward offset is retained. cameraFootprint allows 0.4 label half-extent for rotated placards; server port edges/placement are unchanged.

Verification: 76/76 web tests (73 existing + 3 regression cases for immutable pooled feedback, deterministic bounded variation, shared placard geometry), TypeScript, production build and Docker frontend build passed. No Python runtime changed, so pytest/scenarios were not rerun. Existing Vite large lazy-chunk warning remains (~882.85 KB / 237.83 KB gzip); no new dependencies.

Chrome 154.0.8037.93 headless, real installed Chrome/ANGLE NVIDIA RTX 5050: pointer hover illuminated exactly one original tile with unchanged mesh/child counts and no commands; actual mouse drag covered 450° horizontal orbit and both polar limits, reset restored the original position. Default auto-fit contains tile rims and all port placards at Base 1920×1080/1280×720, Gold 1440×900/1280×720, and offset 50 hex 1920×1080/1280×720, with no page scroll. Framing is checked at default/reset orientation, not a promise that every asymmetric map fits every zoom/azimuth. Gold sea/gold/ships/pirate/ports match the prepared snapshot; move source/cancel checked.

Two real React clients with real server: Base setup → Roll → road/robber → End, 4 turns/tick 18; Gold Haven setup → Roll → ship/pirate → End, 17 turns/tick 50. Natural ship move was not reached in this run. Existing engine-built fixture harness checked both SVG and 3D settlement/city/road/ship, move source/cancel/destination with renderer switching, robber/pirate explicit second victim and stronger selected surface, free roads before Roll, rejected stale command without phantom occupancy, and SVG full setup. These fixtures use mocked browser transport and the real command executor; they do not certify a full natural match. An initial live run could not build because the harness chose resource-incomplete setup positions; repeat setup selections ensured access to both construction resources, without runtime or rule changes.

Performance observed for prepared Base / Gold / 50: 0 extra idle frames over 1s each; gl.info.render.calls 327 / 303 / 519, triangles 10228 / 9294 / 20358. One shared hex geometry per scene, demand rendering, no per-frame React state loop. After 50-hex 3D→2D, geometries/textures returned to 0 and WebGL context was released. These are machine-specific observations, not low-end/FPS/load certification. Main interaction/render fixture runs reported no console warnings or page errors.

Eight PNGs under docs/design/references/game-ui-polish-1-1/ are linked in [[Design System#Polish 1.1 visual evidence]]; temporary harness/snapshots/raw reports remain outside the repo. Current checkout still has uncommitted Game UI Phase 1 changes and no local game-ui-phase-1 tag; polish diff is measured from task-start working state, not HEAD. No commits/tags created. Proposal: `fix: polish board interaction visuals`, tag `game-ui-polish-1-1`. Compose stays running at http://localhost; only web rebuilt/restarted, backend room state preserved. Next phase not started.
