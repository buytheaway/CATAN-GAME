---
tags: [catan, seafarers, план]
updated: 2026-10-09
---

# Seafarers S2B-1 — explicit scenario rules

[[Project State]] · [[Карты и сценарии]] · [[Правила Seafarers]] · [[Architecture Decisions]]

## Scope and checkpoint

Historical S2B-1 checkpoint scope below. S2B-2B.1 supersedes new writer/marker with v4/3 and S2B-2, retaining explicit old schemas and non-fog rules. Trusted fog foundation is implemented/tested; public fog gameplay remains DISABLED. Current boundaries — [[plans/seafarers-fog]], [[Project State]].

**Completed/verified 2026-10-09; READY FOR CHECKPOINT in explicit custom scenario scope.** S2A is committed as `e79dee4`; the working tree was clean before this task. A completed-phase commit and clean working tree satisfy the checkpoint gate. Tags are optional unless the user explicitly requires one. No automatic commit/tag. Named presets retain their approved existing rules; unapproved per-preset parameters remain deferred.

Flow: custom map JSON → materialized board/topology → shared Python scenario configuration → setup/build validation → candidate GameState → PostgreSQL COMMIT → personalized snapshot/legal → existing React controller and renderers. Recovery restores recorded state, without executing gameplay rules.

## Initial inventory and exact preset policy

All four existing presets are custom project maps, not reproductions of official scenarios. None currently declares starting islands, exploration, or special island VP. Preserve their map IDs, JSON, gameplay flags and target (room overrides still apply).

| Preset | Land / sea; island IDs | Existing mechanics retained | Start restriction / island bonus / target |
| --- | --- | --- | --- |
| `seafarers_simple_1` | 13 / 6; `0` | Ships, no Gold/pirate/movement | None / 0 / 10 |
| `seafarers_simple_2` | 19 / 18; `5` | Ships, sea ring; no Gold/pirate/movement | None / 0 / 10 |
| `seafarers_gold_haven` | 15 / 22; `4`, `13` | Two islands; Gold, pirate, movement; offboard robber | None / 0 / 10 |
| `seafarers_pirate_lanes` | 13 / 24; `9`, `13` | Two islands; Gold, pirate, movement | None / 0 / 10 |

The [official Seafarers rulebook](https://www.catan.com/sites/default/files/2021-06/catan-seafarers_2021_rule_book_201201.pdf), pp. 5–8, assigns special VP per scenario. Heading for New Shores starts on the main island, awards +2 for each player's first settlement on each smaller island, and targets 14 VP. The Four Islands has different setup/bonus conditions. Those rules do not establish a product specification for Gold Haven/Pirate Lanes. No official map, target or bonus is silently assigned to these custom presets. Fog/discovery is deferred.

## Explicit custom configuration

Optional `rules.scenario` object:

```json
{"starting_islands": [4], "new_island_vp": 2}
```

The values above illustrate an explicitly configured custom map, not new defaults for Gold Haven. Allowed keys only; starting islands are nonempty unique stable component IDs (minimum original tile index). Omitted/null means unrestricted. `new_island_vp` is an explicit nonnegative integer; omitted/0 disables awards. Scenario mechanics require Seafarers. References are checked against the materialized board; no scenario-name dispatch. Random terrain with explicit starting IDs requires an unambiguous, validated materialized topology.

Setup settlements must touch an allowed component when configured. Existing land/distance/supply checks and anchored road/ship choices remain authoritative; React receives filtered legal targets. Restricted setup additionally rejects openings that leave too little distance-rule capacity for the remaining snake placements. Capacity uses maximum matching of the bipartite hex-intersection graph, not an exponential search or a map generator. Undersized starting regions fail before match creation. This guard is disabled for unrestricted setup/Base. Setup islands actually occupied by each player are recorded as that player's home islands when bonuses are enabled. Setup never awards bonus VP. A main-phase legal settlement on a non-home island awards the configured extra VP once per player per island; another player's settlement does not consume it. City upgrades and further settlements on that same island do not award it again. Bonus points are public, included once in total VP, and checked through existing own-turn victory timing. Hidden development VP remains private during play.

Validate setup for 2–6 players on explicitly configured layouts with adequate space, and retain the existing presets' setup regressions. Arbitrary custom maps and every possible blocking opening are not certified; this phase does not implement a general map generator or change Base setup strategy.

## State and compatibility

One scenario state groups immutable configuration, per-player home-island sets and awarded-island sets. The award ledger is persisted, not reconstructed from current settlements or VP during recovery. Topology remains derived from the saved board graph.

New trusted writer: codec **v3 / engine_compatibility 2**, with explicit reading of released v1/1 and v2/1; their schemas remain frozen. Legacy states receive a disabled empty scenario state structurally, including old maps whose unrecognized scenario keys were ignored. No VP/achievement reconciliation. v3 explicitly includes Seafarers offboard `-1`, so new writes are no longer disguised as the older contract. Existing S2A v2/-1 records remain readable; they are not rewritten automatically.

New matches: durable immutable `catan-seafarers-s2b-1` marker. Verified `catan-seafarers-s1` matches can continue only with scenario mechanics disabled, preserving their original marker; they do not acquire scenario rules from old map JSON. Unknown/NULL markers retain F2 restriction. A mismatch between S1 provenance and enabled scenario state must fail closed. New rematches use the new marker and fresh scenario state. Existing SQL text metadata is sufficient; no schema migration/backfill.

Rollback: older binaries cannot decode v3. After a head advances to v3, rolling the binary back alone cannot resume that match. Preserve DB backups/head history; no automatic previous-head fallback or codec downgrade. Old pre-S2A binaries also cannot read v2 offboard states; metadata/codec checks cannot retroactively repair that already released boundary. Do not use a pre-F2 backend to bypass ruleset restrictions.

## Verification plan

- Shared engine: restriction/accepted and rejected setup, road/ship choices, 2–6 setup, home islands, different bonus values, duplicates/cities/ownership, resource rejection atomicity, ordinary/hidden/achievement VP and own-turn win.
- Codec/offline/Qt: exact v1/v2/v3 structures, missing ledger rejection, no rule execution, persistent award history and old defaults, Base compatibility.
- PostgreSQL/WS: actual COMMIT/restart/reconnect/receipt, direct invalid commands, old S1 and unknown markers, new rematch state, privacy/F1 regressions.
- React: scenario overview/prompt/public bonus rendering and existing controller/legal architecture; full web tests, TypeScript, production build.
- Real two-client browser acceptance: two custom JSON configurations with different explicitly enabled rules. Report setup and expansion evidence separately from Test Tools funding; do not claim natural full games.
- Full PostgreSQL-backed pytest; unchanged scenario harness baseline **348/508** (140 pre-roll +20 pirate connectivity failures). No assertion rewriting/skips.
- Relevant Obsidian links/file references and final diff/scope review.

## Verified results — 2026-10-09

- Full Python suite with an isolated PostgreSQL database: **881 passed, 0 skipped**, 183.23 s; S2A baseline 823 +58. Added 49 scenario/config/codec cases, 7 authority/PG/WS cases, 1 real Qt round-trip; existing unsupported compatibility parametrization adds one case. Existing tests' legacy fixture envelopes/DB columns were updated to remain real v1/v2 fixtures, not relabel new fields as old.
- Restricted setup: **100 seeded runs** (two archipelagos ×2–6 players ×10 choices/seeds), plus unsafe-opening/capacity rejection. Initial experiment without the capacity guard deadlocked for restricted six-player Gold Haven, so the guard is behavior-based.
- Full web **253 passed** (+3); TypeScript and production build passed. Existing Three chunk 946.95 kB/256.21 kB gzip warning remains, no dependency/renderer change.
- Actual Chrome **154.0.8037.98**, production dist/FastAPI/real isolated PostgreSQL: two custom profiles, **43 commands/3 intentional rejections**. JSON confirmed by both clients; natural setup and anchored ships, configured region filtering/rejection, public +2/+3 awards after paid crossing, duplicate-settlement rejection, city no-reaward, 2D/3D, desktop layout/counter bounds and verified refresh on both clients; ordinary End Turn retains ledger. Resources/dice explicitly supplied through Test Tools; neither a full natural match nor production/device/load certification.
- Full unchanged scenario harness: **348/508**, all 160 failure records exactly equal to S2A (140 pre-roll,20 pirate connectivity). Five successful bot summaries differ only in Qt's nondeterministic seed; pass/fail/steps are unchanged. Scenario files/assertions were not modified.
- Recovery/receipts tested with a new Coordinator, failed COMMIT with no publication/award, accepted replay after restart, fresh rematch epoch/seq/home/award state, native S1 v1/v2 marker preservation and enabled-state/S1 mismatch restriction. Existing F1/F2/Auth suites passed with real PostgreSQL.
- Read-only metadata inventory of the prior isolated S2A test database found 105 S1-marked matches and one NULL marker. These are test fixtures, not production inventory; that database was not rewritten. This task used separate disposable test/browser databases. Production containers/databases were not started or modified.
- The real Qt adapter needed local ScenarioState copying/serialization to avoid losing the new ledger. Actual file save/load and subsequent shared city command preserve existing VP/awards and private ship-turn history. No desktop UI redesign/new scenario selector.

Browser report/screenshots: `%TEMP%/catan-s2b-1/browser-final/`; scenario reports: `%TEMP%/catan-s2b-1/scenarios/reports/`; full pytest XML: `%TEMP%/catan-s2b1-pytest.xml`. These are local verification artifacts, not repository assets or permanent portable links. No Docker build/full natural matches/mobile/load benchmark in this phase.

## Deferred and remaining risks

Preset-specific product parameters remain unapproved and unchanged. Fog/discovery, additional official scenarios, richer scenario editor, S2C generator/balance work and S3 natural full-match acceptance are not implemented here. Largest Army's tied-holder bug was deferred at the S2B-1 checkpoint, then fixed in a separately authorized focused patch; recorded historical scores are not repaired. Current evidence — [[Project State#Largest Army tie handling — focused correctness fix]]. This does not change the historical S2B-1 verification above.
