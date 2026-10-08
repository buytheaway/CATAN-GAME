---
tags: [catan, архитектура, adr]
updated: 2026-10-08
---

# Architecture Decisions

[[00 Главная]] · [[Project State]] · [[Documentation Policy]]

Основание: архитектурные ограничения из предоставленной пользователем инструкции и спецификации правил. Accepted обозначает принятое направление, а не утверждение, что реализация полностью соответствует ему.

## ADR-015 — Match ruleset provenance and safe legacy restriction

Status: **Accepted by user; implemented/verified 2026-10-08, F2 Strategy C.**

Decision: nullable `matches.ruleset_id` is immutable match-level provenance, separate from `snapshot_version`, `engine_compatibility` and GameState.state_version. Only new matches receive `catan-seafarers-s1`. Additive Alembic `f2a001` leaves existing markers NULL, including v2 heads; absent/unrecognized markers require compatibility review. No timestamp, codec version or successful decode establishes S1 provenance.

Recovery decodes v1/v2 without running gameplay rules. Valid restricted matches load as in_match with ownership intact, not quarantined/corrupted. Backend blocks commands before seq/receipt consumption, legal projection, timer processing/resumption and start/rematch. The commit fence prevents rewriting GameState, timer, epoch or snapshot. Metadata-only Continue, guest renewal, account claim, chat and leave remain possible; restricted writes skip match/result/participant upserts, preserving old VP/achievements/winner/final scores. No personalized match_state is published; public room/inspection metadata describes `compatibility_required`.

Reason: pre-S1 road-only scoring, mixed routes and lost incumbent history cannot safely be reconciled merely by decoding. V2 may contain pre-S1 derived scores after an earlier recovery/write. Format compatibility allows reading, not executing current rules.

Consequences: even a genuine S1 match created before the marker existed is restricted without verified provenance. Finished historical results stay unchanged; restricted rooms cannot rematch, but users can retain their seat, return Home and create a separate current match. No automatic conversion, dual engine, backfill or deletion. Strategy D is a possible future **explicit maintenance operation**, requiring a separate decision and transaction/idempotency/rollback design; it is **not implemented**. Do not manually stamp existing matches current. Older backends ignore this gate and must not be used for rollback. Downgrading the column loses provenance; re-upgrade leaves existing matches unknown.

Evidence — [[plans/persistence-auth#F2 — match ruleset compatibility (Strategy C)]], [[Состояние игры#Snapshot format versus match ruleset — F2]], [[Сервер и протокол#Match compatibility gate — F2]]. ADR-014's v1→v2 progression applies only to independently verified current rulesets after F2; unmarked legacy cannot reach End Turn to clear unknown history.

## ADR-014 — Seafarers turn history and codec v2

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

Status: **Accepted; implemented/verified 2026-10-06, Persistence Phase 1A. Historical checkpoint description below.** Codec remained unchanged in 1B; durable Room adapter uses it. Auth/Continue were unimplemented at 1A, subsequently completed in 1C/ADR-013. Current codec v2 and ruleset gate are described in ADR-014/015; released v1 remains readable and immutable.

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
