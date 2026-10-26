---
tags: [catan, архитектура, adr]
updated: 2026-10-26
---

# Architecture Decisions

## ADR-026 — Pinned account Test Mode preference

Status: **Authorized and implemented, 2026-10-26; verification and limits — [[Project State]].** Extends the historical server-only opt-in in ADR-005; no generic admin role.

The existing enabled local account `buytheaway` was inspected read-only and pinned by immutable `users.id = 9ceeeab2-9d25-4e67-84f7-3bb09e4914c6`. Username, display name, guest name, client pid and HTTP/WS payloads cannot assign this capability. A different database/account with the same name has no access. Migration `owner01` adds default-false `users.test_tools_enabled`; no lookup/backfill, credential change or auto-provisioning. Missing account/preference/database fails closed; no RAM fallback.

The cookie-authenticated owner may POST the strict boolean preference to `/api/auth/test-mode`, under existing Origin/session checks. Home/lobby/match account controls show an always-visible ON/OFF switch only when the server identifies that owner. ON permits the existing explicit pre-start **Enable Test Room** flow; it never changes an ordinary match. Tool execution still requires a Test Room, its account-owned host seat, current controller/session, valid epoch/sequence and non-Fog state. OFF overrides the developer flag for this owner. Other local developer hosts retain `CATAN_ENABLE_TEST_TOOLS=1`; they never gain the owner toggle.

Privileged candidate COMMIT rechecks the durable preference under PostgreSQL SHARE locks; the toggle UPDATE requires exclusive locks. A command commits before OFF, or OFF wins and the detached candidate is discarded with a final rejected receipt. No already-issued packet can be recalled. Private publication independently retains F1 ownership/session checks and reads the current capability under its authorization locks. Open owner sockets receive refreshed capabilities/personal state; ordinary Roll ignores a saved forced die while permission is OFF. Tools cannot act on normal/opponent rooms, and Fog remains disabled for Test Tools.

Preference survives logout/login/restart independently of room snapshots. Existing Test Room policy is retained: excluded from Active Games and automatic startup restoration, not deleted; refresh/Continue works while the room remains live. This feature does not implement persistent test-room discovery, historical conversion or gameplay rules. [[Сервер и протокол#Owner Test Mode toggle]], [[Deployment#Owner Test Mode]], [[React интерфейс#Owner Test Mode]].

## ADR-025 — Explicit custom Fog beta admission and emergency stop

Status: **Authorized and implemented, 2026-10-18; acceptance verified; results and limits in [[Project State]].** Supersedes ADR-018's blanket production availability restriction only for the new, explicitly admitted beta provenance. Historical internal CURRENT-marker fixtures retain their closed production behavior; their test capability is not a production authorization mechanism.

Decision: [fog_beta.py](../../app/fog_beta.py) owns the detached canonical recipe/closed descriptor and strict deployment policy for **`seafarers_fog_beta_2`**: exactly two players, shared-preassigned exploration, target 12, discard 7, no ports/island VP, no turn timer, Test Mode or Qt support. Selection accepts the server ID only, never client-uploaded Fog configuration. The ordinary host/seat/session/controller checks, room lock, detached candidate, shared engine, durable receipt/COMMIT and F1 per-recipient publication remain authoritative. Fog-specific rematch requires a finished result and fresh admission.

**New admission and existing gameplay are separate controls.** `CATAN_FOG_BETA_ADMISSION=0` is the default; it hides/refuses new selection/start/rematch while allowing already verified beta matches to continue. `CATAN_FOG_BETA_EMERGENCY_STOP=1` pauses existing gameplay/private publication as well as new admission; default `0`. Only literal `0`/`1` are valid deployment values. These are server settings, not client identity, network flags or ownership credentials.

New matches receive immutable **`catan-fog-beta-1`**, independently of snapshot format. Compatibility validates the saved canonical profile/count/visible board/hidden unordered pools and recorded Fog history without running gameplay; emergency stop adds `reason:"fog_beta_paused"`. Admission-off alone does not change compatibility. Unknown/legacy/internal markers cannot inherit beta authority. Existing metadata-only reconnect/Continue/claim may preserve paused matches without rewriting their head/results; commands, rematch and timers cannot mutate them.

Writer **v4 / engine compatibility 3** and historical readers are unchanged; no SQL migration, backfill, historical VP/achievement reconciliation or conversion. Recovery restores committed assignment/ledger/Gold state exactly. Normal rematch is the only operation generating a fresh assignment/opening. A v4-capable older build must F2-restrict the unknown marker; a pre-v4 build is not a supported rollback target. Stop admission first for a routine rollout reversal, use emergency stop for a gameplay halt, retain all database data, and resume with the compatible build rather than rewriting old heads.

Consequences: one deliberately limited **custom** beta, not official Fog Islands or broader competitive/player-count certification. SVG/Board3D/controller/Gold UX are reused. F1/F2, COMMIT-before-ACK, idempotency, room quotas/closure and non-Fog scenarios remain constraints. Exact configuration/rollback — [[Deployment#Fog beta deployment controls]]; scope/testing — [[plans/seafarers-fog#Public Beta Phase 1 — authorized implementation, 2026-10-18]]. Dated ADR-018 descriptions below preserve the older checkpoint and are superseded only as stated here.

## ADR-024 — Canonical Four Islands using the existing personal island ledger

Status: **Implemented in authorized Official Seafarers S3B scope, 2026-10-16.** Final verification and limits — [[Project State]]. ADR-023 remains valid for New Shores; this decision adds a separate scenario profile.

Decision: register `seafarers_official_four_islands_3` / `_4` from the Fifth Edition 2021 printed pp.11–13. The two illustrated boards require exactly 3/4 actually connected participants. Opening settlements may be on any island: the player's one or two accepted opening islands become personal home islands. The existing ledger awards +2 once for the first main-phase settlement on each other island, independent of opponents; ordinary own-turn victory uses target 13. No additional gameplay executor or score calculation is introduced.

Selection/construction authenticates the full canonical recipe and typed official identity, preserving original IDs and fixed harbor anchors. Public metadata admits only the two new fixed registry descriptors, retaining the closed projection. Official target/discard constraints are read from the verified recipe (13/7 here, unchanged 14/7 for New Shores); client settings cannot override them. Standard ships, movement, routes, robber/pirate, costs and supply are shared unchanged. Optional variable layouts are outside S3B.

New Four Islands matches receive durable immutable **`catan-seafarers-s3b-four-islands`**, independent from snapshot format. Compatibility verifies the recorded family/variant/count, frame opt-in, unrestricted opening policy, +2 bonus and 13/7 settings. S3A and older markers cannot silently resume this profile. Existing matches retain their provenance; no migration, backfill, historical score/achievement reconciliation or classification by codec is performed.

Writer **v4 / engine compatibility 3** already stores materialized boards, personal homes/awards, VP and ship-turn history. Recovery restores these records without reading today's map recipe or invoking gameplay. Rematch checks the exact currently connected count, creates a new epoch/S3B marker and empty personal ledger, preserving the finished result. Rollback to binaries unaware of this marker must restrict S3B matches; there is no downgrade or older-head fallback. F1/F2, COMMIT-before-publication/ACK, durable receipts and public Fog DISABLED remain required. [[Карты и сценарии#Official The Four Islands — S3B]], [[Состояние игры#Official scenario persistence — S3B]].

## ADR-023 — Canonical official New Shores boards and sea-frame provenance

Status: **Implemented, authorized Official Seafarers S3A scope, 2026-10-13.** Verification and limits — [[Project State]]; source/layout — [[Карты и сценарии#Official Heading for New Shores — S3A]].

Decision: register separate canonical `seafarers_official_new_shores_3` / `seafarers_official_new_shores_4` boards from the Fifth Edition 2021 printed pp. 8–10. Required actual participant counts are exactly 3/4; setup uses main component 0, existing per-player/per-island ledger awards +2, victory target is 14 on the player's turn. Selection clears inherited target/discard overrides; subsequent contradictory target/discard settings reject. Official IDs/markers alone are not trusted: new selection/construction compares the entire supplied recipe against the shipped canonical source. Existing four custom presets retain their original data and policy.

The two complete printed frame sea positions are materialized as ordinary sea tiles after the 35/42 loose components. Explicit `rules.sea_frame=true` permits shipping on singleton graph edges bordering the physical inner sea frame. No arbitrary sea halo or paths on the unprinted outer frame are generated. This opt-in is a new execution capability, rather than another game's scoring model.

New official matches therefore receive durable immutable **`catan-seafarers-s3a-new-shores`**. Base/custom new matches retain **`catan-seafarers-s2b-2`**; existing verified S1/S2B-1/S2B-2 provenance remains unchanged. Older/unknown markers cannot silently execute sea-frame state. S3A compatibility checks recorded identity, exact count/metadata, frame flag, starting region, bonus, target and discard threshold without reconstructing the board or recalculating gameplay. Current-ruleset metadata identifies the applicable family; snapshot version alone never establishes provenance.

Codec **v4 / engine compatibility 3** already stores raw rules, materialized board/ports and island ledger; no new GameState field, SQL migration, historical backfill or score/achievement conversion is needed. Recovery restores committed data exactly, never reloads today's preset or executes rules. Rematch creates a fresh epoch and empty ledger and rechecks connected count. Older binaries do not know the S3A marker and must restrict those matches rather than resume them. F1 publication ownership, F2 restriction, durable receipts/COMMIT-before-ACK and public Fog DISABLED remain constraints.

Scope: fixed illustrated terrain/token layouts; harbor anchors fixed and types shuffled under general Seafarers setup (pp.3/7). Optional variable layouts, official scenarios 2–9 and a physical cardboard-frame renderer are not implemented. The pp.8/9 three-player robber/pirate typo is documented explicitly in the map note.

## ADR-022 — Explicit host-owned pre-match lobby closure

Status: **Accepted within authorized Room Lifecycle Phase 1; implemented/focused-tested 2026-10-12.** Supersedes ADR-021's historical lack of a public Close action, not its conservative retention or quota policy.

Decision: expose a correlated `close_room` intent only for a never-started lobby. Require current controlling-socket ownership and host identity, then revalidate durable account session/membership or guest credential inside the closure transaction. Room lock protects takeover/start/join races; the same PostgreSQL advisory lock as room creation serializes quota release with admission. The DB guard checks status, revision, host, epoch and absence of current or historical matches. No client-supplied pid/user/name is an authorization proof.

COMMIT atomically records `closed`, `closed_at`, revoked guest credentials and a bounded operation receipt. Only then fence RAM/controller bindings and send public `room_closed`; no game state is disclosed. Startup excludes closed rooms. Closed never-started metadata can be hydrated only to resolve uncertain COMMIT, never reopened or mistaken for a corrupt match. No gameplay rules, historical snapshot conversion or new SQL migration.

The host confirms **Close Lobby** in React; Home/Continue is refreshed and the closed guest binding is removed. Closing a tab or Back to home only disconnects and retains ownership. Explicit closure releases concurrent IP/global lobby reservations, but does not refund the rolling accepted-creation rate. Repeated closure is safely refused without another write; lost notices cannot reauthorize revoked credentials. Active/finished matches are outside this operation. No automatic expiry, deletion, surrender or account logout is introduced. Details/evidence — [[Сервер и протокол#Explicit lobby closure — Room Lifecycle Phase 1]], [[Project State]], [[Deployment#Room creation admission — SEC-03]].

## ADR-021 — Durable room admission, conservative lobby retention

Status: **Accepted within authorized SEC-03, implemented/focused-tested 2026-10-12.**

Decision: admit new rooms using configurable accepted-creation rate per canonical ASGI IP, concurrent lobby capacity per origin and total durable lobby capacity. Reuse SEC-04's exact proxy trust; IP is an abuse budget, never an identity/ownership proof. Guests and accounts on the same network share that budget. Store only an internal SHA-256 origin digest and the existing creation timestamp; the digest is not anonymization or a credential and must never enter public DTOs. Legacy origins remain NULL, still counting toward global capacity.

In durable mode, a PostgreSQL transaction advisory lock serializes quota checks across admission callers; check before allocating Room/seat/credential, then insert using that same transaction. COMMIT precedes registration/binding/publication. Rejection performs no write and does not disable persistence. Read authoritative DB metadata rather than creating a RAM fallback or an unbounded IP cache; accepted budgets survive reconnect/restart. Single-worker gameplay architecture remains unchanged. Explicit memory mode uses a bounded, expiring accepted-creation deque and refuses when full instead of evicting live budgets.

No automatic expiration/deletion: disconnect is not abandonment; valid guest credentials and account seats must remain recoverable. Active and finished matches/snapshots are never cleanup targets. Safe never-started expiry requires a separate product/lifecycle policy and transaction proving absence of match history and recoverable ownership, then explicit expired status without deleting historical data. It is **deferred**, not implemented. Defaults, capacity exhaustion and NAT/IPv6 limits — [[Deployment#Room creation admission — SEC-03]], [[Сервер и протокол#Room creation quotas — SEC-03]]. Existing ADR-012 recovery/F1/F2 constraints are preserved.

**Historical SEC-03 checkpoint lifecycle verification, 2026-10-12:** ordinary legitimate create/leave could exhaust persistent lobby capacity indefinitely. Start Match released a reservation; the internal explicit-close helper had no public/admin entry point and was unsafe as an indiscriminate active-room sweep. ADR-022 subsequently adds safe user-authorized pre-match closure. Credential expiry and elapsed room expiry timestamp still do not change the admission predicate `status="lobby"`; automatic retirement remains deferred.

## ADR-020 — Exact reverse-proxy peer trust for abuse limits

Status: **Accepted within authorized SEC-04, implemented/focused-tested 2026-10-12.**

Decision: authenticate proxy identity at Uvicorn's ASGI boundary; trust only the reserved web address on a dedicated Compose proxy network. Nginx overwrites forwarding with its actual client peer. Reserve backend's separate address too to prevent startup allocation collisions. Keep PostgreSQL on the original default network/volume, with no backend/DB host ports. Local module startup and standalone image use empty trust. Never use `*` or a whole Docker subnet as a convenient fix.

Auth reads canonical ASGI IP for its unchanged per-peer/global budgets; it does not interpret client forwarding or use IP as session/seat identity. IPv4/IPv6/NAT/global-cap/single-worker limits and extra upstream proxy policy are explicit in [[Deployment#Trusted proxy and auth budgets — SEC-04]]. Existing cookie/Origin and persistence/publication ADRs remain unchanged. **Historical SEC-04 scope:** no distributed limiter or SEC-03 quotas were introduced by that fix; subsequent room admission is ADR-021.

## ADR-019 — Corrective theft and shortage execution, unchanged ruleset family

Status: **Accepted within the authorized B1/B2 correctness fix, implemented/focused-tested 2026-10-12.**

Decision: use server-owned, card-weighted secure theft and the official aggregate bank-shortage policy for **future accepted commands**. They enforce the already approved Base/Seafarers rules rather than introduce new scenario mechanics, state/value domains or achievement formulas. Therefore this focused patch does **not** require a new gameplay compatibility marker: new matches keep `catan-seafarers-s2b-2`, existing verified-compatible S1/S2B-1/S2B-2 matches keep their original immutable marker. The marker identifies an approved rules family, not a claim that historical binaries had no implementation bugs. Existing S1 scenario constraints and unknown/Fog compatibility restrictions are unchanged.

Recorded resource hands are primary persisted history and cannot safely be reconstructed from today's board. Neither recovery nor this patch recalculates historical theft/production, VP/achievements or finished results. No snapshot/schema version, database migration, provenance backfill, dual engine or automatic conversion is needed. Snapshot v4/3 and released historical readers remain. F2 Strategy C still protects unknown provenance; Strategy D remains future explicit maintenance, not implemented here.

RNG is a private execution dependency independent of map seed; internal tests and isolated legal probes may inject it, but no client payload or persistence codec can do so. A committed random outcome is recovered through exact hands/events and durable receipts. Failed pre-COMMIT execution may discard its draw; after COMMIT/lost ACK/uncertain response, the recorded outcome must be reused without another execution. Candidate/COMMIT/publication and F1 recipient checks remain constraints.

Rollback: these snapshots have no new format requirements, but restoring an older buggy binary reintroduces biased theft/order-dependent future production; it must not be presented as equivalent gameplay. Historical accepted outcomes are preserved in either direction, never reconciled automatically. Evidence/limits — [[Игровой движок#Random theft and bank shortages — B1/B2]], [[Состояние игры#Theft/production persistence — B1/B2]], [[Project State]].

[[00 Главная]] · [[Project State]] · [[Documentation Policy]]

Основание: архитектурные ограничения из предоставленной пользователем инструкции и спецификации правил. Accepted обозначает принятое направление, а не утверждение, что реализация полностью соответствует ему.

## ADR-018 — Trusted fog foundation with public feature disabled

**Historical foundation/internal-integration decision; production availability partially superseded by [[#ADR-025 — Explicit custom Fog beta admission and emergency stop]] on 2026-10-18.** The dated statements below retain their checkpoint context. Their privacy, single-engine, immutable assignment, pure recovery and private test-capability constraints remain accepted. Only the new canonical beta marker has a separate production admission policy; old internal matches stay closed. The natural follow-up is now published as `93439ef`; its activation proposal was design-only then, rather than an unimplemented current decision.

**Natural-match follow-up, 2026-10-17; test-only, public DISABLED:** published .3B is `d6f94a1`. Whole two-player Fog play now starts at the original builder's empty opening and uses the actual dispatcher/engine/COMMIT/receipt/F1 publisher through victory and fresh rematch. Only the guarded test launcher admits its privately bound native room through lifecycle feature/Repository fences; ContextVars confine admission to that original transaction. It never authorizes another room/unknown provenance, supplies gameplay resources/scores/occupancy, or changes recovery. Normal startup installs no admission/capability, including with a valid account cookie or forged Fog environment/client fields. This does not approve a production policy, a new ruleset or public activation. Actual final counts/browser evidence and limits — [[Project State]], [[plans/seafarers-fog]]. The plan's proposed public-release marker and rollout phases are **design proposals, not implemented decisions**.

**S2B-2B.3B follow-up, authorized/implemented 2026-10-16; public DISABLED:** existing pure projection/exploration is now connected to the real dispatcher/candidate/COMMIT/receipt/F1 publisher for explicitly scoped internal fixtures only. `FogMatchAccess` is an immutable Python room UUID/match UUID capability requiring native current provenance, non-Test-Mode and valid Fog state. Only the guarded isolated test process installs it; no network/env/DB/marker/restore opt-in. The capability never replaces seat/session ownership and is rechecked at private publication. Default production entrypoint, HTTP summaries, public selection/start/rematch/timers/debug/Qt and ordinary serializers stay gated. No codec/ruleset migration, historical reconciliation or rule execution during recovery. Test recovery explicitly rebinds the fixture capability after pure restoration. Real serialized counterfactuals, authority/idempotency/rollback, F1 ownership/logout ordering and Chrome refresh/restart/renderers verify this internal scope; actual final suites and limits — [[Project State]], [[plans/seafarers-fog]]. Public activation and broader natural Fog acceptance require separate authorization.

**Historical S2B-2B.3A follow-up, authorized/implemented/fixture-tested 2026-10-12:** React SVG/Board3D accepts only the prepared public tile/event shape. Unknown/invalid tiles have uniform Fog presentation and no actual terrain GLB/number/resource/userData/coast inference; original IDs/coordinates and authoritative legal lists remain. Finite reveal follows new committed ticks with refresh/reconnect baselines, never runs rules or delays state. Discovery text/personal Gold modal read public facts and existing pending choices; frontend reward/hidden assignment models are prohibited. 269 web/TS/build, 105 relevant PG-backed Python and 13 public-fixture Chrome groups verified that presentation scope. .2B checkpoint is `dc121da`; .3A did not change any backend gate or authorize public play. Live endpoint acceptance was future .3B at that checkpoint and is now implemented above in internal scope. Historical .2A/.2B constraints remain intact. [[plans/seafarers-fog]], [[React интерфейс#Public Fog presentation — S2B-2B.3A]].

**S2B-2B.2B follow-up, authorized/implemented/tested 2026-10-12:** pure internal `project_fog_player_dict` / `_project_fog_snapshot` produce allowlisted public-shaped personalized data; neither is a public endpoint nor an authorization/restore mechanism. Unknown tile content is masked even game_over, shared revelation uses original IDs, private assignments/digest/ledger/continuation/island internals are omitted. Public metadata accepts only approved primitive fields; legal projection probes the existing known-terrain executor. Counterfactual valid v4 land/sea/token assignments have equal snapshots/legal/metadata/events/errors/pending until accepted discovery.

Outbound Room metadata and gameplay events now use closed typed field lists. Unknown/nested payload fields and future/debug/unknown-tile Fog events are dropped; `discover_tile` contains only an already-revealed ID/terrain/number and public reward summary, never the chosen Gold resource. Events are appended to the detached candidate, committed with it, then promoted before publication. `_broadcast` refuses `match_state`; private publication must keep the F1 recipient/ownership/session/controlling-socket checks. Recent/Active JSON map names are read without JSON-to-text coercion and only string names reach the safe DTO. Default serializer/snapshot/WS/HTTP/debug/timer/Qt Fog gates stay **DISABLED**. Codec v4/3, provenance, historical schemas, rules and pure recovery do not change. Existing Visible-bank inference tradeoff in ADR-005 remains accepted; field privacy is not a promise against deductions from publicly visible counts. Evidence: 1159 Python/253 web/TypeScript, focused 74 cases; [[plans/seafarers-fog]].

**S2B-2B.2A follow-up, authorized/implemented/tested 2026-10-12:** the foundation decision below is retained as historical checkpoint scope (`0fa8f6d`). Internal discovery/rewards/known-terrain execution and Gold continuations now exist. `apply_cmd` and `board_legal_moves` require explicit keyword-only `trusted_fog=True` for internal fog; the default and every public WS/debug/serializer/Qt boundary remain disabled. Accepted routes reveal endpoint-adjacent original IDs once, with durable reward/continuation records; unknown terrain cannot decide placement, production, initial grants or robber/pirate targets. Setup advancement and current-player victory resume once after discovery Gold finishes.

The private commit opt-in is limited to an existing current-marker fog match with unchanged epoch/status/timer and no lifecycle operation; assignment/history and historical-finished-state fences remain. Coordinator/Repository keep the real COMMIT/receipt/promotion/uncertainty path. Unknown provenance cannot opt in; no public handler forwards a client field as this keyword. Codec v4/3, marker and pure recovery remain unchanged. At this .2A checkpoint (`1b41360`) secure projection/events/frontend/rendering were future work; .2B supplies their internal projection foundation and .3A supplies fixture-tested rendering. Public integration/activation remains planned, **public DISABLED**. Evidence and rollback limits — [[plans/seafarers-fog]].

Historical foundation status: **Implemented, authorized S2B-2B.1, 2026-10-09.** Follow-ups above supersede its implementation scope; the constraints below remain accepted. Public fog availability is **DISABLED**. Verification results and limits — [[plans/seafarers-fog]]. This is the approved custom `shared-preassigned-v1` profile, not official Fog Islands draw-on-reveal semantics.

Decision: extend the existing ScenarioRules/ScenarioState with frozen FogRules, FogState, FogDiscovery and FogContinuation records. Actual terrain/number values remain in the single materialized BoardState, with original tile/vertex/edge IDs. Shared discovery uses a revealed subset of initially hidden IDs and one reward record per revealed tile. Stored continuation describes a pending discovery choice but does not execute it. Fog cannot combine with starting_islands or positive island VP bonuses.

Map recipe **version 2** contains visible tiles, `terrain:"fog"` slots and exact terrain/number pools; ordinary maps remain version 1. Trusted build assigns pools once using independent `SystemRandom`, never a public map seed; explicit RNG injection supports deterministic internal tests. Full client-specified hidden layouts and private seed fields are rejected. Initial setup capacity, robber/pirate placement and authored/auto ports use visible territory, without classifying unknown slots as land or sea. Existing presets are unchanged.

Trusted writes use **snapshot_version=4 / engine_compatibility=3**, still 43 GameState fields. Released **v1/1, v2/1 and nested v3/2 schemas are explicit/frozen**, restore fog-disabled structural defaults and retain recorded VP/achievements/scenario history. V4 stores full assignments, mask, ledger and continuation. Pure validation/digest checks do not run rules, award resources, reveal tiles or consume RNG. Assignment immutability is enforced by validation and same-match commit transition fences; mutable Tile is not globally replaced by a second model.

New matches receive **`catan-seafarers-s2b-2`**. Existing verified S2B-1 and eligible S1 non-fog matches keep their marker and remain compatible; NULL/unknown provenance stays F2-restricted. Fog is restricted even under the current marker. Metadata-only Continue/claim/takeover preserves ownership and old heads/results; commands, timers, legal projection, snapshot publication and rematch remain fenced. Active/Recent summaries check both the loaded game and marker. No SQL migration, backfill, automatic conversion or RAM fallback.

Until S2B-2B.2 supplies secure projection/legal/execution, public selection/start, shared apply_cmd, legal hints, UI/network serialization, debug tools and real Qt conversion/save/load reject fog before exposing or mutating trusted data. No match_state is published, including after game_over or reconnect. Internal trusted fixtures may be constructed/committed for testing only; this is not a public creation path. F1 current-recipient authorization and COMMIT-before-publication/ACK remain required.

Rollback: pre-v4 binaries cannot read an advanced v4 head, even for a non-fog match retaining an older marker. No downgrade, older-head fallback, VP/reward reconciliation or Strategy D operation is implemented. Remaining exploration/rewards/known-terrain production/Gold continuation/projection/legal-probe/rendering work is explicitly future scope. **Do not enable public fog merely because its codec round-trip passes.**

## ADR-017 — Explicit scenario state, codec v3 and S2B-1 provenance

Historical S2B-1 writer/marker below, superseded for new writes/matches by ADR-018. Its start/bonus/history, immutable provenance and non-executing recovery constraints remain accepted; v3's nested schema remains frozen.

Status: **Implemented/verified 2026-10-09 in authorized S2B-1 scope.** Existing preset product parameters remain unchanged; generic custom-map opt-in is implemented. No official rules are assigned by preset name.

Decision: `rules.scenario` explicitly configures `starting_islands` (stable component roots, optional/null = unrestricted) and `new_island_vp` (integer 0..10, 0 = disabled). One shared `GameState.scenario` stores immutable ScenarioRules plus per-player home/awarded island sets. Materialized topology stays in BoardState; core costs, route/army/hidden VP and own-turn victory stay in the shared executor. Restricted setup includes a bipartite maximum-matching capacity guard so accepted opening choices leave enough distance-rule positions for the remaining snake order. Unrestricted/Base setup does not use this guard.

Home islands are the player's accepted setup islands, not a reconstruction from current ownership. Only accepted main-phase settlements award the configured extra VP, once per player per non-home island; an opponent's arrival does not consume the award. Cities/further settlements do not repeat it. Total VP is updated once before the existing own-turn check. Public special VP is a breakdown already included in total VP. No development-card disclosure or award on setup.

New trusted writes use **snapshot_version=3 / engine_compatibility=2**, 43 GameState fields; exact released v1/1 and v2/1 schemas remain readable. V3 explicitly stores the scenario ledger and Seafarers offboard -1. References/recorded ledger are validated; no VP, achievements, map or award is recalculated on restore. V1/v2 receive only a disabled structural scenario default, even if old raw map metadata contained previously ignored scenario keys. No SQL migration/backfill and no rewriting old heads just to mark them.

New matches use durable immutable **`catan-seafarers-s2b-1`**. Verified **`catan-seafarers-s1`** matches remain executable only with scenario mechanics disabled, preserving their marker; shared core rules are unchanged, so this does not introduce a second engine or conversion. The commit fence prevents adding scenario mechanics to such a match. An S1 marker paired with enabled scenario state is compatibility-required but retains metadata-only ownership/Continue. NULL/unrecognized markers remain F2-restricted regardless of codec. New rematches have a new epoch/marker and fresh scenario history; old match scores/results are not reconciled.

Reason: raw JSON labels/format version do not establish historical gameplay provenance, and an award ledger cannot safely be inferred from accumulated VP. Additional scenario rules must not accidentally change established custom presets or active S1 matches.

Rollback: pre-v3 binaries cannot resume any head advanced to v3; rolling back the binary alone is insufficient. There is no automatic older-head fallback, downgrade, recalculation or Strategy D operation. Existing S2A v2/-1 records remain readable here but are still incompatible with pre-S2A binaries; that historical boundary cannot be repaired by pretending the records had a different released version. Preserve appropriate backups and compatibility-aware deployment; never deploy a pre-F2 binary to bypass provenance.

Evidence: full **881 Python / 253 web tests**, TypeScript/build, 100 restricted seeded setup runs (2–6), PostgreSQL COMMIT/failed transaction/receipt/restart/reconnect/rematch, actual direct WS refusal and real Qt file round-trip. Real Chrome tested two different explicit custom JSON profiles with natural setup, funded expansion and two-client refresh; no full natural games. Scenario baseline unchanged 348/508. Details — [[plans/seafarers-s2b-1]], [[Состояние игры#Scenario persistence — S2B-1]].

## ADR-016 — Materialized map topology and offboard Seafarers robber

Historical S2A checkpoint: `e79dee4`. Its unchanged codec/ruleset identifiers are superseded for new writes/matches by ADR-017 above; the materialized-board and no-recovery-rule-execution decisions remain accepted.

Status: **Implemented/verified 2026-10-09, authorized S2A scope.**

Decision: new matches use updated named map definitions; persisted matches keep their materialized tiles/order/vertices/edges/adjacency/ports/source and scores. `topology.land_components/island_ids/coastal_edges` derive island/coast identity from that same stored shared-edge graph. Island ID is the minimum original tile index in a land component, deterministic within a board; no second coordinate graph, mutable scenario model or new network/codec field. No discovery bonus or start-island restriction is invented.

New-map ports must be real land↔sea/frame coasts without shared endpoints; authored edge/kind/order remain intact. Auto placement is deterministic and bounded by deck/coast capacity. Existing historical invalid coast placement remains readable during recovery; it is neither silently repaired nor revalidated by rebuilding the map. A separately created match/rematch uses the then-current source definition and normal build validation; restricted F2 matches still cannot rematch.

No-desert Seafarers starts with robber `-1`, as the official FAQ specifies an offboard start. It is presentation/state, never a legal move target; Seven/Knight use the existing single-figure pending lifecycle and land/sea validation. Codec **v2** accepts -1 only for Seafarers robber fields; all other negative references reject. Released **v1 remains frozen**, new writes stay v2/engine_compatibility=1 with 42 fields, and the match marker remains `catan-seafarers-s1`. There is no rules/VP/achievement reconciliation during restore and no classification of unknown markers as current.

Reason: rebuilding a saved map after a preset update changes IDs/topology and destroys persistence meaning. A local render-height/coast transform must not decide legality. An arbitrary initial Gold blocker contradicts approved Seafarers behavior.

Consequences: this is a **v2 value-domain extension**, not a field/schema migration. The new decoder reads historical on-board v1/v2, but an S1 binary rejects new offboard v2 heads despite the same format number; rolling back those records to S1 is unsafe. Do not rewrite a head to make rollback pass. Future releases must document value-domain constraints independently of field coverage and ruleset provenance. S2B needs explicit discovery/start-island scenario state before using these derived IDs for awards; reordering a definition does not preserve cross-definition island identity.

Evidence: frozen S1 fixture and fresh PostgreSQL coordinator preserve the old 19-hex Gold Haven board/source/ports/VP with both current and unknown markers; unknown remains restricted. New maps use 37 tiles. Full Python/web and focused two-client Chrome verification — [[plans/seafarers-s2a]], [[Состояние игры#Seafarers S2A — stored maps and offboard robber]]. Historical ADR-011/014/015 retain their checkpoint context and constraints.

## ADR-015 — Match ruleset provenance and safe legacy restriction

Historical F2 marker assignment: new matches used S1 at that checkpoint. ADR-017 introduced S2B-1; ADR-018 assigns S2B-2 for new matches and supports verified S2B-1/eligible S1 non-fog games without changing their markers. Unknown/NULL restriction, immutable provenance and absence of automatic conversion remain accepted.

Status: **Accepted by user; implemented/verified 2026-10-08, F2 Strategy C.**

Decision: nullable `matches.ruleset_id` is immutable match-level provenance, separate from `snapshot_version`, `engine_compatibility` and GameState.state_version. Only new matches receive `catan-seafarers-s1`. Additive Alembic `f2a001` leaves existing markers NULL, including v2 heads; absent/unrecognized markers require compatibility review. No timestamp, codec version or successful decode establishes S1 provenance.

Recovery decodes v1/v2 without running gameplay rules. Valid restricted matches load as in_match with ownership intact, not quarantined/corrupted. Backend blocks commands before seq/receipt consumption, legal projection, timer processing/resumption and start/rematch. The commit fence prevents rewriting GameState, timer, epoch or snapshot. Metadata-only Continue, guest renewal, account claim, chat and leave remain possible; restricted writes skip match/result/participant upserts, preserving old VP/achievements/winner/final scores. No personalized match_state is published; public room/inspection metadata describes `compatibility_required`.

Reason: pre-S1 road-only scoring, mixed routes and lost incumbent history cannot safely be reconciled merely by decoding. V2 may contain pre-S1 derived scores after an earlier recovery/write. Format compatibility allows reading, not executing current rules.

Consequences: even a genuine S1 match created before the marker existed is restricted without verified provenance. Finished historical results stay unchanged; restricted rooms cannot rematch, but users can retain their seat, return Home and create a separate current match. No automatic conversion, dual engine, backfill or deletion. Strategy D is a possible future **explicit maintenance operation**, requiring a separate decision and transaction/idempotency/rollback design; it is **not implemented**. Do not manually stamp existing matches current. Older backends ignore this gate and must not be used for rollback. Downgrading the column loses provenance; re-upgrade leaves existing matches unknown.

Evidence — [[plans/persistence-auth#F2 — match ruleset compatibility (Strategy C)]], [[Состояние игры#Snapshot format versus match ruleset — F2]], [[Сервер и протокол#Match compatibility gate — F2]]. ADR-014's v1→v2 progression applies only to independently verified current rulesets after F2; unmarked legacy cannot reach End Turn to clear unknown history.

## ADR-014 — Seafarers turn history and codec v2

Historical writer version/count: v2 and 42 fields at S1. ADR-017 advanced to v3/43; ADR-018 advances new writes to v4/43. Historical reading and conservative missing ship-history semantics are preserved.

Status: **Implemented/verified 2026-10-08, authorized Seafarers S1.** Existing full codec v1 remains a frozen released schema; new writes use snapshot_version=2 / engine_compatibility=1, covering 42 GameState fields.

Decision: keep active-player `ships_built_this_turn` (original edge tuples) and `ship_moved_this_turn` in shared engine state. Successful main-phase ship construction records its edge; accepted movement consumes one move; normal turn cleanup clears both. Setup ships do not populate main-turn history. Legal projection probes the same executor rather than reconstructing these restrictions in React.

Persistence validates exact new types, board references and current-player ownership. Strict v1 decode supplies an empty built set and a conservative movement lock for any main-phase Seafarers/movement-enabled save: even an unrolled turn may contain free ships from Road Building. Only normal End Turn resets unknown legacy history. Input is copied; migrations do not rebuild maps, execute rules or guess historical moves. Offline views preserve known fields and conservatively handle missing history; personalized network views remove both fields.

Reason: deriving age/used movement from occupied ships, renderer, socket connection or current dice status permits illegal movement after refresh/restart. Extending released v1 in place silently loses state or rejects valid old checkpoints.

Consequences: no SQL migration, new public field, alternate model or Room lifecycle redesign. Existing atomic commit/rejected receipt/replay/takeover rules remain. Real PostgreSQL fresh-coordinator hydration checks both account and guest ownership, Gold setup anchor, route/VP/privacy and v1→v2 progression. A legacy player may lose an otherwise legitimate move for the remainder of the restored turn; old backend binaries cannot read v2 writes. Full verification evidence — [[plans/seafarers-s1]].

## ADR-013 — Account sessions and durable seat ownership

Status: **Accepted; implemented/verified 2026-10-07, Auth Phase 1.** User authorized accounts/cookie sessions/explicit guest claim/account Continue after `persistence-phase-1c`.

Decision: opaque 256-bit cookie bearer, SHA-256 session hash in PostgreSQL, HttpOnly/SameSite=Lax/Path=/ and Secure by default. Absolute expiry 30 days; last_seen writes throttled to 5 minutes; successful login/register issues a fresh session and revokes the incoming one, logout revokes only the current browser session. Argon2id password hashes with encoded parameters/random salt, baseline 19 MiB/t=2/p=1. No JWT/account framework/email/OAuth/profile/history.

Durable RoomPlayer.user_id determines account ownership independently of match pid. Direct account Host/Join needs no guest token. Claim requires both authenticated session and guest proof, atomically sets ownership and revokes the old guest credential without changing name/pid/GameState. An ephemeral per-connection nonce identifies the requesting current WS; it is not a recovery credential. Matching socket upgrades in place, another controller is fenced. Unique active room/user membership is enforced in runtime and PostgreSQL. Retained rematch participants keep ownership through compact pid; excluded memberships retire.

Reason: one existing commit/RoomPlayer/WS system can support both guests and accounts; cookie sessions give straightforward revoke/logout/restart durability without JWT lifecycle complexity. A nonce prevents a token holder from silently upgrading another browser's live socket to account authority. Session/user share locks during room mutation give logout and in-flight commands a transaction order; every private account publication also rechecks session validity. Same-account verified Continue takes over the seat, with no automatic reclaim loop by the old browser.

Consequences: HTTP mutations require JSON and an exact configured Origin, including login/register/logout/claim; missing/null/foreign origins fail and no permissive CORS is added. Cookie WS checks browser Origin before acceptance. Origin-less non-cookie desktop guests and same-origin plain-HTTP guests remain supported. Production auth requires HTTPS and configured exact HTTPS origins; local HTTP explicitly opts into development mode. Vite proxies both API and WS on the site origin. Account session is never stored in JS/localStorage or put in a URL; existing guest bearer limitations remain. Details — [[Сервер и протокол#Auth Phase 1 — HTTP and WS ownership]], [[Deployment#Account cookies and HTTPS — Auth Phase 1]], [[plans/persistence-auth#Auth Phase 1 — completed 2026-10-07]].

## ADR-012 — Durable commit gate and conservative restart

Status: **Accepted; implemented/verified 2026-10-06, Persistence Phase 1B.** User authorized PostgreSQL durability, stable guest ownership, commit-before-ACK and paused restart policy. Engine/rules remain unchanged.

Decision: one active backend worker/replica keeps committed Room/GameState in RAM; SQLAlchemy 2 async sessions + Alembic + psycopg 3 commit durable aggregates to PostgreSQL. Every command, timer, config/chat mutation, reconnect and lifecycle transition uses the same Room lock. Execute on detached candidate, save head/private runtime/seq/receipt/metadata in one transaction, COMMIT, promote RAM, then personal broadcast/ACK. Failed writes discard candidate. Ambiguous COMMIT requires exact revision/head/receipt lookup; until resolved room is fenced. Never re-roll/re-steal or load an older ACKed head. Final engine RuleError persists consumed seq/receipt only; pre-engine ownership/epoch/gap/no_match failures are unconsumed.

Decision: guest token uses 256-bit secure entropy, DB SHA-256 only, constant-time comparison, 30-day authenticated inactivity expiry, no reconnect rotation. Retained RoomPlayer UUID follows compact rematch pid; excluded/closed members revoked in same transaction. UUID/name/pid/room code are not credentials. **Historical scope at 1B:** account/session identity was future work; it is now implemented by ADR-013, without replacing guest ownership. Start/rematch use additive request_id + expected_match_id, persisted bounded operations; legacy controls without fields remain accepted but cannot express replay-safe rematch intent.

Decision: recovery validates current head and reconstructs exact board/deck/bag/dice/pending/feed/config without generation. Lobby, live and finished rooms load disconnected. Test/closed/expired/abandoned rooms are excluded; corrupt head quarantined, healthy rooms recover independently. Timed matches wait for first valid participant reconnect. For turn/grace, resume remaining = max(20s, min(configured duration, saved UTC deadline minus current UTC)); blocked/stopped preserve meaning. No offline automatic turn chain or automatic mandatory choices.

Consequences: startup Alembic is safe only under the one-worker/replica deployment assumption. Readiness is 503 until DB/schema/recovery ready; failed write/outage blocks mutations, WS emits retryable persistence_unavailable/1013. Recovery reads committed state and forces ordinary verified reconnect after same-process outage. Head + 2 predecessors, receipts 256/participant and operations 256/room are bounded. **Historical exclusions at 1B:** auth/Continue UI were not yet present; guest Continue arrived in 1C and account Auth/Continue in ADR-013. Retention scheduler, backup and multi-worker coordination remain future work. RAM-only dev remains compatible mode; durable Compose never falls back. Historical 1B verification: full pytest 508, web 130, real PostgreSQL/process/Chrome restart and isolated volume retention/deletion. Details — [[plans/persistence-auth#Persistence Phase 1B — implementation and verification]], [[Deployment]].

## ADR-011 — Separate full trusted GameState codec

Status: **Accepted; implemented/verified 2026-10-06, Persistence Phase 1A. Historical checkpoint description below.** Codec remained unchanged in 1B; durable Room adapter uses it. Auth/Continue were unimplemented at 1A, subsequently completed in 1C/ADR-013. Current codec v4/3 and ruleset transition are described in ADR-018, with the compatibility gate retained from ADR-015; released v1/v2/v3 remain readable and immutable.

Decision: full private engine persistence has its own `app/persistence/snapshots.py` surface, separate from existing network/offline serialize.to_dict/from_dict/to_player_dict. Envelope snapshot_version=1 / engine_compatibility=1 contains all shared GameState fields, explicit known dataclass construction and stored materialized geometry; it contains no Room/DB metadata. Restore does not execute commands, generate board or shuffle. Required/unknown fields, primitive types, references and versions fail closed; field-coverage guard prevents silent new engine field loss. v1 is immutable after release; future schemas need explicit version compatibility/migration.

Reason: old serializer omits secrets/counters and old-view equality can hide loss. Extending its network projection base with secrets would risk disclosure. Dedicated JSON/type equivalence, independent objects and original command outcomes prove a usable recovery prerequisite without gameplay/network changes.

Consequences: full payload is never a client projection; 1B coordinator is its private server caller. All 40 GameState fields/nested models covered; pieces/port ownership/property aliases are derived from saved board/rules rather than duplicated. Non-JSON metadata and oversized/deep payloads are unsupported explicitly. Phase 1A verification: 445/445 pytest, including 179 codec cases, all map presets and 50 hex; at that checkpoint engine/server/frontend were unchanged. Room adapter/commit/recovery are now described in ADR-012. Qt save remains separate and retains its older integer-key bug.

## ADR-010 — Durable room state and optional account identity

Status: **Architecture direction approved by user for staged work — 2026-10-06. Historical proposal below, audited at `745d749` / `game-ux-2-3`.** Codec 1A, durable guest backend 1B, guest Continue 1C and Auth Phase 1/account Continue are implemented and tested. Profiles, richer history and password reset remain planned. Current contracts — ADR-012/013/014/015; full rationale/schema — [[plans/persistence-auth]].

Decision proposed: retain one backend worker, Room/RoomManager and shared Python GameState as committed active runtime; PostgreSQL provides durability. Normalize room/seat/account/match identity, metadata, sessions and safe final results; use a separate versioned full trusted GameState codec plus private Room checkpoint data. Candidate execution → DB transaction/commit → runtime promotion → personal broadcast/ACK. Persist consumed sequence and bounded receipts including final rejection; serialize timer/lifecycle/commands under a room lock and resolve ambiguous commits before retry. No Redis, broker or event-sourced rules engine.

Reason: process-local rooms/tokens/RNG/timers disappear on restart. Current to_dict/from_dict omits private state and cannot be a complete recovery format; adding secrets to its network-projection base is unsafe. Recovered games need both complete engine state and usable durable ownership/replay protection.

Identity proposed: stable RoomPlayer/MatchPlayer UUIDs coexist with current room code, compact pid and room-local match_id. Guest seat uses hashed bearer credential; optional account uses opaque hashed server session and HttpOnly/Secure/SameSite cookie. Account binding requires both session and guest proof, revokes guest credentials and preserves match membership. New authorized connection fences old owner. No mandatory registration or JWT stack.

Consequences: the original stages separated codec 1A and DB/adapters/recovery/guest credentials 1B from later Continue/Auth/Profile. **Superseded implementation assumptions:** Continue UI and Auth are complete, including verified account controlling-socket takeover (ADR-013); Profile/history/reset remain future scope. DB failure blocks mutations; no success ACK before commit and no silent fallback to an older ACKed checkpoint. Hash-only credential storage and lifecycle request IDs are implemented; timer grace/guest expiry are accepted in ADR-012. Room retention remains future work. Plain HTTP Docker needs TLS before production cookie auth. ADR-001/002/005/006/007/008/009 remain constraints; this persistence decision does not change gameplay rules.

## ADR-009 — Server-owned room policy, independent presentation colors

Status: Accepted; implemented and verified 2026-10-06, Game / Room UX 2.2.

Decision: Room owns validated lobby-only settings, unique slot colors, private balanced_v1 bag, monotonic turn timer and bounded chat. Shared engine receives only the approved starting_pid/target_vp and ordinary roll/end commands. Default starter/dice Random, timer Off, bank Visible. Rematch keeps options/colors/chat, selects starter again and resets match timers/RNG/sequence. Config_revision orders map/settings/colors; request_id confirms settings/color intentions, retaining existing map_revision behavior. Chat has a separate monotonic chat_revision because presence/config and messages have different lifecycles.

Reason: Transport policy needs Room identity/lifecycle, while shared rules must remain independent of React/WS and be usable offline. Colors do not identify players or order turns. One lifespan scheduler avoids dormant tasks per room; pending/free-road states require explicit user choices. Request confirmation must not be inferred from a presence broadcast.

Consequences: UX 2.2 added room/snapshot fields with VERSION=1; no engine rewrite/state-management library. Automatic timeout uses existing authoritative executor without consuming client seq. UI counts down remaining and renders server facts. Visible bank is an explicit privacy tradeoff (ADR-005); private RNG bag/deck stay hidden. Phase 1B now persists room/chat/RNG/timer separately from GameState; multi-worker coordination, mandatory automation and desktop feature parity remain separate work. Details — [[Сервер и протокол#Room policy — Game / Room UX 2.2]], ADR-012.

## ADR-008 — Same-origin Docker deployment, one backend worker

Status: Accepted; implemented and verified 2026-10-04 as Production Infrastructure Phase 1.

Decision: Nginx с production React build и FastAPI/Uvicorn с общим Python engine; Phase 1B добавляет третий private PostgreSQL service с named volume. Browser использует один origin; exact /ws и /health проксируются backend. Наружу опубликован только web. Backend запускается с workers=1, без reload; backend/web работают non-root.

Reason: Пользователь запросил production-like запуск одной командой. RoomManager/GameState являются process-local, поэтому несколько workers/replicas разделили бы пользователей одной комнаты между независимыми состояниями.

Consequences: Backend readiness проверяется HTTP healthcheck до запуска web. Production WS URL выводится из страницы; local Vite сохраняет VITE_WS_URL как опциональный override и backend для proxy. Base images закреплены digest, server dependencies — точными версиями, frontend использует npm ci. **Historical:** исходная Infrastructure Phase 1 была RAM-only и без account auth. Phase 1B добавила PostgreSQL, затем ADR-013 — работающие account sessions/ownership/Continue. TLS deployment и горизонтальное масштабирование — отдельные задачи. Инструкции — [[Deployment]], исторический план — [[plans/containerization]].

## ADR-001 — Server-authoritative game state

Status: Accepted

Decision: Клиент запрашивает действие. Движок/сервер определяет результат кубиков, выдачу ресурсов, законность построек и изменение GameState. Проверка кнопок в UI не является защитой правил.

Reason: Все участники должны играть по одной модели; произвольный клиент не должен определять результаты или видеть чужие секреты.

Consequences: Полная валидация до изменений, атомарность отказа, отдельный контроль доступа к снимкам. Phase 1 устранила подтверждённые нарушения grant_resources/roll/private snapshots и конкретные неатомарные ветки. Это enforcement существующего решения, не гарантия полной корректности всех правил; см. [[Project State]].

## ADR-002 — Shared Python engine

Status: Accepted

Decision: Сохранить app/engine как ядро правил для server и offline desktop. Переписывание на другой язык требует отдельного архитектурного решения.

Reason: Общие правила уже используются несколькими клиентами и проверяются сценариями.

Consequences: React не становится вторым авторитетным движком. UI-конвертеры и сетевые контракты должны оставаться согласованными с ядром.

## ADR-003 — React web client

Status: Accepted

Decision: React/TypeScript — основной кандидат для нового современного UI. PySide пока сохраняется.

Reason: Browser-клиент уже существует; подготовка нового интерфейса не требует удаления рабочего desktop-пути.

Consequences: Сначала документировать состояния и references, затем отдельная задача на реализацию. Концептуальный дизайн не меняет правила/протокол сам по себе. [[Design System]] не является списком уже реализованных экранов.

**Historical checkpoint — 2026-10-04, Board3D Phase 1:** пользователь отдельно утвердил experimental R3F/Three renderer. На этом этапе BoardRenderer сохранял default SVG, а 3D был view-only без command callbacks. Python authority и network contract были сохранены.

**Superseded visual/interaction scope:** отдельно утверждённая Board3D Phase 2 подключила общий `useBoardInteraction` controller с персональными server legal targets; Game UI Phase 1 сделала 3D default. Сейчас SVG/Three вызывают одинаковые callbacks и не определяют правила. Terrain/building GLB integration и Product Polish Phases 1–4, включая audio, реализованы; полные natural matches/mobile/performance certification не заявлены. Доказательства — [[plans/board3d]], [[plans/game-ui-redesign]], [[React интерфейс]].

## ADR-004 — Base, Seafarers and scenario rules

Status: Accepted

Decision: Различать Base Game → Seafarers mechanics → ограничения конкретного сценария. Переопределения должны иметь явно определённый источник.

Reason: Морские маршруты, fog, бонусы островов и цели победы не универсальны для всех карт.

Consequences: Наличие enable_seafarers не доказывает поддержку всех сценариев. Сейчас часть правил находится в общем dispatcher; это описание реализации, а не изменение решения. Использовать [[Правила Base Game]], [[Правила Seafarers]], [[Карты и сценарии]].

## ADR-005 — Player-specific network projection

Status: Accepted; implemented in Phase 1, 2026-10-02.

Decision: Сохранить trusted/offline to_dict и добавить to_player_dict для multiplayer. Собственная рука и choices доступны своему pid; чужой player содержит публичные counters/VP. Утверждённая 2026-10-03 policy: active VP соперника исключает hidden VP cards; после game_over players.vp раскрывает total VP всех участников. Чужая res/dev hand остаётся приватной и после завершения. Уточнение пользователя 2026-10-06: bank Visibility является room option, default Visible; server projection может добавить точные public counts. Hidden сохраняет прежнюю projection без bank. Map seed, private RNG bag и development deck/count/order не передаются; deck перемешивается независимым источником случайности.

Reason: Удаления чужого res недостаточно: в двух игроках состав руки восстанавливается из bank и своей res, колода — из seed. Hidden защищает от bank deduction; Visible намеренно принимает этот tradeoff для casual games. Отдельная projection сохраняет offline serialization и не раскрывает остальные секреты вне принятой policy.

Consequences: Сервер строит разные snapshots по соединениям. Клиент обрабатывает отсутствие чужого res/dev_cards; банк показывает counts только при Visible, иначе bank_available. to_player_dict сам остаётся private, Visible bank добавляется отдельным серверным слоем. Spectator API нет; старым клиентам нужна адаптация. Детали — [[Сервер и протокол]].

Game UX 2.3 extension (2026-10-06): committed Room gameplay events are also projected per recipient through a closed allowlist. Theft resource is visible only to thief/victim; production composition only to recipient; no raw engine event/debug-secret broadcast. Presentation history cannot execute rules. Test capability requires explicit server opt-in and lobby Test Room, with current active host ownership; normal multiplayer contract stays protected. Details — [[Сервер и протокол#Game UX 2.3 — personalized events and Test Mode]].

2026-10-26: the historical server-only opt-in above is extended by ADR-026's pinned, durable owner preference. Explicit Test Room/current host ownership and all private projection constraints remain.

## ADR-006 — Consumed sequence for final command outcomes

Status: Accepted; existing semantics retained and tested in Phase 1, 2026-10-02.

Decision: Последовательная команда расходует seq/cmd_id и при RuleError. Учёт производится после engine outcome; ACK applied=false завершает intent. Pending очереди принадлежат room+match; reconnect использует bearer token и last consumed number.

Reason: Rejection — окончательный результат запроса. Success-only numbering без синхронного изменения обоих клиентов создаёт gap после отказа; незаконный intent не должен replay бесконечно.

Consequences: Имя last_seq_applied сохранено, но означает last consumed. Отказ не меняет GameState/tick, меняется transport metadata. Новая попытка получает новый номер. Тесты проверяют duplicate/gap/lost ACK/reconnect/rematch. Владение слотом не является новой user auth системой.

## ADR-007 — Rematch with connected participants

Status: Accepted; implemented and verified 2026-10-03.

Decision: Новый матч включает участников, реально подключённых на момент старта, минимум двух. Отсутствие прежнего участника не требует его возвращения и не создаёт пустой PlayerState. Боты и account auth не добавляются.

Reason: Пользователь утвердил, что отключившийся участник не должен навечно блокировать rematch. Старый барьер «весь прежний состав должен reconnect» противоречил этому решению; существующая модель уже поддерживает фильтрацию и уплотнение pid.

Consequences: В реализации подключённый host сохраняет исключительное право запуска; при его отключении первый подключённый участник может запустить rematch и становится host только после успешного создания игры. До нового матча токены восстанавливают прежние слоты. Сохранившиеся участники сохраняют token и получают компактный pid; исключённые токены не дают доступ к новым слотам. Новый match_id сбрасывает tick, seq и cmd_id history; отказ при недостаточном составе сохраняет прежнюю игру и identity. Проверки и пределы — [[Сервер и протокол]] и [[Результаты аудита]].
