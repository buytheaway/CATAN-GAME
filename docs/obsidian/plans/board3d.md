---
tags: [catan, plan, board3d]
updated: 2026-10-24
---

# Board3D

## Visual Phase 5E.2 - proportions and visual hierarchy

**Implemented and verified; READY FOR CHECKPOINT as an opt-in experiment,2026-10-24.** Published5E.1 checkpoint is `3d82af6c8fc4449bd80b28f8c4bf20bde689e14e`, exact local/origin/main equality verified after normal fast-forward push. Its19 intended files were committed separately, excluding the existing user graph and temporary artifacts; the423-test/GPU evidence below is historical, not rerun for checkpointing.5E.2 remains uncommitted and is not approved for production-default promotion.

Actual path: committed player-specific snapshot → existing BoardRenderer/controller → Board3D → revealed HexTile3D → cached terrain's owned clone. A presentation-only optional `terrainDetail` prop defaults to `current`; GamePage/App, commands, snapshots and saved preferences gain no setting/field. Only the external e2e wrapper explicitly passes `pilot`. Default measured node transforms/visibility equal5E.1. No new GLBs/Blender models/materials, lighting overhaul or ship-default change. Hidden Fog, game IDs, numbers, anchors, raycasting, camera/ocean/frame and shared finite animation architecture remain unchanged.

### Measured baseline and hierarchy

`proportions-inventory.cjs` measures exact loaded mesh vertices under actual scene transforms, not source-file units or guessed sizes. The logical pointy hex has radius1, across-flats width1.732051, across-corners2, area2.598076. Terrain transform remains scale1/1.2 and Y rotationπ/2. Sizes below are X×Y×Z in scene units; axis-aligned footprints include empty corners and are not occupied-pixel areas. Terrain heights include their original bases/landforms; decoration rows isolate individual groups. Triangles are visible single-pass mesh-instance totals, not shadow-inclusive draw cost.

| Object | Current measured size / height | Approx triangles | Pilot |
|---|---|---:|---|
| Five sheep | individual heights.331–.387; Alert.458×.380×.609 | Pasture total11990 | uniform.8, Alert.367×.304×.488; same five animals/support points |
| Wheat |7 masses +2 fringe groups; mass heights.420–.531 | Fields44300 | hide Mass02/07; remaining5masses/2fringes height×.78; Fields33114 |
| Forest |7 pines, individual heights.682–.762; tile height.984 |2910|unchanged |
| Mountains |tile1.732×1.408×1.986 |2470|unchanged |
| Hills / Desert |tile heights.593 /.499 |5522 /4590|unchanged |
| Sea / Gold |tile heights.325 /.519 |4784 /5310|unchanged |
| Road, unit edge |.884×.087×.144 |616|unchanged |
| Settlement |.346×.420×.306 |804|unchanged |
| City |.500×.547×.434 |1664|unchanged |
| Procedural ship |.716×.422×.264 |88|default, unchanged |
| Opt-in GLB ship |.704×.535×.280 |215|opt-in, unchanged |
| Robber / pirate |.400×.559×.400 /.773×.464×.343 |684 /128|unchanged |
| Number / port badge |.820×.085×.820 /.720×.058×.720 |194 /120|unchanged |

All eight terrain bases remain1.732×1.986 in XZ. Pasture's complete height.761→.685 and Fields.756→.626 in the pilot; their ground/rims do not scale. Original hillside contact is preserved at each animal's own support, not flattened to a global Y. Ocean cells are1.732×.172×2; default one-ring counts Base18/NS4 26/FI4 24. Actual full frame bounds: Base12.284×.210×11.185, NS4 17.481×.210×14.185, FI4 15.748×.210×14.185. These are existing unchanged meshes, not new gameplay boundaries.

At actual Base2560×1440 native overview, Alert sheep projected geometry box56.7×64.7px→45.2×51.7; the measured settlement48.8×57.6, city71.2×81.8, number93.9×69.5 remain unchanged. These examples occupy different board positions/depths and are not a segmented visible-silhouette or visibility-percentage comparison. Matched nearby-object crops provide the visual evidence. Raw measurements: `%TEMP%/catan-proportions-5e2/baseline-inventory-corrected.json`, `envelopes.json`, and final capture report inventories. The first raw inventory included nested sheep mesh names in group counts; it is preserved, with the corrected count explicitly five independent groups.

Confirmed hierarchy concerns: a sheep's AABB footprint is larger than a settlement's and can visually compete with a nearby house; wheat groups can exceed settlement height and dominate the tile/city surroundings. Actual baseline crops show both. This does not prove every player misses a building, nor that realistic animal/house scale is required. Numbers remain legible; no additional missing figure, hidden port, ownership defect or third high-impact category was established. Trees/mountains being taller is intentional terrain vocabulary, not sufficient evidence for another global rescale. The desired hierarchy is owned pieces → neutral threats/mandatory targets → numbers/ports → terrain identity → decoration, without changing event/hit priority.

### Two-category controlled proposal

`terrainProportions.applyTerrainDetail` accepts only the explicit pilot, on a fresh owned clone **after5E.1 clearance**. Five named sheep groups shrink uniformly20% about measured footprint centre/minimum Y; their poses, centres and hillside foot contact persist. Wheat Mass02/07 are hidden, and remaining named wheat groups compress Y22% about their original base; XZ footprint/ground stay fixed. No other family changes. Materials/geometries/templates/raycast functions are shared and unchanged; repeated application is idempotent with weak scene references. Current-mode restoration uses a fresh source clone. No animation loop or per-frame React state is introduced. Procedural loading/error fallback remains the existing fallback, not a new artistic variant.

This is deliberately **opt-in, awaiting user art approval**. Shrink amount, which wheat clumps to retain, sparse/solid field balance and broader miniature proportions are subjective. Do not infer approved production art from dimensions, tests or a faster GPU sample. No broader water/material/palette/Forest/Mountains/piece/default-ship redesign is implemented.5E.1 original robber anchors/standing clearance and occupied badge offset remain in both variants.

### Actual comparison and verification

Loopback gallery **http://127.0.0.1:18788/** uses exact committed5E.1 `git show` blobs for OLD and current renderer with explicit pilot for NEW. The current/pilot selector switches live without moving the camera; selecting the committed source loads that exact bundle. One-ring/frame-on is fixed on both sides. All snapshots are synthetic PUBLIC display data with existing source IDs; occupancy is not a legality-certified match, and no account/backend/private Fog recipe is exposed.

Final gallery has113 actual PNGs:102 matched Base/NS4/FI4/Fog-before/Fog-after overview/close/orbit/crops,8 matched procedural/GLB ship views with existing four owner colors, and3 focused1440×900 normal/reduced/static views. Full captures are2560×1440; native crops600×600. Every PNG hash/public-state/native-camera equality is checked. Root inspected adjacent sheep/house, wheat/city, Fields12/tile29, full Base/NS4 and rotated before/after views. Reports/media: `%TEMP%/catan-proportions-5e2-final-live-toggle/` (`paired-capture-report.json` preserves the102 source report, `capture-report.json` adds supplements), `%TEMP%/catan-proportions-5e2-ship-captures/`, `%TEMP%/catan-proportions-smoke-accepted/`. Original28 baseline and intermediate102 captures remain in separate directories, not overwritten. [Launch/reproduction](../../../web/e2e/README.md#visual-phase-5e2---opt-in-proportions-pilot).

**428 frontend tests / TypeScript / production build pass, exit0**, including5 new actual-GLB tests for default/unknown no-op, sheep contact/centre/scale, wheat count/height/footprint, cache/resource immutability, idempotency and5E.1 preservation. Logs: `.venv/test-artifacts/proportions-5e2-final/`.30 existing Chrome regression groups pass on production-current (threats8/buildings7/ships6/ocean9), plus8 focused opt-in groups: committed/default equality, live restore without camera reset, Fields12/anchor/raycast, SVG round-trip, motion/idle, hidden Fog/reveal, legal ship pointer/build/move/GLB/reconnect/reload, and construction on public synthetic Fields/Pasture. Ships regression omits the old synchronous timing via the existing ignored acceptance-only wrapper; it is not GPU evidence. Reports: `%TEMP%/catan-proportions-5e2-visual/df7069cafc/`, `%TEMP%/catan-proportions-ships-regression/` and accepted smoke folder. Intermediate test-tool selector/unsupported fixture-reset failures remain recorded, not classified as production defects.

No backend change, production-default change or new raycast/controller path, so no full Python/scenario suite or fresh PostgreSQL multiplayer run. Docker daemon is also unavailable; no production database was started or modified. Final5E.1 live36/7 and earlier55/12 remain historical evidence, not rerun2026-10-24. Fresh Chrome checks the unchanged default, opt-in public controller, reload/reconnect and new-frame behavior; no fresh durable server-restart/gameplay certification is implied. The support tests preserve original minimum Y/footprint centre, not physical collision fitting of every hoof to the hillside.

### Performance gate

**Completed, exit0:12cases/96readings/11520valid async GPU queries, zero disjoint/errors.** Exact `3d82af6` versus opt-in pilot, Base/NS4/FI4/50 ×normal/reduced/static; two ABBA/BAAB blocks. Chrome155.0.8059.85, RTX5050Laptop driver610.74,1440×900/DPR1. Identical camera/public state/ship default/ocean/frame/normalized ambient boat poses,90warm/120GPU/60wall frames per reading. Loading/compile/warm-up excluded. No other test browser/screenshot/video during timing; FC25 absent at preflight/spot checks. Sampled temperature63–67C, GPU utilization14–42%; clocks/power are unlocked. All raw samples, worse readings, opposing block deltas, idle and telemetry remain in `%TEMP%/catan-proportions-gpu-20261024/paired-performance.json`. Separate untimed `pass-inventory.json` reconciles actual Three main/shadow callbacks with native calls/triangles in every case. Bundle hashes match final screenshots/accepted opt-in smoke. No5E.2 commit/push or5F.

| Scene/mode | GPU median old→pilot ms | GPU p95 old→pilot ms |
|---|---:|---:|
| Base normal |4.406→3.774|12.472→12.376|
| Base reduced |3.992→4.121|12.768→12.679|
| Base static |4.301→4.841|12.245→12.850|
| New Shores4 normal |10.204→9.700|20.302→18.707|
| New Shores4 reduced |10.475→10.111|20.395→19.548|
| New Shores4 static |9.362→9.765|18.382→18.466|
| Four Islands4 normal |8.485→8.213|17.166→16.977|
| Four Islands4 reduced |8.602→7.088|18.901→18.531|
| Four Islands4 static |7.369→7.648|18.331→17.744|
| Fifty normal |4.049→3.417|12.760→12.813|
| Fifty reduced |4.211→4.318|13.074→13.293|
| Fifty static |2.850→3.855|10.844→12.545|

Timings are **mixed, not proven universal improvement/equivalence**. Base/NS4/FI4 static medians worsen in both blocks, despite fewer primitives. FI4 normal/reduced, NS4 reduced and other cases retain opposing or differing deltas. The50-hex fixture has no Fields/Pasture and is explicitly an **unchanged control**, not a dense wheat/sheep stress test; its identical draw/triangle workload also has large timing variance (static median+1.005ms, opposite block signs). This suggests measurement/environment variation but does not isolate a cause. No unfavorable result is discarded, no low-end/mobile or sustained FPS certification is claimed. Default production appearance was not promoted to the pilot.

| Scene | Main calls old→pilot | Shadow calls old→pilot | Main+shadow triangles old→pilot |
|---|---:|---:|---:|
| Base |1188→1132|931→875|586262→496774|
| New Shores4 |2061→1991|1638→1568|918554→806694|
| Four Islands4 |1875→1805|1455→1385|821472→709612|
| Fifty control |1398→1398|1099→1099|320022→320022|

Counts agree across motion modes. Shared scene material/geometry/program/texture counts remain: Base175/250/11/29, NS4215/305/11/38, FI4183/260/11/34, fifty118/149/12/17. Mesh-node totals also remain1213/2080/1916/1394; hidden wheat still exists in the owned graph. GPU-uploaded geometry drops256→242 /311→297 /266→252; fifty154 unchanged. All96 readings have stable post-warm-up resources. GLB bytes/transfer sizes do not improve because files are unchanged. Reduced idle0 everywhere; static NS4/FI4/fifty0, Base's existing decorative boats10–11frames/s; normal Base10–11/others12–13. No additional permanent render clock. Initial clone fitting/cold-start latency is not certified by this steady-state microbenchmark.

## Visual Phase 5E.1 - piece readability and occlusion

**Historical verification2026-10-21; committed/pushed2026-10-24 as `3d82af6c8fc4449bd80b28f8c4bf20bde689e14e`.** Baseline was published `b1c5a2f0ae0409a55ba991eb478e8693972fd9c6`; only the user's graph was already modified. Reproduced actual Chrome Four Islands4 tile29 Fields12 at native overview and wheel close-up before renderer changes. Images/report are under `%TEMP%/catan-readability-5e1-initial-1792592113413/`. Tall wheat intersects the existing robber body; depth-independent number badges independently cover its projected silhouette. This is a visual defect, not incorrect tile/state.

Affected path: sanitized public snapshot → BoardRenderer's existing threat observer/cues → Board3D public robbers → HexTile3D revealed terrain → owned TerrainHexVisual clone. `terrainReadability.clearRobberVegetation` hides only approved named wheat/pine/sheep groups whose transformed local XZ bounds intersect radius0.34 around the existing robber anchor. Current GLBs hide4 Fields groups,3 Forest pines or2 Pasture sheep; other five terrain assets keep every group. The helper never hides base/rim/main landforms or mutates shared materials/geometries/templates, including cached bounds. A fresh clone restores vegetation when clearance ends.

Vegetation-only pictures improved the body but a rotated view still lost much of the hat under the number overlay. The final occupied badge therefore moves0.2 left in local X, at its original height/size, fully inside the same hex. Its printed number/pips/colors and depth-overlay policy stay intact. No robber/pirate anchor, world position, scale or visual motion changes; no global token depth change that would bury numbers in mountains. The finite existing public departure cue retains clearance/print offset until expiry, then restores both; static/reduced/disconnected modes keep only the final figure's tile. Hidden Fog never mounts terrain, tokens or clearance. Failed GLB uses existing colored ground, omitting procedural hints on that occupied tile; this degraded fallback intentionally prioritizes the figure over decoration.

### Actual visual and regression evidence

Final matched capture report: `%TEMP%/catan-readability-5e1-final/paired-capture-report.json`, completed with50 actual2560×1440 PNGs/native-pixel crops. Exact public-state, native-camera/projection and file hashes are recorded. Both sources include5D.2 one-ring/frame. Original FI4 tile29 has overview/close-up and three successive real orbit orientations; also Base, New Shores4, Forest/Pasture/Hills/Mountains/Desert/Gold and Fog before. No generated concept images. The gallery's `capture-report.json` preserves those entries and adds the6 focused smoke PNGs (56total), including normal/reduced/static and fallback. Captions distinguish test-controlled states from the linked original interactive scene. Root visually inspected the initial/interim/final exact case, rotated views, terrain crops and full Base/New Shores. Original and vegetation-only reports remain under `%TEMP%/catan-readability-5e1-initial-1792592113413/`, `%TEMP%/catan-readability-5e1/` and quick-study directories; no unfavorable intermediate evidence was overwritten.

Final CPU verification: **423 frontend tests, TypeScript and production build passed, exit0**. New11 regressions exercise actual shipped GLBs/cache identity/local bounds and real React token/hex props, physical separation/containment, values, restored position and hidden gating. Evidence/hashes: `.venv/test-artifacts/readability-final-20261021-1/`. Board3D chunk990.97kB/270.33gzip retains the existing size warning. No backend change, so no full Python/scenario suite rerun or new Python-count claim.

Chrome: existing30 distinct groups pass (threats8/buildings7/ships6/ocean9). Final-token-source threats8/ocean9 were refreshed; building/ship results before the print-only offset are retained rather than counted twice. New6 focused groups on final source verify other-clone immutability, original tile29/anchor/number, actual ignored terrain raycasts/ordinary click no-mutation, departure retention/expiry, hidden Fog fail-closed, static/reduced idle0 and normal12frames/s, plus expected Fields404 fallback. Reports: `%TEMP%/catan-readability-5e1-visual/b1dd2a6e74/`, `%TEMP%/readability-final-token-a0662d7bd3b14a6eb8ce8b8d82418b17/` and `%TEMP%/readability-smoke-final-e8aa4bcf273449349bf10c415997b1bd/` (6 additional PNGs). The first smoke inspector wrongly counted tile metadata as a token; its failed report is preserved, then only that test inspector was corrected. Ships regression omitted its legacy synchronous timing using an ignored acceptance-only wrapper; those screenshots/counters are not GPU timing evidence.

Real TCP/WebSocket/PostgreSQL:55 checks/12 prepared scenarios passed on clearance source before the final badge-only offset: threats36/7, buildings12/3, ships7/2. Three-player theft privacy, accepted/rejected anchors, Seven/Knight, Fog/Gold, receipts, reconnect and restart/no replay remain intact. Fresh disposable databases only, no user data/volume reset. Reports: `%TEMP%/catan-readability-5e1-live/18c31122e3/`; source hashes/statuses/logs retained under ignored `.venv/test-artifacts/`. These are prepared acceptance fixtures, not natural full matches.

After the final print offset/build, **all36 threats checks/7cases were rerun successfully, exit0/errors[]** against final production assets `Board3D-Bxc_GmzL.js`/`index-CRUsmJeM.js`. Report: `%TEMP%/catan-readability-5e1-final-threats-live/2a2ca94b80/threats/report.json`; source hashes match the tested/GPU renderer. Three-player rejection/privacy, Seven/Knight/victims/Fog/offboard, durable duplicate receipts, reconnect/refresh and restart/no replay pass. The existing test PostgreSQL container is restored to its original stopped state; new disposable databases remain intact. Final preview navigation also passed:56 gallery images, actual terrain switching, reset of the synthetic terrain choice when changing maps, disabled absent terrain options and no browser runtime errors. Preview remains running; test browsers/backend processes are closed.

### Performance and verification boundary

Corrected asynchronous GPU A/B **completed, exit0**:9cases/72readings/**8,640 valid queries**, zero disjoint or unexpected errors. Chrome155.0.8059.85 / RTX5050Laptop / driver610.74; viewport1440×900/DPR1, identical public scene/procedural ships/camera/ocean/frame/boat poses. Two counterbalanced ABBA/BAAB blocks,90warm/120query/60wall frames per reading; loading/compile/warm-up separate. No screenshots/video/other test browser during timing; FC25 absent at preflight/spot checks. Telemetry64–68C,11–36% sampled GPU load, unlocked power/clocks. Full chronological samples, both block deltas, resources, telemetry and unfavorable tails: `%TEMP%/catan-readability-gpu-20261021-final/paired-performance.json`. Untimed actual Three main/shadow callbacks reconcile with native calls/triangles in every measured case in `pass-inventory.json`. Source hashes match the paired capture/focused smoke bundles.

| Scene/mode | GPU median before→after ms | GPU p95 before→after ms |
|---|---:|---:|
| Base normal |5.477→5.359|9.093→8.159|
| Base reduced |4.542→4.272|13.111→13.256|
| Base static |5.188→5.450|12.994→11.172|
| Four Islands4 normal |8.396→8.576|12.099→11.992|
| Four Islands4 reduced |9.046→9.206|16.528→18.128|
| Four Islands4 static |8.916→8.571|13.191→11.521|
| Fifty normal |5.373→5.160|12.578→12.629|
| Fifty reduced |5.503→5.611|7.432→7.742|
| Fifty static |5.641→5.628|12.394→12.767|

Do not call this equality or a proven speedup. FI4 normal/reduced medians rise~2.1%/~1.8%; reduced p95 worsens1.600ms. FI4 static improves, while controls with identical geometry also vary. Opposing block deltas occur for Base reduced, FI4 reduced, fifty normal/static and are retained. This single unlocked desktop run cannot establish causality or zero cost, mobile/low-end certification or sustained game FPS. There is no added structural draw/resource/idle cost; graphics remain bounded in the tested desktop scope.

| Scene | Actual main calls before→after | Shadow calls before→after | Combined triangles before→after |
|---|---:|---:|---:|
| Base |1188→1188|931→931|586262→586262|
| Four Islands4 |1901→1875|1481→1455|851936→821472|
| Fifty |1398→1398|1099→1099|320022→320022|

Counts agree across all3motion modes. Main+shadow combined calls:2119 unchanged Base,3382→3330 FI4,2497 unchanged fifty. Scene material/geometry/program/GPU-geometry/texture counts are unchanged per pair: Base175/250/11/256/29; FI4183/260/11/266/34; fifty118/149/12/154/17. All72 readings retain equal before/after steady-state resource counts. No assets or additional meshes/materials/geometry factories are added. Reduced idle0 on all maps; static FI4/fifty0, existing Base decorative boats still10–11frames/s on both sources; normal Base10, FI4/fifty12–13. No new permanent render clock.

### Deferred5E.2 proposals and limits

Actual representative maps did not establish another missing settlement/city/ship, wrong owner color, hidden port caused by the frame, or ghost hiding an unrelated real piece. The existing same-owner settlement replacement ghost is intentional. Synthetic seven-hex pirate/port silhouette proximity is not evidence of an attainable legal match defect. Broader figure/token proportions, green-on-forest contrast and water material-family consistency remain proposals, not implemented fixes or user art approval. This local treatment does not promise zero natural occlusion from every possible camera/neighbor landform or future replacement asset. It preserves main landforms and logical hit surfaces; ordinary orbit remains available.

Historical5E.1 loopback gallery: **http://127.0.0.1:18787/**; [restart/capture/smoke/GPU instructions](../../../web/e2e/README.md#visual-phase-5e1---piece-readability). At that verification source/tooling remained uncommitted; the authorized checkpoint/push followed on2026-10-24 as recorded above. Temporary media/benchmarks remain outside Git. User graph hash was preserved as `040082d631add3046746a2205cf29241d842bf5b85aadb79e081cbe2beb9b25e`. These statements describe5E.1, not a prohibition on subsequently authorized5E.2.

## Visual Phase 5D.2 - decorative ocean and continuous frame

**Historical verification2026-10-21, subsequently committed/pushed as `b1c5a2f0ae0409a55ba991eb478e8693972fd9c6`.** The final GPU repetition after the user closed the external game passed all15 cases; evidence and remaining limits are below. Base correctness prerequisite is checkpointed/pushed as `b61215b1ea1f2693b0f828720f8384ac4e291327`; exact local/remote hash verified. The completed1696-pass Python suite is historical evidence for5D.1 and is not rerun just for checkpointing. User graph remains excluded.

### Existing conventions and intended boundary

Before implementation inspected actual path: Python materialized/public tile geometry → React state → `BoardRenderer` → `createRenderModel` → `Board3D`. `publicTileCenter` uses public center or pointy axial `x=sqrt(3)*(q+r/2), z=1.5*r`; coordinates divide server XY by `size` into Three XZ, Three Y is visual only. Logical hex radius1; current beveled terrain rims are slightly inset. Visible terrain rim is `BOARD_RIM_TOP=.218333`; tile hit plane `TILE_TOP=.26` and server vertices/edges/IDs remain unchanged. Ports retain their supplied edge/endpoints and local coast normal; legal/controller targets remain entirely snapshot-driven. Existing `DecorativeOcean` is background scenery, not complete water hexes or a board perimeter. SVG has independent existing rendering/target handlers.

New client-only `oceanGeometry` derives one/two exterior rings from **all public geometric coordinates**, including unknown Fog slots, without reading terrain/numbers/visibility. Existing playable Sea and printed full-frame Sea cells count as occupied. Exterior flood excludes enclosed holes; exact lattice corners order exposed edges into continuous outer loops. The visual frame follows that union, with joined corners. These cells/edges are presentation metadata only; never extend GameState, IDs, ports, legal projection, exploration, commands or snapshots. All new meshes ignore raycasts.

Shared instanced water bodies/accents and a continuous frame use restrained existing sea/tabletop colors. Default one ring; two rings/frame-off/before are preview controls, not gameplay modes. No new Blender/dependency/animation loop. Camera footprint includes decorative perimeter and conservative public relief/piece bounds; fit stays stable across ordinary snapshots, Fog reveal and ship-model switches. World coordinates/sizes stay unchanged. Before/after source bundles use the committed5D.1 renderer and current actual components; synthetic display occupancy is labeled. Matched screenshots and async GPU query A/B across Base/NS4/FI4/7/50 and motion modes are required before a readiness claim. Raw contradictions are preserved. Implementation/verification did not create a commit or push; checkpointing requires explicit authorization.

### Geometry, framing and scoped corrections

| Actual public footprint | Playable cells | First ring | Second ring additional | Two-ring total decoration | Exterior edges, one/two rings |
| --- | --- | --- | --- | --- | --- |
| Base Standard |19|18|24|42|42/54|
| New Shores3, Four Islands3/4,37-cell custom/Fog footprints |37|24|30|54|54/66|
| New Shores4 |44|26|32|58|58/70|
| Seven-hex public fixture |7|12|18|30|30/42|
| Fifty-hex public fixture |50|32|38|70|70/82|

`buildOceanLayout` derives pointy-axial cells from public centers (priority) or q/r, preserves original scale, and rejects off-grid/unsafe footprints rather than guessing. Bounded exterior flood excludes enclosed holes. Integer corner keys make exact joined CCW exterior loops. Existing playable Sea/full frame Sea remains occupied. The single mitered band has an outside skirt and inner lip; all scenery uses ignored raycasts and has no server tile/edge IDs. Four shared instanced meshes plus one frame mesh avoid per-cell draw/material allocation; lifecycle cleanup retains StrictMode leases.

The final image review found narrow striped shoreline artifacts: water and existing coastal box tops were coplanar at `BOARD_RIM_TOP=.218333`. The smallest correction sets `DECORATIVE_WATER_TOP=BOARD_RIM_TOP-.008`; only new water/seams/waves and the frame's inner lip follow that plane. Existing terrain, coast, hit targets and pieces stay at their original elevations. A regression verifies the actual pooled water geometry remains more than0.007 below the coast top. Pre-fix images and GPU data are retained, not silently replaced.

Before the initial live building acceptance, the existing informational `.game-error` DOM alert covered an otherwise correct raycast target. Only `pointer-events:none` is added; visible error text/`role=alert` remain and there are no focusable children. The historical bundle remains a negative control in the Chrome occlusion check. Base ambient boats now include decorative cells in their clearance, retaining the old clock/routes and all gameplay ships. Shared ocean materials are memoized, preventing hover-driven instance replacement.

Camera uses actual frame vertices plus a constant public relief/piece envelope; no hidden terrain or mutable ownership participates. At aspect1.64, native old→one-ring fit distances: Base11.855→14.518, New Shores3 14.865→18.516, New Shores4 15.431→18.730, Four Islands3 14.187→18.404, Four Islands4 14.580→18.404. The increase fits the requested larger physical outline; stable relief adds no further distance on these fixtures compared with old relief plus the same frame. Two rings are optional and visibly reduce playable area. Normal views retain the full outline/ports/pieces; intentional wheel close-ups crop. Existing Four Islands4 robber/Fields12 partial occlusion remains an unrelated known limitation, not fixed here.

### Evidence and verification boundary

Completed evidence before the final shoreline clearance correction is preserved: **412 frontend tests**, TypeScript, production build; **49 actual Chrome PNGs** covering five official boards, public Fog before/after, native/matched cameras, one/two rings, frame off and close/detail crops; **9 Chrome smoke groups** for hover/snapshot instance stability, raycast pass-through, controls, frustum, no game commands, Fog camera stability and error-overlay retry; **55 live multiplayer checks across12 prepared scenarios**,2–3 real Chrome/WebSocket clients and PostgreSQL. Ship7/building12/threat36 groups include accepted/rejected commands, Fog/Gold, victim choice, uninvolved theft privacy, receipts, reconnect and restart. Fresh isolated test DBs only; test PostgreSQL was returned to stopped, no existing data/volumes reset. These are prepared/funded acceptance fixtures, not natural full matches. Six focused official layout/outer-sea legal shipping Python tests pass; no new full Python/scenario run is claimed.

Initial final49 images/report: `%TEMP%/catan-ocean-5d2-final-v3/`. A test-tool SHA bug originally hashed the JSON representation of Buffer. `ocean-support.cjs` now hashes the bytes directly; original manifest is retained as `capture-report-original-json-buffer-hashes.json`, corrected manifest records old hashes/dimensions and all49 PNG bytes are unchanged. This was a report verification defect, not image manipulation. The source bundle hashes in these captures equal the initial full GPU run; both precede the explicit shoreline correction above. Earlier incomplete/failed reports remain historical.

Live artifacts: `%TEMP%/catan-ocean-5d2-live/956675def9/{ships,buildings,threats}/report.json`; local logs/status under ignored `.venv/test-artifacts/ocean-*-live-956675def9.log` and `ocean-live-status.json`. Actual legal outer-sea photo is constructed through production `apply_cmd` setup settlement/ship and checked legal projection, then exported through a public allowlist; ordinary gallery occupancy is only synthetic display data. Neither preview exposes trusted FogState/recipes, private hands or account credentials.

**Post-correction visual verification,2026-10-21:** frontend **412/412**, TypeScript and production build passed again (exit0). Lazy Board3D989.60kB/269.73gzip; the existing500kB chunk warning remains. Final **49 PNGs** are under `%TEMP%/catan-ocean-5d2-final-v4/`, including seven native/matched before/after camera pairs, five official layouts, public Fog before/after, one/two rings, frame off, close/detail views and legal outer-sea opening. All byte hashes verified, all model responses200, no console/page errors; all seven matched public-state/camera pairs agree. Actual final views show the shoreline striping removed without moving terrain/pieces. The full **9 Chrome smoke groups** pass again, report `%TEMP%/catan-ocean-smoke-final-v4/browser-smoke.json`: Fog camera/outline stable, no decoration raycast hits or commands, stable instances/resources, clipping/resize/SVG round-trip and visible alert retry intact. These visual-only changes do not invalidate the55 completed multiplayer checks above, which were reused rather than presented as newly run. Status/logs: ignored `.venv/test-artifacts/ocean-post-clearance-status.json`, `ocean-web-tests-post-clearance.log`, `ocean-typescript-post-clearance.log`, `ocean-build-post-clearance.log`.

Preview/gallery: **http://127.0.0.1:18786/**. From root, set `NODE_PATH` to existing `.venv/test-artifacts/fog3a-tools/node_modules`, `CATAN_OCEAN_OUTPUT` to `%TEMP%/catan-ocean-5d2-final-v4`, then `node web/e2e/ocean-demo.cjs`. [Exact commands](../../../web/e2e/README.md#visual-phase-5d2---decorative-ocean-and-continuous-frame). Actual gallery, report, preview and PNG HTTP200 checked; listener binds127.0.0.1 only. No backend/DB/login is required. Test scripts are not imported by App or bundled into production. Media/raw reports are excluded from Git and temporary storage may be cleared; regenerate if absent. Final corrected-source GPU results and environment limitation are below.

### Controlled GPU measurements - original geometry retained

First complete report: `%TEMP%/catan-ocean-gpu-final-9c783e92f85545ae86a827ed70d52f91/paired-performance.json`, exit0, Chrome155.0.8059.85, RTX5050 Laptop/driver610.74. **15 cases,120 readings,14,400 valid asynchronous timer samples, zero disjoint samples/errors.** This report measures the geometry before the explicit0.008 shoreline clearance fix; it is retained as real evidence, not silently relabeled final. Both source hashes are recorded in the report.

Same1440x900/DPR1, scene/public-state/owner occupancy, current full-frame camera, lighting/model and motion settings per pair. Counterbalanced ABBA then BAAB; each reading compiles first, warms90 paced frames, measures120 asynchronous `TIME_ELAPSED_EXT` GPU spans and60 separate CPU-wall spans. Main and shadow calls/triangles are counted together; full chronological frames, block medians, resources, telemetry and idle counts remain in JSON. The runner launches no parallel capture/video/GPU workload; exclusive use of the user's system GPU is not guaranteed. Actual Base ambient poses/visible boats are recorded; external probe normalizes both sides to the same after-boat poses during timed spans only, restores the native render/pose afterward and observes real idle. This is a bounded render-span diagnostic on one unlocked GPU, not sustained FPS, speedup proof or lower-end certification.

| Scene/mode | Before median ms | After median ms | Before p95 ms | After p95 ms |
| --- | --- | --- | --- | --- |
| Base normal |4.404|4.164|13.521|11.790|
| Base reduced |5.014|4.303|10.888|12.798|
| Base static |4.486|4.615|12.790|12.041|
| New Shores4 normal |12.532|9.725|18.905|20.276|
| New Shores4 reduced |12.603|10.157|19.938|20.950|
| New Shores4 static |12.467|9.698|18.142|19.882|
| Four Islands4 normal |11.155|8.929|14.107|13.210|
| Four Islands4 reduced |11.065|8.520|16.314|17.888|
| Four Islands4 static |10.819|8.720|16.969|19.379|
| Seven normal |0.626|0.597|2.876|1.944|
| Seven reduced |0.571|0.668|2.330|2.924|
| Seven static |0.895|1.058|2.277|2.678|
| Fifty normal |6.403|4.732|12.862|12.030|
| Fifty reduced |5.732|4.810|14.453|13.499|
| Fifty static |4.764|4.697|13.391|12.980|

| Scene, all motion modes | Main+shadow calls before/after | Triangles before/after | Instanced meshes / total instances after |
| --- | --- | --- | --- |
| Base |2113/2119|582656/586262|4/109|
| New Shores4 |3693/3699|913262/918554|4/174|
| Four Islands4 |3376/3382|847070/851936|4/157|
| Seven |430/436|53028/55410|4/67|
| Fifty |2491/2497|313542/320022|4/210|

All five scenes add5 mesh objects,6 main-pass draw calls,4 GPU geometries,6 scene materials and3 shader programs, with no additional textures. Resources are stable across timed frames and ordinary hover/snapshots. Reduced is0 idle frames in both versions; non-Base static is also0. Existing Base ambient boats still render about10Hz even when other effects are Static; this predates5D.2. Normal Seafarers/shared motion remains12–13Hz in both versions. No added ocean clock/idle rendering.

**Unfavorable and contradictory data:** seven reduced/static medians and tails increase; Base static block deltas have opposite signs (+0.790/-0.365ms), as do fifty static (+0.313/-0.605ms). New Shores4 and some Four Islands p95 worsen despite lower medians. Temperature/power-state variation and GPU scheduling remain uncontrolled; start/end60→64C,1575→1620MHz do not establish a cause. No equivalence/improvement claim. The short smoke report with seven-static p95 1.621→3.438ms is also retained under `%TEMP%/catan-ocean-gpu-smoke-ac631bea76aa4cbfb19243189c203802/`, explicitly only4 samples per reading, not full acceptance. Final corrected-water measurements are separate below.

### Final-source GPU run - completed, environment-confounded

`%TEMP%/catan-ocean-gpu-post-clearance-final/paired-performance.json`: exit0, same15 cases/120 readings/14,400 valid queries, zero disjoint/errors. Its source hashes exactly match the final49 capture manifest. Mesh/resource/call/triangle counts match the first report above; reduced and non-Base static idle remain0, Base legacy static ambient remains10Hz. All resource/no-command assertions pass.

| Scene/mode | Before median ms | After median ms | Before p95 ms | After p95 ms |
| --- | --- | --- | --- | --- |
| Base normal |4.350|4.455|10.966|11.852|
| Base reduced |4.840|4.775|12.841|13.111|
| Base static |6.090|5.271|12.398|10.783|
| New Shores4 normal |12.663|9.927|20.202|19.974|
| New Shores4 reduced |13.213|10.060|21.293|15.650|
| New Shores4 static |13.047|10.464|20.812|19.428|
| Four Islands4 normal |10.370|5.616|14.379|16.572|
| Four Islands4 reduced |11.773|9.674|14.914|14.874|
| Four Islands4 static |13.316|10.378|21.742|15.069|
| Seven normal |1.757|1.189|6.323|5.577|
| Seven reduced |2.300|1.786|4.060|4.087|
| Seven static |1.105|2.413|4.077|3.974|
| Fifty normal |7.569|6.900|11.928|8.971|
| Fifty reduced |7.630|7.039|11.678|9.862|
| Fifty static |7.744|6.954|11.741|9.183|

**Environment limitation, not a proven renderer defect:** late in the final run driver telemetry reaches94% utilization and78C, compared with8–35% and62–68C across first-run readings. Afterward `nvidia-smi` also lists an existing `FC25.exe` GPU process. That proves neither per-process utilization nor that this game caused a particular sample, but clean steady GPU conditions cannot be certified. No unrelated user process was stopped. Seven-static pooled median worsens by1.308ms; its block deltas have opposite signs (+1.335/-0.101ms). Four Islands normal p95 also worsens. Preserve these data; do not report equivalence, a speedup, or attribute every variation to the new ocean. Driver power/clock/scheduling variation and unexcluded external load limit inference. A fresh final-source run with other GPU workloads closed is needed for an unqualified controlled-performance sign-off. Browser/functional checks remain verified.

Both original complete raw reports, their unfavorable readings, original pre-fix screenshots and smoke report remain outside Git; their combined validation confirms28,800 valid samples. No production/gameplay/asset change is justified solely by these confounded timings. **Historical review verdict before the clean repetition: NOT READY FOR CHECKPOINT pending final GPU verification.** The repetition below supersedes that readiness status while preserving these measurements and their limits; no5E/commit/push.

### Clean GPU repetition after closing the external game - 2026-10-21

**Completed, exit0; READY FOR CHECKPOINT for Visual5D.2.** Following the user's confirmation, FC25 was absent at preflight, periodic checks and completion; no user process was stopped. Used the unchanged `ocean-gpu.cjs`, same Chrome155.0.8059.85/RTX5050 Laptop/driver610.74,1440x900/DPR1, motion settings, ABBA/BAAB order,90 warm/120 asynchronous GPU/60 wall frames per reading. Exact source hashes, final capture bundle hashes, public scene signatures, canonical cameras and call/triangle counts match the earlier final-source run. No renderer, tests, assets or benchmark implementation was changed to obtain this result.

Raw report: `%TEMP%/catan-ocean-gpu-clean-final-e56b24379ecc4dc39cba14aaa85c753f/paired-performance.json`. **15 cases,120 readings,14,400 valid queries, zero disjoint/errors.** Preflight49C; recorded reading telemetry51–63C and0–22% utilization, with no repeat of the earlier94% load. GPU clocks remain unlocked (observed240–2707MHz), so this is a controlled paired single-device diagnostic, not universal equivalence or sustained-FPS certification. Previous two raw report hashes are unchanged; all three full reports retain360 readings/43,200 valid queries. Validation/status files are ignored `.venv/test-artifacts/ocean-gpu-clean-{preflight,baseline,final-status,summary}.json` and `ocean-gpu-clean-validation.txt`.

| Scene/mode | Before median ms | After median ms | Before p95 ms | After p95 ms |
| --- | --- | --- | --- | --- |
| Base normal |2.608|2.237|3.949|2.815|
| Base reduced |2.553|2.353|3.329|2.973|
| Base static |2.515|2.198|3.540|2.744|
| New Shores4 normal |4.497|3.974|5.354|4.794|
| New Shores4 reduced |4.538|4.144|5.478|5.320|
| New Shores4 static |4.499|4.106|5.401|5.117|
| Four Islands4 normal |4.093|3.533|5.195|4.467|
| Four Islands4 reduced |4.079|3.611|5.020|4.330|
| Four Islands4 static |4.261|3.593|5.309|5.107|
| Seven normal |0.473|0.496|1.167|1.038|
| Seven reduced |0.498|0.528|0.993|1.048|
| Seven static |0.501|0.508|1.453|1.255|
| Fifty normal |2.871|2.590|13.999|10.774|
| Fifty reduced |3.386|2.682|12.099|12.042|
| Fifty static |2.942|2.371|12.949|11.874|

Costs/resources match the earlier table exactly: +6 main-pass calls,4 GPU geometries,6 scene materials,3 programs, no new textures; resource counts remain stable within every reading. Reduced and non-Base Static still have0 idle frames; existing Base ambient10Hz and normal shared12–13Hz are unchanged. No new ocean timer. Unfavorable results are retained: seven medians increase0.007–0.030ms, seven-reduced p95 rises0.055ms, and fifty-reduced block deltas disagree (-1.423/+0.438ms). Fifty p95 remains much larger than its median. No broad speedup claim or explanation of every historical outlier is supported. The earlier1.308ms seven-static increase is not reproduced here, but remains in the preserved report.

The outstanding performance-verification gate is closed for the tested desktop/GPU scope. Existing412 frontend tests, TypeScript/build,49 PNGs,9 Chrome smoke groups,55 prepared live multiplayer checks and six focused Python checks are reused, not rerun or assigned new counts; source hashes confirm they still apply. Remaining limits: one GPU/Chrome, unlocked clocks/desktop scheduling, no low-end/mobile certification, optional two-ring readability tradeoff, existing Four Islands4 robber/Fields12 occlusion and existing large-chunk warning. Procedural ships remain default, GLB opt-in; no art approval,5E,commit,push or tag.

## Visual Phase 5D - map audit gate and bounded ocean scope

**Historical5D.1 prerequisite/audit status, superseded for rendering by5D.2 above.** The following “not implemented” statements describe their dated checkpoints, not the current renderer. Base fix is now published as `b61215b`; no historical maps/snapshots are rewritten by5D.2.

**Current correction,2026-10-20:** separately authorized Base Standard number-placement fix is implemented; focused maps,1000 seeds ×3/4 players, historical codec/PostgreSQL and508/508 scenarios pass. Final isolated-PG suite1696 passed/3 opt-in Docker skips, exit0; frontend383 passed. **Base blocker fix READY FOR CHECKPOINT**; [[Project State#Base Standard number placement - Visual 5D blocker fix, 2026-10-20]]. New recipe policy and exact old canonical recipes on new start/rematch separate red tokens through the actual graph without extra RNG; old match heads remain untouched. Official Seafarers and other custom presets are unchanged. The Gold harness derivative removes the inherited Base-only policy, retaining its fixed Gold fixture/assertions. [[Карты и сценарии#Base Standard random-number correction]]. Ocean/frame/camera scope below is still **not implemented** and does not start as part of this fix. Existing5C PNGs are historical; regenerated public gallery fixtures use corrected production numbers.

### Historical audit stop - before authorized Base correction

**Historical result2026-10-20: NOT READY at the audit stop.** Phase0 is complete:5C documentation/public gallery tools committed as **`f3dacbbb1b6f2b19008e7aee3f186c491bb4fcbc`**,7 intended files, staged whitespace/exact remote HEAD checked, normal push to `origin/main`, no tag. Graph/screenshots/generated reports/secrets excluded. Procedural remains default, GLB opt-in. The following audit paragraphs describe that earlier state, not new generator verification.

Phase1 inspected the actual engine recipes/materialization and source2021 Seafarers diagrams, not only display fixtures. Four fixed official Seafarers variants **PASS** terrain/token positions, port anchors/orientation, inventories, axial geometry and island connectivity. Base3/4 has correct19-land outline, inventory and coastline-valid ports, **but FAILS official random-token placement**: seed17 puts neighboring Fields8/Pasture6 at tiles9/10, shared edge21/31. The official Base fully random alternative forbids neighboring red numbers; this known code limitation has no approved rules exception. User requires correct underlying maps and an explicit stop on a material mismatch. Therefore no decorative renderer work was started and the existing bug was not fixed automatically.

Full matrix, exact counts/source/file references and reproduction — [[Карты и сценарии#Visual 5D - official layout audit and Base stop gate]]. Counts: Base19+0sea; New Shores3 22+15=37,4 28+16=44; Four Islands3 20+17=37,4 23+14=37. Seafarers Sea totals each include two existing full frame Sea spaces beyond loose component inventory. The source PDF was freshly fetched and matches the previously inspected cached diagrams. Native snapshot round-trip preserves the Base counterexample, and old/current gallery geometry matches production.

World extents are8.660254x8 Base,12.124356x11 for the37-hex official boards,13.856406x11 for New Shores4. Read-only projection of saved actual5C matrices shows overview rim heights82.0% Base and90.7–95.4% Seafarers in the same Canvas. Auto-fit changes viewing distance; similar screen occupancy is not evidence of identical world size. Camera/runtime unchanged.

### Requested visual scope - not implemented

After the map gate is satisfied or the user explicitly revises its scope: derive a configurable one/two-ring ocean from public coordinate occupancy only; keep it separate from playable tiles/graph/IDs/snapshots/legal targets/Fog decisions. Shared/instanced restrained water geometry, a continuous exterior-edge frame, camera fit covering frame/ports without excessive empty margin, and actual before/after gallery/GPU-timer/regression acceptance are required. The visual frame must be documented separately from the official physical cardboard frame. Hidden terrain/number assignments must never influence decorative outlines. Existing SVG, owner/controller/animation/persistence/security boundaries remain.

Phases2–6 **not implemented or tested**: no water ring/frame, new camera behavior, matched ocean before/after images, GPU A/B or multiplayer regression claim. Existing5C gallery remains inspectable at localhost18785; it is the **before** renderer, not a5D preview. No new Blender asset/model/default change. Four existing official layout tests passed; exact read-only production/codec/gallery checks passed. Full frontend/TS/build/GPU/live tests were not run because rendering never changed. Only affected Obsidian notes are modified after the checkpoint; existing DB and user graph remain untouched.

## Visual Phase 5C - read-only art review

**Completed visual investigation2026-10-20; published as `f3dacbbb1b6f2b19008e7aee3f186c491bb4fcbc`. READY FOR USER ART DIRECTION REVIEW, no A/B/C art implementation approval.** Phase5B.2 checkpoint **`0c5b2864bb989683ddd089ccdd92d696ec922ff9`** contains21 intended files; normal `origin/main` push/exact remote hash verified, no tag. User graph and media were excluded. Its completed383-test/TS/build/live acceptance results were reused without another expensive suite. The5C review changed only offline preview/capture tooling and documentation; production code/assets/DB/protocol/defaults remain unchanged.

### Actual captures and reproducibility

[art-direction-review.cjs](../../../web/e2e/art-direction-review.cjs) reuses the existing public Fog visual server and actual GamePage/Board3D. [art-review-boards.py](../../../web/e2e/art-review-boards.py) builds five non-Fog boards offline at fixed seed17, then outputs a closed board-field allowlist only. Shipped Base Standard19; official New Shores3/4 has37/44 tiles; official Four Islands3/4 both37. Frame Sea hexes are included. Display roads, ships, settlements and cities are explicitly synthetic fixture occupancy selected from the original graph, not legal command replays; no second game engine. [art-review-controller.js](../../../web/e2e/art-review-controller.js) publishes only those synthetic client frames through the existing test socket. Fog uses the existing public seven-hex fixture with three unknowns, then a synthetic revealed public frame; no trusted recipe or future assignments. Robber/pirate component study shows a public pirate position and removes the owned boats from the small area.

**24 full2560x1440 PNGs + two native browser detail clips**,12 scene configurations: five complete boards, Fog before/after, four-color procedural/GLB comparison, GLB on New Shores4, white/purple owners, neutral threats. Chrome155.0.8059.85, DPR1, existing neutral lighting, Still controls/reduced motion. Normal is unmodified CameraRig auto-fit; Close is existing real wheel limit and intentionally crops. Procedural/GLB captures on the same public fixtures have identical state hashes and camera matrices at both distances. No mesh/material/camera pose is replaced by the capture script. The initial incomplete instrumentation report remains separate; its double-count of tile metadata and number-token nodes was corrected, not a production renderer issue.

Gallery **http://127.0.0.1:18785/**. Restart from root: `node web/e2e/art-direction-review.cjs`; server and its fixture upstream bind127.0.0.1 only. No backend/PostgreSQL/login or environment secret is required. Gallery links26 original PNGs and12 actual interactive previews; it never serves arbitrary artifact paths. Existing procedural remains default, Blender opt-in. Capture command and tools requirement — [e2e README](../../../web/e2e/README.md#visual-phase-5c---actual-board-art-review).

Raw images, `capture-report.json`, `boards.json`, `gallery-smoke.json`, initial incomplete counter report and gallery overview are under `%TEMP%/catan-art-direction-5c/`, excluded from Git. Capture report includes all PNG SHA/dimensions, board/token/piece counts, camera/projection, public-state hashes, actual asset responses and12 GLB hashes/mesh/material/triangle inventory. Temporary storage may be cleared; regenerate with the checked-in tool if needed. No video/new art variant was produced in5C.

### Findings and proposal boundary

Full observed/style/complexity comparison and prioritized art work — [[Design System#Visual Phase 5C - current renderer and art direction proposal]]. Main proposal **A: clean stylized low-poly tabletop** extends the accepted brief; B: handcrafted miniature warmth is an alternative, C: atmospheric fantasy conflicts with accepted non-cinematic constraints and is comparison-only. No option is user-approved. Proportion/detail imbalance across wheat/sheep/houses, different Sea/ocean treatment, ship/pirate/harbor family and Fog integration are artistic concerns. One concrete readability issue appears in `05-four-islands-4-procedural-normal.png`: robber tile29/Fields12 is partly hidden behind wheat/number presentation at default camera, hat still visible. No missing state/gameplay defect claimed or fixed. Preserve number/port readability and ownership semantics first.

Read-only asset inventory finds44,300 triangles/2,744,072bytes in Fields mesh definitions, versus2,470 mountains and215/13,216bytes ship pilot. All12 terrain/building/ship GLBs are untextured. Declared materials and geometry counts are not draw timings; no bottleneck or GPU improvement is inferred. Both5B.2 primary/repeat raw reports remain byte-identical, including contradictory results. No new GPU benchmark, art approval, default promotion, dynamic animation regression or other-hardware certification.

Verification: all26 PNG hashes/dimensions and12 source GLB hashes verified; token/piece counts, empty fixture command output, hidden Fog masking and opponent privacy assertions pass. **104 recorded model responses are200; capture errors[]**. Gallery HTTP/images/preview links and six actual interactive scene reloads pass, including real zoom/reset, GLB readiness and default no-GLB-fetch. Node syntax/offline public generator, documentation links and Git whitespace checked. Full frontend383 tests/build and Python/PostgreSQL were not rerun: production/dependencies/assets are unchanged. Graph/data preserved. Review published as `f3dacbb` with7 intended files; normal push/exact remote verified. No A/B/C style implementation starts automatically; the subsequently requested bounded-ocean scope is gated above.

## Visual Phase 5B.2 - ship topology and selective culling

**Implemented/verified in experimental opt-in scope,2026-10-20; published as `0c5b2864bb989683ddd089ccdd92d696ec922ff9`.** Phase5B.1 was committed/pushed as `986c99c3cd1b0a7bb38857b75401a4dde2f1bd2a`; exact upstream hash and six-file scope verified, user graph excluded. Original `.blend`/GLB/exporter remain recoverable from that checkpoint (same asset as5A), providing the requested version-control backup before correction. Phase5B.2 checkpoint has21 intended files, cached whitespace and exact remote HEAD verified; graph/artifacts excluded, no tag.

### Actual topology and minimal corrections

The existing Blender5.2.2 LTS Store CLI opened the original native source read-only. [ship_topology.py](../../../tools/blender/ship_topology.py) audits positional-weld adjacency without editing vertices/normals; [export launcher](../../../tools/blender/export_ship_pilot.ps1) supports `-InspectOnly [-SourcePath ...]`. Original CanvasIvory has16 inconsistent shared edges despite unit/finite normals, no boundary/degenerate triangles. Its eight sidewall face windings are reversed explicitly. The closed PlayerColor pennant is consistently inward (signed volume about-0.000031725); its five faces are reversed, without moving vertices. Other originally closed components were outward.

The original colored rail is a renderable open DoubleSide shell, with14 boundary edges at the inner lip/lower seam. Opening alone is not classified as a defect. To support FrontSide as a solid rail, inner wall and underside are added within the same external outline:14 quads/28 triangles. This changes visible inner-wall shading slightly; the hidden underside closes that component. The separate HullWood top-facing inset deck is an intentional thin overlay: its seven boundary edges are retained, not repaired indiscriminately. No smoothing, retopology, hull/sail redesign or outer-point displacement.

Native source and reimported GLB now have zero inconsistent/shared non-manifold edges, zero degenerate triangles/invalid unit normals; all closed components have positive signed volume. Only the documented deck overlay remains open. These checks do not test arbitrary self-intersections or claim a boolean-unioned printable solid: the original overlapping component construction is retained.

### Selective culling and appearance boundary

Opaque HullWood and PlayerColor use **FrontSide**; thin billowed CanvasIvory conservatively retains **DoubleSide**, avoiding an unnecessary additional canvas-side change. Above-board CameraRig limits remain21.6-52.2 degrees from vertical. The open deck faces upward throughout that supported range. No global FrontSide replacement.

Transparent hover/source echoes preserve the established **DoubleSide on all three Canvas-owned ghost material copies**, opacity.46, depth policy, no shadows and ignored raycasts. Initial candidate inherited opaque FrontSide in ghosts (four draws); it was not kept. [cloneShipScene](../../../web/src/board3d/shipAssets.ts) wraps existing clonePieceScene only for this local ship policy; [ShipAsset.tsx](../../../web/src/board3d/ShipAsset.tsx) uses it. Cached source/neutral and other piece materials are never mutated. Final isolated ghost stays six draws; triangles374->430 reflect enclosure, not an advertised ghost optimization.

Unchanged: Procedural default/no-request/loading-error fallback, exact PlayerColor palette, source pivot/scale/edge IDs/owner/root yaw, build550/move900/depart350 ms/shared12Hz wrappers, controller, SVG and snapshot path. No backend/rules/protocol/persistence/security/Fog gates/dependencies or other model changes.

### Export and size

The same checked-in exporter regenerates only the existing pilot `.blend`, GLB and manifest. The native saved source was reopened/inspected; a second fresh temporary-root export produced identical GLB bytes, with successful GLB reload/topology/bounds validation. Original is preserved in Git and outside Git at `%TEMP%/catan-ship-topology-5b2/original/`.

| Property | Original | Corrected |
| --- | --- | --- |
| GLB bytes | 12,080 | 13,216 (+1,136) |
| Triangles | 187 | 215 (+28) |
| Source vertices | 128 | 128 |
| Exported POSITION vertices | 339 | 381 (faceted normal splits) |
| Meshes/materials/textures | 3/3/0 | 3/3/0 |
| Native blend bytes | 100,816 | 101,000 |

Corrected SHA256 **`0a6b103f64fd29bca195666e1e6ab97808f4812b2de6fec785b413a932294749`**; unchanged bounds `[-.40,0,-.14]..[.40,.535,.14]`. Manifest adds source/import topology and explicit culling policy. No baked animation, external dependency or additional Blender model. Native blend byte identity across saves is not claimed. Independent frontend tests inspect the actual GLB winding, normals, closed-component volumes, culling, hash/manifest, owner/ghost isolation and original transforms/motion.

### Visual verification and differences

Actual Board3D original/corrected/procedural captures use the same public snapshot, owner colors, camera, viewport and lights/shadows. Normal/close, both azimuths, high/low allowed polar limits, real legal hover,24 ships/50 hexes and matched construction/movement ages pass. Original/corrected root anchors and finite scales match. Final30 screenshots/report: `%TEMP%/catan-ship-topology-5b2/visual-animations/comparison.json`; static18-shot final set also retained under `visual-final/`. Construction ages175/275/1200 ms; movement175/450/1200. Clock control is test-only, on disposable capture pages, and uses actual production cues. Normal views and GPU runs do not use it.

Pointer drags initially coalesced differently, so `visual-candidate/` retains the failed camera-comparison report. Final runner records actual input poses, then restores the original control-generated camera only for matched capture; no production camera change or alternate renderer. Static normal/close/back/ghost images were inspected. The outline/colors/style remain; closed inner rail and local shadow/inner-face shading differ. Pixel equivalence and new artistic approval are not claimed. Current six-group art regression also passes, including fallback404, finite motion/recovery fences, resource sharing, reduced/static/SVG, colors, ports/Fog and resize; WebM at `art-regression/3bb5e67366ac7f1ea6a31a5349c9159b.webm`.

### Controlled original/corrected GPU comparison

[ship-topology-compare.cjs](../../../web/e2e/ship-topology-compare.cjs) reuses the unchanged asynchronous samplePage probe from5B.1. Same current Board3D runtime, original fixed GLB bytes from Git versus corrected bytes. Chrome **155.0.8059.85**, RTX5050 Laptop/ANGLE D3D11/driver610.74,1440x900/DPR1/Canvas1186x723. Two independent complete ABBA/BAAB runs, fresh contexts/readiness on each side,90 warm/120 GPU/60 wall samples per reading, main plus shadows. **96 readings/11,520 valid GPU timers/5,760 wall samples/8,640 warm samples, zero disjoint/browser errors**. All chronological samples, opposing readings and telemetry remain saved. Clock/power/ambient phases are not locked; other user applications remain. This is a render command-span benchmark, not sustained FPS or isolated fragment execution.

All arrows original -> corrected, ms; pooled nearest-rank GPU median/p95:

| Scene | Primary median | Primary p95 | Repeat median | Repeat p95 |
| --- | --- | --- | --- | --- |
| 7 normal | 1.950 -> 1.785 | 4.097 -> 4.054 | .853 -> 1.061 | 3.324 -> 3.670 |
| 7 reduced | 1.677 -> 2.030 | 4.280 -> 4.322 | 1.522 -> 1.365 | 3.675 -> 3.596 |
| 7 static | .870 -> .929 | 3.656 -> 3.597 | .963 -> 1.082 | 3.975 -> 3.477 |
| 50 normal | 7.440 -> 7.376 | 13.794 -> 14.539 | 7.676 -> 7.162 | 14.618 -> 14.178 |
| 50 reduced | 7.652 -> 7.560 | 14.813 -> 14.345 | 7.558 -> 7.544 | 14.882 -> 15.144 |
| 50 static | 7.462 -> 7.419 | 14.742 -> 14.322 | 7.720 -> 7.517 | 14.625 -> 13.782 |

Both runs: calls395->395/triangles52,452->52,676 on seven tiles; calls2390->2390/triangles317,934->319,278 on50. Programs9->9; scene materials104/111 unchanged; resident geometry/texture counts154/6 and153/17 respectively, matching before/after every steady reading. Topology closure adds triangles; culling does not reduce submitted draw counts. Whole-scene unique geometry counts149/146 also match. Shared idle remains12Hz normal and0 reduced/static.

**No repeatable overall speedup claimed.** Seven-static median is worse in both runs (+.059/+.119 ms); other small-scene signs reverse. Fifty-normal median improves in both, but p95 does not uniformly improve. Corrected maximum GPU spans20.630 ms primary/21.646 repeat are retained. Per-reading clocks1335-2602MHz/P2/P4 and61-65 C vary. Chrome5B.1 was155.0.8059.80 and its warm in-page method differs; absolute timings across phases do not establish a regression or its cause. Raw reports: `gpu-primary/paired-performance.json`, `gpu-repeat/paired-performance.json` under the same temporary artifact root. No outlier filtering.

### Cold-load correction and limitations

The first two steady runs served original bytes from memory but corrected bytes through filesystem reads. Their cold-fetch fields are retained **but are not a symmetric asset-loading comparison**; neither fetching path runs inside the timed steady phase after readiness/compile/warm-up. The comparison helper now preloads both fixed public GLBs and uses the same response branch. Separate `--cold-only` ABBA/BAAB verification on7/50 normal adds16 fresh contexts, HTTP cache disabled, with no GPU timing phase. `cold-normalized/cold-load.json` records every reading.

Symmetric fetch nearest-rank medians:7 hex1.70->4.50 ms;50 hex1.70->1.60. Ranges original1.30-6.70/corrected1.50-8.70 ms. Detection includes UI automation:7 median30.0->31.4 ms,50 median41.9->40.2. Reported transfer12,380->13,516 bytes. Small four-reading-per-side samples do not prove a loading improvement or latency regression. Browser/driver shader caches are not flushed; first draw may precede detection, so no isolated first-use shader compilation claim. Steady program/resource endpoints match; raw wall/compile diagnostics remain in the full reports.

### Verification and readiness

**383 frontend tests /TypeScript /production build pass**, actual exit0. Lazy Board3D982.80kB/267.22gzip; existing chunk warning retained. Blender native inspection, two byte-identical exports/reimport and manifest/independent GLB topology checks pass. Chrome matched capture/current six-group art and seven-group construction regressions pass; the latter preserves cross-piece/default-procedural behavior and does not independently certify new GLB animation. **Two actual two-client ship/Fog WebSocket/PostgreSQL cases /seven groups pass**: rejected-state equality, accepted build/move/discovery/private Gold, duplicate receipt, refresh/native reconnect/two backend restarts without replay. Fresh disposable localhost DB only; existing accounts/matches/volumes untouched. Test PostgreSQL was stopped after verification without deleting its data; task backend exited. Reports `live/report.json`, `building-regression/after.json`. No production backend change, full Python/scenario/Docker-build rerun or new natural match claim.

Interactive original and corrected preview is running independently: `node web/e2e/ship-topology-demo.cjs`, localhost18781/18782 respectively; select **Ship model -> GLB pilot**, or Procedural on either. Final real Chrome smoke verifies both actual URLs, four ships,187/215 triangles and expected12,080/13,216-byte SHA, zero default asset requests/browser errors. `preview-smoke.json` and two PNGs are saved under the same artifact root. Both use actual Board3D/public synthetic snapshots, ports/Fog/four colors and existing Construct/Move/50/camera controls. No public feature gate or trusted recipe endpoint. [Instructions](../../../web/e2e/README.md#visual-phase-5b2---ship-topology-comparison).

**Historical verdict: READY FOR CHECKPOINT for topology correctness and experimental opt-in scope; published as `0c5b286`.** Affected documentation links/Git whitespace and complete intended-file scope were checked; graph/source backup/other assets and database data preserved. Performance optimization/default promotion remains unproven; low-end/mobile/other APIs and arbitrary underside cameras/self-intersections are not certified. User aesthetic approval remains separate. No tag or broader art overhaul.

## Visual Phase 5B.1 - ship GPU investigation

**Historical investigation completed/tested2026-10-19; published2026-10-20 as `986c99c3cd1b0a7bb38857b75401a4dde2f1bd2a`.** Six intended files committed/pushed with exact remote hash/whitespace checks; graph/artifacts excluded, no tags. No promotion or art approval. Published Phase5A is `5a3902cd22e080c14d4b6b43c415ed8026297118`. That5B.1 checkpoint made no runtime/model change; its original asset measurements below remain historical. Subsequently authorized5B.2 is documented above.

### Historical evidence and confirmed measurement defects

Both original Phase5A reports are preserved, including 50-normal synchronized wall medians3.80->3.70 ms and independent3.85->5.00 ms/p95 up to11.20. The latter aggregate contains one GLB reading6.20/11.20 followed by3.80/4.40. Across all four GLB readings from both reports, reading medians are3.80/3.60/6.20/3.80; procedural3.70/3.90/3.80/3.90. No universal order/warming trend is established. Do not discard the anomalous reading.

The old field `gpuMedianMs` actually times CPU `performance.now()` around `gl.render + gl.finish`: synchronized render **wall time**, including JS/driver/wait/scheduling and potentially an earlier queued R3F frame. It is not isolated GPU elapsed time. The old helper saves only per-reading summaries; underlying60 wall and30 submission durations were discarded. Historical statements about preserving every raw timing sample are superseded here. Their missing frame samples cannot be recovered. Unequal readiness dwell (GLB side calls fullyReady twice), twelve burst warm renders, ten-render bursts versus paced submission measurements, asymmetric screenshots and unrecorded animation phases/power states limit attribution. Old calls/triangles cover the main pass only: Three resets info after shadow rendering, although timed work includes shadows.

Original immutable reports: `%TEMP%/catan-ship-art-pilot-final/paired-performance.json` SHA256 `ebe9feb20dd6a33ab45cf30dd8afe46b7f9c2c8e512f1226788066ed9bd113ac`; `%TEMP%/catan-ship-art-pilot-repeat/paired-performance.json` SHA256 `2b10d543e8b8e690e5889a60b66b8303a1b9d3a15e02adf46eff9b314e41a1b0`.

### Corrected controlled method

[ship-art-gpu.cjs](../../../web/e2e/ship-art-gpu.cjs) pins the same published5A `web/src` on both sides and verifies the unchanged GLB SHA, then switches models in one actual public Ship Art Demo page. This compares current production-default procedural versus opt-in GLB, rather than different renderer bundles. Chrome155.0.8059.80, RTX5050 Laptop/ANGLE D3D11, driver610.74,1440x900/DPR1/Canvas1186x723; matching public snapshot hash, camera, shadows, occupied edges/owners, four ships on seven hexes and24 on50. Two separate Chrome runs cover all six normal/reduced/static cases.

Each run/case uses ABBA then BAAB (A=Procedural, B=GLB), four readings per model. Both models are loaded before the paired phase. Every reading waits for compileAsync, then90 paced warm renders,120 GPU queries and60 separately paced synchronized wall samples. All frames have chronological indices/timestamps. GPU uses asynchronous `EXT_disjoint_timer_query_webgl2` with availability/disjoint checks; invalid results remain recorded. Wall samples drain earlier work outside the measured span. Automatic R3F drawing is paused/restored only by the external probe; existing normal ambient listeners continue, settled fixtures have no active finite cues. This measures command-span render cost, not sustained gameplay FPS, GPU busy utilization or an isolated ship shader. Actual durations vary with refresh/scheduling and are recorded; clocks/power are not locked. No user applications are stopped. Sampling order/counts/cadence are identical; no claim of an exclusive GPU or fixed millisecond period.

Counters explicitly reset before rendering with info.autoReset=false, including **main plus shadow passes**, unlike historical5A counters. Both runs complete exit0/errors[]: **96 paired readings total;11,520 valid GPU timers,5,760 wall samples and8,640 warm samples**, zero disjoint results. Program/resource counts match before and after every steady reading (nine shader programs); these endpoint checks do not profile every allocation between samples. No model reload after switching; exactly one12,080-byte GLB/page. Normal idle returns to12 frames/s; reduced/static0; no fixture commands sent. Raw values and outliers are retained, never filtered to improve results.

### Complete steady-state results

All arrows are Procedural -> GLB, ms. GPU median/p95 are nearest-rank statistics pooled from480 GPU samples per model/case/run, not the historical mean-of-two-reading-medians metric. New GPU values must not be compared numerically with old wall-time fields as though they were the same measurement.

| Scene | Primary GPU median | Primary GPU p95 | Repeat GPU median | Repeat GPU p95 |
| --- | --- | --- | --- | --- |
| 7 normal | .695 -> .657 | 1.336 -> 1.219 | .674 -> .595 | 1.222 -> 1.037 |
| 7 reduced | .652 -> .621 | 1.215 -> 1.237 | .652 -> .642 | 1.181 -> 1.162 |
| 7 static | .580 -> .561 | 1.201 -> 1.165 | .677 -> .640 | 1.154 -> 1.084 |
| 50 normal | 3.256 -> 3.134 | 4.191 -> 3.990 | 3.337 -> 3.189 | 4.533 -> 4.040 |
| 50 reduced | 3.208 -> 3.166 | 4.023 -> 3.885 | 3.306 -> 3.233 | 4.058 -> 4.021 |
| 50 static | 3.430 -> 3.407 | 4.204 -> 4.271 | 3.293 -> 3.115 | 4.344 -> 3.796 |

Separate synchronized render wall-time diagnostics (240 samples/model/case/run):

| Scene | Primary wall median | Primary wall p95 | Repeat wall median | Repeat wall p95 |
| --- | --- | --- | --- | --- |
| 7 normal | 1.40 -> 1.40 | 2.90 -> 2.10 | 1.40 -> 1.30 | 2.00 -> 1.80 |
| 7 reduced | 1.40 -> 1.40 | 1.80 -> 1.70 | 1.40 -> 1.40 | 1.80 -> 1.70 |
| 7 static | 1.30 -> 1.30 | 1.80 -> 1.80 | 1.30 -> 1.40 | 1.80 -> 1.90 |
| 50 normal | 4.50 -> 4.40 | 5.20 -> 5.40 | 4.80 -> 4.60 | 5.90 -> 5.10 |
| 50 reduced | 4.70 -> 4.60 | 5.60 -> 5.30 | 4.70 -> 4.70 | 5.40 -> 6.10 |
| 50 static | 4.80 -> 4.70 | 5.50 -> 5.40 | 4.70 -> 4.60 | 5.60 -> 5.50 |

Main+shadow counts are stable in all modes/runs: seven tiles calls411->395/triangles51,660->52,452;50 tiles calls2486->2390/triangles313,182->317,934. More triangles and fewer calls do not independently establish performance equivalence. In these warmed in-page comparisons both models retain the already-loaded geometry caches:154 geometries/six textures on seven tiles,153/17 on50, with no steady churn. Historical separate-page5A GLB readings added three shared geometries; that is not a between-model memory delta in the new warmed test. The paired-block deltas/per-reading medians, submit timings, every sample and sensor snapshots are in the raw reports.

**Contradictory tails remain:** primary50-static GPU max14.889 ms GLB, versus procedural50-normal max11.047; independent repeat maximum9.594 occurs in procedural50-static. The worst GLB span also has16.90 ms submission/22.60 ms query-ready wall time. Primary50-static p95 is slightly worse for GLB; repeat50-reduced wall p95 is6.10 versus5.40. These are retained, not explained away by lower medians. Timer spans can include scheduling/command-feed stalls; they do not isolate asset shader execution.

### Loading, warming and attribution limits

Twelve fresh page/context JS caches with HTTP cache disabled: GLB fetch duration **1.70-4.70 ms**,12,080-byte body/12,380-byte reported transfer. Opt-in to rAF detection **17.50-40.10 ms** includes UI automation, parsing/mounting and scheduling. A first render may precede detection; the explicitly named post-detection render and remaining compileAsync wait do not measure true first-use shader compilation. Browser/driver shader caches were not forcibly cleared. Remaining compileAsync waits2.40-16.70 ms include traversal/driver work; steady program count is9->9. Initial fetching/remaining compile waits and warm frames are excluded from steady statistics.

Confirmed environmental variation in the new runs, including start/end snapshots: P2/P4/P5 states, graphics clock **540-2572 MHz**,53-62 C,7.99-22.99 W. Per-reading snapshots alone are P2/P4,54-62 C. These snapshots demonstrate varying power/clock conditions; they do **not** prove thermal throttling or explain the historical6.20/11.20 reading, whose telemetry/raw frames were not recorded. Driver scheduling, other GPU work, CPU/GC/JIT/command-feed stalls, warming and normal-phase variation remain possible contributors. Matching snapshots/camera/counts and matching endpoint resources rule out mismatched board sizes, ship counts, repeated loading and net per-reading program/resource growth in the new comparison. No specific historical root cause is proven.

### Asset audit and future optimization candidates

The actual `ship_pilot.blend` was opened read-only with installed Blender5.2.2 LTS background CLI, without saving. Three mesh objects plus identity root/pivots match the export profile; source vertices128 versus exported POSITION/NORMAL vertices339 (flat-normal splits),187 triangles. GLB has three opaque PBR materials, no textures/UV/tangents/skin/morph/baked animation/external resources. Original local-X heading, grounded Y pivot, `.88 * edge length` X scale and outer edge position/yaw/motion wrappers remain. Source and GLB hashes are unchanged.

All three GLB materials are **DoubleSide**; procedural materials use FrontSide. This disables culling and changes shadow-side work; transparent DoubleSide ghost rendering takes six draws/374 submitted triangles versus five/88 procedural, but settled paired cases have no ghosts. The broader/taller sail also changes projected/shadow coverage. These are real mechanisms, **not proof of the old timing spike**. The template/geometry/neutral materials are shared, owner/ghost copies pooled, and cloning does not copy geometry or introduce an animation mixer/extra clock.

Do not blindly switch to FrontSide: topology inspection found inconsistent sail edge winding, an inward-wound pennant and open gunwale/deck surfaces currently masked by DoubleSide. A future5B.2 candidate is to repair intended winding/surfaces first, then evaluate selective culling/ghost single-pass handling with equivalent front/back/shadow visual acceptance. It is not an approved or measured optimization. Instancing three parts is another conditional future option only if profiling warrants its complexity; preserve exact anchors/owner colors/motion/ghosts. Do not merge flat-normal splits or simplify art merely to reduce a count.

### Evidence, reproduction and verdict

Raw reports and13 screenshots each: `%TEMP%/catan-ship-gpu-5b1-primary/gpu-investigation.json`, `%TEMP%/catan-ship-gpu-5b1-repeat/gpu-investigation.json`. Each directory contains7/50 normal/reduced/static procedural and GLB PNGs plus `7-glb-close.png`; normal, close-up and50 GLB images were visually inspected. Four owner colors and existing Fog/buildings/ports use synthetic PUBLIC fixtures, not a natural full match. Native source read report: `%TEMP%/catan-ship-source-audit-323115393be64aeeacddb4027050d446.json`. Earlier5A videos/screenshots/reports remain untouched.

Existing preview stays loopback-only: `node web/e2e/ship-art-demo.cjs` -> `http://127.0.0.1:18780/?demo=1&shipsart=1`. Use model/50 tiles controls and real wheel zoom; default remains Procedural. [Corrected benchmark instructions](../../../web/e2e/README.md#visual-phase-5b1---gpu-investigation).

**Verdict: INCONCLUSIVE for default promotion; no demonstrated persistent GLB-specific regression on this tested GPU.** Both new50-normal medians/p95 favor GLB, but small differences, retained tails, unlocked clock/power, one GPU and an unidentified historical outlier prevent equivalence/general performance claims. Continue optional art evaluation separately; do not promote or redesign the model based only on the original wall-time anomaly. Phase5B.2 art refinement can be proposed with topology/culling validation and user art review, not started automatically.

Verification: **380 frontend tests pass** (377 existing +3 benchmark aggregation/order/invalid-timer cases), TypeScript passes; smoke and both complete controlled runs exit0. No Python suite, new backend/PG acceptance, production build or Docker build run: runtime, dependencies and deployment are unchanged. No new claim about full-match/gameplay coverage. User graph, asset/source, database data and production default preserved.

## Visual Phase 5A - Blender pipeline and ship pilot

**Historical completed verification; published as `5a3902cd22e080c14d4b6b43c415ed8026297118` on2026-10-19 after explicit authorization.** Exactly27 pilot files committed/pushed normally; cached whitespace and exact remote HEAD verified, graph/artifacts excluded, no tags. One additional temporary-root export reproduced identical GLB bytes at checkpoint. Phase4 checkpoint is `2d93c40caed5c5febfc88f49e1234fb7853d2db1`. The following5A evidence is historical; measurement definitions/limits are corrected by Phase5B.1 above.

### Toolchain and reproducible source

Actual **Blender 5.2.2 LTS** is installed as Windows Store package `BlenderFoundation.Blender_5.2.2.0_x64__ppwjx1n5r4v9t`. Initial PATH/standard-folder discovery missed this installation; the earlier missing-toolchain description is superseded. Direct execution of its WindowsApps binary returns Access denied in this shell. The registered Store application can run the same background CLI through standard IApplicationActivationManager activation, preserving package identity. No ACL/PATH/registry/installation change or another Blender copy; MCP is not needed by the checked-in launcher. The existing GUI scene is never opened or replaced by the exporter.

Reproduce from root: `powershell.exe -NoProfile -File tools/blender/export_ship_pilot.ps1`. Classic/portable installations can pass `-BlenderPath`. [Launcher/source contract](../../../tools/blender/README.md). `export_ship_pilot.py` creates the original model in a fresh `--background --factory-startup` CLI process and exports only selected mesh/root nodes, Y-up normals/materials, no textures/cameras/lights/baked animations. Outputs: `docs/design/references/blender/ship_pilot.blend`, `ship-pilot.json`, `web/public/models/pieces/ship-pilot.glb`. Existing terrain/building sources remain unchanged. The script regenerates its pilot outputs, not manual edits to generated source.

Two independent output roots produced identical GLB bytes, SHA-256 `07f4fe56c41de24d85f332ab5f7dafbeec176767f51df137a2c2a72d20e911f9`; both exports reimported and verified mesh/material/triangle/world-bounds data inside disposable CLI processes. Native blend byte identity is not claimed. Asset: **12,080 bytes /187 triangles /3 meshes /3 untextured PBR materials**, no external resources or required extensions. `HullWood` and `CanvasIvory` stay neutral; exact `PlayerColor` alone receives existing ownership colors. Three bounds approximately `[-.40,0,-.14]` to `[.40,.535,.14]`.

### Art direction and runtime boundary

Observed baseline: matte warm terrain/rims/raised relief, ivory tokens and beveled owner-colored buildings; player ships were simpler five-mesh hull/deck/mast/sail/accent. The pilot adds a faceted wooden hull, continuous owner-colored gunwale/benches/pennant and a broad lightly billowed ivory sail. Restrained geometry only: no realistic texture set, rigging, particles, pirate/terrain/building replacement or board redesign. Four real project palette colors are inspectable in the synthetic preview. This is one experimental art pilot, not final art approval.

Unchanged flow: committed player-specific snapshot -> GamePage/BoardRenderer -> public render ships -> ShipFleet3D -> original Ship3D anchor/motion group -> selected body. [shipAssets.ts](../../../web/src/board3d/shipAssets.ts) caches one immutable GLTF template/page; [ShipAsset.tsx](../../../web/src/board3d/ShipAsset.tsx) reuses existing Canvas-owned `clonePieceScene` material isolation and ignored raycasts, with original procedural body while loading/on failure. Failed loads are cached until page refresh. Cached source geometry/neutral materials are not disposed by local primitive clones.

**Ship model: Procedural /GLB - pilot** is local BoardRenderer state, default Procedural. Default never requests the new GLB; explicit choice loads it once, additional asset transfer **12,080 bytes** with no textures. Refresh resets the local choice. Confirmed ships, legal hover ghosts and finite source echoes use the same selected body. Original edge root midpoint/Y=.32/local-X heading/yaw `-atan2(dz,dx)` remain; GLB X scale is `ship.length*.88`, without terrain transforms. Inner construction550 ms/movement900 ms/departure350 ms and shared 12 Hz rocking retain original triggers/poses. No new continuous clock, server option, model IDs, alternate game state or controller/rules change. SVG remains unchanged.

### Executed verification

**377 frontend tests pass** (369 checkpoint +8 ship asset cases), TypeScript and production build pass. Real GLB/cache/concurrent/failure fallback, six ownership colors, neutral/ghost isolation, raycast/resource ownership, profile/axes and original animation endpoints tested. Build: Board3D **982.63 kB /267.16 gzip**, versus checkpoint981.25/266.78; existing chunk-size warning remains. No dependency change. Full Python/scenarios not rerun: production backend is untouched; Blender tooling is separate from engine runtime.

Chrome155.0.8059.80: **six public art acceptance groups** pass on final runtime/asset, including default no-request, one cached load, four colors with unchanged shared neutral materials, exact anchors, active GLB source echo, construction/movement, stale/duplicate/reject, Fog/settlement/port, multiple camera distances, 24 ships/50 hexes, SVG, resize, Still/reduced/shared idle and 404 procedural fallback. Final artifacts: `%TEMP%/catan-ship-art-pilot-final/acceptance.json`, PNGs and WebM path in report. Initial successful report/video under `catan-ship-art-pilot/` also retained. Fresh checkpoint BEFORE7/50/near/far/construction/movement/reduced captures remain at `catan-ship-art-pilot-baseline/`; these earlier scenes are baseline inspection, not the matched four-owner performance fixture.

**Seven real two-client ship/Fog WebSocket/PostgreSQL groups pass**, actual exit0, production frontend/executor/F1/receipts with guarded prepared fixtures. GLB selected before paid build/move; both clients must load actual GLB for occupied ships. Invalid command preserves both personalized snapshots; accepted ship motion/discovery/private Gold, duplicate receipts, refresh/native reconnect and two backend restarts preserve exact state without replay. Local model choice is selected again after recovery/mandatory Gold completion and stays quiet. Four expected restart refusals, no unexpected JS/console errors. Report `%TEMP%/catan-ship-art-live-final-2/report.json`. Initial test-oracle wait incorrectly required a visible GLB in a zero-ship opening; fixed to wait only for actual occupancy, then require GLB after the accepted build. Initial failed report is retained separately; no runtime defect or gameplay assertion weakened.

Existing final-source visual regressions also pass: **eight robber/pirate groups and seven construction groups**, including exact anchors, neutral theft privacy, source echoes, cached reconnect/new epoch, combined Fog/ships/buildings, static/reduced and resize. Reports `%TEMP%/catan-ship-art-threat-regression/after.json` and `catan-ship-art-building-regression/after.json`.

These are prepared/public fixtures and bounded acceptance, not new natural/competitive four-player matches. Test-only internal Fog capability stays in its existing isolated launcher; public admission/emergency defaults remain0/0. No production backend/protocol/persistence/auth/rules/maps/Fog-gate change, database reset or volume deletion.

### Viewable comparison and controlled performance

`node web/e2e/ship-art-demo.cjs` -> `http://127.0.0.1:18780/?demo=1&shipsart=1` (loopback; optional `CATAN_SHIP_ART_PREVIEW_PORT`). Actual Board3D and synthetic PUBLIC snapshots, four owner colors,7/50 tiles, model toggle, Construct/Move/Reset/Multiple ships and existing effects/reduced controls. Reset before replaying consumed targets. No backend, trusted assignments, credentials or gameplay execution. Earlier procedural BEFORE capture/preview is retained at18779. Restarting that helper compiles the current working tree; use the comparator's pinned Git blobs for a reproducible checkpoint comparison. [Browser reproduction](../../../web/e2e/README.md#visual-phase-5a---blender-ship-art-comparison).

Primary and one independent repeat both complete exit0/errors[], retaining per-reading summaries, not the individual frame timing arrays (see Phase5B.1 correction above). Exact checkpoint2d93c40 runtime Git blobs versus new GLB, same four-owner public state/hash/camera/DPR1/shadows/Chrome155/RTX5050 Laptop/ANGLE D3D11,1440x900/Canvas1186x723. One measured page at a time, B/A/A/B ordering,12 warm renders,60 synchronized render+finish wall and30 submission samples per reading. Table preserves originally reported values; its old GPU label actually denotes synchronized wall time. Mean of two medians; p95 is the worse reading. No isolated GPU/CPU or sustained-FPS claim.

| Scene | First wall median ms | Repeat wall median ms | First wall p95 ms | Repeat wall p95 ms | First submit median ms |
| --- | --- | --- | --- | --- | --- |
| 7 normal | .90 -> .95 | .80 -> .85 | 2.20 -> 3.00 | 1.60 -> 1.50 | 1.30 -> 1.20 |
| 7 reduced | .90 -> .90 | .80 -> .85 | 2.40 -> 2.30 | 1.40 -> 2.40 | 1.20 -> 1.10 |
| 7 static | 1.50 -> .85 | .85 -> .85 | 2.70 -> 2.10 | 1.40 -> 1.60 | 1.65 -> 1.15 |
| 50 normal | 3.80 -> 3.70 | **3.85 -> 5.00** | 4.90 -> 4.40 | **5.90 -> 11.20** | 4.10 -> 3.90 |
| 50 reduced | 4.00 -> 3.75 | 3.50 -> 3.55 | 4.90 -> 5.10 | 4.60 -> 4.60 | 4.20 -> 4.20 |
| 50 static | 3.75 -> 3.70 | 3.70 -> 3.50 | 5.30 -> 5.50 | 4.80 -> 4.10 | 4.15 -> 3.95 |

**Contradictory50-normal repeat is retained, not discarded:** two current readings had medians6.20/3.80 ms, aggregate5.00 versus baseline3.85. Initial7-static baseline also varied1.20/1.80 ms. No third timing run, optimization or GPU-performance-equivalence claim. The pilot remains explicitly opt-in with unchanged procedural default; it is not approved as a default replacement. Low-end/mobile/battery and broader hardware behavior remain unverified.

Stable counts (both runs):7 tiles/four ships calls237->229, triangles29,574->29,970;50 tiles/24 ships calls1387->1339, triangles180,310->182,686. Each pilot is three meshes/187 triangles versus five procedural meshes/88 triangles. Three additional shared geometries; textures unchanged (six small/17 large). Payload12,080 bytes once after opt-in; Chrome reported12,380 bytes response transfer including accounting/header overhead, no extra textures. Default makes no model request. Ship-only shared idle12->12 Hz before/after finite motion; all-still/reduced0, no idle React commits or geometry/texture churn. Transient source echo uses the same selected body/resources; no new continuous clock.

Reports: `%TEMP%/catan-ship-art-pilot-final/paired-performance.json` and `catan-ship-art-pilot-repeat/paired-performance.json`; both preserve raw GPU/CPU/calls/triangle/resource readings and matched PNGs. Final acceptance's actual SVG round-trip was also checked separately (two DOM checks, SVG present/Canvas absent and quiet GLB restoration) in `svg-round-trip.json`. Recording is separate from measurements; final video `f4fe86d4245e8efa0f0ba9734d1f1a9b.webm`. Earlier successful report/video and checkpoint BEFOREs are retained separately. Do not infer four-player live or full natural-match certification from these public display fixtures.

Historical scope: one original pilot asset/source/profile plus reproducible CLI tooling; optional body/cache/control propagation and focused tests/previews/docs. No production backend, engine rules, protocol, database schema, Fog admission, auth, dependency, terrain/building/robber/pirate asset change. User GUI scene, graph/accounts/matches/volumes preserved. Test PostgreSQL was stopped without deleting data. Phase5A was subsequently published only with explicit authorization as recorded above.

### Exact change scope and limits

**27 intended files**, excluding pre-existing user graph; runtime8 files **+88/-16 lines**.

- Runtime: `web/src/components/BoardRenderer.tsx`; `web/src/board3d/{Board3D.tsx,InteractionOverlay3D.tsx,Pieces3D.tsx,ShipFleet3D.tsx,board3d.css,ShipAsset.tsx,shipAssets.ts}`.
- Tests/preview7: `web/e2e/{fog-fixture.tsx,ships-live.cjs,ship-art-demo.cjs,ship-art-visual.cjs,ship-art-compare.cjs}`; `web/tests/{fixtures/publicShipArt.ts,ship-asset.test.mjs}`.
- Export tools2: `tools/blender/{export_ship_pilot.py,export_ship_pilot.ps1}`.
- Art/source/profile3: `docs/design/references/blender/{ship_pilot.blend,ship-pilot.json}`, `web/public/models/pieces/ship-pilot.glb`. Source blend100,816 bytes; production build GLB copy matches source SHA.
- Documentation7: this plan, Project State, Design System, React interface, Styles/visual boundaries, `web/e2e/README.md`, `tools/blender/README.md`.

No blocking runtime/security defect found in focused independent review. Checkpoint readiness covers one optional art pilot and reproducible export, not default-art rollout, GPU equivalence or broader hardware/competitive acceptance. Failed load retries require page refresh; generated pilot outputs are overwritten on re-export, so preserve manual art revisions separately. User aesthetic approval remains separate. No automatic Phase5A commit/push/tag or further art pass.

## Visual Phase 4 — robber and pirate presentation plan

**Historical completed verification, 2026-10-18; published as `2d93c40caed5c5febfc88f49e1234fb7853d2db1` on2026-10-19.** Exact upstream hash/normal push and22 intended files/all11 new sources verified; graph/artifacts excluded. Visual Phase 3 checkpoint `93ee22574fd843e87e571e086367374851a47b12` was committed/pushed normally. Its saved343 frontend/three focused PostgreSQL/38 browser groups, video and both performance reports were reused rather than rerunning full suites solely for that checkpoint. Phase4 evidence below is historical, not Phase5A candidate acceptance.

Audit/path: shared Seven/discard or played Knight → existing pending robber-or-pirate choice → shared controller's destination/victim command → server lock/candidate/COMMIT/receipts → personalized snapshot/public event feed → GamePage/BoardRenderer → Board3D. Existing public movement events already contain `from_tile`/`tile`; `theft` contains public victim/quantity and resource details only for entitled participants. Animation copies only closed public fields, never private resource/hand/VP data. No protocol addition. Historical pre-Phase4 Robber3D performed an unfenced implicit 420 ms movement; Pirate3D was static. This phase replaces that presentation using established baseline/cue/ref infrastructure.

Implemented: [threatFeedback.ts](../../../web/src/board/threatFeedback.ts) observes above 2D/3D, requiring adjacent committed ticks, one matching fresh public move event and matching old/new figure positions. Hydration, first-fresh reconnect, duplicate/stale/gap/new match/ambiguous multi-figure changes are quiet. Only known public endpoints participate. [threatMotion.ts](../../../web/src/board3d/threatMotion.ts) interpolates a 650 ms lift/travel/arrival only across a shared public edge between two known appropriate land/sea tiles; distant moves use ≤300 ms departure and ≤850 ms destination arrival, without a transit route. Unknown/offboard endpoints snap. The canonical Seafarers robber `-1`→known land can show a correlated 700 ms theft card only; its pawn stays at the exact final anchor, without source geometry/echo/arrival. Missing or ambiguous evidence stays quiet.

[Threats3D.tsx](../../../web/src/board3d/Threats3D.tsx) reuses pooled procedural bodies, original anchors/IDs/yaw and controller/victim targets. All bodies/echoes/cards ignore raycasts. Pirate Y±.004/pitch±.006/roll±.012 uses existing 12 Hz SceneMotion; finite useFrame/invalidate effects expire without per-frame React state or a new ambient timer. A fresh correlated public theft produces the same ivory box-card geometry/material/public metadata for every viewer, including entitled viewers. Card local size is .14×.20×.014, local height .95–1.17 above the confirmed destination anchor. No stolen-resource texture/color/identity. **Robber / pirate → Still**, SVG, reduced motion and disconnect cancel effects and keep baselines current.

### Threat verification and limits

Verified 2026-10-18 on frozen final source: **369/369 frontend tests** (343 checkpoint +26 threat cases), TypeScript and production build pass. Final lazy Board3D 981.25 kB/266.78 gzip; existing chunk-size warning remains. **10 focused Python tests pass**: seven actual-engine validated/conserving fixtures and three PostgreSQL pure-recovery guards, including native offboard robber and Fog. No production Python/protocol/schema/codec/rules/auth/security/gates/maps/assets/dependencies/deployment change. Full Python/scenarios/Docker were not rerun; earlier full-suite and natural-match results remain historical.

Chrome 155.0.8059.80: **eight public threat visual groups** pass, including exact final anchors/yaw, safe distant endpoints, canonical offboard theft-only card, resource-counterfactual identical cues, active card/echo/body raycast checks, rapid events, stale/error/duplicate, cached reconnect, SVG, refresh/new epoch, static/reduced cancellation, combined ship/road/Fog and 1024×768 layout. Before renderer is exact `93ee225` Git blobs, with no checkout/reset. Existing **13 SVG/Fog renderer groups** and **seven building visual groups** also pass; those regression runs preceded the final isolated threat-card height/offboard refinement. Final threat runner and the actual multiplayer acceptance below use the final source/build.

**Seven real three-client WebSocket/PostgreSQL cases /36 groups pass, actual exit 0.** Robber/pirate ×Seven/Knight, no victim, known Fog boundary and Gold Haven's native robber `-1`. Normal production frontend/controller/owning sockets/executor/COMMIT/receipts/F1 are used. Invalid commands preserve all three complete personalized snapshots. Independent known initial hands/dev/VP and exact post-theft deltas are checked; actor/victim receive ore identity, observer2 receives no stolen-resource field or another player's private composition/cards/VP. All three see identical neutral-card geometry/material/metadata. Durable duplicate receipts draw nothing new; refresh/native reconnect and seven guarded backend/PG recoveries preserve exact state without rule or RNG replay. Audit totals: three Seven rolls, six theft draws, seven pure recoveries. 21 expected connection refusals during intentional restarts, no unexpected JS/console errors.

Prepared/funded fixtures and test-subprocess-only RNG, not new natural full matches, live rematch acceptance or public Fog activation. Rematch/no-replay is checked at the new match-epoch observer boundary in unit/Chrome tests; no live internal Fog rematch is claimed. The unchanged rejection banner can cover tile centers: browser acceptance clicks an exposed point inside the same legal hex, verifying the outgoing command, with no force-click or callback bypass. Public Fog admission/emergency defaults remain 0/0; no test capability enters normal startup.

### Threat performance comparison

Primary and one bounded repeat both exit 0 with no browser errors. Exact `93ee225` runtime blobs/current source, same synthetic public scenes/hash, Chrome155.0.8059.80/RTX5050 Laptop/ANGLE D3D11, viewport1440×900, Canvas1186×723/DPR1/shadows/camera. One measured page at a time, no concurrent browser workload/video encoding. Before/after/after/before;12 warm renders,60 GPU-synchronous `gl.render + gl.finish` and30 CPU-submit samples per reading. Medians are the mean of two medians; p95 is the worse reading. CPU submission includes driver/GPU stalls and is not isolated CPU frame time or sustained FPS.

| Scene | Primary GPU median ms | Primary GPU p95 ms | Primary CPU submit median ms | Repeat GPU median ms |
| --- | --- | --- | --- | --- |
| 7 normal | .90→.90 | 1.90→1.40 | 1.25→1.20 | .90→1.05 |
| 7 reduced | .90→.95 | 1.80→1.40 | 1.80→1.25 | 1.25→.95 |
| 7 static | .95→.90 | 2.00→1.40 | 1.25→1.30 | .90→.85 |
| 50 normal | 4.20→4.20 | 6.60→9.60 | 4.05→4.10 | 3.90→3.65 |
| 50 reduced | 4.10→3.85 | 6.20→5.40 | 4.70→4.20 | 3.70→3.85 |
| 50 static | 3.80→4.65 | 5.00→6.90 | 3.95→5.00 | 3.70→3.80 |

Steady counts match exactly before/after in both runs:7 tiles/one ship **258 calls /32,394 triangles /152 geometries /6 textures**;50 tiles/24 ships **1426 /183,430 /151 /17**. Transient endpoints add only the original9-mesh robber or8-mesh pirate echo for≤300 ms; theft adds one pooled card for≤700 ms. No permanent mesh/asset addition. Pirate alone gives12 ambient frames/s before/after finite feedback; all three pirate/Fog/ship subscribers share12–13 rather than multiplying clocks. With other effects Still, enabling pirate deliberately adds12 Hz idle rendering; **all-still/reduced0**, no idle React commits or geometry/texture churn.

Primary50-static +.85 ms did not reproduce at the same magnitude (+.10 ms repeat); repeat7-normal +.15 ms and50-reduced +.15 ms also show variance. Both original reports and all readings are retained, including p95/CPU stalls. No optimization, zero-cost, sustained-FPS or low-end/mobile/battery claim. This is one desktop GPU. Repeat: `%TEMP%/catan-threats-visual-phase4-repeat/paired-performance.json`; both runs include12 matched PNGs. Video is recorded separately from timings.

Preview stays loopback-only: `node web/e2e/threats-visual-demo.cjs` → `http://127.0.0.1:18777/?demo=1&threats=1`. Actual GamePage/Board3D, existing GLBs, synthetic PUBLIC 7/50 scenes; movement/theft/sequence/road/ship/reset/reduced/static controls. No gameplay execution, trusted state, assignment recipe or credentials are served. [Reproduction](../../../web/e2e/README.md#visual-phase-4--robber-and-pirate-preview-and-verification).

Evidence outside Git: `%TEMP%/catan-threats-visual-phase4/{before,after,paired-performance}.json`, before/after PNGs and WebM path recorded in `after.json`; `%TEMP%/catan-threats-phase4-live-final-7/report.json` and seven public screenshots; `%TEMP%/catan-threats-phase4-fog-regression/report.json`, `catan-threats-phase4-buildings-regression/after.json`; `.venv/test-artifacts/threats-web-final.log`. Synthetic seat proofs/private fixture manifests remain outside served/tracked paths. User graph/accounts/matches/volumes were preserved. Phase4 was published only with subsequent explicit authorization as recorded above.

**Final checkpoint review, 2026-10-19:** reused the completed 2026-10-18 suites and both independent performance reports; did not relabel them as new runs. Confirmed reports/media exist, reviewed all new runtime/test/preview files, and found no blocking runtime/security issue. Preview was no longer listening after interruption; restarted the existing loopback helper and passed a fresh Chrome smoke (actual robber/pirate buttons, exact final anchors, neutral card, Still/reduced, no gameplay commands/errors). Evidence: `%TEMP%/catan-threats-visual-phase4/final-review-preview.{json,png}`. No production code change. Rechecked585 affected documentation links and Git whitespace; temporary files remain outside tracked scope. Docker Desktop is not running at this review; completed PostgreSQL acceptance is reused, no new connectivity result or database/volume operation. Test-oracle limitation: the live restart animation monitor observes for15 s while backend readiness permits30 s; unusually slow restart beyond that observation window has not been separately verified. Normal tested restarts, exact restored state, pure recovery and unit reconnect/new-epoch fences pass; this is not a reproduced renderer replay defect.

Intended scope: **22 files** excluding pre-existing user graph. Runtime7 files **+296/−52 lines**: `web/src/board/threatFeedback.ts`, `web/src/board3d/{Board3D.tsx,Pieces3D.tsx,Threats3D.tsx,threatMotion.ts,board3d.css}`, `web/src/components/BoardRenderer.tsx`. Tests/preview9: `tests/{threat_visual_support.py,test_threat_visual_fixture.py}`, `web/e2e/{fog-fixture.tsx,threats-visual-demo.cjs,threats-visual.cjs,threats-live.cjs,threats-compare.cjs}`, `web/tests/{threatVisual.test.mjs,fixtures/publicThreats.ts}`. Documentation6: this plan, Project State, React интерфейс, Design System, Стили и визуальные границы, browser README. Generated media/artifacts remain untracked/ignored; index remains empty. Only the task-started disposable PostgreSQL container is stopped; preview remains independently running. No data/volume deletion.

## Visual Phase 3 — construction feedback plan

**Historical completed verification, 2026-10-18; published as `93ee22574fd843e87e571e086367374851a47b12`.** Exact upstream hash and normal push verified before Phase4; 22 intended files, no tag, user graph excluded. Phase 2 checkpoint `f315519f0d06cf5bf131f9bc2247e82c1c3abc64` is published. Its ship rejection assertion compares both full personal snapshots and uses explicit property existence. Rerun: 323 frontend tests, six ship visual groups and seven real two-client ship/PostgreSQL groups passed.

Affected path: existing authoritative Python executor/COMMIT/public snapshot → React GamePage → BoardRenderer → Board3D → Road3D/Settlement3D/City3D → PieceVisual → existing GLB/procedural fallback. Gameplay/controller/targets and server remain unchanged. Pre-change audit: `usePieceFeedback` ran inside the 3D mount with generic 260 ms scale feedback, without tick/fresh-object recovery fencing or a distinct city-upgrade transition. The implementation below extends this mechanism rather than adding another animation scheduler.

Implemented: existing `pieceFeedback.ts` now observes public `occupied_e`/`occupied_v` plus match key/tick/connection above the renderer toggle. Adjacent additions identify roads/settlements; same-owner1→2 identifies a city upgrade. Hydration, stale/duplicate/coalesced/ambiguous changes and first fresh reconnect frame establish quiet baselines. `PieceVisual` reuses the existing loader/material pool/fallback and finite R3F invalidation: road-axis growth450 ms, settlement emergence550 ms, city emergence700 ms plus a300 ms shrinking ghost settlement. The echo has no vertex/level/target identity and ignores raycasts. Original anchors/rotation/owner colors remain fixed. No per-frame React updates, new continuous interval, particles, model replacement or private terrain inputs. Reduced motion and **Construction effects → Motion/Still** clear feedback, consume baselines and restore final transforms without replay. Ship/Fog controls remain independent. Settled refs skip frame work, async GLB loading never restarts cue timestamps, and echo clones use pooled ghost materials/dispose=null.

The planned public-only preview extension, screenshots/video, matching committed/current A/B, lifecycle/pose tests and owning two-client construction/recovery checks are complete within the limits below. Full Python/scenarios were not required because production backend did not change. Phase3 was committed/pushed only with explicit user authorization; graph, accounts/data and gates were preserved.

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

Evidence outside Git: `%TEMP%/catan-buildings-visual-phase3/{before,after,paired-performance}.json`, before/after PNGs and WebM path in `after.json`; `%TEMP%/catan-buildings-phase3-live-final/report.json` (three cases/12 groups), `catan-buildings-phase3-fog-rendering/report.json`, `catan-buildings-phase3-ships/after.json`. Recording is in a separate context, excluded from timings. No trusted assignments/recipes/private manifest/seat proofs are served or committed. User graph edits, accounts, matches and database volumes remain preserved. This historical Phase3 scope added no tag, Robber/Pirate animation or backend feature; Phase4 is described separately above.

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
