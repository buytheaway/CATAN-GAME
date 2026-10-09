---
tags: [catan, plan, seafarers, fog]
updated: 2026-10-09
---

# Seafarers fog — trusted foundation

[[Project State]] · [[Architecture Decisions]] · [[Карты и сценарии]] · [[Состояние игры]]

## Scope and status

S2B-2A design is approved. S2B-2B.1 is **completed/tested 2026-10-09; READY FOR CHECKPOINT in foundation scope**: trusted domain, private recipes, codec v4/3 and provenance. Public availability is **DISABLED**; the complete fog feature is **partially implemented**. Exploration execution, rewards, Gold continuation execution, secure playable projection and SVG/Board3D rendering belong to S2B-2B.2. No existing preset is converted to fog. Baseline HEAD was `c049b22`; unrelated Obsidian graph/workspace preferences are preserved. No automatic commit/tag.

## Approved profile

`shared-preassigned-v1` uses shared, monotonic discovery and privately preassigned immutable terrain/number values in the existing BoardState. Original tile/vertex/edge IDs are retained. One ledger entry per discovered hex; continuation metadata is durable. Fog cannot combine with `starting_islands` or positive `new_island_vp`. Unrevealed content stays private even after game_over.

Official Fog Islands draws from face-down terrain/token stacks on discovery. This custom digital profile assigns content before play; it is not a claim of identical draw-on-reveal semantics.

## Implementation boundaries

- ScenarioRules/ScenarioState own fog configuration and history; no second topology model.
- Map format v2 is a recipe of visible tiles and fog slots with exact unordered pools. Hidden assignment uses independent trusted randomness; deterministic RNG injection is test-only.
- Trusted codec v4/engine compatibility 3 preserves assignment/history. Explicit v1/1, v2/1, v3/2 schemas restore fog-disabled state without running rules or rewriting VP/achievements.
- New matches use `catan-seafarers-s2b-2`. Existing verified S2B-1 and eligible S1 markers remain unchanged; unknown provenance stays F2-restricted.
- Until playable projection/validation exists, public selection/start, gameplay/legal/snapshot publication, debug tools and Qt conversion/save/load reject fog. Internal trusted construction and persistence fixtures are permitted.
- Existing COMMIT-before-publication/ACK, F1 ownership and account/guest Continue semantics remain.

## Verification

Verified **2026-10-09**:

- **Full pytest: 1003 passed, 0 skipped, 142.31 s**, using a separate disposable PostgreSQL 17 database initialized with existing migrations and real PySide6 offscreen paths. No production database, new migration, historical-data conversion or runtime service deployment was used.
- **93 new fog cases** in four files: typed configuration/masks/ledger/continuation, exact pools/private RNG/visible-only setup/coasts, invalid recipes/indices/snapshots/transitions, all 12 ordinary presets, frozen historical schemas, JSON v4 round-trip and disabled command paths.
- Real WS two-client selection/start refusal, safe error payloads, ordinary Base start, injected trusted fixture command/debug/rematch/publication fences. This is handler acceptance, not a playable fog browser match.
- Real PostgreSQL COMMIT/fresh Coordinator restores both recorded and pending trusted histories without gameplay execution; reconnect/account Continue/claim/takeover retain ownership but expose no private frame, timers remain inert and old heads/participants/results remain unchanged. Historical S2B-1 v3/Base/Seafarers markers continue unchanged and later accepted commands use writer v4.
- Real Qt conversion refusal, save preserving an existing file and load preserving current game/file; ordinary Base/F3/scenario save/load regressions remain green in full pytest.
- F1 private publication, F2 unknown marker/metadata-only fences, Largest Army and prior Base/Seafarers tests included. Initial full run found unordered SQL row comparisons in a shared test helper; full records now compare by actual participant and composite receipt primary keys, without weakening contents. Explicit Largest Army historical v3 coverage is retained alongside v4.
- **Web tests: 253 passed, 0 skipped; TypeScript passed**. Frontend/runtime/assets were not changed; production build/Docker/browser were not rerun for this foundation.

Scenario harness/expectations are unchanged and were not rerun. Last verified S2B-1 baseline remains historical **348/508**, with **140 pre-roll** and **20 pirate connectivity** failures. The separate Largest Army harness tied-holder limitation remains known broken; this phase does not fix or reclassify it.

## Exact implementation files

Runtime: `app/engine/{state,scenario,exploration,maps,rules,legal,serialize}.py`, `app/match_rulesets.py`, `app/persistence/{snapshots,repositories}.py`, `app/auth/routes.py`, `app/server_mp.py`, `app/test_tools.py`, `app/ui_v6.py`. New exploration.py contains foundation validation/gates only. No SQL migration/React/Board3D/preset/GLB/audio/deployment changes.

Tests: `tests/test_fog_foundation.py`, `tests/test_fog_feature_gate.py`, `tests/test_fog_recovery.py`, `tests/test_fog_desktop.py`; historical writer/version regression updates in `tests/test_persistence_snapshots.py`, `tests/test_match_rulesets.py`, `tests/test_seafarers_scenarios.py`, `tests/test_seafarers_recovery.py`, `tests/test_seafarers_scenario_recovery.py`, `tests/test_largest_army.py`, `tests/test_largest_army_recovery.py`.

Documentation: this plan; `Project State.md`, `Architecture Decisions.md`, `Состояние игры.md`, `Сервер и протокол.md`, `Карты и сценарии.md`, `Desktop клиент.md`, `Инварианты движка.md`, `Игровой движок.md`, `Карта файлов.md`, `React интерфейс.md`, `Правила Seafarers.md`, `00 Главная.md`, `plans/README.md`, `plans/persistence-auth.md`, `plans/seafarers-s2b-1.md` under `docs/obsidian/`. Historical ADR/checkpoint evidence is preserved with superseding scope.

## Next stage

S2B-2B.2 must implement accepted road/ship discovery, known-terrain legality/production/robber/pirate, rewards and setup continuation, allowlisted personalized projections/events, legal-probe isolation and both renderers. Only then can the public feature gate be considered for removal, after two-client raw-payload acceptance. No automatic activation follows foundation completion.
