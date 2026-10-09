---
tags: [catan, план, движок, seafarers]
updated: 2026-10-08
---

# Seafarers Hardening — S1

Status: **Completed / READY FOR CHECKPOINT — verified 2026-10-08.** Authorized scope: existing core Seafarers rules, mixed routes, ship lifecycle, destination-island connectivity, Gold/pirate correctness and authoritative multiplayer/recovery. No production map redesign/generator, scenario rewards, new expansions, visual/audio/assets, auth/deployment work or automatic commit/tag.

S1/F1/F2/F3 checkpoint subsequently recorded as `seafarers-hardening-s1` → `b5cc066`, verified 2026-10-09. This plan retains S1's dated scope/results. Production-map/coast/offboard limitations recorded below were subsequently addressed in [[plans/seafarers-s2a]]; scenario rewards/fog, natural full matches and other deferred mechanics remain future work.

## Initial audit and affected path

Current checkpoint `0d1c455`; initial worktree clean. Read current engine/rules/legal/serializers, networking/commit/codec and existing tests rather than treating old audit notes as proof. React GamePage/shared board controller → WSClient existing command envelope → owning Room lock/candidate executor → shared Python apply_cmd → durable commit/receipt → personalized snapshot + legal projection → existing SVG/Three renderers. Rules belong only in Python; legal hints execute the same commands on copies.

Confirmed: ships connect directly to roads and through foreign buildings; ship-only destination settlements reject; movement is adjacent-only, can detach, ignores source pirate/new construction/once-per-turn and maritime circle exceptions. Longest Road counts only roads and removes a holder on a qualifying tie. Gold ignores robber blocking, omits second-setup entitlement and deadlocks with exhausted bank. Existing malicious command, pirate trigger/victim and hidden-recipient projections generally work. Production Seafarers maps remain one land component; use minimal test-only multi-island geometry for connectivity.

Primary references for ambiguities: [official 2025 Seafarers rules](https://www.catan.com/sites/default/files/2025-03/CN3083%20CATAN%E2%80%93Seafarers%20Rulebook%202025%20secured%20reduced.pdf), [official Seafarers FAQ](https://www.catan.com/faq/seafarers), [official Base FAQ](https://www.catan.com/faq/basegame). Original [[Спецификация пользователя]] remains the project requirements source; scenario-specific bonuses/fog/rewards stay separate.

## Implementation boundaries

1. Extend existing route traversal with ships only under enable_seafarers; transition kind only through own settlement/city, stop at foreign buildings, never reuse an edge. Keep the shared 2VP award surface; correct qualifying tie retention explicitly and test Base Longest Road as well. Recalculate only after final committed movement/build/interruption, no transient award transfer during removal.
2. Reuse ship placement checks with optional setup anchor/source exclusion. Add topology-only shipping endpoint/closed-path/circle helper, not a second game model. Track active-turn built ships and one successful move; reset at turn cleanup. Reject before mutation, include source/destination pirate checks and real post-removal connectivity.
3. Allow existing setup route to be road or ship and Road Building credit to pay for either in Seafarers. Minimal shared-controller/command flag changes only where current road-only payload prevents engine-valid actions; preserve renderers/style/audio and existing public legal shape.
4. Gold: block occupied Gold, grant second-setup choices, resolve without impossible obligations when bank exhausts. Keep existing recipient ordering; do not invent shortage arbitration or scenario rewards. Existing Seven/Knight/victim/private-feed model remains.
5. New ship-turn fields require explicit trusted codec v2 with strict backward v1 migration, not modification of released v1. All old main-phase Seafarers/movement-enabled saves conservatively lock movement until End because history is unavailable, including unrolled turns with possible free-ship construction. Preserve complete state/offline serialization; keep new private flags out of network projections. Durable Room/receipt/auth architecture unchanged. Older backend binaries cannot read v2 writes.

6. Mixed-route recalculation exposes the old off-turn victory bug: only the active player may win, and entering their turn checks existing VP before Roll. This and qualifying Longest Road tie retention deliberately correct shared approved Base behavior, with explicit Base tests. Other Base achievement/theft/production rules stay outside S1.

## Verification and remaining scope

| Verification | Result, 2026-10-08 |
| --- | --- |
| `.venv/Scripts/python.exe -m pytest -o addopts='' -q -ra` with isolated CATAN_TEST_DATABASE_URL | **694 passed**, no skips; real PostgreSQL 17, separate `catan_persistence_test` DB |
| `npm.cmd test` in web | **235 passed** |
| `npm.cmd run type-check` / `npm.cmd run build` in web | Pass; existing Three chunk-size warning remains |
| `tests.run_all.main()` with unchanged loader/seeds and reports redirected into TEMP | **348/508**, identical failed scenario/seed set to pre-change baseline; suite still exits 1 for 160 historical failures |
| `node web/e2e/seafarers-s1.cjs` using production dist + test-only real WS server + native Chrome | **8 groups, 46 commands / 2 rejections**, Base + three-player Gold Haven, 1920×1080/1440×900/1280×720 |

New Python cases: ships/open topology **22**, route graphs/ties/VP/victory **20**, Gold/Seven/Knight/privacy **31**, actual two-island geometry **4**, real WS **13**, real PostgreSQL restart/account+guest **10**, codec regressions **30**: **130 total** beyond the 564-case baseline. Web adds four controller/SSR behavior cases. Existing setup helpers now resolve Gold; existing movement fixtures age through real turns rather than clearing flags manually.

Mixed-route tests cover switches at own settlements/cities, foreign blockers, branches, loops, edge reuse, ship-only and Base road-only scoring, incumbent/no-incumbent ties, transfer/loss/idempotence, final-movement award and own-turn wins. Shipping covers closed paths with foreign interruption, pure maritime degree and official circle cases. A three-hex test-only forest→sea→fields board has disjoint home/destination islands and uses ordinary ship/settlement commands; WS repeats accepted expansion and rejects premature/foreign attempts without mutation. No production island IDs/bonus rewards were added.

Fresh PostgreSQL Coordinator hydration covers exact built/moved flags, End Turn reset, rejected receipts and replay after pruning, setup Gold pending/anchor/index, route/VP/private cards and v1→v2 progression. Both guest token and account Continue are exercised; existing commit ambiguity/outage/dice/timer/auth suites remain green. Live WS comparisons include full engine state and tick/dice/bag/feed/timer for each rejection.

Browser coverage uses actual R3F mouse targets and natural Base/Gold setup. Rare actions are funded with explicitly enabled existing Test Tools; no frontend snapshot/controller/engine mock. It checks initial ships/second Gold choices, two free ships before Roll, construction age, real three-player turn aging, one successful movement/second refusal, fresh token reconnect after refresh, Knight→pirate theft with a private observer, 2D↔3D and resize. Evidence is temporary `catan-seafarers-s1/browser/{report.json,gold-haven-s1.png}`; no asset changes. This is not a full natural match, mobile/Qt interaction certification, low-end/load benchmark or scarcity policy proof.

Scenario maintenance is explicit: qualified tie validation in the harness now matches approved Longest Road semantics, not the previous bug. The Gold scenario resolves its new setup obligation and, for seeds 6/10 where the old map fallback starts robber on Gold, moves it through a real Knight before testing unblocked production. The eight previously failing scenarios were not rewritten to become green. Pirate's old road-only fixture may now reject at placement discovery instead of its later missing-Roll check. No new failing scenario/seed remains.

No confirmed new P0 or blocker-level regression remains in verified S1. Codec rollback requires a compatible backend; old v1 readers reject v2. User `.obsidian/graph.json` / `workspace.json` preferences are preserved separately and not included in S1. No automatic commit/tag.

S2: map/start-island/scenario definitions, offboard initial robber for no-desert scenarios, coastline/auto-port validation, fog/exploration/explicit special VP. S3: full natural multiplayer playtests, scenario balance, broader devices/performance and long-session verification. Existing deterministic theft, general Base production shortage allocation and unrelated achievement/victory mismatches are separate unless required by the affected route flow. Do not silently turn their current bugs into intended rules.
