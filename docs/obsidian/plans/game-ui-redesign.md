---
tags: [catan, план, web, дизайн]
updated: 2026-10-05
---

# Game UI Redesign

[[Project State]] · [[Design System]] · [[React интерфейс]] · [[plans/board3d]]

## Phase 1 — Game Screen Composition

Status: Completed — 2026-10-05. READY FOR CHECKPOINT. Base: clean commit a1cbd7e (Board3D Phase 3). User authorizes composition/HUD changes, scoped match CSS, compact controls, legal-marker/port presentation and camera framing; not gameplay/backend/controller or terrain/piece overhaul.

### Before implementation

Chrome opened the unchanged production GamePage on 2026-10-05. Board is a widget in a two-column grid with a clamped canvas height. Bright blue page and large cream status/resource/action/player/log cards compete with it. Debug metadata and always-open log dominate; resources resemble form chips, actions are a permanent button row, branding and view controls look provisional. Legal targets are already action-specific in the shared controller, but setup rings are too prominent. Ports have excessive white area. Preserve the existing 3D art and interaction.

The attached image is the user-named primary reference. Observed image still contains the old blue/cream dashboard; the explicit target requirements take precedence for adaptation: dominant board, compact top strip, contextual prompt, bottom-left resource hand, bottom-right action dock, drawers, unified dark background and small controls. Do not reproduce old card composition literally or invent a missing reference asset. Save an actual pre-change browser screenshot as rejected baseline.

### Affected execution path

App holds match/room/status/log/error. GamePage owns useBoardInteraction and existing discard/gold form state. New HUD only presents these values. Build selection → unchanged controller targets from personal legal → BoardRenderer (SVG or Three) → original callback → original command → WSClient envelope/ACK → existing server/engine → player-specific snapshot → App.setMatch → GamePage and board. Roll/end/discard/gold retain existing payloads and availability conditions. Public player strip uses snapshot vp/resource_count/dev_count; exact hands remain personal.

### Implementation boundaries

- Viewport match shell: compact top players/goal/room, central board stage, bottom resource hand/action dock. Scoped CSS leaves LobbyPage/global lobby appearance intact.
- Move BoardControls out of BoardRenderer into the dock; same controller props/callbacks. Build palette is local presentation; victims keep explicit server-driven choice. Trade/dev controls cannot send fabricated commands: their full UI remains later scope.
- Compact 2D/3D selector, 3D default with existing SVG/error fallback; local camera reset. Replace raw tile-index footer with GamePage context prompt.
- Log/info overlay drawers; existing discard/gold forms in a compact focusable overlay. Preserve log data, error messages and pending commands.
- Only local Three embedding/marker/port/framing changes. Terrain, models, topology transforms, protocol and legal remain unchanged; no extra dependencies or animation loop.

### Verification

Existing web/controller/renderer tests; a small set of meaningful HUD/action/prompt/drawer/selector/privacy tests; TypeScript, production and Docker frontend build. Real Chrome: Base setup/main/build, Gold sea/gold/ship/pirate and ship movement, 2D/3D/reset, drawer open/close, keyboard focus and 1920×1080 / 1440×900 / 1280×720 without gameplay-page scroll. Keep engine-built controlled fixtures separate from real two-client flows. Capture screenshots under docs/design/references/game-ui-redesign-phase1/. Python/scenarios not rerun if untouched; check protected file hashes.

### Implemented result and verification limits

GamePage now composes GameTopBar, central BoardRenderer/ContextPrompt, ResourceHand and action dock/BoardControls. HUD and overlays live in web/src/game/, with match-only CSS. Local presentation helpers read the same server snapshot and original controller; no alternate game model/rules. Default 3D, compact view/reset and original SVG remain. Debug footer removed; log/info hidden by default. Trade/dev buttons explicitly unavailable; no command/forms added. Mandatory discard/gold focus trap and nonmodal victim chooser retain original commands. Ports/markers changed only visually; hit areas, topology/IDs, terrain/pieces, camera direction and resource lifecycle are unchanged.

2026-10-05: 73/73 web tests (65 existing + 8 focused UI cases), TypeScript, production web build and Docker frontend build passed. Existing BoardView assertion now expects unavailable Pirate to be hidden; command/no-authorization assertions preserved. Test JSX tracer now forwards real React Fragment used by icons. Drawer dismissal/render defaults are SSR-tested; actual drawer state transitions, renderer switching and keyboard behavior are tested in Chrome, not claimed as SSR state transitions.

Chrome 154 / ANGLE / NVIDIA RTX 5050 against production Docker:
- Real independent Host/Join clients, confirmed map selection/Start: Base Standard all eight setup actions, Roll, road, robber and End across 5 turns (tick 21); Gold Haven setup/Roll/ship/pirate/End across 9 turns (tick 28). Both clients agree on public state. A prior random run did not accumulate an available road build within its 40-turn harness limit; subsequent real room did. Controlled fixtures cover availability deterministically instead of asserting a stochastic turn count.
- Engine-built prepared states + mocked transport with the actual server executor: both SVG and Three settlement/city/road/ship; ship source/cancel/destination and switching; explicit second victim for robber/pirate; two free roads before Roll; rejected affordability with unchanged occupancy/no phantom; full eight-click SVG setup. Natural ship move was not reached in the final short Gold run; this branch was verified in the real-engine fixture.
- Real browser UI checks: initial setup/default 3D, idle no legal targets, City targets only when selected, palette/Cancel/Escape, log/info open/toggle/close/Escape/focus restore, 2D↔3D without commands/state mutations, zoom/reset, mandatory gold/discard focus trap and non-dismissal. Six long player names retain current turn/info/log controls at 1280.
- Base/Gold at 1920×1080, 1440×900, 1280×720: stage 872/712/546px high (80.7/79.1/75.8% viewport), Canvas 820/660/494px. No horizontal/vertical page scroll, hand/dock overlap or buttons outside viewport. Island remains auto-fit to actual footprint; these figures describe the scene, not island screen-area or visual-attention percentages.
- No page/console errors or WebGL warnings. Existing demand rendering: zero extra idle frames; unmount releases shared geometries/textures and context. Vite retains lazy Three chunk warning (~881 KB, ~237 KB gzip); no new libraries/assets except screenshots/native SVG code.

Evidence: [[Design System#Game UI Redesign Phase 1 — implemented composition]], docs/design/references/game-ui-redesign-phase1/. Main/build/Gold captures use prepared current-engine snapshots; base-setup is a real room, baseline was captured before edits. Harness/raw snapshot files stay outside repo. Screenshots are implementation evidence, not final new concepts.

Runtime Python, server/legal/serialization/reconnect, wsClient/shared interaction, SVG source, maps/generator, terrain/piece models, dependency manifests/lockfiles and Docker architecture stayed unchanged. Python pytest/scenarios not rerun; 186 and 348/508 remain historical results. Docker was already running and remains available at http://localhost; only web container replaced, backend not restarted.

Existing limitation observed: mountain/tree geometry can occlude the exact midpoint of some road hit surfaces. A visible point on the same prism/orbit remains usable; original handlers/terrain are unchanged. The browser harness chooses a visible point through actual projection/raycast and still sends a real mouse click, not a command bypass. This interaction follow-up is outside composition scope. Full match, mobile, low-end/browser matrix and formal accessibility certification not covered.

Checkpoint proposed, not executed: commit `feat: redesign game screen around board`, tag `game-ui-phase-1`.

### Later phases

Lobby/menu, trade/dev forms, settings, results, mobile, gameplay P1 and further terrain art remain outside Phase 1. No automatic follow-up phase, commit or tag.
