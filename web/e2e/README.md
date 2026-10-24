# Game UI / Game Room UX browser checks

## Visual Phase 5E.2 - opt-in proportions pilot

Exact committed5E.1 `3d82af6` versus an explicit two-family proposal. Production
`terrainDetail` remains `current`; only this wrapper selects `pilot`. No backend,
private map/recipe or new gameplay executor. Ships stay procedural by default.

```powershell
$env:CATAN_PROPORTIONS_OUTPUT = Join-Path $env:TEMP 'catan-proportions-5e2-final-live-toggle'
node web/e2e/proportions-demo.cjs
# Open http://127.0.0.1:18788/ (loopback only).
```

Gallery pairs OLD/NEW actual renders, not mockups. Current/pilot toggles live
inside NEW and preserves camera; Source OLD loads the exact committed bundle.
The one-ring/frame is fixed for comparison. Original FI4 contains tile29/Fields12;
other scenes cover Base/NS4, Fog before/after and procedural/GLB ships.

For fresh captures/inventory/checks, use the existing external Playwright install
and a **fresh** `CATAN_PROPORTIONS_OUTPUT` / `CATAN_E2E_OUTPUT`; old raw reports
are intentionally not overwritten:

```powershell
$env:NODE_PATH = Join-Path (Get-Location) '.venv/test-artifacts/fog3a-tools/node_modules'
node web/e2e/proportions-inventory.cjs
node web/e2e/proportions-capture.cjs
# --baseline records original Base/FI4 only; --ships records both ship variants
# in another fresh output directory. Full PNGs2560x1440, native crops600x600.
node web/e2e/proportions-smoke.cjs
node web/e2e/proportions-gpu.cjs
node web/e2e/proportions-gpu.cjs --passes <paired-performance.json>
```

Inventory reports exact transformed geometry bounds/triangles and projected
bounding rectangles, not segmented visible-pixel percentages. Smoke checks real
clone restore,5E.1 clearance, hidden Fog, SVG, raycasts, legal pointer/controller,
public build/ship/threat events and reconnect/reload. Synthetic display frames
never certify engine legality or replace real multiplayer testing. GPU runs
must be exclusive of other captures/benchmarks; async warm90/query120/wall60,
counterbalanced ABBA/BAAB, normal/reduced/static on Base/NS4/FI4/50. Pass inventory
is separate/untimed. Preserve worse timings, raw samples and source hashes.
Detailed measured inventory, evidence and remaining art decisions are in
`docs/obsidian/plans/board3d.md`,5E.2 section. No art/default promotion is implied.

## Visual Phase 5E.1 - piece readability

Real public-fixture Board3D, paired against published5D.2 `b1c5a2f`.
Both sides retain the same one-ring/frame, camera, snapshots and assets.
No account/server/database or trusted Fog map is exposed. Synthetic display
occupancy is not a legality-certified match. Procedural ships remain default.

```powershell
$env:NODE_PATH = Join-Path (Get-Location) '.venv/test-artifacts/fog3a-tools/node_modules'
$env:CATAN_READABILITY_OUTPUT = Join-Path $env:TEMP 'catan-readability-5e1-final'
node web/e2e/readability-demo.cjs
# Open http://127.0.0.1:18787/ (loopback only); Ctrl+C stops the preview.
```

The gallery serves actual captures if present; `Source` switches committed/current,
and `Readability terrain` selects an existing public tile as a synthetic robber
standing-area study. Original scene preserves Four Islands4 tile29/Fields12.
Orbit/zoom/reset and existing motion preferences work normally. To reproduce
matched2560x1440 captures, use another terminal with the same output variable:

```powershell
node web/e2e/readability-capture.cjs
```

Captures include native-pixel crops, hashes, public-state/camera equality and
four orientations of the exact Fields12 case. Original reproduction and interim
vegetation-only evidence are retained separately in temporary storage.
`readability-smoke.cjs` checks lifecycle/Fog/pointer/static/reduced behavior.
`readability-gpu.cjs` reuses corrected async timer queries and ABBA/BAAB ordering
for Base/Four Islands4/50 ×normal/reduced/static. Run after other browser/GPU
work stops, set a fresh `CATAN_E2E_OUTPUT`, and preserve raw worse results.
No screenshots/video during timing; loading/compile/warm-up are excluded.
After timing, `node web/e2e/readability-gpu.cjs --passes <paired-performance.json>`
records untimed actual main/shadow callbacks and verifies their sum against
native calls/triangles for every measured scene/mode; it does not alter timings.
Exact evidence and limitations: `docs/obsidian/plans/board3d.md`,5E.1 section.

## Visual Phase 5D.2 - decorative ocean and continuous frame

Actual GamePage/Board3D, with shared PUBLIC synthetic snapshots, not concept
images or a live match. The before bundle reads checkpoint `b61215b` with
`git show`; the after bundle reads the working tree. No checkout/reset, backend,
credentials, private Fog recipe, database or production debug API is involved.

```powershell
$env:NODE_PATH = Join-Path (Get-Location) '.venv/test-artifacts/fog3a-tools/node_modules'
# Use the completed final capture folder for the existing49-image gallery:
$env:CATAN_OCEAN_OUTPUT = Join-Path $env:TEMP 'catan-ocean-5d2-final-v4'
node web/e2e/ocean-demo.cjs
```

**http://127.0.0.1:18786/**. Scene/source/ring/frame/close/reset controls are
test-only. Base, official New Shores3/4, Four Islands3/4, public Fog before/after,
and seven/fifty-hex scenes use real components. The outer ship is synthetic
display occupancy on an existing playable sea edge; it is not evidence of a
legal match. Decorative cells never enter the snapshot or fixture graph.
Procedural ships remain default; `model=glb` explicitly selects the existing pilot.

Capture actual official layouts, matched before/after camera views, native
overview, two rings, frame off, wheel close-ups and native-pixel detail crops:

```powershell
# Select a fresh directory: previous evidence is never overwritten.
$env:CATAN_OCEAN_OUTPUT = Join-Path $env:TEMP ('catan-ocean-5d2-' + [guid]::NewGuid().ToString('N'))
node web/e2e/ocean-capture.cjs
# Add the real legal setup/outer-sea-ship view to that capture manifest:
node web/e2e/ocean-outer-capture.cjs
# Narrow hover/snapshot/instance/raycast/Fog-reveal invariants, no GPU benchmark:
node web/e2e/ocean-smoke.cjs
# Serve that same artifact directory after capture, if the preview was stopped:
node web/e2e/ocean-demo.cjs
```

The default artifact directory is `%TEMP%/catan-ocean-5d2/`; use the same
`CATAN_OCEAN_OUTPUT` for capture and gallery. `CATAN_OCEAN_PORT` overrides18786.
Captures include real reset/resize/SVG round-trip and public-state checks.
Normal/close views and native-pixel detail crops are labeled separately.
Historical5C images are preserved and are not claimed as new ocean evidence.
PNG SHA256 values hash the actual file bytes, not JSON-encoded Buffer objects.
If reviewing an old pre-correction manifest, retain its original separately.

Run GPU measurements separately from screenshot/video or other GPU workloads:

```powershell
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP ('catan-ocean-gpu-' + [guid]::NewGuid().ToString('N'))
node web/e2e/ocean-gpu.cjs
# Independent bounded repeat: select another fresh directory first.
node web/e2e/ocean-gpu.cjs
```

`--smoke` on either runner is a short tool check, not complete acceptance.
The GPU runner reuses the corrected5B.1 asynchronous timer/disjoint probe,
ABBA/BAAB,90 paced warm/120 GPU/60 separate wall samples per reading. Base,
New Shores4, Four Islands4 and7/50 hexes each cover normal/reduced/static.
The complete after/frame overview camera is copied identically to both sides;
native camera fits are also retained. This separates changed framing from the
cost of extra geometry. Base's existing decorative boats move farther out to
clear the new ring: native poses and rendered visibility are recorded, while
only the external GPU probe temporarily normalizes both sides to identical
after-boat poses. The original render method and latest native pose are restored
after sampling. Existing clocks and idle observations remain actual; Base's
legacy boat clock can still render10Hz in the effects-Static mode, while reduced
motion stops it. Full chronological timings, pooled median/p95,
shadow-plus-main calls/triangles, instance/material/resource inventory, idle
frames and GPU telemetry are retained, including failures or unfavorable results.
Reports cannot be overwritten. This is a single unlocked-GPU render-span
diagnostic, not sustained FPS, artistic approval or low-end certification.

## Visual Phase 5C - actual board art review

Actual current GamePage/Board3D, not generated concept images. Public-only
synthetic snapshots; no backend, database, credentials or feature-gate bypass.
Five shipped board geometries (Base Standard, official New Shores3/4 and Four
Islands3/4), public Fog before/after and component/owner/ship studies. Occupancy
is synthetic display scaffolding, **not a played or legality-verified match**.

Open the existing gallery and interactive previews:

```powershell
node web/e2e/art-direction-review.cjs
```

**http://127.0.0.1:18785/**. Both review server and its existing fixture upstream
bind loopback. No production source/assets are edited. Original procedural is
the default; GLB is explicit opt-in. The gallery offers current-state photos
and written A/B/C proposals, not rendered variants or user art approval.

Generate the26 real Chrome screenshots (24 full2560x1440/DPR1 plus two native
browser clips), using the already provisioned external Playwright tools:

```powershell
$env:NODE_PATH = Join-Path (Get-Location) '.venv/test-artifacts/fog3a-tools/node_modules'
node web/e2e/art-direction-review.cjs --capture
```

Default output: `%TEMP%/catan-art-direction-5c/`. Override with
`CATAN_ART_REVIEW_OUTPUT` consistently for capture and preview; port override is
`CATAN_ART_REVIEW_PORT`. Existing project `.venv` Python is used to construct
offline non-Fog public board fields; `CATAN_REVIEW_PYTHON` can select an existing
interpreter. No installation/DB migration/startup happens in this tool.

`art-review-boards.py` outputs only an explicit geometry/config/occupancy
allowlist from shipped maps. `art-review-controller.js` supplies synthetic
client frames and chooses real Still/model controls; it never executes rules
or modifies a mesh/camera. Normal is actual auto-fit, Close real wheel zoom,
with expected crop. Fog uses existing public fixtures, no trusted recipe or
future assignment. Screenshots use the production renderer unchanged.

`capture-report.json`: original PNG hashes/dimensions, camera/projection,
public-state hashes, token/piece counts, model responses,12 source GLB hashes
and static triangle/material inventory. Static inventory is **not a GPU
benchmark**. Initial incomplete counter report and all historical GPU reports
remain preserved. Images/video/raw JSON stay excluded from Git; temporary
storage can be cleared, so regenerate if absent. Gallery serves only its
listed capture basenames, not arbitrary files. The test-only files are never
imported by App or included in a production bundle.

Completed2026-10-20:26 capture SHA/dimension checks, zero browser errors,
104 model responses200, matched procedural/GLB state/camera pairs. Separate
gallery smoke verifies all26 image URLs,12 links, six interactive scenes,
default no-GLB-fetch and actual zoom/reset. No new broad GPU/full Python/web
suite/build run;5B.2's383 tests/TS/build/live checks remain dated evidence.
Detailed proposal — [Design System](../../docs/obsidian/Design%20System.md#visual-phase-5c---current-renderer-and-art-direction-proposal).

## Visual Phase 5B.2 - ship topology comparison

Original and corrected assets, same real current Board3D/public snapshot:

```powershell
node web/e2e/ship-topology-demo.cjs
```

- Original5A GLB: **http://127.0.0.1:18781/?demo=1&shipsart=1**
- Corrected GLB: **http://127.0.0.1:18782/?demo=1&shipsart=1**

Select **Ship model -> GLB pilot** on each, or **Procedural** to compare the
unchanged default. Four colors, ports/Fog, Construct/Move/Reset/50 tiles and
wheel/orbit are existing actual components, no backend. Original serves one
fixed public GLB from Git986c99c, never arbitrary repository/private files.
Current and original buffers are preloaded before serving through the same
branch. Restart helper/refresh pages after re-export; per-page loader stays cached.
Override ports with `CATAN_SHIP_ORIGINAL_PORT` /`CATAN_SHIP_CORRECTED_PORT`.

Use the existing external Playwright NODE_PATH as in5B.1, and a fresh
`CATAN_E2E_OUTPUT` directory for every run (reports cannot be overwritten):

```powershell
node web/e2e/ship-topology-visual.cjs
node web/e2e/ship-topology-compare.cjs
# Independent repeat: choose another fresh output directory.
node web/e2e/ship-topology-compare.cjs
# Separate normalized cold-only7/50 comparison, no GPU measurement phase:
node web/e2e/ship-topology-compare.cjs --cold-only
```

The visual runner captures normal/close/opposite azimuths/polar limits, real
legal hover, procedural and24 ships/50 hexes, plus actual production construction
and movement at matched cue ages on disposable clock-controlled pages. Pointer
coalescing differs across runs: raw input camera poses are recorded before
canonicalizing the original control-generated pose for matched capture. Production
CameraRig/animations are unchanged. Static and GPU runs use no fake clock.

GPU comparison reuses5B.1 samplePage, ABBA/BAAB,90 paced warm/120 GPU/60 separate
wall samples per reading; main plus shadow calls/triangles, materials/geometry/
programs, fetch/transfer, raw timings/telemetry and opposing results are preserved.
One measured page at a time; no video/screenshots during measurement. Same
current runtime on both sides; only original/corrected GLB bytes differ. No
performance threshold is weakened to claim a speedup. Unsupported/disjoint
timers and endpoint resource changes remain detectable. Power/clocks/ambient
phases are not locked; this is not sustained FPS or broader hardware certification.

Saved artifacts `%TEMP%/catan-ship-topology-5b2/`:
`visual-animations/comparison.json` +30 matched PNGs, `visual-final/` static set,
`gpu-primary/paired-performance.json`, `gpu-repeat/paired-performance.json`,
`cold-normalized/cold-load.json`, `art-regression/` report/video,
`live/report.json`. The first two steady runs' cold fields retain a discovered
RAM-versus-disk serving asymmetry; use the separately normalized cold report for
loading comparisons. All steady samples were measured after readiness/warming.
The failed candidate camera comparison is retained separately, not counted as
passed. Final ship ghosts keep legacy DoubleSide, not the discarded candidate's
inherited FrontSide. Shape/inner-wall/shadow differences and mixed timings:
[Board3D](../../docs/obsidian/plans/board3d.md#visual-phase-5b2---ship-topology-and-selective-culling).

## Visual Phase 5B.1 - GPU investigation

Historical5B.1 runner validates the original asset SHA. With the corrected5B.2
working GLB, use the original/corrected comparison above; do not replace historical
hashes or reset the working tree merely to run the older experiment.

The historical `ship-art-compare.cjs` reports preserve5A evidence, but its
`gpuMedianMs` is synchronized `render + finish` wall time, and the old helper
discarded frame timing arrays. Do not reinterpret it as isolated GPU timing.

Use the corrected benchmark with the existing external Playwright installation
and installed Chrome. In this workspace its module root is
`.venv/test-artifacts/fog3a-tools/node_modules` (ignored; no dependency upgrade):

```powershell
$env:NODE_PATH = (Resolve-Path '.venv/test-artifacts/fog3a-tools/node_modules').Path
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP ('catan-ship-gpu-' + [guid]::NewGuid().ToString('N'))
node web/e2e/ship-art-gpu.cjs
```

Run again with a fresh output directory for an independent repeat. `--smoke`
checks the probe on seven-static with short sample counts, not the full matrix.
Existing reports cannot be overwritten. The runner pins published5A `web/src`,
checks the original GLB SHA, and switches current procedural/GLB in the same page.
Fixtures/public asset must match that checkpoint; source checkout is never reset.
It uses true asynchronous WebGL timer queries with validity checks, ABBA/BAAB,
equal90 warm/120 GPU/60 separate wall samples per reading, six cases and four
readings/model/case. Main-plus-shadow counts, resource/program stability, clock/
temperature/power snapshots, chronological samples, block results and cold fetch
timing are saved to `gpu-investigation.json`. Unsupported timers fail explicitly;
invalid/failing results remain recorded. Screenshots/video are outside timing;
no video is recorded by this runner. Automatic R3F drawing is temporarily paused
inside the external probe, ambient listeners continue, and the setting is restored.
No production instrumentation or server command is used.

This is render-span microbenchmarking, not sustained FPS or exclusive GPU access.
Actual paced durations are recorded; power/clocks are not locked and other user
applications are not stopped. Initial GLB detection includes automation; a draw
can precede detection, so remaining compileAsync wait is not first-use shader
compilation cost. Browser/driver shader caches are not forcibly cleared.

Completed primary/repeat: `%TEMP%/catan-ship-gpu-5b1-primary/` and
`catan-ship-gpu-5b1-repeat/`. Each has13 PNGs: seven/fifty normal/reduced/static
for both bodies and `7-glb-close.png`; raw reports retain opposing tails.
For interactive inspection, `node web/e2e/ship-art-demo.cjs` opens the existing
loopback preview at **http://127.0.0.1:18780/?demo=1&shipsart=1**. If already
running, reuse it. Select **Ship model**, **50 tiles**, and wheel zoom; default
remains Procedural. This serves only synthetic PUBLIC snapshots without backend.
Full results, historical corrections, source audit and limits:
[Board3D investigation](../../docs/obsidian/plans/board3d.md#visual-phase-5b1---ship-gpu-investigation).

## Visual Phase 5A - Blender ship art comparison

From root with existing dependencies: `node web/e2e/ship-art-demo.cjs`.
Open **http://127.0.0.1:18780/?demo=1&shipsart=1**; override with
`CATAN_SHIP_ART_PREVIEW_PORT`. Actual Board3D/public synthetic7/50 scenes,
four existing palette colors, Fog/settlement/city/port, **Ship model**
Procedural /GLB pilot, existing Construct/Move/Reset/Multiple ships and
effects/reduced controls. Reset before replaying consumed targets. No rules,
backend, trusted assignments, credentials or public Fog activation.

Use existing external Playwright `NODE_PATH` and installed Chrome/ffmpeg:

```powershell
node web/e2e/ship-art-visual.cjs
# Run after all other browser/GPU workloads finish:
node web/e2e/ship-art-compare.cjs
```

Use a fresh `CATAN_E2E_OUTPUT` per run. The visual runner writes acceptance.json,
before/after/near/far/fallback PNGs and a WebM path in that report. The comparator
reads exact `2d93c40caed5c5febfc88f49e1234fb7853d2db1` runtime Git blobs without
checkout/reset, with identical public fixture/camera/DPR/shadows/GPU and
sequential B/A/A/B samples. Normal/reduced/static7/50, GPU render+finish,
diagnostic CPU submission, calls/triangles/resources/transfer and shared idle
are checked. Preserve both original and any bounded repeat report; timing
variance is not a performance improvement. Source art is not substituted into
the committed baseline. No sustained FPS/mobile certification.

For real ship/Fog smoke, build `web/dist`, use the existing `ships-live.cjs`
requirements (fresh private output, localhost disposable `DATABASE_URL` ending
`_test`, unused loopback origin). Set `CATAN_E2E_SHIP_MODEL=glb` before running
`node web/e2e/ships-live.cjs`; default remains the original procedural checks.
The opt-in selects the actual GLB via the normal local control, requires loaded
GLB for occupied ships, and rechecks quiet model selection after recovered Gold
completion. A zero-ship opening has no model to load. Original authoritative
commands/ownership/receipts/privacy/recovery assertions remain. This is a
guarded prepared two-client test, not a natural match or production Fog bypass.
Keep private manifests/proofs and generated files outside served/tracked paths.

Blender installation/source/export/reload/reproducibility:
[tools/blender](../../tools/blender/README.md). Final results/limits:
[Board3D plan](../../docs/obsidian/plans/board3d.md#visual-phase-5a---blender-pipeline-and-ship-pilot).

## Visual Phase 4 — robber and pirate preview and verification

From the repository root, with existing `web/node_modules`:

```powershell
node web/e2e/threats-visual-demo.cjs
```

Open **http://127.0.0.1:18777/?demo=1&threats=1**. Actual GamePage/Board3D,
existing terrain/piece GLBs, public synthetic land/sea/Fog and7/50-tile scenes.
Controls: Move robber, Move pirate, Generic theft, Movement sequence, Construct
road/ship, Reset,50 tiles, Reduced motion, existing independent effects selects.
Generic theft includes a new confirmed public movement event, not an uncorrelated
private-hand signal. This display fixture neither runs rules nor sends gameplay
commands. It exposes no trusted recipe, assignments, server seed or credentials.
`CATAN_THREAT_PREVIEW_PORT` changes the loopback port; Ctrl+C stops the preview.

Use the existing external Playwright via `NODE_PATH`, installed Chrome and its
matching external ffmpeg cache:

```powershell
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-threats-visual-phase4'
node web/e2e/threats-visual.cjs --baseline
node web/e2e/threats-visual.cjs
# Run after all other browser workloads finish:
node web/e2e/threats-compare.cjs
```

Baseline is exact published Phase3 `93ee22574fd843e87e571e086367374851a47b12`,
read through existing sourceRef Git blobs, never checkout/reset. Public fixtures
are shared between versions. Before/after PNGs, `before.json`, `after.json` with
the actual WebM path, and `paired-performance.json` stay outside Git. A/B uses
one Chrome/page at a time, matched scene/camera/DPR/shadows, B/A/A/B ordering,
7/50 normal/reduced/static scenes, GPU `render+finish`, diagnostic CPU submission,
steady draw/resource equality and shared-clock idle assertions. CPU submission
includes driver/GPU stalls; these are not sustained FPS or mobile benchmarks.

Build `web/dist` before real acceptance. Set `DATABASE_URL` to a fresh isolated
localhost PostgreSQL `*_test` database, external Playwright `NODE_PATH`, unused
loopback `CATAN_E2E_ORIGIN` (default `http://127.0.0.1:18778`) and a fresh private
`CATAN_E2E_OUTPUT`, then run `node web/e2e/threats-live.cjs`.
`tests.threat_visual_support` prepares seven three-player fixtures: robber/pirate
via Seven/Knight, no-victim, known Fog boundary and native offboard Gold Haven
robber. It controls RNG only inside the guarded test subprocess and validates
copied commands/conservation before acceptance. No production activation seam.
The actual production executor/ownership/COMMIT/F1/receipts are used. Three owning
profiles verify exact known initial private state, actor/victim-only resource
details, identical neutral cards, rejection equality, durable duplicate receipts,
refresh/native reconnect and guarded pure PostgreSQL recovery without rule/RNG
reexecution. No live internal Fog rematch or natural full match is claimed.

The rejection banner may cover a projected tile center; acceptance chooses an
uncovered point inside the same public legal hex and asserts the actual outgoing
command. No force-click or gameplay bypass. The private fixture manifest has
synthetic seat proofs; keep it and server diagnostics outside served/tracked
paths. The runner stops its own backend/Chrome and preserves database records
and volumes. Production Fog admission/emergency defaults stay0/0. Focused tests:
`tests/test_threat_visual_fixture.py`; current results/limits:
[Board3D plan](../../docs/obsidian/plans/board3d.md#visual-phase-4--robber-and-pirate-presentation-plan).

## Visual Phase 3 — construction preview and verification

From the repository root, with existing `web/node_modules`:

```powershell
node web/e2e/buildings-visual-demo.cjs
```

Open **http://127.0.0.1:18775/?demo=1&buildings=1**. Actual GamePage/Board3D,
existing GLBs, synthetic PUBLIC 7/50-tile scenes, roads/settlements/cities/ships
and Fog. Controls: Construct road/settlement, Upgrade city, Build sequence,
Build together, Construct ship, Reset, 50 tiles, Reduced motion. Reset before
replaying consumed targets. Sequence delivers three rapid public frames;
together demonstrates simultaneous additions. This preview does not calculate
legality, send real commands or expose a trusted recipe, secret assignment or
credentials. Real legality is checked separately against the owning backend.
`CATAN_BUILDING_PREVIEW_PORT` changes the loopback-only port; Ctrl+C stops it.

Use the existing external Playwright via `NODE_PATH` and installed Chrome:

```powershell
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-buildings-visual-phase3'
node web/e2e/buildings-visual.cjs --baseline
node web/e2e/buildings-visual.cjs
node web/e2e/buildings-compare.cjs
```

Baseline always reads exact `f315519f0d06cf5bf131f9bc2247e82c1c3abc64` UI blobs
through the existing esbuild sourceRef plugin, never checkout/reset or today's
renderer labelled old. Baseline/after PNGs and `before.json`/`after.json` remain
outside Git; after records the short WebM path (matching external Playwright
ffmpeg cache required). The paired runner uses one Chrome/page at a time and
matching fixture/camera/DPR/shadows/GPU with before/after/after/before sampling;
normal/reduced/all-still 7/50 scenes, steady draw/resource equality and idle
are checked. CPU submission includes driver stalls; no sustained FPS claim.
Run benchmarks after other browser workloads finish.

`buildings-live.cjs` uses the normal production frontend/executor/receipts/F1
and a guarded test-only `tests.building_visual_support` launcher. Require built
`web/dist`, fresh private output, a localhost disposable `DATABASE_URL` ending
`_test`, and unused `CATAN_E2E_ORIGIN` such as `http://127.0.0.1:18776` (distinct
from the standalone preview). Both-client rejection equality, explicit owner-0
occupancy, accepted effects, duplicates, refresh/native reconnect and PostgreSQL
restart are checked. Prepared/funded rooms include a real engine-built ship;
the road discovers Fog/Gold. The private manifest contains synthetic seat proofs
and stays outside served/tracked paths. Recovery restores committed state;
fixture preparation and copied-command validation never run again on recovery.
No public Fog activation, production test capability, destructive DB operation,
new rule or live internal Fog rematch is introduced. The runner stops its own
backend/Chrome; retain volumes/accounts/matches. Current results and limitations:
[construction plan](../../docs/obsidian/plans/board3d.md#visual-phase-3--construction-feedback-plan).

## Visual Phase 2 — ships preview and verification

From the repository root (existing `web/node_modules` installed):

```powershell
node web/e2e/ships-visual-demo.cjs
```

Open **http://127.0.0.1:18773/?demo=1&ships=1**. Real GamePage/Board3D with
synthetic PUBLIC snapshots, stationary/fleet/Sea/Fog-boundary ships, labelled
Construct/Move/Reset/50 tiles controls. Reset before replaying an operation;
its consumed target is a no-op until Reset. Reduced motion reloads a test-only
forced preference; normal production uses the OS preference. Ordinary Ship
effects → Still is available too. This is a visual simulator, not an engine,
legal evaluator, backend endpoint or live Fog activation. No database,
account, credentials, trusted assignment or server flag is needed. The loopback
static server serves only its temporary bundle and public models/assets.
Use `CATAN_SHIP_PREVIEW_PORT` for a different port; Ctrl+C stops it.

With the existing external Playwright `NODE_PATH`:

```powershell
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-ships-visual-phase2'
node web/e2e/ships-visual.cjs
node web/e2e/ships-compare.cjs
```

The first runner checks actual poses/raycasts/construction/movement/freshness,
static/reduced/fleet/layout behavior, screenshots and a separate video context.
`after.json` records completion/errors and the generated WebM path. Video needs
the matching ffmpeg cache from external Playwright (`playwright install ffmpeg`);
no project dependency is added. `--measure-only` writes a separate
`after-performance.json`. Original pre-edit `before.json`/images are retained;
`--baseline` refuses runtime changes or a HEAD other than `608f14e`.

The second runner performs controlled same-Chrome before/after/after/before
measurements using frontend blobs from that exact committed checkpoint through
an esbuild onLoad plugin. It never checks out, resets, stages or changes source
files. Only one page renders at a time with identical public fixtures, camera,
assets/DPR/shadows and viewport. `paired-performance.json` retains all samples;
12 warm renders, 60 GPU-synchronous and 30 CPU-submission samples per reading.
CPU submission includes driver stalls; this is not sustained FPS/isolated CPU
frame time. Run performance without other browser acceptance workloads.

`ships-live.cjs` separately runs two real owning clients against production
React/executor/COMMIT/receipts/F1 and isolated localhost PostgreSQL. It uses the
existing guarded `tests.fog_live_support --ship-motion` launcher. The extra
prepared move is validated on a detached engine copy; restoration never moves
it. The private manifest binds exact room/match IDs and synthetic credentials,
stays outside served/tracked paths and never contains trusted Fog assignments.
Require a fresh localhost `DATABASE_URL` ending `_test`, production `web/dist`,
an unused loopback `CATAN_E2E_ORIGIN` (e.g. `http://127.0.0.1:18774`) and a fresh
output directory; do not share this DB concurrently with mutating pytest cases.
The normal production Fog gate remains disabled. Existing `fog-live.cjs` default
fixtures/acceptance stay available. Actual results/scope/limits are in
[Project State](../../docs/obsidian/Project%20State.md) and the
[ship plan](../../docs/obsidian/plans/board3d.md#ship-visual-verification-and-performance).

## Fog Visual Phase 1 — local public-only preview

From the repository root, with the existing `web/node_modules` installed:

```powershell
node web/e2e/fog-visual-demo.cjs
```

Open **http://127.0.0.1:18772/?demo=1**. This standalone loopback-only static
server builds the existing public fixture entry into a unique OS temporary
directory. It uses real GamePage/BoardRenderer/Board3D, normal terrain/building
GLBs and a real ship at a Sea/Fog boundary. **Reveal one/two** supplies a new
synthetic public frame; Reset/50 tiles and the ordinary Fog effects/2D/3D/camera
controls are available. It is a visual simulator, not a multiplayer game or a
legality generator. No PostgreSQL, backend, account, live WebSocket or Fog
admission switch is needed. Only the bundle and `web/public` assets/models are
served; no trusted map recipe, assignment, private manifest or project files.
It is never imported by the production App/build. Stop with Ctrl+C; to change
the port, set `CATAN_FOG_PREVIEW_PORT` before launching.

Automated Chrome checks/measurements need the existing external Playwright
installation through `NODE_PATH` (no new project dependency):

```powershell
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-fog-visual-phase1'
node web/e2e/fog-visual.cjs
```

`after.json` records completion, errors, diagnostics and screenshots. The
original `before.json`/`before-*.png` were captured before runtime changes on
the `ee56e23` renderer with this same public scene and viewport. `--baseline`
is reserved for that unchanged pre-visual renderer and refuses later/modified
source; it must never be used to label the new rendering as old. After 12 warm-up
renders, 60 GPU-synchronous samples measure render latency, not sustained FPS. Current
before/after values and hardware/limits are in the [Fog plan](../../docs/obsidian/plans/seafarers-fog.md#fog-visual-phase-1--implementation-plan-2026-10-18).

Retain `fog-rendering.cjs` for full shared SVG/3D/Gold/ship interaction checks.
`fog-live.cjs` separately exercises two owning TCP clients and isolated
PostgreSQL discovery/reconnect/backend restart/raw public projection. Its
synthetic credentials/private manifest must remain outside served/tracked
files; the standalone public preview above needs none. These scoped live
fixtures do not enable normal public Fog. All screenshots/diagnostics belong
in ignored temporary output, not the production asset tree.

## Official The Four Islands — S3B, natural full matches

The existing `node web/e2e/natural-full-matches.cjs` runner also accepts both
Four Islands traces generated by `tests/test_official_four_islands_natural.py`.
Set `CATAN_FULL_MATCH_OUTPUT` while running that pytest file with an isolated
`CATAN_TEST_DATABASE_URL`; the resulting `seafarers_official_four_islands_3.json`
and `_4.json` contain synthetic legal command transcripts, not private hands or
credentials. `CATAN_NATURAL_TRACE` can select one file or a JSON array combining
both. Use the existing external Playwright `NODE_PATH`, a fresh isolated
localhost `DATABASE_URL` ending in `_test`, production `web/dist`, and the normal
loopback test launcher (default `http://127.0.0.1:18768`). No Test Tools or grants
are enabled; controlled map/deck/dice/theft RNG is private to the test process.

Additional Four Islands assertions check lobby guidance/locked 13 VP, personal
home exclusion and exactly +2 public island VP on each new settlement award,
HUD rendering and the final committed award ledger. The shared checks cover
setup, private/public consistency, early/late SVG and Board3D, real victory,
all-client refresh/Continue, backend restart and host rematch. Roll uses the
actual UI; most replay commands use the owning WebSocket, not mouse clicks.
Outputs stay outside Git via `CATAN_E2E_OUTPUT`; actual verification/limits are
recorded in [Project State](../../docs/obsidian/Project%20State.md).

## Official Heading for New Shores — S3A

`node web/e2e/official-new-shores.cjs` uses external Playwright (`NODE_PATH`) and installed Chrome against an **isolated localhost** Docker/Nginx/backend/PostgreSQL stack. Override `CATAN_E2E_ORIGIN` to that stack; the default is `http://127.0.0.1:18094`. Test Tools must be explicitly enabled on this disposable development backend; never enable them on the user's production stack for this test.

It creates three and four real browser profiles for the separate official 2021 layouts. Checks cover exact-count Start rejection, canonical map selection, fixed target/discard settings, natural snake setup with ships, paid island crossing/+2 VP and city non-duplication, personalized snapshots, terrain GLBs/figures/ports/numbers, SVG parity, orbit/zoom/reset, desktop resize and guest refresh. Expansion resources/dice use the existing explicit Test Room tools: this is a focused funded acceptance, not a complete natural competitive game.

Reports/screenshots default to the OS temporary directory `catan-official-new-shores`; `CATAN_E2E_OUTPUT` may select another ignored external path. The report records public geometry/checks rather than credentials or private hands. Public Fog remains disabled and is not tested by bypassing its gates. No volumes, accounts, historical matches or snapshots are deleted. Actual executed results and limitations — [Project State](../../docs/obsidian/Project%20State.md).

## Explicit lobby closure — Room Lifecycle Phase 1

`node web/e2e/lobby-lifecycle.cjs` uses external Playwright (`NODE_PATH`) and
installed Chrome against a running **isolated localhost** Docker/Nginx/backend/PG
stack. Default `CATAN_E2E_ORIGIN` is `http://127.0.0.1:18094`, using the SEC-04
test overlay in [Deployment](../../docs/obsidian/Deployment.md); do not run it against a user's normal database.
It creates disposable guest rooms, one Base match and a synthetic account. No
volumes/data are deleted. Reports/screenshots default to OS temp
`catan-lobby-lifecycle`; `CATAN_E2E_OUTPUT` can select an ignored external path.

Checks: participant denial, native confirmation cancel/accept, guest disconnect
and Continue, terminal notice for both clients, closed-room Join after refresh,
fresh Base start/active closure rejection, account Active Games exclusion,
retained login and new-room creation. Registration uses ordinary Enter activation
of Create account; mouse mode-switch behavior is not certified by this runner.
No game mocks/fixtures or Fog activation.
Run separately from the opt-in Docker pytest acceptance: those tests restart
their disposable backend to check limiter recovery and can interrupt browsers.

## Fog presentation fixtures — S2B-2B.3A

`node web/e2e/fog-rendering.cjs` requires external Playwright (`NODE_PATH`) and
installed Chrome. It builds `fog-fixture.tsx` using the existing web esbuild,
starts a temporary loopback static server on an available port, serves existing
production terrain/building GLBs, and closes browser/server on completion.
Output defaults to OS temp `catan-fog3a-browser`; `CATAN_E2E_OUTPUT` overrides it.
Use an ignored/external output directory. No runtime dependency is added.

This runner is **synthetic PUBLIC presentation acceptance**, with a recorded
fixture transport and real WSClient/GamePage/SVG/R3F/GLBs. It has no backend,
WebSocket/debug endpoint, trusted assignments, recipe, pool, seed or hidden
ledger. Neither test entry nor fixtures are imported by production App/build.
It does **not** prove live Fog multiplayer or bypass any production gate:
public Fog remains DISABLED, pending S2B-2B.3B integration/security acceptance.

The 13 groups cover uniform hidden Three subtrees/materials/shadows and no
terrain requests/tokens/coasts, committed finite reveal/idle/stale/error,
refresh/reconnect/toggle/reduced motion, partial known terrain GLBs and
ports/pieces, original-ID road/ghost/reject/Cancel, setup/free Ship in both
renderers, 3D move-source/Cancel/destination, personal Gold ACK/retry/public log
privacy, 50-tile perspective resize at 1440×900/1024×768 and legacy non-Fog.
Reports and seven screenshots contain only the public fixtures. Mobile/low-end
performance, live ownership/privacy/public activation are not certified here.

## Existing real multiplayer runners

The runner uses installed Chrome through Playwright and real production web/backend
Docker images. Playwright is a test runner only: install it outside the repository
or provide it through `NODE_PATH`. It is not a frontend runtime dependency.

```powershell
docker compose build
docker compose -p catan-ui-e2e -f web/e2e/compose.yaml up -d --wait
# Example if Playwright is already installed in a separate tool directory:
$env:NODE_PATH = '<tool directory>/node_modules'
node web/e2e/game-actions.cjs
docker compose -p catan-ui-e2e -f web/e2e/compose.yaml down
```

The isolated stack binds only `127.0.0.1:18080`; it does not restart production
containers or modify their rooms. Output defaults to the OS temporary directory
`catan-game-ux-2-2`. Override with `CATAN_E2E_OUTPUT`. Set `CATAN_E2E_CASE`
to a mode such as `direct`, `dice`, `gold`, `roomux` or `roomuxhidden` for an
individual regression check; omit it to run all 19 cases.

`fixture_server.py` prepares funded hands, old cards, port ownership and near-win
scores **only in the test container**, for the first match of `fixture-*` rooms.
Setup placements use the existing engine. Rematch is completely unmodified.
The test backend injects a deterministic Random dice function for reliable progression.
Balanced room cases use the real secure production bag algorithm. The 17 previous
cases explicitly choose Host/Hidden/Off so their original gameplay/privacy
assertions do not depend on the new Random starter/Visible bank defaults.
No production fixture initializer or snapshot interception is added. UX 2.3 separately adds explicitly gated production Test Room commands, off by default.

Every UI action travels through nginx, the real WebSocket endpoint, ownership,
command sequences, the normal executor and player-specific serialization. The
initializer also compares the complete GameState and public dice metadata before/after
every rejected command. Native-WebSocket fault injection deliberately corrupts selected commands
to exercise error recovery without bypassing the client's sequence bookkeeping.
Read-only DevTools observation projects actual Three objects for real mouse clicks.

Coverage includes bank ratios 4/3/2, rejected bank trade, broadcast offers (old targeted server path is retained),
accept/reject/cancel/end-turn expiration, purchase and aging, all five dev card
types, before-roll play, new-card and one-card limits, two free-road placements,
Year of Plenty with insufficient hidden bank quantity and corrected retry,
Monopoly transfers, opponent privacy, passive VP, winning VP purchase, final-score
reveal, post-game rejection, ordinary and disconnected-host rematch, lost-rematch
connection/retry, token/pid/
sequence reset, explicit exit/rejoin, unprepared setup/roll, 2D/3D parity and layout.

Game UX 2.1 adapts all existing cases to the direct dock/private card hand and
resource-hand Trade Tray. Additional cases cover paid Road/Settlement/City, local
Give/Want add/remove without balance mutations, cost preview, exact/repeated
server 4+5 faces, finite dice animation/idle/reduced motion/refresh, public-only
bank availability, and Gold Haven lobby selection/Ship/build/move/pirate. Actual
scene projections check port endpoint IDs, geometry framing and HUD occlusion at
1920×1080, 1440×900 and 1280×720. Screenshots and measurements go to the output
directory; no production snapshot interception or gameplay results are fabricated.

Game / Room UX 2.2 adds two-client `roomux` (Random starter/Visible bank) and
`roomuxhidden` (Host/Hidden bank), both with Balanced dice, 60s timer and 12 VP.
They verify host/read-only settings, occupied colors, actual white/orange Three
materials, initial starter, four accepted rolls and exact shared pairs/sums,
decreasing HUD countdown, lobby/game plain-text chat and a separate log tab,
visible/collapsible bank policy, retained token/color/deadline/chat on refresh and rematch
with retained settings/colors, reset dice/timer/match/sequence and first seq=1.
Rematch is an existing server-permitted request, not a fixture-created win.
Automatic timer expiry/grace/mandatory branches are covered by controlled-clock
Python tests; this runner does not claim a long real-time expiry run.

Prepared states are fixtures, not a claimed naturally played full match. Hidden
bank counts and all deck contents/count/order remain absent; Visible intentionally
publishes exact bank counts. UX 2.3 now has a bounded recipient-filtered committed gameplay feed. Screenshots and
state observation describe actual server execution; full natural games,
mobile/low-end/load and desktop-client feature parity are not certified here.

## Game UX 2.3 feedback checks

`playtest-feedback.cjs` adds eight real Chrome/WS cases. Use an explicit external
output directory to keep screenshots/reports outside the working tree:

```powershell
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-game-ux-2-3/after'
$env:CATAN_ENABLE_TEST_TOOLS = '0'
docker compose -p catan-ui-e2e -f web/e2e/compose.yaml up -d --wait --force-recreate
$env:CATAN_TEST_MODE_CHECK = 'off'
node web/e2e/playtest-feedback.cjs
$env:CATAN_ENABLE_TEST_TOOLS = '1'
docker compose -p catan-ui-e2e -f web/e2e/compose.yaml up -d --wait --force-recreate
$env:CATAN_TEST_MODE_CHECK = 'on'
node web/e2e/playtest-feedback.cjs
# Restore OFF for ordinary-room regression checks.
$env:CATAN_ENABLE_TEST_TOOLS = '0'
docker compose -p catan-ui-e2e -f web/e2e/compose.yaml up -d --wait --force-recreate
node web/e2e/game-actions.cjs
```

ON does not enable cheats in normal rooms. The host explicitly enables a Test
Room in lobby, then named actions still require active host ownership and the
normal command sequence. Cases check OFF/normal-room/participant denial,
resource give/remove, specific dev draw, one-shot dice, near-win/final VP,
invalid-source atomic retry, production flights, three-client theft privacy,
card discard with custom threshold and rejected retry, threshold equality,
and a shifted 50-hex custom JSON visual fixture. The fixture is local test data,
not a new preset or generator. Snapshots/feed/real animations are observed;
no resources are fabricated by client animation or inferred theft deltas.

Existing 19 cases are updated for direct Knight/Road Building, broadcast-only
tray, visible Bank and longer finite dice. Base/Gold/50 framing is measured at
1920/1440/1280; finite motion returns to 0 idle frames. 2D unmount checks Three
resource cleanup. Reports may contain test command payloads; committed evidence
is sanitized in docs/design/references/game-ux-2-3/verification.json, without
reconnect tokens, hidden decks or raw personal snapshots. No full natural match,
mobile or low-end/load certification is implied.

## Seafarers S2A maps / real multiplayer

`seafarers-s2a.cjs` runs the ordinary two-client lobby/setup flow on Gold Haven
and Pirate Lanes against the actual FastAPI/WS/PostgreSQL application and built
production frontend. It explicitly uses host Test Tools for deterministic dice,
matured Knight and expansion funding. It does not manufacture map/state snapshots
or claim a naturally played full match. No production database is needed.

Use an isolated disposable PostgreSQL database whose name ends in `_test`, with
`DATABASE_URL` already configured for that database. Apply the current migrations
only to that test database, build the frontend, then start the local test server:

```powershell
# In web/: npm run build; at repository root with the test DATABASE_URL:
.venv/Scripts/python.exe -B -m alembic upgrade head
$env:CATAN_PERSISTENCE_MODE = 'durable'
$env:CATAN_AUTH_MODE = 'development'
$env:CATAN_AUTH_ORIGINS = 'http://127.0.0.1:18766'
$env:CATAN_ENABLE_TEST_TOOLS = '1'
.venv/Scripts/python.exe -B -m web.e2e.seafarers_s2a_server
```

The test launcher refuses a non-test database, mounts `web/dist`, listens on
loopback only and selects psycopg's supported event loop on Windows. It adds no
gameplay endpoints or fixtures. In another terminal, use an available external
Playwright installation and Chrome, keeping output outside the repository:

```powershell
# If Playwright is installed externally, set NODE_PATH to its node_modules.
$env:CATAN_E2E_ORIGIN = 'http://127.0.0.1:18766'
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-s2a-hardening/browser'
node web/e2e/seafarers-s2a.cjs
```

Checks include setup ships/Gold, paid island crossing/settlement/city/road, an
invalid coordinate rejection, real pirate and Seven/discard/robber actions,
personalized privacy, 37 terrain GLBs/number tokens/ports/ownership IDs, SVG/3D,
1920/1440/1280 framing, orbit/zoom/reset and durable guest refresh. Camera checks
wait for the actual React reset effect. Summary/screenshots contain geometry and
counts, without reconnect proofs or dumped private hands. Stop only the local
test server/container you started after verification; leave other services alone.

## Natural full matches — Base and official New Shores

`tests/test_natural_full_matches.py` runs actual TCP WebSocket clients against a
separate FastAPI process and durable PostgreSQL. Its cooperative test players
use their own personalized wire snapshots. Setup, production, trades, build
costs, card maturity, mandatory choices and victory follow normal server rules.
No Test Tools, resource grants, VP edits or live GameState edits are used.

The private test launcher controls map/deck/dice/theft RNG for reproducibility.
Dice use the candidate's persisted roll counter, including after restart; this
is a test-process substitution, never a client command or production override.
These runs establish complete legal play paths, not competitive balance or
coverage of every possible dice/deck sequence. The legacy scenario harness and
its known failures remain separate.

Use an existing isolated localhost PostgreSQL database ending in `_test`.
The launchers reject other database hosts/names and require Test Tools off.
Keep credentials in the process environment and transcripts/screenshots outside
the tracked tree. Never point these checks at the normal development database.

```powershell
# At repository root, CATAN_TEST_DATABASE_URL must already name the test DB.
$env:CATAN_FULL_MATCH_OUTPUT = Join-Path $env:TEMP 'catan-natural-traces'
.venv/Scripts/python.exe -B -X utf8 -m pytest -q tests/test_natural_full_matches.py
```

This generates synthetic command transcripts for Base and official three-player
New Shores. The four-player case is a setup/12-roll smoke, not a complete match.
Transcripts contain test participants' commands (including their discard/Gold
choices), public-state checksums and result summaries. They contain no reconnect
proofs, account credentials, trusted snapshot or private-hand dumps, and are not
logs of real users' games.

For real Chrome replay, build the normal frontend with `npm run build` in
`web/`, use an external Playwright installation via `NODE_PATH` when necessary,
and set `DATABASE_URL` to a separate isolated browser test database:

```powershell
$env:CATAN_NATURAL_TRACE = Join-Path $env:CATAN_FULL_MATCH_OUTPUT 'base_standard.json'
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-natural-base-browser'
node web/e2e/natural-full-matches.cjs
$env:CATAN_NATURAL_TRACE = Join-Path $env:CATAN_FULL_MATCH_OUTPUT 'seafarers_official_new_shores_3.json'
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-natural-new-shores-browser'
node web/e2e/natural-full-matches.cjs
```

The runner starts/stops only its own loopback backend on port 18768, mounts the
existing production build and replays normal accepted commands over each
browser's real owning WebSocket. Representative controls use React UI; most
commands use the real socket directly to keep full-match runs practical.
It observes actual personalized frames and Three scenes, checks SVG/Board3D,
refresh/Continue, results and finished-match recovery. This is not an all-click
human playthrough. No fixture endpoint or synthetic match_state is installed;
public Fog remains disabled. Latest executed results and limitations are in
`docs/obsidian/Project State.md`.

## Internal live Fog — S2B-2B.3B

`fog-live.cjs` uses the existing production build and real HTTP/WebSocket/
PostgreSQL transport, with two independent Chrome profiles for each prepared
fixture. It clicks a last-setup SVG Road and a paid Board3D Ship, resolves
personal Gold, checks public/private state and both renderers, refreshes during
and after rewards, and restarts the actual backend while a choice is pending.
Fixtures are explicitly funded/prepared; this is not a natural full Fog match.

Build `web/dist`, provide an existing isolated loopback PostgreSQL `DATABASE_URL`
whose database name ends in `_test`, and use the external Playwright/Chrome
installation as for the natural runner. No new frontend dependency is needed.

```powershell
# DATABASE_URL must name a disposable browser test database, never user data.
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-fog-live-browser'
node web/e2e/fog-live.cjs
```

The runner owns a loopback backend on port 18769 and starts it through
`python -m tests.fog_live_support`. The launcher refuses non-test/non-loopback
databases and enabled Test Tools. It binds immutable room/match UUID
capabilities only inside that test application's private state. On restart it
uses normal recovery, verifies the saved fixture IDs and explicitly rebinds
them; snapshot decoding itself does not activate Fog. Normal production startup
installs no capabilities, even for the same ruleset or database snapshot.
Public selection/start/rematch/timers/debug remain disabled. No network flag,
fixture endpoint or frontend mock bypasses these boundaries.

The output folder contains `report.json`, public screenshots and a local
`fixture-bindings.json` with **synthetic seat proofs**. Keep this manifest private,
outside all served/tracked folders; never print, publish or commit it. It stores
no trusted assignments, hidden map recipe or private-hand dump. Only the normal
production frontend is served. The runner stops its own processes and never
resets volumes. Wire counterfactual/authorization tests are separately in
`tests/test_fog_live.py` and `tests/test_fog_live_privacy.py`; browser visibility
alone is not the privacy guarantee. Current executed results and public-release
limits are in `docs/obsidian/Project State.md`.

## Natural whole Fog match — internal only

`tests/test_fog_natural.py` starts at an empty normal engine opening and plays a
two-player custom `shared-preassigned-v1` match to server victory using real
owning WebSockets/PostgreSQL. It reuses `full_match_support`'s Backend/Match and
cooperative player, with explicit Fog frontier planning based only on public
known terrain/legal lists. No grants, prepared midgame, score/occupancy edits,
teleports, Test Tools or alternate gameplay executor. Controlled private RNG is
installed only in the guarded isolated test process. The supported-count claim
is two tested players, not general competitive Fog certification.

```powershell
# CATAN_TEST_DATABASE_URL must already name an isolated localhost *_test DB.
$env:CATAN_FULL_MATCH_OUTPUT = Join-Path $env:TEMP 'catan-fog-natural-traces'
$fogScratch = Join-Path $env:TEMP ('catan-fog-natural-' + [guid]::NewGuid().ToString('N'))
.venv/Scripts/python.exe -B -X utf8 -m pytest -q --basetemp=$fogScratch tests/test_fog_natural.py
# DATABASE_URL must name a separate disposable browser *_test DB.
$env:CATAN_NATURAL_TRACE = Join-Path $env:CATAN_FULL_MATCH_OUTPUT 'seafarers_fog_natural.json'
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP ('catan-fog-natural-browser-' + [guid]::NewGuid().ToString('N'))
node web/e2e/fog-natural.cjs
```

Build `web/dist` and use the existing external Playwright/installed Chrome as
above. `fog-natural.cjs` replays that exact accepted-command transcript, using
actual SVG Road, Board3D Ship, Roll and Gold controls at representative points;
bulk moves use the owning sockets. It observes raw personal frames, actual
scene/DOM, finite reveals, resource-hand/VP HUD, refresh, process restart during
Gold, victory/results and a new Fog rematch. This is a legally funded complete
match, not an all-click competitive human playthrough.

`tests.fog_natural_support serve --manifest <private-file>` is **test-only**.
It binds loopback, requires disposable PostgreSQL/Test Tools off and prepares
only a lobby recipe/configuration. ContextVars admit only that privately
recorded native room's start/rematch through the original feature/Repository
fences, retaining dispatcher/host/ownership/count/epoch/transaction/receipt/F1
behavior. Recovery remains pure; only the launcher explicitly rebinds its
recorded fixture capability afterward. No public map-selection flag, endpoint,
environment activation or production initializer is added. Other rooms and
normal production startup stay closed, including forged flags/valid cookies.

Use a **fresh output folder** for a fresh replay: an existing manifest deliberately
restores its recorded room rather than overwriting or resetting it. Local
`private-bindings.json` contains synthetic seat proofs; Python pytest also
retains `private-server.log` for diagnostics. Keep both private and outside any
served/tracked directory; never print/publish/commit them. Reports/screenshots
contain public test UI only. The runner stops its own backend/Chrome and never
resets a volume or deletes a match. Public Fog remains **DISABLED**; do not deploy
this launcher. Current results and the separate activation design are in
`docs/obsidian/Project State.md` and `docs/obsidian/plans/seafarers-fog.md`.

## Public Fog beta admission and natural Chrome acceptance

The preceding internal launchers remain historical test-only admission seams.
Production now has a separate canonical two-player custom beta; admission is
**disabled by default**. Never deploy a test launcher or use its RNG controls.
The beta is not official Fog Islands. Server-owned policy and rollback details
are in `docs/obsidian/plans/seafarers-fog.md` and `Deployment.md`.

`tests.fog_beta_support` starts the normal production application/lifespan and
public endpoints on isolated loopback PostgreSQL `*_test` data. Only its test
process controls randomness. It installs no fixture capability, prepared match,
admission patch or private endpoint. `tests/test_fog_beta.py` exercises normal
Host/Join/select/start, ownership, enabled/disabled admission, emergency stop,
private frames, receipts and pure recovery. Its natural test generates a trace:

```powershell
$env:CATAN_FULL_MATCH_OUTPUT = Join-Path $env:TEMP 'catan-fogbeta-traces'
.venv\Scripts\python.exe -B -u -X utf8 -m pytest -q -o addopts= tests/test_fog_beta.py
$env:DATABASE_URL = $env:CATAN_TEST_DATABASE_URL
$env:CATAN_NATURAL_TRACE = Join-Path $env:CATAN_FULL_MATCH_OUTPUT 'seafarers_fog_beta_2.json'
$env:CATAN_E2E_OUTPUT = Join-Path $env:TEMP 'catan-fogbeta-browser-fresh'
node web/e2e/fog-beta.cjs
```

Use the existing external Playwright installation/Chrome and build `web/dist`
first, as described above. Supply only a disposable localhost test database.
The new runner reuses the full internal replay's renderer/HUD/Gold assertions
through optional test hooks. Its default internal runner retains its original
private-manifest/public-gate checks. Beta creates seats through the actual Home
UI, checks the absent-variable default before deliberate enablement, plays the
complete trace through normal owning WebSockets with representative UI actions,
and checks SVG/3D, pending Gold restart, results/rematch and policy transitions.
Reports/screenshots are public test UI; credentials remain in browser storage,
not reports. This is not an all-click human competitive or mobile certification.

Actual production Docker acceptance uses `compose.yaml` plus
`tests/fog_beta.compose.yaml` under an explicit `*-test` project. Its separate
disposable volume/loopback ports and exact proxy peer do not touch user data.
`CATAN_FOG_BETA_TEST_PROJECT` opts `tests/test_fog_beta_docker.py` into that stack;
it tests the image's actual configuration through Nginx, with no test RNG or
fixture code installed. Run once at default admission `0`, deliberately enable
admission for the isolated stack and rerun for real two-player setup, then
restore `0`. Do not toggle a stack while another acceptance test uses it.
