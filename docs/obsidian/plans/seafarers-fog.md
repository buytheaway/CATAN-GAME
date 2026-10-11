---
tags: [catan, plan, seafarers, fog]
updated: 2026-10-12
---

# Seafarers fog — foundation, exploration and secure projection

[[Project State]] · [[Architecture Decisions]] · [[Карты и сценарии]] · [[Состояние игры]]

## Scope and status

S2B-2A design is approved. S2B-2B.1 was completed/tested 2026-10-09 and checkpointed in `0fa8f6d`. S2B-2B.2A internal exploration engine was completed/tested 2026-10-12 and saved as **`1b41360` — `feat: implement authoritative fog exploration and rewards`** by the user's explicit checkpoint authorization before this phase. Exactly its 22 implementation/test/doc files were staged; Obsidian graph preferences were excluded and staged whitespace check passed. No tag was created.

**S2B-2B.2B secure internal projection/protocol hardening is implemented/tested 2026-10-12; READY FOR CHECKPOINT in this limited scope.** Public availability remains **DISABLED**; the complete Fog feature is **partially implemented**. Pure helpers prepare public-shaped data without an enabled endpoint. Frontend/SVG/Board3D support, explicit public integration and final security acceptance remain future work. Existing presets/rules/codec/deployment/assets are unchanged. No S2B-2B.2B commit/tag is created automatically; unrelated graph preferences remain untouched.

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

## Secure projection — S2B-2B.2B

Authorized/implemented/tested **2026-10-12**. [public_projection.py](../../../app/engine/public_projection.py) owns closed JSON field/type lists. `serialize.project_fog_player_dict(game,pid)` validates a trusted state and uses shared personal filtering; server `_project_fog_snapshot(room,pid)` requires the native-current marker, attaches existing isolated known-terrain legal hints and forces test_mode/test_tools false. Neither helper is a public caller, authorizer or persistence format. Default to_dict/to_player_dict/_snapshot_state/private publisher still reject Fog; no WS/HTTP/client trusted_fog field can opt in.

- Tiles contain exactly original `index,q,r,center,visibility,terrain,number`; unknown content is fog/null/hidden, including game_over. Initial known and discovered contents are shared. Geometry/occupancy/figure/initial visible ports retain existing IDs; no hidden coast/island classification or regeneration.
- Map metadata allows string id/name/description; config allows 11 approved typed fields. Safe scenario exposes only disabled island rules, profile, empty home/award maps and shared visibility. Assignment digest/mask/pools/seed/RNG/ledger/continuation/future choice details are omitted. Room map/preset/config fields also use typed allowlists; nested content under an otherwise approved key is dropped. Recent/Active JSON map-name queries retain native JSON type, and safe_game uses Unknown map for non-strings.
- Own hand/cards, opponent public counts/active visible VP/final total VP and entitled pending Gold retain established privacy. Fog queue is own-only. Visible bank keeps ADR-005's accepted casual inference tradeoff; Hidden omits exact counts. The guarantee is no undeclared hidden assignment/hand/choice field, not protection from deductions using public counts.
- Legal hints reuse known-terrain apply_cmd probes; equivalent pre-discovery errors/pending/dev-card targets cannot reveal actual hidden land/sea/token. Probes remain mutation-free; there is no second rules engine or cost/placement policy in serialization.
- Gameplay history has closed event kinds/public/private/nested fields. Unknown/Fog-debug/future hidden-tile records are omitted. Accepted command precedes ordered `discover_tile` facts containing actor/original tile/public terrain/number and reward none/resource/gold_choice quantity 0-or-1. Gold choice resource is omitted; later choose_gold composition is actor-private. Discovery facts are not rewritten later; history stays bounded to 80.
- Real ordering stays room lock → detached engine candidate → append accepted facts → PostgreSQL COMMIT/receipt → promotion → F1 private publication/ACK. `_broadcast` rejects match_state before sending; every private send still needs the existing current ownership/session/controlling-socket checks. Rejected commands, pre-COMMIT failures and duplicate lost-ACK retries cannot append extra facts/rewards.
- All outbound surfaces were inspected: personal/default serializers, Room/match/map/scenario metadata, legal/figures/routes/dev/pending/errors, event/log/chat DTOs, Recent/Active, game_over, reconnect/Continue/claim/takeover, rematch/start, debug/Test Mode, timers and spectator-like/generic publication. Exact audit/result table — [[Сервер и протокол#Secure internal fog projection — S2B-2B.2B]]. Public creation/execution/legal/publication/debug/timer/Qt remain closed even for host/current marker/finished state.

Codec v4/3, Room v1, immutable marker and v1/v2/v3 readers are unchanged. Normal recovery restores assignment/history/events/choices without rules/RNG/discovery/reward/VP reconciliation. No SQL migration, conversion or RAM fallback.

## Verification — S2B-2B.2B

Verified **2026-10-12**:

- **Full pytest: 1159 passed, 0 skipped, 162.15 s** with separate disposable PostgreSQL 17 and offscreen Qt, in ignored `.venv/test-artifacts`. Full existing Base/Seafarers/Largest Army/S1/F1/F2/F3/codec/recovery regressions included; no production DB/service/migration. **Web: 253 passed, 0 skipped; TypeScript check passed.** Build/Docker/browser were not rerun: frontend/dependencies/assets/deployment unchanged and playable Fog disabled.
- **74 new cases**, [test_fog_projection.py](../../../tests/test_fog_projection.py) 63 and [test_fog_projection_recovery.py](../../../tests/test_fog_projection_recovery.py) 11. After full run, four existing dev-card counterfactual cases were strengthened to include real committed nonempty history with equal display time; final focused run **74 passed, 23.75 s**, no further runtime changes. Existing .2A event/rejected-choice assertions were adjusted to require the exact added discovery sequence and unchanged complete history after rejection.
- Two tests first reproduced raw nested metadata/event payload passthrough with synthetic sentinel values. Typed field projection now removes undeclared keys, including nested values under allowed-looking keys and native SQL map-name objects. No credentials/user private hands were inspected or printed.
- **25 counterfactual cases**: five hidden terrain/token alternatives × main/setup/robber/free-action/pending states, for both player recipients including host. Each alternative validates as an encodable trusted v4 state. Complete snapshots/legal/Room metadata/events/pending match; live state remains unchanged. Eight invalid-command equivalence cases, four pending-Gold errors and four real Knight/Road Building/Year of Plenty/Monopoly command+event pairs extend the check. Land/sea and number differences become visible only after legitimate discovery; other unknown tiles remain masked.
- Real PostgreSQL recovery covers pending setup road/ship, paid road/ship and free road; recorded per-recipient projection/events survive fresh Coordinator, reconnect, rejected choice, duplicate route/choice and lost ACK. Injected before/after-COMMIT faults verify no premature publication, stable committed history and no duplicate awards. No rules execute on restore.
- Expired/revoked durable guests and controlling-socket takeover cannot publish a prepared Fog frame or execute a forged trusted_fog command. Guest claim/account Continue preserves ownership and private-state gates; Recent/Active returns safe metadata even with a synthetic nested map-name value. Existing F1/account-session and unknown-marker regressions remain green in the complete suite.
- **Scenario suite: 348/508**, same eight failing IDs/160 historical failures: 140 pre-Roll command failures and 20 `no legal ship edge found` in scenario_seafarers_pirate_move. No harness/assertion changes; only report output redirected to ignored artifacts. Largest Army historical harness tie limitation remains separate/known broken.

## Historical verification — S2B-2B.2A

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
- Until secure frontend/public integration and activation acceptance exist, public selection/start, gameplay/legal/snapshot publication, debug tools and Qt conversion/save/load reject Fog. Internal trusted construction, explicit engine/probe execution, pure safe projections and native-current persistence fixtures are permitted as described above.
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

Current S2B-2B.2B runtime: new `app/engine/public_projection.py`; changed `app/engine/serialize.py`, `app/game_events.py`, `app/net_protocol.py`, `app/server_mp.py`, `app/persistence/inspection.py`, `app/persistence/repositories.py`, `app/auth/routes.py`. Only read-only inspection SQL in repositories/auth changes; codec/recovery/commit/ruleset/engine rules are untouched. No SQL migration/React/Board3D/preset/GLB/audio/deployment changes.

Current tests: new `tests/test_fog_projection.py` and `tests/test_fog_projection_recovery.py`; exact discovery history/rejected-choice update in existing `tests/test_fog_exploration_recovery.py`.

Current documentation: this plan; `Project State.md`, `Architecture Decisions.md`, `Состояние игры.md`, `Сервер и протокол.md`, `Карты и сценарии.md`, `Инварианты движка.md`, `Игровой движок.md`, `Карта файлов.md`, `React интерфейс.md`, `00 Главная.md`, `plans/README.md` under `docs/obsidian/`. Rules notes and AGENTS.md are unchanged: no gameplay/policy change. Historical ADR/checkpoint evidence is preserved with superseding scope.

Historical foundation runtime: `app/engine/{state,scenario,exploration,maps,rules,legal,serialize}.py`, `app/match_rulesets.py`, `app/persistence/{snapshots,repositories}.py`, `app/auth/routes.py`, `app/server_mp.py`, `app/test_tools.py`, `app/ui_v6.py`. Historical S2B-2B.2A runtime: `app/engine/{exploration,rules,legal,scenario}.py`, `app/match_rulesets.py`, `app/persistence/repositories.py`; tests: new `test_fog_exploration.py`, `test_fog_exploration_recovery.py`, strengthened `test_fog_feature_gate.py`. Historical foundation tests remain `test_fog_foundation.py`, `test_fog_feature_gate.py`, `test_fog_recovery.py`, `test_fog_desktop.py`, plus explicit historical codec/ruleset/Seafarers/scenario/Largest Army version coverage. Foundation and .2A documentation changes are preserved in their checkpoints; they are not counted as new .2B work.

## Next stage

Future work: SVG/Board3D Fog rendering and typed frontend discovery/Gold UX, deliberate integration of the prepared projection/events into authorized endpoints, then two-client raw-payload/ownership/reconnect/game_over acceptance before public activation. Public legal/execution/debug/timer/Qt policy must be separately accepted and checked; current helpers do not remove any gate. Internal 1159-test readiness is not playable Fog readiness. No next phase is started automatically.
