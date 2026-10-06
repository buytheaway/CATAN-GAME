---
tags: [catan, architecture, persistence, auth, plan]
updated: 2026-10-06
status: phase-1a-completed
---

# Persistence + Auth Architecture v1

[[Project State]] · [[Architecture Decisions]] · [[Сервер и протокол]] · [[Состояние игры]] · [[Инварианты движка]] · [[Deployment]]

## Status and boundary

Architecture plan audited 2026-10-06 against `745d749` / `game-ux-2-3`, then used as the user-approved direction for Persistence Phase 1A. **Only full GameState codec 1A is implemented.** Database, Room recovery, auth, Continue and Profile remain unimplemented; their rollout/product policies are still future work. Current accepted authority/privacy/consumed-sequence/rematch decisions remain in force. Codec does not change engine, protocol, player views, dependencies or Docker.

Goal: one FastAPI worker and one PostgreSQL database; committed active games survive process/container restart, guests can continue using their credential, accounts can later list their games. No Redis, broker, event sourcing, multi-instance coordination, engine rewrite or mandatory registration.

## Persistence Phase 1A — completed 2026-10-06

Runtime: `app/persistence/__init__.py`, `app/persistence/snapshots.py`. Public codec API: `encode_snapshot(GameState) -> dict`, `decode_snapshot(dict) -> GameState`, `dumps_snapshot(GameState) -> str`, `loads_snapshot(str) -> GameState`. No server caller/network endpoint added. Full trusted payload stays an internal persistence surface.

Released format:

```json
{"snapshot_version":1,"engine_compatibility":1,"state":{"all GameState fields":"explicit encoding"}}
```

Example describes structure only. No Room/DB metadata in this envelope. `state_version` and engine `tick` are separate stored fields, not format compatibility or Room tick. v1 schema is immutable after checkpoint; future fields require explicit compatibility/decoder/migration review. Unsupported versions, missing/extra fields and malformed types fail closed through SnapshotError subclasses. A runtime schema-coverage guard detects any added/removed dataclass field before silent loss can occur.

Coverage: all **40 GameState fields**, including all nested fields of BoardState (9), PlayerState (6), Tile (5), RulesConfig (11), AchievementState (4) and TradeOffer (8). Geometry is saved as materialized values/IDs, no build_game/graph generation/shuffle during restore. Every gameplay list preserves order, including deck/cards/tiles/setup/gold/victims/offers/history. Integer-keyed maps use canonical decimal strings, edges canonical `a,b`; decoder restores int keys, tuple edges/coordinates/occupancy/ports and sets explicitly. Detached payload/restored state share no mutable references with original.

Intentionally not duplicated: GameState property aliases to board/achievements, player piece counts/remaining pieces and port ownership derived deterministically from saved occupancy/rules. Engine has no live Random object/state field; map seed and exact dev deck are stored. Arbitrary Python objects/tuples inside free-form JSON metadata are rejected, not silently converted. This codec accepts shared engine dataclasses, not Qt Game or a player projection.

Validation checks exact object shapes/required fields, strict primitives (bool is not int), finite numbers, known dev-card/pending/status enums, player ranges/identity, topology membership/adjacency references, offer IDs/next ID, duplicate JSON keys/set IDs, overlapping road/ship occupancy. It does not recompute achievements, scores, map geometry, port accessibility, resource conservation or gameplay legality; current imperfect semantics such as repeated initial robbers and duplicate ports are preserved. Terrain/port strings and raw map rules retain current values rather than adding new map validation rules. No repair/fallback/pickle/eval/dynamic constructors.

Limits: text API ≤8 MiB UTF-8; object structure ≤200,000 nodes including keys / depth 64; canonical ID keys ≤16 decimal digits. Strings/keys must be valid UTF-8 (unpaired surrogates fail explicitly). Non-JSON metadata and out-of-limit snapshots fail explicitly. These are supported-format limits, not a promise to serialize arbitrary Python data. Keys/sets are sorted for stable JSON, but cryptographic canonical bytes/checksums are not yet a contract.

### Verification and performance

Full pytest **445/445 passed**, including **179 new cases** in `tests/test_persistence_snapshots.py`. First 30 characterization cases were run before implementation: existing serializer loses eight field groups but already preserves board/bank/pending/trades/setup/Seafarers fields; equal old serialized views can hide loss of full private state. New assertions recursively compare internal values and types, not old to_dict output.

Base fixtures: new/mid-setup/before/after Roll, initial/partial discard, robber/two eligible victims, targeted active trade, Knight, Road Building 2/1/0/expired roads, Plenty/Monopoly ready/completed (no engine pending picker), hidden VP/new purchase, near victory and genuine game_over via buy_dev at supported target 3. Seafarers: actual ship build/move, pending/moved pirate, multi-step gold queue resolution. Restored commands match original outcomes; new-card rejection and Road Building End/paid-road lifecycle stay unchanged.

All 12 registered presets, including Base Standard/community fixed maps/Gold Haven/Pirate Lanes/multi-robbers, plus shifted 50-hex custom fixture and rotated setup for 1/2/3/4/6 engine participants were round-tripped. Patched build_game/materialization sentinels prove restore does not call them. Mutation isolation, deterministic encoding, corrupted/unsupported/truncated payloads and field coverage are tested. Both active/final personal server projections match original; Hidden bank/foreign hands/active hidden VP/seed/deck/persistence envelope remain protected. Existing network serializer was not edited.

Measured locally on Windows/Python virtualenv, newly started 2-player states, 100 samples each; median text encode includes full validation and JSON dump, decode includes parse/validation/reconstruction. No DB/fs/network cost measured:

| State | UTF-8 JSON bytes | Encode median | Decode median |
| --- | --- | --- | --- |
| Base Standard | 7,662 | 1.250 ms | 0.842 ms |
| Gold Haven | 7,778 | 1.239 ms | 0.826 ms |
| 50-hex custom fixture | 16,363 | 2.715 ms | 1.741 ms |

Engine/state/serialize/rules/server/frontend unchanged, so scenarios/web/build/Docker were not rerun. **348/508 scenarios remains the previous checkpoint baseline**, not a new result. No database/auth/Continue or live room restoration delivered by 1A. Qt offline JSON-key bug remains untouched; a later explicit offline converter could adopt this codec after compatibility testing.

### Precise Phase 1B boundary

Outside GameState and NOT in codec: room code/internal UUID/status/capacity/host/membership/ownership/colors, room-local match_id/Room.tick, selected preset/custom source definition/settings/effective selected config and config/map/chat revisions, received reconnect credential hashes/expiry/revocation, consumed sequence/command and lifecycle receipts, Room seed metadata, exact Balanced bag/algorithm/confirmed dice/roll_count, timer UTC deadline/stage, bounded chat/game_events/private audiences/event_serial, activity/retention timestamps, test flag/private forced test dice policy. WebSockets/connected/monotonic deadlines/locks remain runtime-only.

Database Phase 1B must combine complete engine payload with these durable fields and commit/replay/recovery guarantees. GameState JSON alone cannot restore multiplayer. Next phase requires its own task; suggested checkpoint message `feat: add versioned game state persistence codec`, tag `persistence-phase-1a`.

Current `deploy/backend.Dockerfile` selectively copies server/engine files and does not include `app/persistence/`. It is intentionally untouched because 1A adds no server caller. Phase 1B must include this package when integrating it into the backend image, then verify actual container recovery.

## Current lifecycle: verified code

| Step | Code and actual behavior |
| --- | --- |
| Create | `app/server_mp.py:RoomManager.create_room` allocates Room and named host PlayerSlot in process memory; six-character room code is unique only among currently loaded rooms. |
| Join | `join_room` accepts a free lobby slot; duplicate name is rejected. Name is display data, not proof of ownership. |
| Credential | `PlayerSlot.reconnect_token` uses `uuid.uuid4().hex`, stored plaintext in RAM. Server sends `reconnect_token`; `web/src/wsClient.ts` stores `{token,pid}` under `catan_reconnect_<roomCode>_<name>`. |
| Configure | Host set_map/set_settings and own set_color update Room. map_revision/config_revision protect client intent ordering; chat_revision orders a separate feed. Custom map definition is in selected_map_data. |
| Start | `_start_match` builds a new shared engine GameState from connected named slots, compacts pid, selects starter, creates a separately shuffled dev deck. `_start_and_notify` sends room_state, tokens, personal match snapshots. |
| Execute | `web/src/wsClient.ts:sendCmd` sends room/match/cmd_id/seq; websocket_endpoint checks identity/order, `_apply_cmd` invokes `engine.rules.apply_cmd` on the live GameState. Test actions use an isolated copy. |
| Commit today | Successful execution changes Room tick/dice/bag/event feed/timer in memory, broadcasts personal snapshots, then ACKs. Final RuleError consumes seq/cmd_id but does not change GameState. There is no durable commit. |
| Snapshot | `_snapshot_state` calls `serialize.to_player_dict`, adds derived legal and recipient-projected events/settings/timer/colors/dice. It is a view, not a save file. |
| Disconnect/leave | `RoomManager.leave_room` marks slot disconnected and detaches socket; name/token remain reserved. Explicit leave does not revoke stored token or destroy room. |
| Reconnect | Token lookup plus active_ws binding restores seat; old connection is detached from room/pid, not physically closed. Its later close cannot disconnect the new owner. Live retry is automatic; page refresh still requires Join inputs to load the stored binding. |
| End | Engine sets game_over/winner. Room remains in_match; timer is cleared. Final total VP is public, other players' hands remain private. |
| Rematch | `_start_match` includes connected named participants only, preserves their tokens/colors and room settings/chat; compacts pid and resets match_id/tick/seq/command cache/dice/bag/events/timer. Excluded tokens cannot take new slots. Current rematch handler does not require game_over. |
| Destroy | `RoomManager.destroy_room` removes RAM room and detaches connections; repository search finds a test call, no normal automatic TTL/close flow. |

RoomManager.rooms/connections are process-local dictionaries. Room.game is GameState. Restart loses rooms, ownership/tokens, match state, sequence/deduplication, private bag, timers, chat and gameplay feed. Browser token alone cannot restore a deleted server room. Existing offline Qt saves do not provide multiplayer durability. Current `/health` checks the process, not durable readiness.

### Identifiers and persistence

| Identifier | Meaning | Future treatment |
| --- | --- | --- |
| room_code | Human entry code | Persist; unique, no reuse in v1. Not authorization. |
| pid | Position in the current match/room array | Persist current assignment; changes on rematch. Never account identity. |
| match_id | Current room-local integer epoch | Persist and keep existing wire meaning. Add internal match UUID, unique room+match_no. |
| Room.tick | Accepted gameplay/automatic state publication counter | Persist, reset per new match. |
| GameState.tick | Separate engine field | Preserve exactly; do not equate it to Room.tick. |
| seq / last_seq_applied | Per-seat consumed command number, including final engine rejection | Persist per MatchPlayer; preserve ADR-006. |
| cmd_id cache | Bounded duplicate protection | Persist last 256 receipts per participant plus highest consumed seq. |
| reconnect_token | Bearer credential | Persist hash and lifecycle, not plaintext. |
| map/config/chat revisions | Different ordering domains | Persist; never reset on restart or infer ACK from unrelated presence. |
| Room UUID / RoomPlayer UUID / MatchPlayer UUID | New stable internal identities | Persist; UUID is an identifier, never a credential. |
| durable_revision | New internal room aggregate commit counter | Persist and compare on write; includes changes that do not advance game tick. |
| active_ws, ClientConn, connected, socket maps, locks | Live ownership/presence | Runtime only; every recovered seat starts disconnected. |
| monotonic deadlines/chat rate windows | Process-local clock data | Do not serialize; reconstruct deadline from UTC, rebuild rate limit windows. |

## Guarantees and limits

Successful gameplay ACK and published authoritative state must follow DB commit. Restart restores the latest committed state, including private state and consumed sequence. Lost ACK can cause replay but must not execute the effect twice. Rejected engine commands preserve GameState but their consumed sequence is durable. Lobby configuration, new match and rematch become durable lifecycle transactions.

Availability tradeoff: DB unavailable means no new authoritative mutation/ACK success, not memory-only play followed by rollback. Read/display of already committed RAM state can remain available with an unavailable status. This adds DB latency per command; acceptable for turn-based scale, to be measured. PostgreSQL durable settings/storage and backups are operational prerequisites; no promise against destruction of the database/volume or restoring an intentionally older backup.

## Serialization audit: blocker before DB

`app/engine/serialize.py:to_dict/from_dict` cannot currently be used as a full save codec. Missing: seed, players[].dev_cards, dev_deck, dev_played_turn, free_roads, roll_history and GameState.tick. to_dict writes state_version, but from_dict neither validates nor restores it. A synthetic in-memory JSON round-trip probe on 2026-10-06 confirmed differences in those eight GameState fields/groups. It was a serialization probe, not a simulated legal match or full regression run.

Shared from_dict already converts vertex IDs, tuple edge keys, discard/gold keys and submitted sets. The older integer-key issue exists in `app/ui_v6.py:_load_game`: `_offline_hidden` free_roads/dev_played_turn are loaded with raw dict(), leaving JSON string keys. Its `_game_to_dict` does include extra private fields, but that Qt-specific format is not the new server codec. Do not import PySide for recovery.

With the default state_version=1, a second probe produced equal to_dict views despite unequal full dataclasses. A test comparing only the existing serialized representation can therefore miss precisely this loss of private state.

**Do not just add secrets to to_dict.** to_player_dict starts from to_dict and filters a known set of fields: extending its base with a secret deck/seed can expose it over WS. Create a distinct full trusted codec and prove network privacy independently. Existing to_dict/from_dict can supply carefully reviewed geometry conversions, not completeness/security guarantees. Freeze/deep-copy collections; some existing serialization values share nested mutable references.

Full codec covers every GameState/PlayerState/BoardState/RulesConfig/TradeOffer field, including exact geometry and IDs, deck order/new flags/hidden VP, bank, setup order/anchor, turn/rolled, robber/pirate, pending victims/discards/gold queues, free roads, achievements, offers/next ID and engine counters. Full snapshots stay server-side; never save `to_player_dict`, legal hints, projected events, React state or a socket object as recovery authority.

## Snapshot envelope and compatibility

Conceptual **future Phase 1B room/match** envelope (not the released engine codec envelope above):

```json
{
  "room_snapshot_version": 1,
  "build_commit": "745d749",
  "room_id": "uuid",
  "match_id": "uuid",
  "match_no": 1,
  "tick": 12,
  "engine": {
    "snapshot_version": 1,
    "engine_compatibility": 1,
    "state": {"all engine fields": "explicit typed encoding"}
  },
  "runtime": {
    "dice_algorithm": "balanced_v1",
    "remaining_dice_bag": [[1, 2]],
    "dice": [3, 4],
    "roll_count": 5,
    "event_serial": 9,
    "private_game_events": []
  }
}
```

Example is a future room-envelope sketch, not a valid loadable game or current engine codec input. Only its nested engine envelope goes to decode_snapshot; Phase 1B must define its own Room format version. Timer metadata is stored on matches; chat/settings/membership/transport receipts are separate SQL authority. Envelope duplicates identity/tick only as consistency assertions. Engine compatibility is not every Git commit; build_commit is diagnostic. Existing state_version is preserved but does not replace snapshot_version.

Explicit encodings: maps with integer keys have validated conversion; edges use canonical original vertex pairs, sets restore as sets, private event audience keys restore as integers. No pickle, eval or automatic GameState defaults for missing required secrets. Validate types, sizes, enums, coordinate references, deck/resource counts and cross-field relationships without rejecting previously legal pending/setup/finished states. Validation must account for opted-in Test Room fixtures separately.

Compatibility registry maps supported version to decoder and pure version-to-version migration. Schema-compatible refactor needs no data migration. Actual field/rules changes require fixtures and an explicit migration or a supported legacy decoder; no silent invented deck/seed. Preserve source snapshot before migration. Unknown/corrupt head quarantines that match and reports recoverability; other rooms can load. Older snapshots are for diagnosis/manual repair, **not automatic rollback of an ACKed game**. Never call build_game/new_game to replace an incompatible saved match. Keep backup and quarantine export server-only.

## Proposed PostgreSQL schema

Notation: UUID PKs generated in application; time columns TIMESTAMPTZ UTC; N = NOT NULL, ? = nullable. JSONB has explicit format/schema versions where mutable structure is stored. FK deletion is RESTRICT by default; cleanup explicitly removes dependent ephemeral records only after retention checks. No ORM objects inside GameState.

### users — account identity (Auth Phase)

- PK id UUID. N username_normalized TEXT, display_name TEXT, password_hash TEXT (Argon2 PHC), status TEXT, created_at, updated_at. ? email_normalized TEXT reserved for a later verified-email feature; no email login/reset in v1.
- UNIQUE username_normalized; partial UNIQUE email_normalized where non-null if email feature is later enabled. No unique display_name. Index username already supplied by UNIQUE; status index only if an actual administrative query needs it.
- Lifecycle: registration to disabled/anonymized account; no hard deletion of referenced history in v1. Username policy proposed: ASCII lowercase `[a-z0-9_]{3,32}`; display name trimmed Unicode with a bounded length. Password is not normalized, logged or stored plaintext.

### user_sessions — revocable browser login (Auth Phase)

- PK id UUID. N user_id FK users, token_hash BYTEA, csrf_token TEXT, created_at, last_seen_at, idle_expires_at, absolute_expires_at. ? revoked_at.
- UNIQUE token_hash; indexes (user_id, revoked_at) and expiry for cleanup. CSRF nonce is not the auth bearer; raw session token exists only in issued cookie/request, never DB.
- Lifecycle: login/register creates a session; idle renewal cannot exceed absolute expiry; logout/revocation persists. Multiple device sessions allowed. Proposed idle 7 days, absolute 30 days; product policy, not implemented.

### rooms — durable room metadata

- PK id UUID. N room_code TEXT, status TEXT (lobby/in_match/closed/quarantined), max_players SMALLINT, host_room_player_id UUID, map_id/name TEXT, selected_map_definition JSONB, selected_rules_config JSONB, settings JSONB, map_revision/config_revision/chat_revision/durable_revision BIGINT, chat_history JSONB, created_at, last_activity_at, is_test BOOLEAN. ? current_match_id UUID, closed_at, expires_at.
- UNIQUE room_code. Index (status,last_activity_at). Settings preserve internal nullable target_vp meaning “follow preset”, not just the public effective target. Save validated selected source definition for preset/custom maps so recovery is not dependent on files changing; exact live geometry still belongs in GameState.
- Composite FK (host_room_player_id,id) → room_players(id,room_id); composite FK (current_match_id,id) → matches(id,room_id). Deferrable host FK permits preallocated room/host UUID insertion in one transaction. Membership/match tables have corresponding UNIQUE (id,room_id).
- Lifecycle: create/configure/play/rematch/close; preserve code tombstone in v1. Closed is not a winning result. All host and current-match relations must belong to this room.

### room_players — stable seat and ownership across rematches

- PK id UUID. N room_id FK rooms, display_name TEXT, color TEXT, membership_status TEXT (active/retired/revoked), joined_at, last_seen_at. ? user_id FK users, guest_id UUID, current_room_pid SMALLINT, last_disconnect_at.
- Exactly one user_id/guest_id is present. UNIQUE (id,room_id); partial UNIQUE (room_id,user_id) where user_id non-null; UNIQUE (room_id,guest_id); partial UNIQUE (room_id,current_room_pid) where non-null. Active display names retain current room uniqueness. Index user_id+membership_status for Active Games.
- connected/active_ws are not columns. Disconnect retains ownership; rematch retires excluded seats, clears their current pid and revokes tokens. Retired rows remain for historical match FKs. Compact rematch assignment clears current pids then assigns new values inside one transaction to avoid transient unique collisions.

### seat_tokens — guest credential lifecycle

- PK id UUID. N room_player_id FK room_players, token_hash BYTEA, created_at, expires_at. ? revoked_at, last_used_at.
- UNIQUE token_hash; indexes room_player_id and expires_at. SHA-256 of a high-entropy random bearer is sufficient; password hashing applies to passwords instead. Future issuance uses 256 random bits; existing received UUID tokens can be hashed without changing their value during a controlled migration.
- Lifecycle: issue, verify, slide expiry, revoke. No rotation on every reconnect/rematch for retained guests. Explicit account bind/security rotation/seat retirement/room close revokes previous credential. Proposed 30-day inactivity expiry, renewed by authenticated use and capped by room lifetime; no expiry while regularly used.

### matches — immutable match identity and public metadata

- PK id UUID. N room_id FK rooms, match_no BIGINT, status TEXT (active/finished/superseded/abandoned/quarantined), map_id/name TEXT, settings JSONB, started_at, tick BIGINT, is_test BOOLEAN. ? finished_at, winner_match_player_id UUID, latest_snapshot_id UUID, timer_pid SMALLINT, timer_deadline TIMESTAMPTZ, timer_stage TEXT.
- UNIQUE (room_id,match_no), UNIQUE (id,room_id). Partial UNIQUE room_id where status=active. Index (status,started_at). Composite head FK ensures latest_snapshot_id belongs to this match; winner FK also constrained to same match. Circular references are deferrable and set atomically.
- Timer columns must be all valid together or all absent; stage stopped/blocked is meaningful, not an instruction to restart a countdown. Duration is derived from timestamps, not independently editable.
- Lifecycle: start → normal finish or explicit supersede/abandon. Current rematch can replace a nonfinished game: archive it as superseded, no fabricated winner/final score. game_over commits result metadata and final snapshot together.

### match_players — participant mapping and consumed sequence

- PK id UUID. N room_id UUID, match_id UUID, room_player_id UUID, pid SMALLINT, display_name_at_start TEXT, color_at_start TEXT, last_seq_consumed BIGINT. ? user_id FK users, guest_id UUID, final_vp INT. Composite FKs (match_id,room_id) → matches(id,room_id), (room_player_id,room_id) → room_players(id,room_id) prevent cross-room participant references.
- UNIQUE (match_id,pid), UNIQUE (match_id,room_player_id), UNIQUE (id,match_id). Exactly one account/guest owner at a time; explicit claim of an active guest seat updates its active match ownership in the same transaction. Finished participant identity/display/result is immutable.
- Index user_id+match_id for future history. final_vp only populated at normal game_over, never from an active public VP projection. No resources/dev cards in result metadata.

### game_snapshots — full private checkpoints

- PK id UUID. N match_id FK matches, durable_revision BIGINT, tick BIGINT, snapshot_version INT, engine_version TEXT, payload JSONB, checksum TEXT, created_at.
- UNIQUE (match_id,durable_revision), UNIQUE (id,match_id); index (match_id,durable_revision DESC). Head pointer validates its own committed revision/tick and identity. A chat/config-only commit may advance room durable_revision without replacing game head: head revision is ≤ current aggregate revision, not necessarily equal. Recovery combines that exact head with current normalized metadata. Checksum detects corruption, not a malicious DBA capable of replacing both payload/checksum.
- Lifecycle: insert immutable full checkpoint, move head in same transaction. Keep head and limited prior versions; no command-log reconstruction. Lobby metadata needs no fake GameState snapshot. Read only through private repository; no generic public snapshot API.

### command_receipts — replay protection, not event sourcing

- PK (match_player_id,seq), FK match_players. N cmd_id TEXT, payload_hash TEXT, outcome TEXT, committed_at. ? error_code TEXT, snapshot_id FK game_snapshots.
- UNIQUE (match_player_id,cmd_id); index participant+seq for bounded cleanup. Persist last 256 receipts; older seq is still rejected as duplicate via last_seq_consumed, not reexecuted. Different payload using retained cmd_id is a conflict.
- Rejected engine command writes receipt/consumed seq, no gameplay snapshot/tick change. Early unauthorized/gap/wrong-match errors do not consume seq. Existing duplicate ACK applied=false semantics remain; reconnect snapshot supplies actual state, not a newly invented successful replay.

### room_operations — lifecycle retry protection

- PK (room_id,request_id), FK rooms. N actor_room_player_id FK room_players, operation TEXT, expected_match_no BIGINT, payload_hash TEXT, result_revision BIGINT, committed_at. ? result_match_id FK matches.
- Index room_id+committed_at; limited retained lifecycle receipts. Cross-room actor/result references must be composite FKs or validated within locked room transaction.
- Needed for start/rematch/close retries after commit-before-delivery. Those existing controls lack a durable idempotency key. A future additive request_id/expected-match contract is required when implemented; **not changed now**. Do not promise exactly-once lifecycle operations using current start/rematch messages alone.

### match_results decision

No additional match_results table in v1: matches winner/finish/settings plus match_players final_vp already normalize the result. A closed allowlist query/DTO forms future history. A second independent result copy would add synchronization work. If later statistics need denormalized data, add it in Profile Phase with an explicit migration.

Auth tables wait until Auth Phase; room ownership initially uses guest_id with nullable user_id reserved for later migration. CHECK/partial indexes/FK scope are reviewed manually in Alembic; autogeneration is not a proof of integrity.

## Write model and atomicity

Choose synchronous durability per authoritative operation; no debounce/periodic save as primary guarantee. Optional periodic backup is operational and does not replace commit.

| Event | Durable transaction |
| --- | --- |
| create/join | Room/membership/token hash/source configuration; publish only after commit. |
| map/settings/color | Validated metadata plus revisions; retain existing request confirmation semantics. |
| start/rematch | Archive previous match if needed; new participants/epoch/full snapshot/sequence reset/head/room host and ownership changes together. |
| accepted command | Candidate full state + private bag/feed/dice/timer + tick + receipt + seq + activity; game_over adds final results in same transaction. |
| final engine rejection | Receipt and consumed seq only; GameState, bag/feed/tick unchanged. |
| chat | Bounded 50-message JSON on rooms with chat_revision; no new game snapshot unless game changes. |
| disconnect/leave | Ownership remains; last-seen/disconnect bookkeeping, no persistent connected=true. Socket closure cannot be delayed/undone by DB failure; presence is runtime, bookkeeping may be reconciled. Explicit abandon/revoke is a separate durable action. |
| timeout/stage change | Same locked executor/transaction; automatic command does not consume a client's seq. |
| close | Closed status/revocation/timer stop/tombstone; no silent deletion of active game. |

Minimal safe executor:

1. Acquire per-Room asyncio.Lock. Check current socket generation/ownership and latest committed aggregate; scheduled timer and every lifecycle writer use the same lock.
2. Deep-copy mutable GameState and relevant Room gameplay data into a candidate. Generate proposed outcome once; apply existing engine executor on candidate. Never mutate live state while awaiting DB.
3. Freeze full payload; start explicit DB transaction. Compare expected durable_revision; persist candidate/metadata/receipt/head. Revalidate authoritative credential/session before accepting mutation.
4. Commit. If definitely rolled back, discard candidate and leave runtime state/seq unchanged; report temporary unavailable, not a final consumed RuleError.
5. If commit result is ambiguous (network lost during COMMIT), fence room writes, reconnect DB and query receipt/head. Do not assume rollback, retry with a new ID or regenerate dice. After resolution publish the committed candidate or restore the committed head.
6. Only after durable commit swap candidate into Room, freeze recipient views, broadcast and ACK. Existing snapshot-before-ACK order can remain. Network failure after commit cannot undo the command; reconnect recovers it.

Lock spans validation/candidate/DB commit/promotion. WS sends should not hold room lock indefinitely: build immutable publications tagged match/tick/connection generation; send through ordered per-connection publication queues and reject stale generation. Lifecycle notifications also need order. New async DB awaits invalidate current assumptions that synchronous mutation finishes before network yields; timer's current 2s processing timeout must not cancel an in-flight commit without ambiguity handling.

Read Committed plus one runtime writer and expected revision guard is sufficient for v1; do not hold one global AsyncSession. DB head is durability authority; committed Room remains the fast active read/execute source. No disconnected memory fallback writer. Reject unchanged state may still require durable seq write by ADR-006.

Create/join credential bootstrap has an unavoidable delivery window: server can commit a hashed token then crash before client receives its raw value. Such unclaimed lobby seats can expire; do not claim the browser can recover a secret it never received. Issue/store binding before permitting ordinary UI play. Lost delivered gameplay ACK is handled by durable receipts. A future idempotent bootstrap proof is separate if orphan-free creation becomes required.

## Recovery

FastAPI lifespan connects DB/checks migration compatibility → loads eligible lobby/in_match rooms → validates normalized metadata/head/codec → reconstructs Room/PlayerSlot/GameState from stored values → restores bag/feed/dice/timer/settings/chat/seq/receipts → sets every connected=false and active_ws=None → enables readiness and scheduler.

No build_game, geometry regeneration, startup deck shuffle, new match number or revision reset. Load selected map definition even if a preset file changes/disappears. Rebuild catalog only for future selection; do not replace current source/state from catalog. Rebuild active per-room locks and socket generations, not old WebSocket references. Token hashes and user sessions stay DB-backed. Private event pid mapping remains tied to its saved match, not rematch participants.

A bad room is quarantined and cannot accept mutations; expose only safe recovery status to its verified owners. Unknown DB/recovery outage must return temporary unavailable, not not_found/forbidden that would make current WSClient delete its token. Overall readiness remains false until initial recovery completes; then valid rooms can operate while isolated corrupt rooms are unavailable.

Test rooms: default exclude from recovery, active-game lists and normal history. Production startup requires test tools OFF. Optional isolated development recovery must explicitly opt in, validate test flag/capabilities and never turn DEBUG fixtures into normal results. Private forced next-test dice is either persisted only in that isolated mode or discarded with the excluded room; never applied to a normal recovered match.

## Guest reconnect and account ownership

Guest token is scoped to RoomPlayer UUID + Room UUID, not name/pid/code alone. Verify presented token hash, expiry/revocation and current membership/match entitlement; stable seat can receive a new compact pid on rematch. Hash-only DB cannot resend a token from storage: for validated reconnect the server can echo the presented token if the legacy message requires it; creation/explicit rotation alone needs transient raw issuance. Never log it.

Retained guest participants keep credential across restart/rematch. Excluded seats are revoked when new match commits. Last authenticated activity renews proposed inactivity expiry with bounded metadata writes. Explicit account claim requires BOTH logged-in session and valid guest seat token; account ID/name sent by client is insufficient. Claim updates active ownership and revokes guest credentials atomically. Existing other account seat in same room is a conflict, not a merge by nickname. No automatic claim of old finished games.

Accounts may Continue from another browser/device using session + DB ownership. One active socket per seat: new authorized bind fences old connection before publishing snapshots; old queued commands/finalizer cannot act for the new owner. Same-account takeover is proposed v1 policy, with a clear UI notice; no multiple independent controllers for one seat. Logout revokes current login session and fences its sockets but does not delete games/membership. Guest credentials revoked by account bind do not become a bypass after logout.

## Auth proposal

| Option | Assessment for this project |
| --- | --- |
| Opaque server-side session | Recommended: random cookie bearer, hashed DB record, easy expiry/revoke/logout, same PostgreSQL. |
| Signed identity cookie | Integrity alone gives no convenient immediate revocation; adding DB tracking removes its simplification. |
| JWT access/refresh | Adds token lifecycle/rotation/revocation machinery without single-backend need. |

Future endpoints: POST `/api/auth/register`, `/login`, `/logout`, `/session/refresh`; GET `/api/auth/me`; authenticated GET CSRF/bootstrap data and a display-name update endpoint. All mutating endpoints require JSON, trusted Origin and authenticated CSRF where applicable; register/login need trusted Origin and strict JSON/CORS policy too. /me is a safe DTO, never sessions/password hash. Session refresh renews idle expiry within fixed absolute expiry, not indefinite login; new login/privilege elevation issues a new session ID, no rotation on every WS reconnect.

Cookie: opaque ≥256-bit random value, HttpOnly, Secure on HTTPS production, SameSite=Lax, Path=/, no broad Domain; production can use `__Host-` prefix. Current localhost HTTP needs an explicit local development cookie profile; Secure production auth is not ready on the existing plain-HTTP public setup. CSRF nonce can be read only through same-origin authenticated API and sent as header; it is not the login bearer. WS verifies exact allowed Origin and session/seat entitlement; session revocation/expiry is rechecked before accepted mutation and closes/fences affected live sockets. Logout and in-flight commands must have a defined transaction order, not a stale auth cache that continues accepting actions.

Password hashing: Argon2id, generated salt and encoded parameters; tune on deployment hardware, starting no weaker than OWASP baseline 19 MiB/t=2/p=1. Bound input, rate-limit login/register, use generic login failure, parameterized SQL. Proposed username-only login avoids pretending unverified email supports recovery; optional email verification/reset remains future. Display name changes do not rewrite historical participant names or identify a slot.

## Continue Game and future history contracts

Home/Menu → Active Games → Continue. Account list uses authenticated user_id from session joined to current active membership; guest list starts from browser bindings `{server_origin,room_id,room_code,token,name_hint}` and validates each credential with server. Browser storage indexes simplify discovery, never establish ownership. Migrate old code+name storage after a successful verified reconnect; do not search/join by nickname. If storage is unavailable/cleared, warn that guest continuity is unavailable; accounts remain recoverable from DB after login.

Proposed safe active-game DTO: room_id/code, map_id/name, membership capacity and current participant count, live connected count, match_no, status, public current-turn name, started_at/last_activity_at, can_continue/recovery_status. Example: “ABCD12 · Base Standard · 3/4 participants · 2 online · turn Player2”. No seed, resources, bank, private choices/deck/bag or full snapshot. Reconnect authenticates again and receives ordinary personal room/match snapshots. Pending map settings are not replayed from browser; committed server config wins.

Future history allowlist: match identity, map, participant display/color, winner, final total VP, started/finished UTC, wall duration, dice mode and public settings. Only normal finished, non-test matches produce victory results. Superseded/abandoned entries have status, no invented winner. Final VP publication follows accepted game_over policy; history never exposes exact hands/private events. Public profile exposure vs owner-only history is a future product decision; default v1 is owner-authorized, not world-readable.

## Chat, gameplay events and private randomness

Keep last 50 chat messages in Room row JSONB with chat_revision and original author/name/color/time. No separate unbounded chat table in v1. Plain text, size/rate limits remain; rebuild conservative rate window after restart rather than persist monotonic timestamps. Chat survives rematch independently of game events.

Persist bounded 80-event full internal feed and event_serial inside private match checkpoint. Latest GameState cannot recreate exact theft/resource history. Project with existing `game_events.project(pid)` allowlist AFTER authorization; exact stolen type remains thief/victim-only. Do not create a global public plaintext event table or let frontends fetch the trusted envelope. This feed is presentation history, not a replay engine.

Balanced: persist exact remaining ordered dice pairs and `balanced_v1`. Current `room_options.py` refreshes with a new 36-pair shuffled bag when remaining length ≤12; no RNG seed/state can reconstruct secrets.SystemRandom. Restore without drawing/refilling/shuffling. Random mode stores confirmed faces/count/history, not unrealized future entropy. Save complete development deck order and all purchased cards/new flags/hidden VP/bank; restore without new deck creation. Current free_roads must survive restart within its current turn, but successful End Turn still clears unused entitlement by dcadcab.

## Timer downtime policy — product proposal

Persist UTC deadline/stage/pid on matches; runtime uses monotonic. Recovery computes remaining from saved UTC deadline using current trusted server wall time, then creates a fresh monotonic deadline when resuming. Never serialize monotonic values.

Proposed restart behavior: recovered timed games wait for first authorized participant reconnect; no unattended chains of Roll/End during downtime/startup. Positive saved remaining is resumed with minimum 20s recovery grace; expired deadline gets 20s, not instant automatic action. Internal recovery-waiting status can project existing stopped timer stage until resumed; final wire/UI choice belongs to implementation phase. Previously blocked mandatory choices/free_roads remain blocked; intentionally stopped/failed timer is not silently rearmed. Setup/Off/game_over have no timer. Validate pid/current turn and bound recovered durations. No random mandatory choices. Normal running-server disconnect timer policy stays as today unless separately approved.

DB outage gates automatic mutations just like user commands; ambiguous transactions are resolved before timer retries. This downtime behavior and grace need explicit product acceptance before implementation; not retroactively claimed as current behavior.

## Minimal security controls

| Threat | Control / honest limit |
| --- | --- |
| Stolen guest token | TLS, random bearer, hash at rest, expiry/revoke/seat scope, no URL/log tokens. Possession still grants guest seat; hashing does not cure browser XSS/theft. |
| Stolen session | HttpOnly/Secure/SameSite cookie, expiry/revocation/CSRF/Origin, no localStorage auth token. XSS can still make authenticated requests. |
| Forged identifiers / horizontal access | Derive account from session, verify RoomPlayer/MatchPlayer entitlement on every private read/write; UUID/code/pid are not secrets. |
| Snapshot tampering | No client-controlled trusted load endpoint; strict codec/limits/version/checksum, restricted DB/backup access. Checksum is not authentication against hostile DB administrators; optional external-key HMAC would be separate hardening. |
| SQL injection | Bound SQLAlchemy parameters; no client-built SQL/table names or eval/pickle. |
| Test tools | Default OFF, separate is_test metadata, explicit dev-only recovery, exclude DEBUG matches from normal history. |
| Secret logs | Redact cookies/auth/guest tokens/passwords/full snapshots/private events; metadata-only structured logs. |

DB/backups contain trusted game secrets and account hashes; app-private credentials/network and controlled backup access are required. No claim that a Visible bank hides deductions already accepted by ADR-005. Retention applies to chat too; disclose that bounded chat is stored server-side.

## Future Docker and dependencies

Browser → Nginx → FastAPI → Python runtime + PostgreSQL. Future Compose adds private postgres with named data volume/healthcheck, backend DB secret and startup recovery readiness; only web exposed. One worker remains mandatory. Migration job runs once before accepting traffic; do not independently auto-migrate from every request/worker. Add Nginx `/api/` proxy because current config routes only /ws and /health to backend; otherwise auth URLs become SPA HTML. HTTPS/same-origin and explicit localhost dev mode are prerequisites for cookie auth. Volume is not backup; plan actual backup/restore drills. No Docker changes now.

Current server requirements have FastAPI/Uvicorn/websockets/Pydantic but no DB/migrations/password library. Recommend SQLAlchemy 2.x + Alembic + psycopg 3 async driver; choose exact supported pins at implementation. AsyncSession per operation/task, explicit transactions and no shared global session. Direct psycopg is viable but would duplicate mapping/migration management across membership/auth/history; SQLModel adds another model layer without replacing typed engine dataclasses. Do not add both psycopg and asyncpg unnecessarily. Auth Phase adds argon2-cffi only when needed. No dependency modernization in architecture phase.

## Proposed modules and incremental adoption

```text
app/persistence/
  snapshots.py       full private codec, versions, validation
  db.py              engine/session lifecycle
  models.py          SQL schema only
  repositories.py    room/seat/match reads and explicit transaction writes
  coordinator.py     locked candidate → durable commit → runtime promotion
  recovery.py        reconstruct Rooms at startup
app/auth/
  passwords.py       Argon2id
  sessions.py        cookie credential + expiry/revoke/CSRF
  service.py         register/login/claim orchestration
  routes.py          safe HTTP DTOs
```

Do not introduce generic repository interfaces/DI frameworks per table. Room/PlayerSlot/RoomManager and shared GameState remain. Extract only affected commit paths into coordinator, preserve executor/projection and compatible wire IDs. New persisted UUIDs can be fields alongside legacy IDs. Pilot behind explicit server mode on an isolated stack; production durable mode must never silently fall back to in-memory writes after DB error. Current running RAM games are not magically present in a new DB: controlled drain/finish is simplest initial rollout. If live import is required, freeze rooms, encode/verify state and hash received tokens before switching; separate authorized maintenance step, no offline Qt import by default.

## Checkpointable phases

| Phase | Scope and exit condition |
| --- | --- |
| Persistence 1A — codec | **Completed 2026-10-06.** Full private codec v1, no DB; actual JSON/type equivalence, all presets/lifecycles/privacy/corruption, full pytest 445/445. |
| Persistence 1B — durable guest backend | Postgres/schema/migrations, room/seat/match/snapshot/receipt adapter, hashed guest credentials, locked writes and startup recovery, timer policy, bounded chat/feed, crash/replay tests, isolated Docker restart. Persistent tokens/seq belong here: recovering a game without usable ownership/replay protection is not a safe checkpoint. |
| Persistence 1C — Continue | Guest browser binding discovery, safe active-game DTO, automatic verified Continue/refresh/restart smoke; no auth required. |
| Auth 1 | Users/passwords/cookie sessions/CSRF/Origin, ownership claim/takeover/logout, account Active Games, TLS/development profile. No mandatory registration/reset/social login. |
| Profile | Owner-authorized finished history/results; stats/public-profile decisions separately, no private snapshot exposure. |

Before 1B approve proposed timer downtime, expiry/retention and lifecycle retry contract. Checkpoint each only after its own restart/privacy/crash tests; do not label persistence/auth completed from this design document.

## Future testing matrix

- Codec: full dataclass equality after JSON, not equality of incomplete to_dict views; all fields covered by an explicit schema-completeness guard; 2/6 players, Base/Seafarers/custom, IDs/topology, bank/nonnegative/conservation, deck order/new cards/hidden VP, offers/next ID, pending robber/pirate/discard/gold, setup/current turn/flags, achievements.
- Road Building: restart with 0/1/2 remaining appropriately; rejected placement unchanged; successful End clears unused roads, existing roads remain and later paid road requires resources. Save/restore must not reintroduce the fixed lifecycle bug.
- Room: settings including nullable target override, selected custom/preset definition, config/map/chat revisions, colors/host/compact pid, balanced exact order/refresh boundary, confirmed dice/count, bounded chat, private event audience/id and rematch reset.
- Timer: future/expired UTC deadline, recovery waiting/grace, Off/setup/finished/blocked/stopped, pending/free roads and DB outage. Fake clock unit tests plus real process restart; no dependence on a long sleep.
- Crash points: before mutation, before commit, failed commit, ambiguous commit, after commit before runtime promotion/broadcast/ACK, partial publication, final rejection before ACK. Restore latest committed tick/full state, verify retry once and same cmd_id/different payload conflict. Timer/client race and overlapping join/rematch/config are serialized.
- Credentials: received guest token works after real backend restart; wrong/expired/revoked token fails; raw token absent DB/logs; hashed-token reconnect response; duplicate names cannot claim seat; old socket commands/finalizer fenced; retired rematch token cannot take new pid. Unreceived bootstrap orphan documented/tested.
- Auth: Argon2 verify/reject/rehash policy, username normalization uniqueness, login cookie flags, session issuance/renewal/absolute expiry/revocation/logout, CSRF/Origin, foreign account Active Games denied, same account second device Continue and guest claim conflicts. No guest token bypass after account bind.
- Compatibility/retention: old supported snapshot migration, unknown/corrupt head quarantine without silent rollback, independent healthy room recovery, no reshuffle/regeneration, normal finish vs superseded/test history and snapshot cleanup never deletes active head.
- Implementation verification: full pytest if server/codec runtime changes, relevant web tests/TypeScript/build when UI changes, Docker build + actual isolated stop/start with two clients. Scenario baseline 348/508 remains historical until re-run in that phase; do not weaken its assertions to certify persistence.

## Retention — proposal, no scheduler now

Lobby with no authenticated activity: expire after 7 days. Active matches remain while used; 30 days without authenticated activity may mark abandoned, preserving last checkpoint for recovery grace/manual handling rather than immediate delete. Define activity explicitly (accepted command/validated reconnect/config/chat), not arbitrary unauthenticated lookup or current inconsistent last_activity_ts writes. Account access alone must not mutate an unrelated match.

Finished normal results retained indefinitely in v1; full finished snapshots/private feed kept 30 days then pruned, with only normalized safe result left. Active head is never pruned; keep head plus two prior checkpoints for diagnosis, receipts last 256 and current consumed seq throughout active match. Superseded/abandoned snapshots retained 30 days before cleanup; room code tombstones retained without private payload and not reused. Expired sessions/credentials cleaned after audit grace; secrets never move into public archives. These time values and indefinite-result policy require product approval; account erasure/privacy policy is future work, not promised by this plan.

## Blockers and recommended next step

Codec prerequisite is now closed by a separate full v1 surface; existing to_dict/from_dict remains incomplete and must not be substituted for it. Phase 1B gates remain: commit ambiguity handling, lifecycle idempotency absent from current controls, async Room/timer/socket races, downtime timer policy, ownership stability across compact rematch and deployment TLS/readiness/backups.

**Next separate implementation task: Persistence Phase 1B — durable guest backend adapter and real restart/replay recovery**, using the verified codec. Do not start it automatically; auth/Continue UI remain later checkpoints.

## Audit evidence and sources

Architecture audit read project memory and actual server_mp.py, room_options.py, game_events.py, engine state/serialize/rules, ui_v6 offline save/load, App/wsClient and requirements/deployment configuration. That initial docs-only audit used a synthetic Python -B probe, no runtime checks. Subsequent Phase 1A verification is explicitly recorded above; historical 128 web/348 scenarios remain checkpoint evidence, not new verification.

Primary documentation checked 2026-10-06: [SQLAlchemy asyncio/session concurrency](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html), [OWASP sessions](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), [OWASP password storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html). Exact package versions remain an implementation-time decision; no dependencies installed.
