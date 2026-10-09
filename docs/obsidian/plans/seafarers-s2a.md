---
tags: [catan, plan, seafarers, maps]
updated: 2026-10-09
---

# Seafarers S2A — Maps, islands, coastlines and ports

[[Project State]] · [[Карты и сценарии]] · [[Правила Seafarers]] · [[Architecture Decisions]]

Status: **Completed — verified 2026-10-09, checkpoint commit `e79dee4`.** Checkpoint `seafarers-hardening-s1` verified at `b5cc066` with an initially clean tree; its specific creation was explicitly authorized. A completed-phase commit and clean working tree suffice; tags are optional. The implementation/verification below describes the historical S2A checkpoint. S2B-1 subsequently completed explicit custom scenario configuration, codec v3/2 and a new match marker; current status — [[plans/seafarers-s2b-1]]. S2C/S3 remain unstarted.

## Affected execution path

LobbyPage → WSClient.setMap → locked authoritative dispatch → detached Room candidate → `_start_match` / `rules.build_game` → `maps.build_board_from_map` → stored BoardState → PostgreSQL COMMIT → F1-authorized personal snapshot → App / GamePage → shared interaction controller → SVG or Board3D. Clicks return original IDs to the existing executor. Recovery reads saved geometry and never rebuilds a preset.

## Initial inventory and confirmed problems

All twelve presets have 19 hexes. Eight Base presets have 19 land / 0 sea / one island. Seafarers Coastal Lanes has 13/6/one, Simple Sea Ring 9/10/one, Gold Haven 15/4/one (two Gold), Pirate Lanes 13/6/one (one Gold). Nine auto ports use four generic and one of each specialized resource; at seed 1 respectively 5/8/4/4 Seafarers ports are not on a real coast. Base coast placement is valid. Simple maps truncate the 19-card terrain deck, and Pirate Lanes truncates its deck; resource/desert supply can vary unexpectedly. Gold Haven has no desert and falls back to robber index 0, a Gold hex. No preset declares a starting region or player-count restriction; Room supports 2–6. No preset is an official named Seafarers scenario, and no island reward/fog is currently represented.

## Implementation decisions

- Preserve all twelve IDs/names/options and Base layouts/decks. Coastal Lanes and Sea Ring remain one-island maps; correct exact terrain decks and real-coast ports. A 30-seed randomized setup probe found four six-player deadlocks on the old nine-land Sea Ring (10–11 settlements placed, then no legal vertex). Extend that preset to the standard 19-land core plus a complete 18-sea ring, without inventing a player-count restriction.
- Deliberately extend Gold Haven and Pirate Lanes to a radius-three 37-hex grid with two separated land components and a navigable channel. Keep land/Gold totals, rule flags and 10VP target. No newly invented starting-island restriction: setup may use any legal land intersection.
- Derive components/coast edges from stored `edge_adj_hexes` and terrain, not another coordinate graph. Island ID is the smallest original tile index of its component, stable within a materialized saved board. No mutable island state, new rewards or codec fields.
- Auto ports choose a bounded, deterministic set of real coast edges without shared endpoints. Explicit ports retain their edge/type/order but must validate coast, identity and overlap at map creation. Recovery does not retroactively reject historical ports.
- No-desert Seafarers uses robber `-1` (offboard); land clicks still require real tile IDs. Keep numeric wire shape. Extend only codec v2's robber value domain; frozen v1 remains unchanged. Pirate remains a valid sea index or absent. Normal recovery performs no rules/VP reconciliation.
- Board3D port offsets must face the adjacent water, including inward-facing channel shores. Preserve round token/readout/artwork, GLBs, models, ocean, audio and existing camera architecture. Both renderers hide an offboard robber.

## Implemented layout and data contract

| Preset | S1 land/sea/islands | S2A land/sea/islands | Gold/desert | Initial figures |
| --- | --- | --- | --- | --- |
| Eight Base presets | 19/0/1 | unchanged 19/0/1 | 0/1 | unchanged desert; two robbers in base_20vp_multi_robbers |
| seafarers_simple_1 | 13/6/1 | 13/6/1 | 0/1, now fixed quotas | desert; no pirate |
| seafarers_simple_2 | 9/10/1 | 19/18/1 | 0/1, now full standard deck | desert; no pirate |
| seafarers_gold_haven | 15/4/1 | 15/22/2 (8+7) | 2/0 | robber -1; pirate first sea index 0 |
| seafarers_pirate_lanes | 13/6/1 | 13/24/2 (7+6) | 1/1, now fixed quotas | desert; explicit sea pirate index 2 |

Complete twelve-preset registry/targets/flags — [[Карты и сценарии#Presets]]. Room support remains 2–6, without new start regions. All twelve maps have nine nonoverlapping coast ports, four generic and one specialized per resource; all required resources remain represented. Gold/Pirate islands have no shared land edge or vertex, and sea has one component. Graph, IDs and geometry still come only from board_geom; topology helpers are read-only. Main commands/route scoring/victory rules stay S1.

Codec writes stay v2/engine_compatibility=1 and current ruleset marker stays `catan-seafarers-s1`. V2 alone extends robber value domain to -1 for Seafarers; frozen v1 remains unchanged. Old heads and original source definitions are restored directly, never rebuilt, port-repaired or rescored. **Old S1 binaries cannot read new offboard v2 heads**: do not rollback those records to S1 or rewrite heads to disguise the difference. No SQL migration/marker backfill, F1/F2 changes or RAM-only fallback. Policy — [[Architecture Decisions#ADR-016 — Materialized map topology and offboard Seafarers robber]].

## Verification completed — 2026-10-09

| Check | Actual result and scope |
| --- | --- |
| Full pytest with isolated PostgreSQL | **823 passed, 0 skipped, 0 failed**, 99.40s; +66 S2A cases over historical F3 757. Includes Base/S1/F1/F2/F3/auth/ownership/PG/Qt regressions |
| Full web suite | **250 passed**, +9 geometry/render-model cases over F2 241 |
| TypeScript | `npx tsc --noEmit` passed |
| Production web | `npm run build` passed; Board3D ~946.95 kB /256.21 kB gzip, existing chunk-size warning |
| Scenario harness | **348/508 passed, 160 failed**; exact same failing scenario/seed pairs and details as final S1: 140 pre-roll and 20 pirate-connectivity fixture failures. No scenario source/assertions changed |
| All-preset topology | Twelve presets ×20 seeds, deterministic geometry/IDs/coasts/port kinds; eight Base states compared directly to S1 loader across 20 seeds and unchanged |
| Setup | Four changed Seafarers ×2–6 players ×30 seeds = **600 randomized completed setups**, alternating ship preference; Gold choice/route lifecycle/supply included. Not exhaustive over every possible placement order |
| Reachability | Actual paid cross-island ship chains and ordinary +1VP destination settlements; all four updated maps have legal paid roads/settlements/cities reaching existing 10VP. Explicit funding/production fixtures, not naturally earned full games |
| Recovery | Frozen S1 v2 Gold Haven and fresh PG coordinator retain old 19-hex board/source/ports/VP with compatible or unknown marker; new separate room gets 37. v1 decode/security/Continue/rematch/atomicity regressions pass |
| Qt | Real file round-trip retains offboard -1; negative index is not drawn on final sea tile. Shared S1/F3 history remains intact |
| Chrome multiplayer | Real production dist/FastAPI/WS/PG, Chrome **154.0.8037.98**; two clients on each Gold Haven/Pirate Lanes; **69 command attempts including two intentional invalid-coordinate rejects**, ten focused acceptance groups |

[test_seafarers_maps.py](../../../tests/test_seafarers_maps.py), [test_seafarers_map_recovery.py](../../../tests/test_seafarers_map_recovery.py), [test_desktop_ship_persistence.py](../../../tests/test_desktop_ship_persistence.py) and [seafarersMaps.test.mjs](../../../web/tests/seafarersMaps.test.mjs) hold focused regressions. Web geometry fixtures are asserted against actual Python snapshot output, not an independent map model. Existing synthetic v1 fixtures now use historically valid on-board robber values instead of relabeling a new offboard v2 state; old schema/security assertions remain. Other setup/Gold/victim fixture adaptations remove old 19-hex adjacency/number assumptions without weakening rules. Scenario fixtures were deliberately untouched.

Browser runner [seafarers-s2a.cjs](../../../web/e2e/seafarers-s2a.cjs) uses ordinary lobby/Start/setup plus named Test Tools for deterministic dice, matured Knight and explicit expansion resources. Natural setup/Gold/initial ship, paid crossing (observed route lengths 7 and 2), coastal settlement→city/road, invalid build atomicity, pirate pending consumption, next turn/Seven/discard/robber, original piece ownership, all 37 terrain GLBs/number tokens, nine ports, SVG/Three switch, orbit/zoom/Reset, desktop resize and verified guest refresh pass. Screenshots of both maps in both views were inspected. Camera implementation required no change; reset verification waits for the real React effect. No browser JS errors. This is a partial multiplayer flow, **not a naturally played full match**; account/revoke/timer/game-over branches are covered by Python regressions rather than newly replayed manually here.

Artifacts remain outside the repository under `%TEMP%/catan-s2a-hardening/`: `pytest-full.xml`, `pytest-full.log`, `web-tests.log`, `browser/report.json`, four browser screenshots; scenario report `scenarios/reports/report_20261009_142859.json` compared with S1 `report_20261008_204932.json`. Reports do not publish reconnect proofs/private hands. These are local verification artifacts, not tracked design references or production evidence. Reproduction instructions — [web/e2e/README.md](../../../web/e2e/README.md).

## Known limits and remaining work

- The 160 pre-existing scenario failures remain known broken, with unchanged reasons; green pytest does not resolve them.
- Custom JSON is structurally validated, not certified balanced/playable. Oversized decks may truncate; small auto coasts may have fewer ports. No universal 6/8 adjacency constraint or probability-balance guarantee.
- An invalid historical authored port definition remains recoverable as its stored board but may fail a separately requested new-map/rematch build; historical records are not silently repaired.
- Full natural matches, all possible opening orders, official 5–6-player extension mechanics, mobile/low-end and load/performance certification are not inferred from these checks. No Docker build was run; no deployment/dependency changes were made.
- Historical heads retain their previous layouts, including previous coast/initial-robber defects. F2 unknown ruleset remains restricted; this task does not convert old gameplay.

## Explicitly deferred

At the S2A checkpoint, scenario-specific starting islands and island bonuses were deferred to S2B; explicit custom mechanics are now implemented/tested in [[plans/seafarers-s2b-1]]. Preset product parameters and fog/exploration remain deferred. S2C: broader scenario/port customization and balance work under a separate task. Full natural long matches, 5–6-player official extension mechanics and mobile/low-end performance certification are not inferred from fixtures. No public generator/editor, ruleset conversion, auth/persistence/deployment rewrite or new assets.
