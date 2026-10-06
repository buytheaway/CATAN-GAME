---
tags: [catan, архитектура, adr]
updated: 2026-10-06
---

# Architecture Decisions

[[00 Главная]] · [[Project State]] · [[Documentation Policy]]

Основание: архитектурные ограничения из предоставленной пользователем инструкции и спецификации правил. Accepted обозначает принятое направление, а не утверждение, что реализация полностью соответствует ему.

## ADR-011 — Separate full trusted GameState codec

Status: **Accepted; implemented/verified 2026-10-06, Persistence Phase 1A.** The user authorized codec implementation from [[plans/persistence-auth]]; database/auth/Room recovery are not implemented.

Decision: full private engine persistence has its own `app/persistence/snapshots.py` surface, separate from existing network/offline serialize.to_dict/from_dict/to_player_dict. Envelope snapshot_version=1 / engine_compatibility=1 contains all shared GameState fields, explicit known dataclass construction and stored materialized geometry; it contains no Room/DB metadata. Restore does not execute commands, generate board or shuffle. Required/unknown fields, primitive types, references and versions fail closed; field-coverage guard prevents silent new engine field loss. v1 is immutable after release; future schemas need explicit version compatibility/migration.

Reason: old serializer omits secrets/counters and old-view equality can hide loss. Extending its network projection base with secrets would risk disclosure. Dedicated JSON/type equivalence, independent objects and original command outcomes prove a usable recovery prerequisite without gameplay/network changes.

Consequences: no server caller yet; full payload is never a client projection. All 40 GameState fields/nested models covered; pieces/port ownership/property aliases are derived from saved board/rules rather than duplicated. Non-JSON metadata and oversized/deep payloads are unsupported explicitly. Full pytest 445/445, including 179 codec cases, all map presets and 50 hex; runtime engine/server/frontend unchanged. Phase 1B still must persist Room identity/ownership/seq/bag/timer/chat/events and implement durable commit/recovery. Qt save remains separate and retains its older integer-key bug.

## ADR-010 — Durable room state and optional account identity

Status: **Architecture direction approved by user for staged work — 2026-10-06; only codec Phase 1A implemented.** Audit base `745d749` / `game-ux-2-3`. Database/auth/product policies below are future scope, not runtime guarantees. Full rationale/schema — [[plans/persistence-auth]].

Decision proposed: retain one backend worker, Room/RoomManager and shared Python GameState as committed active runtime; PostgreSQL provides durability. Normalize room/seat/account/match identity, metadata, sessions and safe final results; use a separate versioned full trusted GameState codec plus private Room checkpoint data. Candidate execution → DB transaction/commit → runtime promotion → personal broadcast/ACK. Persist consumed sequence and bounded receipts including final rejection; serialize timer/lifecycle/commands under a room lock and resolve ambiguous commits before retry. No Redis, broker or event-sourced rules engine.

Reason: process-local rooms/tokens/RNG/timers disappear on restart. Current to_dict/from_dict omits private state and cannot be a complete recovery format; adding secrets to its network-projection base is unsafe. Recovered games need both complete engine state and usable durable ownership/replay protection.

Identity proposed: stable RoomPlayer/MatchPlayer UUIDs coexist with current room code, compact pid and room-local match_id. Guest seat uses hashed bearer credential; optional account uses opaque hashed server session and HttpOnly/Secure/SameSite cookie. Account binding requires both session and guest proof, revokes guest credentials and preserves match membership. New authorized connection fences old owner. No mandatory registration or JWT stack.

Consequences proposed: start with codec-only Phase 1A; implement DB/adapters/recovery/guest credentials together in 1B, then Continue UI, Auth and Profile separately. DB failure blocks new mutations; no success ACK before commit, no silent fallback to an older ACKed checkpoint. Hash-only credential storage changes token issuance/reconnect internals; lifecycle controls need future retry identifiers. Downtime timer grace, retention and account takeover policies remain proposals requiring product acceptance. Current plain HTTP Docker needs TLS before production cookie auth. ADR-001/002/005/006/007/008/009 remain accepted constraints; nothing here modifies runtime or protocol now.

## ADR-009 — Server-owned room policy, independent presentation colors

Status: Accepted; implemented and verified 2026-10-06, Game / Room UX 2.2.

Decision: Room owns validated lobby-only settings, unique slot colors, private balanced_v1 bag, monotonic turn timer and bounded chat. Shared engine receives only the approved starting_pid/target_vp and ordinary roll/end commands. Default starter/dice Random, timer Off, bank Visible. Rematch keeps options/colors/chat, selects starter again and resets match timers/RNG/sequence. Config_revision orders map/settings/colors; request_id confirms settings/color intentions, retaining existing map_revision behavior. Chat has a separate monotonic chat_revision because presence/config and messages have different lifecycles.

Reason: Transport policy needs Room identity/lifecycle, while shared rules must remain independent of React/WS and be usable offline. Colors do not identify players or order turns. One lifespan scheduler avoids dormant tasks per room; pending/free-road states require explicit user choices. Request confirmation must not be inferred from a presence broadcast.

Consequences: Additive room/snapshot fields with VERSION=1; no engine rewrite/state-management library/new dependencies. Automatic timeout uses existing authoritative executor without consuming client seq. UI only counts down remaining and renders server facts. Visible bank is an explicit privacy tradeoff (ADR-005); private RNG bag/deck stay hidden. In-memory room/chat/RNG/timer state disappears on restart; persistence, multi-worker coordination, mandatory automation and desktop feature parity remain separate work. Details and measured limits — [[Сервер и протокол#Room policy — Game / Room UX 2.2]], [[plans/game-ui-redesign#Game / Room UX 2.2 — Match Settings, Timer and Chat]].

## ADR-008 — Same-origin Docker deployment, one backend worker

Status: Accepted; implemented and verified 2026-10-04 as Production Infrastructure Phase 1.

Decision: Два Compose-сервиса: Nginx с production React build и FastAPI/Uvicorn с общим Python engine. Browser использует один origin; exact /ws и /health проксируются backend. Наружу опубликован только web. Backend запускается с workers=1, без reload; оба runtime containers работают non-root.

Reason: Пользователь запросил production-like запуск одной командой. RoomManager/GameState являются process-local, поэтому несколько workers/replicas разделили бы пользователей одной комнаты между независимыми состояниями.

Consequences: Backend readiness проверяется HTTP healthcheck до запуска web. Production WS URL выводится из страницы; local Vite сохраняет VITE_WS_URL. Base images закреплены digest, server dependencies — точными версиями, frontend использует npm ci. Restart теряет комнаты/партии/tokens; контейнеризация не вводит persistence или account auth. TLS и горизонтальное масштабирование требуют отдельной задачи. Инструкции и доказательства — [[Deployment]] и [[plans/containerization]].

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

2026-10-04, Board3D Phase 1: пользователь отдельно утвердил experimental R3F/Three renderer. BoardRenderer сохраняет default SVG; 3D получает тот же player-specific snapshot, вычисляет только визуальные позиции и не получает command callbacks. Python authority и network contract сохранены. Правила/полный interaction не переносятся в meshes; Phase 2 требует отдельного решения. Доказательства — [[plans/board3d]].

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
