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

## Phase 2 — Trade / Development Cards / Endgame

Status: Completed — 2026-10-05. READY FOR CHECKPOINT. Base: clean 9c6c820 (user commit includes Phase 1 and Polish 1.1); local game-ui-phase-1 tag absent. No new board/terrain redesign, engine rule changes, database or dependency modernization.

Capability audit: rules.trade_with_bank/best_trade_rate already enforce 4:1/3:1/2:1 port ownership, turn/roll/pending, hand and bank. apply_cmd already supports targeted/broadcast trade_offer_create with give/get/to_pid, accept/decline/cancel and end-turn cancellation. Offers are public snapshot terms, not private hands. No in-place edit; replacement means cancel then create. Broadcast decline closes the whole offer; disconnect does not itself cancel it. UI must describe this existing lifecycle honestly.

buy_dev/play_dev already implement the five cards, passive VP, new-card and one-play restrictions. to_player_dict includes only personal dev_cards/new, dev_played_turn/free_roads, bank_available booleans and public opponent counts; no exact bank/deck availability. Knight enters existing robber/pirate pending, Road Building supplies existing free board targets, Year of Plenty uses a/qa/b/qb and Monopoly r. check_win sets game_over/winner_pid; final VP reveal and connected-player rematch/leave_room exist. Engine events are not broadcast; no fabricated client game history. Known off-turn victory, achievements and unused free-road lifecycle remain gameplay backlog, not silently changed here.

Affected path: GamePage → compact Trade/Dev/Results components → existing WSClient command envelope → server._apply_cmd → unchanged engine.apply_cmd → personal snapshot → App.setMatch → hand/offer/results UI and original shared board controller. Card/resource state never changes optimistically. ACK correlation releases UI request waiting; server error preserves editable choices. Knight/free roads reuse useBoardInteraction and original renderer callbacks. Results use winner_pid/final vp; rematch identity/sequence comes only from server. Back to Lobby wraps existing leave_room with explicit local transport cleanup.

Implementation: native React/CSS compact bank/player trade modal and incoming drawer; self-only dev mini-hand/details/pickers; results overlay and existing rematch/leave controls. Pure presentation helpers read existing wire fields, choose displayed port ratio and validate form input only. Extend TypeScript for already-serialized fields, not wire semantics. Controls use snapshot restrictions; final validation remains server authority, particularly two identical Year of Plenty resources with hidden bank counts.

Verification planned: focused web component/controller/transport regression tests, TS, production/Docker build, real Chrome with two clients. Engine-built controlled fixtures must exercise actual WebSocket server validation/privacy/ACK and victory/rematch (separate temporary test server/container, not a public debug endpoint). Check 4/3/2:1, reject atomicity, domestic lifecycle, all dev cards/limits/privacy, winning action/final scores/blocked actions/rematch/reconnect/exit. Natural setup/Roll/build flow stays separate from fixtures. No Python runtime edits expected; scenario baseline remains historical unless rules change. Update existing UI/design/state notes with dates and limits; no session logs.

### Implemented Phase 2

Runtime: GamePage/App plus TradePanel, DevelopmentCards, Endgame, actions, useGameCommand, presentation and scoped game.css. WSClient types existing snapshot fields, returns sendCmd identity, exposes local matching-ACK/consumed-reconnect notification and wraps existing leave_room with explicit cleanup. No wire command/serialization changes, no backend edits and no additional production libraries. BoardRenderer/BoardView/Board3D/useBoardInteraction/engine/maps/Docker architecture untouched.

UI supports bank 4/3/2:1, targeted/broadcast create/accept/reject/cancel, two-column quantities and server error recovery. Own mini-hand/groups/new restrictions, buy, all five types/pickers, Knight existing pending/victims and Road Building original free targets work. Road automatic selection waits for shared-controller reconciliation; both placement steps stay interactive after the first ACK. Victory uses server winner/final scores, active actions disappear, connected-policy rematch supplies new match/pid/sequence, and explicit leave/rejoin retains the existing room/name token cache. A lost rematch request allows a retry after reconnect instead of leaving the UI waiting permanently.

### Verification — 2026-10-05

- 92/92 web tests (76 prior + 16 focused behavior cases), TypeScript and production build passed. Added cases cover displayed ownership/ratio, offers/audience/own affordability, self-only card grouping, new/one-play/before-roll/passive restrictions, existing payloads, server result delegation, matching ACK and consumed reconnect/leave cleanup. No WebGL pixel tests. Full pytest additionally rerun: 186/186 passed. Scenario suite not rerun because rules.py/engine are unchanged; 348/508 remains the historical baseline, not a new result.
- Docker compose build passed for production web/backend; only the production web container replaced. User backend/rooms were not restarted. App remains available at http://localhost. Test-only compose/fixture initializer under web/e2e does not enter the production images/command or deployment architecture.
- Chrome 154.0.8037.93, real production frontend/nginx/WS with separate two/three-client contexts: 14 E2E cases, 45 command attempts, 7 expected rejections. 4/3/2:1 confirmed against owned port fixtures; invalid bank command kept hand/tick unchanged and selection editable. Player target/broadcast offers accepted off-turn, rejected, cancelled/replaced and cancelled by End; both sides' real balances updated.
- Buy → own new card; opponent gets count only; new play rejected atomically; End/next turn ages it. Knight played before Roll → original 3D robber target; one-play restriction/second-card rejection checked. Road Building before Roll → 1/2 and 2/2 → both original free roads without resource payment. Year of Plenty intentionally asks two wood with only one in hidden bank: exact server rejection preserves state/card/picker; changing to wood+ore succeeds. Monopoly transfers three players' wood through authoritative snapshots. Own VP visible, opponent hidden VP omitted until game_over.
- Controlled winning VP purchase → winner/10 VP/final opponent VP; opponent res/dev_cards stay private; UI hides actions and raw post-game command is rejected atomically. Normal rematch, deliberately lost rematch + reconnect/retry, disconnected-host rematch, compact pids, retained-token refresh, match_id increase and first new seq=1 checked. Back to Lobby broadcasts disconnect, stops automatic reconnect and explicit Join with prior room/name restores the old result.
- Test initializer compares complete deep-copied GameState before/after every rejected command. Fixtures only prepare first-match hands/setup/cards/scores and deterministic test dice; rematch uses unmodified initialization. This is real server execution, not intercepted/synthetic match_state. Runner/limitations: [web/e2e/README.md](../../../web/e2e/README.md).
- Unprepared first match in test stack: all 8 setup clicks, Roll, End and 2D↔3D with no state/command mutation on view switch. Separately the ordinary production backend (no fixture/dice patch) passed the same two-client Base flow, tick 10. Full natural multi-hour match and all paid building branches were not replayed in this task; existing controller tests/earlier Phase 1 evidence remain separate.
- Desktop 1280×720, 1440×900, 1024×768: five dev types alongside resource hand fit without page horizontal scroll, HUD overlap or off-screen cards. Optional modal Escape works. No page/console/WebGL errors; existing demand rendering adds 0 idle frames. Main JS ~201.87 KB / 63.68 KB gzip; unchanged lazy Three ~882.85 KB / 237.83 KB gzip retains size warning. No low-end/mobile/FPS certification.

Evidence — [[Design System#Game UI Phase 2 — implemented actions and results]], docs/design/references/game-ui-phase2/. Permanent snapshots/resources are never optimistic. Engine events still are not sent to clients, so the existing transport log is preserved rather than fabricating game history.

### Remaining boundaries and gameplay gaps

No new backend capability blocker was found for these UI actions. Existing engine behavior is not a guarantee of complete intended Base rules: off-turn victory detection, achievement ties, deterministic theft and unused Road Building free_roads surviving End remain separate gameplay issues. The free-road lifecycle was confirmed by reading rules.end_turn_cleanup / apply_cmd(end_turn), not corrected or claimed covered as a desired rule. Server offers are not reserved, broadcast decline closes globally, disconnect alone leaves an offer and in-place edit is unavailable; UI describes these boundaries.

Exact bank quantity and deck availability are unavailable by existing privacy contract; valid-looking forms can still receive a server rejection. Full event feed, lobby/menu/settings/mobile, save/persistence, Seafarers routes and further design/art are future independently authorized tasks. No automatic Phase 3/refactor/commit/tag.

Checkpoint proposal: commit `feat: complete web game actions and endgame UI`; tag `game-ui-phase-2`.
