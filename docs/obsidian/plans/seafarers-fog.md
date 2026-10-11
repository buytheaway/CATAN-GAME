---
tags: [catan, plan, seafarers, fog]
updated: 2026-10-12
---

# Seafarers fog — foundation and internal exploration

[[Project State]] · [[Architecture Decisions]] · [[Карты и сценарии]] · [[Состояние игры]]

## Scope and status

S2B-2A design is approved. S2B-2B.1 was completed/tested 2026-10-09 and checkpointed in `0fa8f6d`. **S2B-2B.2A internal exploration engine is completed/tested 2026-10-12; READY FOR CHECKPOINT in internal-engine scope.** Public availability remains **DISABLED**; the complete fog feature is **partially implemented**. Secure playable network projection/events and SVG/Board3D/frontend support remain future phases. Existing presets remain unchanged. This implementation began from clean HEAD `df5c813`; no new commit/tag is created automatically.

## Internal exploration engine — S2B-2B.2A

- `rules.apply_cmd(..., trusted_fog=True)` is a keyword-only trusted in-process entry point. The default still rejects fog before mutation. WS commands cannot opt in by including a similarly named field; server/debug/serialization/Qt gates remain active.
- Accepted paid/free/setup roads and ships, including Road Building, call `_finish_route` → `exploration.discover_route`. Ship movement discovers at the destination only. Both endpoints' vertex adjacency and edge adjacency determine all discoveries, sorted by original tile index within each command. Frozen history changes; actual assignments/IDs/geometry never change.
- Settlement/city/roll/legal queries do not discover tiles. Unknown tiles count as neither known land nor known sea. Road/ship/settlement predicates use known terrain; production, initial resource/Gold grants and robber/pirate targets skip unknown tiles. Initial setup capacity is visible-only; subsequently revealed land may participate in the same known-terrain setup/capacity guard. Stored initial ports remain unchanged and do not classify hidden shores.
- Standard producing land gives one matching bank card if available; Sea/Desert gives none. Unpaid shortages are recorded `unavailable`, without debt or cancelling placement. Every reveal has one reward record; completed entries are immutable, and touching/retrying cannot re-award them.
- Each discovered Gold tile creates one ordinary-resource entitlement via existing `pending_gold`, queue and `choose_gold`. Ledger entries become awarded in recorded order, including bulk/different-resource choices. Invalid/unauthorized choices preserve the whole state. If the bank empties, remaining entries become unavailable and the continuation completes; later refills do not revive them.
- `FogContinuation` retains original command/pid/edge/setup. Gold blocks End Turn and unrelated actions. Setup anchor/index/turn stay intact until the final choice, then advance once. Ordinary second-settlement Gold has no discovery continuation and still resumes the route step. Road Building retains its second free action; ship build/move history stays consumed. Current-player victory checks after the exploration reward continuation completes, including a newly earned Longest Route.
- Internal `board_legal_moves(..., trusted_fog=True)` executes on a complete independent copy per probe. The normal non-fog geometry memo remains; fog probes share neither BoardState tiles nor visibility/history/bank/continuation with live state or other probes. Public fog legal projection still rejects.
- `Coordinator.commit(..., trusted_fog=True)` forwards an explicit private test/executor opt-in to both transition fences and Repository. It permits only existing native-current fog matches with the same marker/epoch/status/timer and no lifecycle operation; assignments/history and finished-state fences still apply. Unknown/S1/S2B-1 provenance cannot opt in. No public caller sets this keyword. Real Room locking, ownership, detached candidates, transaction/receipt, COMMIT-before-promotion and uncertainty resolution are retained; no transaction waits for a Gold choice.
- Writer stays **v4 / engine compatibility 3**, Room wrapper v1, marker `catan-seafarers-s2b-2`; no schema migration or historical conversion. Normal recovery restores recorded pending/history without executing discovery, rewards, RNG, rules or score recalculation. Public Continue/takeover still provides restricted metadata, no playable snapshot.

## Verification — S2B-2B.2A

Verified **2026-10-12**:

- **Full pytest: 1085 passed, 0 skipped, 163.53 s**, with separate disposable PostgreSQL 17 and real PySide6 offscreen round trips. Initial run had 12 fixture errors from inaccessible system pytest temp storage; the complete rerun used an independent directory under ignored `.venv/test-artifacts`, without changing assertions or file permissions. No production database/service/migration was used.
- **82 new cases**: 59 internal engine/legal cases in [test_fog_exploration.py](../../../tests/test_fog_exploration.py), 23 command/persistence/provenance/ownership cases in [test_fog_exploration_recovery.py](../../../tests/test_fog_exploration_recovery.py). Existing real two-client WS gate acceptance now also attempts forged `trusted_fog` command fields. All earlier Base/Seafarers/scenario/Largest Army/F1/F2/F3/codec regressions remain included.
- Actual PostgreSQL tests cover setup road/ship, paid road/ship and pre-Roll Road Building pending Gold; every intermediate choice/restart/reconnect restores exactly. Accepted/rejected receipts, concurrent duplicate, lost ACK, failures before write/COMMIT and confirmed/unresolved post-COMMIT retries cannot duplicate rewards. Independent row locking while pending verifies no open transaction awaiting input. Public creation/commands/legal/private snapshots/debug/rematch/timers remain blocked.
- Focused PG/public-gate/real-Qt verification: **41 passed**. Four additional internal complete setups (2/6 players, default/rotated starter) used accepted commands and a real JSON v4 round-trip after every step; all completed without pending or double advancement. These are internal acceptance checks, not browser matches.
- **Scenario suite: 348/508**, same 160 historical failures: 140 pre-Roll command failures and 20 `no legal ship edge found` pirate cases. Runner/rules/assertions were not weakened; report output alone was redirected to ignored test artifacts. The separate historical Largest Army harness limitation remains unresolved.
- Frontend/runtime/types/assets/deployment were unaffected. Web tests, TypeScript, production/Docker build and browser acceptance were not rerun; the latest web result remains historical **253 passed / TypeScript passed, 2026-10-09**. Public playable fog is not verified or enabled.

## Approved profile

`shared-preassigned-v1` uses shared, monotonic discovery and privately preassigned immutable terrain/number values in the existing BoardState. Original tile/vertex/edge IDs are retained. One ledger entry per discovered hex; continuation metadata is durable. Fog cannot combine with `starting_islands` or positive `new_island_vp`. Unrevealed content stays private even after game_over.

Official Fog Islands draws from face-down terrain/token stacks on discovery. This custom digital profile assigns content before play; it is not a claim of identical draw-on-reveal semantics.

## Implementation boundaries

- ScenarioRules/ScenarioState own fog configuration and history; no second topology model.
- Map format v2 is a recipe of visible tiles and fog slots with exact unordered pools. Hidden assignment uses independent trusted randomness; deterministic RNG injection is test-only.
- Trusted codec v4/engine compatibility 3 preserves assignment/history. Explicit v1/1, v2/1, v3/2 schemas restore fog-disabled state without running rules or rewriting VP/achievements.
- New matches use `catan-seafarers-s2b-2`. Existing verified S2B-1 and eligible S1 markers remain unchanged; unknown provenance stays F2-restricted.
- Until secure playable projection/frontend exists, public selection/start, gameplay/legal/snapshot publication, debug tools and Qt conversion/save/load reject fog. Internal trusted construction, explicit engine/probe execution and native-current persistence fixtures are permitted as described above.
- Existing COMMIT-before-publication/ACK, F1 ownership and account/guest Continue semantics remain.

## Historical verification — S2B-2B.1

Verified **2026-10-09**:

- **Full pytest: 1003 passed, 0 skipped, 142.31 s**, using a separate disposable PostgreSQL 17 database initialized with existing migrations and real PySide6 offscreen paths. No production database, new migration, historical-data conversion or runtime service deployment was used.
- **93 new fog cases** in four files: typed configuration/masks/ledger/continuation, exact pools/private RNG/visible-only setup/coasts, invalid recipes/indices/snapshots/transitions, all 12 ordinary presets, frozen historical schemas, JSON v4 round-trip and disabled command paths.
- Real WS two-client selection/start refusal, safe error payloads, ordinary Base start, injected trusted fixture command/debug/rematch/publication fences. This is handler acceptance, not a playable fog browser match.
- Real PostgreSQL COMMIT/fresh Coordinator restores both recorded and pending trusted histories without gameplay execution; reconnect/account Continue/claim/takeover retain ownership but expose no private frame, timers remain inert and old heads/participants/results remain unchanged. Historical S2B-1 v3/Base/Seafarers markers continue unchanged and later accepted commands use writer v4.
- Real Qt conversion refusal, save preserving an existing file and load preserving current game/file; ordinary Base/F3/scenario save/load regressions remain green in full pytest.
- F1 private publication, F2 unknown marker/metadata-only fences, Largest Army and prior Base/Seafarers tests included. Initial full run found unordered SQL row comparisons in a shared test helper; full records now compare by actual participant and composite receipt primary keys, without weakening contents. Explicit Largest Army historical v3 coverage is retained alongside v4.
- **Web tests: 253 passed, 0 skipped; TypeScript passed**. Frontend/runtime/assets were not changed; production build/Docker/browser were not rerun for this foundation.

At that foundation checkpoint the scenario harness was not rerun; its historical S2B-1 baseline was **348/508**, with **140 pre-roll** and **20 pirate connectivity** failures. The S2B-2B.2A rerun above confirms the same baseline. The separate Largest Army harness tied-holder limitation remains known broken.

## Exact implementation files

Historical foundation runtime: `app/engine/{state,scenario,exploration,maps,rules,legal,serialize}.py`, `app/match_rulesets.py`, `app/persistence/{snapshots,repositories}.py`, `app/auth/routes.py`, `app/server_mp.py`, `app/test_tools.py`, `app/ui_v6.py`. S2B-2B.2A runtime changes only `app/engine/{exploration,rules,legal,scenario}.py`, `app/match_rulesets.py`, `app/persistence/repositories.py`. No SQL migration/React/Board3D/preset/GLB/audio/deployment changes.

Current S2B-2B.2A tests: new `tests/test_fog_exploration.py`, `tests/test_fog_exploration_recovery.py` and strengthened existing `tests/test_fog_feature_gate.py`. Historical foundation tests: `tests/test_fog_foundation.py`, `tests/test_fog_feature_gate.py`, `tests/test_fog_recovery.py`, `tests/test_fog_desktop.py`; historical writer/version regression updates in `tests/test_persistence_snapshots.py`, `tests/test_match_rulesets.py`, `tests/test_seafarers_scenarios.py`, `tests/test_seafarers_recovery.py`, `tests/test_seafarers_scenario_recovery.py`, `tests/test_largest_army.py`, `tests/test_largest_army_recovery.py`.

Current documentation: this plan; `Project State.md`, `Architecture Decisions.md`, `Состояние игры.md`, `Сервер и протокол.md`, `Карты и сценарии.md`, `Инварианты движка.md`, `Игровой движок.md`, `Карта файлов.md`, `React интерфейс.md`, `Правила Seafarers.md`, `00 Главная.md`, `plans/README.md` under `docs/obsidian/`. Foundation also updated `Desktop клиент.md`, `plans/persistence-auth.md` and `plans/seafarers-s2b-1.md`; those files are unchanged in S2B-2B.2A. Historical ADR/checkpoint evidence is preserved with superseding scope.

## Next stage

Future phases must provide allowlisted personalized board/event projection that never exposes unknown assignments, public legal/protocol acceptance, SVG/Board3D fog rendering and frontend discovery/Gold UX. Two-client raw-payload/ownership/reconnect acceptance is required before public activation. S2B-2B.2A supplies only the internal engine/reward/continuation and probe isolation; it does not start those next phases or remove any public gate.
