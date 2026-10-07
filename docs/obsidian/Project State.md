---
tags: [catan, состояние]
updated: 2026-10-07
---

# Project State

## Board3D — finalized terrain GLBs

**Completed visual integration — verified 2026-10-07.** Все восемь finalized GLB из `web/public/models/terrain/` подключены через TerrainHexVisual/Three GLTFLoader. Одна загрузка на тип, собственные scene nodes на hex, общие geometry/materials. GLB не участвуют в raycasting: исходный простой hex, vertex/edge targets, controller и snapshot IDs сохранены. Loading/error fallback — прежний procedural terrain; ошибка одного asset не заменяет всю сцену. Number tokens и tile feedback рисуются поверх relief без изменения игровых координат; camera footprint учитывает более высокие модели. Sea GLB появляется только на настоящих sea tiles, DecorativeOcean остаётся отдельным статичным декором.

Verification: **169/169 web tests** (162 прежних + 7 focused cases), TypeScript и production build. Все 8 GLB попадают в `dist/models/terrain/` без изменения bytes. Chrome 154/production frontend + существующий isolated fixture server: **11/11 acceptance groups** — Base natural setup/Roll, paid settlement/city/road, free roads, Knight/robber/victim, ship/move/pirate на Gold Haven, exact dice, production/theft flights, hover всех восьми terrain, camera, 2D/3D, reconnect/refresh и missing-Mountains fallback. Gold Haven 1920/1440/1280 desktop framing/layout прошёл. Snapshot rerenders сохраняют terrain clone UUIDs; toggle использует кеш, idle +0 frames. GLB/.blend/.blend1 и пользовательский graph.json не менялись.

Performance measured before/after on RTX 5050 Laptop, 1920×1080, two 19-tile presets, 20 warm renders with GPU completion: Base **2.2 → 10.2ms**, Gold Haven **1.9 → 10.3ms** median; rendered triangles **22,020 → 275,562** / **19,658 → 233,010**. Fields сохраняет исходные ~44k triangles и является основным вкладом в Base. Заметного зависания камеры на проверенном GPU нет, low-end/mobile/50-hex GLB performance не сертифицированы; asset optimization не выполнялась. Build сохраняет warning о крупном lazy Board3D chunk (~939kB).

Python runtime, server, protocol, auth/persistence, Docker, dependencies и unrelated UI не менялись; pytest/scenarios/Docker не повторялись. Browser server использовал existing engine-built fixtures и opt-in Test Room для управляемых событий; естественно проходились Base setup/Roll, не полная партия. Fixture запускается без auth DB: его прежние /api/auth/me 503 исключены из renderer checks; Auth acceptance этим этапом не повторялась. Evidence/screenshots/measurements находятся в `%TEMP%/catan-terrain-integration/`. Детали — [[plans/board3d#Terrain GLB integration — visual scope]], [[Design System#Finalized terrain GLBs — implemented]].

## Auth Phase 1 — Accounts and Account Continue

**Completed — verified 2026-10-07. READY FOR CHECKPOINT.** Implemented after `4cdfc1a` / `persistence-phase-1c`: username/password registration, login/logout, database-backed opaque HttpOnly sessions, direct account-owned Host/Join, explicit guest claim, safe My Active Games and cross-browser Continue. No profiles/history/OAuth/reset/email or gameplay changes.

Alembic `f1a001` adds users, hash-only user_sessions and nullable RoomPlayer.user_id; partial unique active room/user index prevents two seats for one account. Existing NULL-owned guest rooms/matches/tokens survive upgrade. Ownership stays with durable RoomPlayer UUID; pid/epoch/sequence come from the existing WS identity flow. Guest credentials remain separate. Claim requires session + valid guest token, atomically assigns ownership/revokes the token, preserves pid/name/GameState and only upgrades the requesting active socket when its in-memory connection nonce matches; otherwise the old controller is fenced. Login/register never auto-claim. Lost claim success can retry idempotently for the same owner/proof.

Argon2id: 19 MiB/t=2/p=1, random library salt, rehash on successful login. Username ASCII 3–32, trim/lowercase, no controls; display name Unicode 1–32 without controls/formats; password exact Unicode 10–128 code points/≤512 UTF-8 bytes. Session absolute expiry 30 days, last_seen writes at most once/5 minutes. New login/register rotates the incoming browser session; logout revokes only that session and fences its sockets. Account command transactions share-lock session/user before mutation; private snapshot publication revalidates account sessions. Transient DB failure keeps recovery intent; confirmed expiry/revocation stops retries.

Production defaults to Secure/HttpOnly/SameSite=Lax/Path=/ cookies and exact HTTPS `CATAN_AUTH_ORIGINS`. Local HTTP requires explicit `CATAN_AUTH_MODE=development`; existing same-origin guest HTTP and Origin-less desktop guest WS remain supported. Browser cookie WS validates Origin. Vite now proxies `/ws` as well as `/api` so cookies stay on the site origin; explicit guest WS override remains. Public internet deployment still requires HTTPS/operational hardening.

Verification: **564/564 pytest**, including **90 real-PostgreSQL cases**, **162/162 web**, TypeScript/production build, Docker backend/web, host/container pip check and nginx -t. Previous-schema upgrade preserved guest match/head/token. Real Chrome 154/Nginx/PG **10/10 Auth acceptance checks**: ordinary mixed room setup/Roll, cross-browser takeover, foreign denial, logout/old-cookie replay, SIGKILL and full down/up without -v, explicit guest claim/current socket/new browser/restart, logged-out guest Recent/Continue/Roll. Screenshot inspected; 1920/1440/1280 desktop checks passed. Local browser medians: login 27.3ms, /me 4.9ms, Active Games 7.7ms (6 samples), WS account Continue 24.3ms (3 samples); not load testing. Engine/codec/rules/player projection unchanged; scenarios not rerun, **348/508 historical**.

Отдельно на текущем Auth image повторён весь прежний guest Continue E2E: **10/10**, включая две комнаты, refresh, cached-name correction, loading/503/retry, backend SIGKILL, down/up с сохранением volume и удаление только подтверждённо закрытой binding. Проверки выполнялись в изолированном `catan-persistence-test`.

Отдельная Argon2id verification median: **16.9ms**, 12 samples, настоящий worker-limited verify в Docker Python 3.12, без DB/network. Login 27.3ms выше включает полный HTTP/DB/session path.

No confirmed Auth Phase 1 blocker. Remaining scope: production TLS/backup/load/retention, future account recovery/password reset/profile/history only on separate request. One worker and one controlling socket/seat; auth limiter is process-local and default Nginx may share peer budget. Password/session secrets are not logged or cached in browser JS; HttpOnly does not prevent an XSS from making authenticated requests. Details — [[plans/persistence-auth#Auth Phase 1 — completed 2026-10-07]], [[Architecture Decisions#ADR-013 — Account sessions and durable seat ownership]]. Checkpoint: `feat: add account authentication and game ownership`, tag `auth-phase-1`.

## Persistence Phase 1C — Continue Game / Recent Games

**Completed — 2026-10-06. READY FOR CHECKPOINT.** Landing показывает компактные dark Recent Games над прежним Create/Join. До 10 browser-local guest proofs в `catan_recent_games`, schema version 1: room_code, reconnect_token, last_known_name, last_seen_at; optional server_url защищает ручной WS override от проверки на другом backend. Старые `catan_reconnect_<room>_<name>` мигрируют без pid; старые ключи удаляются только после успешной записи соответствующего proof в новый список; overflow keys сохраняются до появления места. GameState/руки/dev cards/DB UUID не кэшируются.

`POST /api/reconnect/inspect-many` проверяет до 10 credentials одним read-only PostgreSQL metadata SELECT. DTO содержит только room/map/own name/color/counts/status/target VP/updated time и optional public winner. Private snapshots не читаются; inspection не bind/renew/resume/mutate. Server name/color authoritative. Continue использует прежний WS reconnect; token подтверждается повторно, pid/match/seq приходят с сервера. Retained rematch proof остаётся одной entry, excluded/closed/expired/revoked proof удаляется отдельно после подтверждённого отказа. 503/429/network/DB failure сохраняют список.

SessionStorage pointer на room/name/server (без token/pid) позволяет той же вкладке автоматически восстановиться после refresh. StrictMode не дублирует старт; permanent rejection не запускает повторный reconnect или Join по имени. Explicit leave убирает только current pointer, оставляя Recent. Loading/outage затрагивают лишь Recent, Create/Join доступны. API проксируется Nginx `/api/` и Vite на тот же backend, что configured dev WS; `/ws` сохранён.

Verification: **535/535 pytest**, включая **73 real-PostgreSQL cases**; **150/150 web**, TypeScript, production web build, Docker backend/web, nginx -t и pip check. После последних WS изменений повторены live-server Join/reconnect case и Chrome smoke свежего Docker-образа: Host/Join/Start, refresh двух клиентов, Continue с тем же room/match/tick и privacy без browser errors. Chrome 154/Nginx/PG: **10/10 E2E checks**, обычные два клиента, Host/Join/Start/natural setup → backend SIGKILL → card/Continue → same seat/match/state/deck/bag → accepted Roll → automatic refresh → full down/up без -v → Continue. Две bindings, lobby Continue, cached-name correction, held loading/503/retry и internal durable close одной комнаты с accepted End в другой. Итоговый screenshot просмотрен, старый layout Connection/Room сохранён. Median browser HTTP latency, 12 samples: single **8.2ms**, batch 5 distinct valid proofs **8.4ms**. Local Docker Desktop, не load benchmark.

Проверки destructive restart выполнялись только в `catan-persistence-test`, normal stack на :80 не перезапускался; volume сохранялся. Сценарии не повторялись: engine/rules/codec/Board3D/personal serializer неизменны, **348/508 historical**. Нет подтверждённого нового blocker в scope 1C. Auth/Profile/history/TLS/backup/retention/multi-worker и прежние gameplay P1 остаются отдельными задачами. Guest proof остаётся localStorage bearer: XSS/потеря browser storage лишают защиты/восстановления, nickname не помогает. Один active socket на seat; новая verified вкладка заменяет ownership. Legacy bindings без адреса предполагают default backend; known manual-server proofs не отправляются чужому endpoint. Checkpoint: `feat: add continue game recovery experience`, tag `persistence-phase-1c`. Auth автоматически не начинается.

## Persistence Phase 1B — Durable Multiplayer State

**Completed — 2026-10-06. READY FOR CHECKPOINT.** PostgreSQL хранит committed Room/Match, private codec v1, hashed guest credentials, consumed sequence/receipts, точный Balanced bag, UTC timer, config/colors/membership/revisions, последние 50 chat messages и 80 canonical private events. Активная модель остаётся Python Room/GameState в памяти одного backend worker. Durable mutation проходит общий room lock: candidate → SQL transaction/COMMIT → RAM promotion → personal broadcast/ACK. Отказ записи не применяет и не подтверждает candidate; неопределённый COMMIT разрешается чтением head/receipt, без повторного random effect.

Startup выполняет Alembic и восстанавливает lobby, active и finished-awaiting-rematch rooms без build_game/shuffle. Все места сначала disconnected. Старые received guest tokens работают; DB содержит SHA-256, не raw token. Stable Room/RoomPlayer/Match UUID не заменяют room code, compact pid и integer match_id. Retained rematch member сохраняет credential; excluded member retired/revoked. Timer после recovery paused до первого verified reconnect, затем минимум 20s с сохранением pending/blocked/stopped. Closed/expired/abandoned/Test Rooms не загружаются; corrupt head quarantined без fallback на older ACKed state.

Проверено: **508/508 pytest**, включая **63 real-PostgreSQL cases**; **130/130 web**, TypeScript, production web build, Docker backend/web и pip check. Отдельный Windows backend process + реальные WS: kill/restart, same tokens/state/seq, wrong/revoked tokens, old pid mismatch. Chrome 154 + Docker/PostgreSQL/Nginx, два обычных клиента: Base setup → Balanced Roll → naturally funded paid road/chat → refresh → backend SIGKILL → next action → second restart → PostgreSQL stop/start → full down/up без -v. Отдельный explicit isolated down -v подтвердил удаление данных. Проверены Hidden bank/privacy, private deck/bag/state digests и no success during DB outage. Startup без DB: health 503, retryable error + WS 1013, no RAM fallback.

Локальная median durable latency, 12 warm samples на command: Roll 22.23ms, Road 22.47ms, bank Trade 22.70ms, End 22.36ms; encode 2.10–2.35ms, SQL transaction 19.68–20.50ms. Это Docker Desktop PostgreSQL 17.11 / Windows Python 3.13, не production/load benchmark. Engine/rules/maps/codec/network privacy/UI не менялись; scenario suite не повторялась, **348/508 остаётся historical**. Единственный frontend runtime diff — lifecycle retry в WSClient; Board3D/React/CSS не затронуты.

Ограничения: один worker/replica; нет accounts/auth, Continue UI, automatic retention/cleanup и backup system. Refresh требует прежний Join/name/room/token flow. Local dev без DATABASE_URL остаётся memory mode; Compose принудительно durable и не деградирует при outage. Guest token expiry — 30 дней authenticated inactivity. Неполученный issuance token нельзя восстановить по имени. Live RAM rooms старого image не импортируются автоматически; нужен отдельный controlled rollout. Details — [[plans/persistence-auth#Persistence Phase 1B — implementation and verification]], [[Сервер и протокол#Durable command and recovery flow — Persistence 1B]], [[Deployment#Persistence verification — 2026-10-06]], [[Architecture Decisions#ADR-012 — Durable commit gate and conservative restart]].

Checkpoint существует: commit `1e4dfb9`, tag `persistence-phase-1b`. Следующие Continue/Auth/Seafarers этапы требуют отдельной задачи. Existing `.obsidian/graph.json` preference change оставлено вне scope.

## Persistence Phase 1A — Full Trusted GameState Codec

**Completed — 2026-10-06. READY FOR CHECKPOINT.** Separate `app/persistence/snapshots.py` exposes encode/decode/dumps/loads for full private shared-engine state. Envelope snapshot_version=1 / engine_compatibility=1; all 40 GameState fields and nested dataclasses preserved through JSON, explicit int/tuple/set restoration, materialized board IDs/order, complete private deck/cards/bank/pending/free_roads/counters. Exact shapes/versions/types/references, duplicate keys/IDs and format limits validated; no generation/shuffle/repair/automatic defaults. Details — [[plans/persistence-auth#Persistence Phase 1A — completed 2026-10-06]], [[Состояние игры#Full trusted persistence codec v1]], [[Architecture Decisions#ADR-011 — Separate full trusted GameState codec]].

Full pytest **445/445** passed: 266 checkpoint tests plus **179 codec cases**, including 30 pre-implementation characterizations. All 12 map presets/50-hex custom fixture, Base lifecycle/dev/trade/endgame, ship/move/pirate/gold, command continuation/atomic refusal, deep type equivalence, mutation independence and active/final Hidden-mode privacy verified. Existing to_dict/from_dict remains incomplete; to_player_dict/server/engine runtime were not changed. Qt offline JSON-key issue was audited but not fixed.

Measured 100-sample local median: Base 7,662 bytes / encode 1.250ms / decode 0.842ms; Gold 7,778 / 1.239 / 0.826; 50-hex 16,363 / 2.715 / 1.741. Includes validation/text JSON, excludes DB/fs/network and long-match growth. No new dependencies, Docker/auth/HTTP/WS/React changes. Web/build/scenarios not rerun because those paths/engine were untouched; **348/508 is historical**.

At the 1A checkpoint Room durability was still absent; it is now implemented separately by 1B above. Room bag/timer/chat/private event feed/ownership/revisions are NOT in this engine codec. Codec schema v1 freezes at checkpoint; unknown/new fields need explicit compatibility review. Checkpoint message `feat: add versioned game state persistence codec`, tag `persistence-phase-1a`; not created automatically. Existing `.obsidian` preferences remain outside task.

Предыдущая verification: **2026-10-06 — Game UX 2.3 Completed, READY FOR CHECKPOINT.** Полный pytest **266/266**, web **128/128**, TypeScript, production web build и оба Docker images проходят. Docker/nginx + Chrome 154: **27/27 E2E cases**, 103 command attempts, 12 ожидаемых refusals. Scenario suite повторена: **348/508**, прежние 160 failures в восьми сценариях; assertions/rules для них не ослаблялись. Scope/evidence/limits — [[plans/game-ui-redesign#Game UX 2.3 — Playtest Feedback Pass]], [[Design System#Game UX 2.3 — implemented playtest feedback]].

Игроки и timer справа, Log/Chat сворачиваются, Bank виден как animation anchor. Hand — пять мини-карт со stack/count; Knight/Road Building играются прямо из руки, Monopoly/Plenty открывают необходимый picker, VP passive. Trade Tray отправляет existing broadcast offer или maritime trade отдельными кнопками. Discard выбирается картами; новый host-only lobby setting `discard_threshold` default 7, strict hand > threshold, прежняя floor(hand/2), locked после Start и сохраняется при rematch.

Server Room хранит bounded personalized game_events (80), добавленные только после успешных commands. Exact production cards видит получатель, stolen type — только thief/victim; observer получает back/generic event. Snapshot остаётся authoritative, animation не изменяет ресурсы. Test Tools: `CATAN_ENABLE_TEST_TOOLS=1` + явное Enable Test Room в lobby + active host ownership; normal room запрещает test_action даже с включённым env. Все named actions validated/logged, default OFF, нет arbitrary code/raw editor. Контракт — [[Сервер и протокол#Game UX 2.3 — personalized events and Test Mode]].

Board3D получил static decorative ocean, отдельные terrain visuals, finite robber movement и 2500ms dice roll/settle/linger/fade. В сравнении с UX 2.2 Base шире на 22–24%, выше на 17–19% на трёх desktop размерах; SVG/controller/IDs сохранены. Base/Gold/50 hex fixture: idle +0 frames, 50-fixture 2D switch освобождает geometries/textures. Новое найденное перекрытие top vertex подсказкой исправлено переносом prompt в свободную середину header. Live socket reconnect уже automatic; refresh сохраняет token, но требует обычный Join — identity не менялась.

Дополнительно обычный production stack на http://localhost с Test Tools OFF прошёл двумя Chrome-клиентами настоящие setup → Roll → 2D/3D → End (10 commands), без fixture initializer. Локальные containers обновлены текущими проверенными images; public deployment не выполнялся.

Ограничения: rare states prepared только isolated test fixture, не полная естественная партия; mobile/low-end FPS/load/Qt new-feature parity не сертифицированы. Visible bank допускает two-player deductions. Three chunk warning и прежние gameplay P1 остаются. Dependencies, map JSON/generator, Seafarers rules, auth/persistence не менялись. Checkpoint: commit `feat: refine gameplay UX from playtest feedback`, tag `game-ux-2-3`.

Предыдущая verification: **2026-10-06 — Game / Room UX 2.2 Completed, READY FOR CHECKPOINT.** Полный pytest 234/234, web 119/119, TypeScript, production web build и оба Docker images проходят. Chrome 154: 19 E2E cases, включая два новых двухклиентских Visible/Hidden flows. Сценарии действительно повторены до/после изменения setup: **348/508**, те же 160 отказов с идентичными outcomes/failure details. Настройки комнаты, случайный starter, независимые цвета, Balanced dice, server timer, plain-text chat и bank visibility реализованы. Engine менялся только для rotated setup/первого main turn; прежние gameplay P1 не исправлялись. Доказательства/limits — [[plans/game-ui-redesign#Game / Room UX 2.2 — Match Settings, Timer and Chat]], [[Design System#Game / Room UX 2.2 — implemented room policy and HUD]].

Defaults: Dice Random, starter Random, timer Off, bank Visible; target VP следует preset до явного host override. Только host меняет настройки до Start; после Start они locked и сохраняются для rematch. Цвета red/blue/orange/white/green/purple уникальны, назначаются сервером, сохраняются при reconnect и compact pid. Config/request ordering не допускает откат pending/new settings; прежний map_revision flow сохранён.

Timer существует в Room и обслуживается одним lifespan scheduler: main only, expiry до Roll → ordinary Roll +20s, после Roll → End только без pending/free_roads. Countdown между snapshots — UI; сервер использует monotonic clock. Чат отдельно от transport log: последние 50 сообщений, 500 символов, 5/10s на слот, plain text. Visible публикует точный bank, Hidden сохраняет bank_available; seed, RNG bag, deck и чужие руки/hidden VP закрыты. Видимый банк намеренно допускает deductions в двух игроках.

Проверки используют отдельный Docker test stack; production-комнаты не перезапускались. Browser expiry automation проверяется отдельно fake-clock backend tests; полный естественный матч/mobile/low-end/load не сертифицированы. UI ещё не имеет полного engine event feed, accounts/persistence, общего settings/menu/mobile redesign. Qt игнорирует additive поля; новые settings/chat/timer UI не переносились в desktop. Checkpoint этого этапа: commit `feat: add multiplayer room settings timer and chat`, tag `game-ux-2-2`.

Предыдущая verification: 2026-10-05 — Game UX 2.1 после `dcadcab`: 108/108 web tests, полный pytest 203/203, TypeScript, production/Docker build и 17 Chrome 154 E2E cases проходят. Direct build actions, Ship только при server-enabled ships, cost preview, one-click buy_dev, resource-hand Trade Tray, точные server dice и конечная 950ms 3D-анимация, two-endpoint port docks, более насыщенные terrain/pieces. Base и Gold Haven проверены на 1920×1080, 1440×900, 1280×720; размер Base land относительно baseline вырос примерно на 17–19%. Engine/rules/legal/serialization privacy/maps/dependencies не менялись; server добавляет публичные Room.dice/roll_count в snapshot. Сценарии не повторялись: последний реальный результат 348/508 ниже. Prepared states используют настоящие commands/ACK/engine, full natural match/mobile/low-end FPS не сертифицированы. Scope/evidence — [[plans/game-ui-redesign#Game UX 2.1 — Direct Actions / Trade Hand / Dice / Board Readability]] и [[Design System#Game UX 2.1 — implemented direct tabletop UX]]. READY FOR CHECKPOINT; commit/tag не создавались автоматически.

Предыдущая verification, 2026-10-05 — Road Building lifecycle fix после Game UI Phase 2 (`d9a1d07`): полный pytest 195/195 passed, включая 9 новых regression cases. Сценарии до/после: 348/508 passed, те же 160 отказов в восьми сценариях с `Must roll before actions`; outcomes и failure details совпали. Успешный End Turn теперь обнуляет неиспользованный free_roads заканчивающего ход игрока; построенные дороги остаются, legal.road_free=false после End и на следующем собственном ходу. Runtime diff — одна строка в engine.rules.end_turn_cleanup; UI/protocol/legal architecture/maps не менялись. Web/build/browser проверки не повторялись: frontend не затронут. Подробности — [[Инварианты движка#Road Building lifecycle — verified 2026-10-05]].

Предыдущая verification, 2026-10-05 — Game UI Phase 2: 92/92 web tests, 186/186 pytest, TypeScript, production web build, Docker build и 14 Chrome 154 E2E cases прошли. Добавлены bank/player trade, личная dev hand/все пять карт, итоговые VP/winner/results, rematch и явный выход. Prepared games проверены через настоящий WebSocket в отдельном Docker stack; обычный production backend отдельно прошёл двухклиентский Base setup/Roll/End/2D↔3D (tick 10). Backend/rules/protocol/board/controller/maps/dependencies не менялись. Scenario suite не повторялась: 348/508 — исторический baseline. Полная естественная партия, mobile и low-end FPS не сертифицированы. Детали/limits — [[plans/game-ui-redesign#Phase 2 — Trade / Development Cards / Endgame]] и [[Design System#Game UI Phase 2 — implemented actions and results]].

Предыдущая verification, 2026-10-05 — Board3D Polish 1.1: 76/76 web tests, TypeScript, production build, Docker frontend build/up и Chrome 154 headless прошли. Hover использует emissive настоящей плитки; azimuth свободный 360°, tilt/zoom/reset сохранены. Terrain имеет стабильные небольшие вариации, порты — compact dock/placard; декоративные meshes больше не перехватывают legal hits. Base/Gold/50-hex fixture: framing, отсутствие page scroll, 0 дополнительных idle frames, cleanup при 2D switch. Два live React-клиента: Base — setup/Roll/road/robber, 4 хода/tick 18; Gold — setup/Roll/ship/pirate, 17 ходов/tick 50. Move ship и multiple victims дополнительно проверены engine-built fixtures в обоих renderer. Python/protocol/maps/controller/HUD/dependencies не менялись; pytest/scenarios не повторялись. Evidence/limits — [[plans/board3d#Game UI / Board3D Polish 1.1]] и [[Design System#Polish 1.1 visual evidence]].

Предыдущая UI verification, 2026-10-05: Game UI Redesign Phase 1 — 73/73 web tests (65 прежних + 8 UI cases), TypeScript, production/Docker build. Fullscreen match shell, compact HUD/hand/dock, закрытые drawers и default 3D; SVG сохранён. Desktop 1920×1080, 1440×900, 1280×720, шесть длинных имён, drawer/Escape/focus и modal focus trap проверены. Исторические Python результаты: 186 pytest и 348/508 scenarios. Подробнее — [[plans/game-ui-redesign]].

Map/design analysis: 2026-10-04 — код checkpoint `hardening-phase-1` (`3cd8812`), построение всех 12 карт в памяти, повторяемость seed, topology/ports/snapshot/legal и границы map validation. В рамках этого анализа полный test/build/scenario набор не повторялся, runtime и зависимости не менялись; последующая Docker verification указана выше. Подробности — [[Карты и сценарии]] и [[Design System]].

[[00 Главная]] · [[Architecture Decisions]] · [[Результаты аудита]]

## Phase 1 Status

**Completed — 2026-10-03. Checkpoint: `3cd8812`, tag `hardening-phase-1`.** Утверждённые решения VP visibility/rematch закреплены тестами; открытых подтверждённых P0 и новых blocker-level regressions в проверенном scope нет. Это завершение Production Hardening Phase 1, не всей реализации правил CATAN. Прежние 160 сценарных отказов и отдельные P1 остаются за пределами этапа.

## Current Architecture

Общий Python-движок обслуживает локальный PySide-клиент и FastAPI WebSocket-сервер. React/TypeScript получает снимки партии и отправляет намерения. Active Room/GameState живут в памяти одного процесса; PostgreSQL хранит durable committed aggregates для restart recovery. Qt и browser имеют отдельные представления состояния. Multiplayer использует player-specific snapshot, trusted/offline to_dict сохранён, private persistence — отдельный codec v1.

Docker production-like: Browser → Nginx (React dist, /ws, /health) → один FastAPI worker → shared engine + private PostgreSQL с named volume. Только web port опубликован; backend/web non-root, без host mounts. Alembic и recovery завершаются до readiness. Локальный Python + Vite workflow сохранён. Инструкции — [[Deployment]].

Карта архитектуры уже существует: [[Карта файлов]], [[Точки входа]], [[Сценарий сетевой партии]]. Новый дублирующий Architecture.md не нужен.

## Working

- Создание поля из JSON-пресета, начальная расстановка и основной цикл реализованы в движке.
- Desktop offline имеет бот, строительство, обмены, карты развития и сохранения; у этих возможностей есть ограничения и ошибки.
- Сервер обрабатывает комнаты, команды и снимки; web показывает lobby и match с интерактивным SVG-полем.
- Lobby map selection: Room authoritative; map_revision растёт при успешном set_map. WSClient отбрасывает меньшую revision в той же комнате, сохраняет последний pending выбор и держит один запрос в ожидании плюс последний queued выбор. Start ждёт подтверждения; disconnect/смена комнаты сбрасывают pending, reconnect получает актуальную карту сервера.
- BoardRenderer теперь default 3D, компактный 2D/3D selector и прежний SVG/error fallback. Оба renderer получают один snapshot и общий controller GamePage с personal server legal. GamePage размещает BoardControls в нижнем dock; оформление отделено в game/. Gameplay остаётся в Python. Scope — [[plans/board3d]] и [[plans/game-ui-redesign]].
- Production roll принимает только `{type: "roll"}`; две кости генерирует сервер. CATAN_DEBUG_ROLLS больше не открывает публичный debug-путь.
- Game UX 2.1: Room хранит подтверждённые dice=[a,b] и монотонный roll_count, одинаковые у обоих клиентов; engine получает прежнюю сумму. End Turn сохраняет последний pair, rematch сбрасывает pair/counter. HUD не придумывает грани из суммы; reduced motion показывает результат сразу, 3D-анимация заканчивается без idle frames.
- Публичный список команд исключает grant_resources. Helper остался в trusted engine для подготовки тестов и проверяет весь payload перед выдачей.
- Имя не даёт доступ к занятому слоту; reconnect требует существующий токен и отзывает старое соединение.
- React Join использует один transport helper для открытого и подключающегося WS: token выбранной пары room/name → reconnect, отсутствие token → join_room. Смена комнаты/игрока очищает прежний token в памяти; создание комнаты не использует старый token. Отклонённый reconnect очищает соответствующий cache без автоматического Join по имени.
- Каждый старт, включая rematch, включает только подключённых участников, минимум двух; pid уплотняются вместе с сетевыми привязками. Отключившийся прежний участник не создаёт пустое место в новом GameState. Подключённый host запускает rematch; если он отключён, это может сделать первый подключённый участник, который становится host после успешного старта.
- Reconnect token восстанавливает прежний слот до rematch. Сохранившиеся участники сохраняют token с новым pid; исключённый участник теряет доступ к слоту при новом матче. match_id увеличивается; tick, sequence и deduplication history сбрасываются.
- В снимке свои ресурсы/dev-cards и private choices; во время игры чужой VP исключает скрытые VP-карты. После game_over все players.vp содержат итоговые total VP для действующего экрана результатов; чужие res/dev_cards остаются закрытыми. Seed/колода/private RNG bag не передаются; bank counts передаются только при Visible, Hidden сохраняет прежнюю availability-only projection. Колода перемешивается независимо от карты.
- Pirate использует одно разрешённое событие после 7/завершения discard либо Knight: pending `robber_move` позволяет выбрать land robber или sea pirate при enable_pirate. Успех закрывает pending и допускает максимум одну кражу; повтор без нового события отклоняется общим движком. React/PySide клики согласованы с этим событием.
- Trade начинается кликом по собственной resource card: локальный немодальный Give/Want tray над рукой, targets Everyone/connected player/Bank. Bank 4:1/3:1/2:1 по собственным port endpoints, включая прежние batch exchanges; targeted/broadcast offer, accept/reject/cancel и отмена при end turn сохранены. Состав рук не изменяется до snapshot. Изменение offer = cancel + новое предложение; broadcast Reject закрывает offer для всех согласно существующему engine. Закрытый log drawer содержит сворачиваемую bank availability без точных counts.
- Direct Road/Settlement/City и Dev Card в dock; Ship полностью скрыт без enable_seafarers/положительного max_ships. Setup показывает только обязательный инструмент. Стоимость — один presentation config; доступные цели/команды проверяет прежний shared controller/server legal.
- Dev cards: dock Dev Card отправляет один buy_dev напрямую; own hand/type/count/new появляется только после snapshot. Клик по своей карте открывает Play/inspect: Knight через общий robber/pirate controller, две бесплатные дороги, Year of Plenty picker, Monopoly picker и passive VP. UI объясняет new/one-play/turn/pending restrictions; окончательная проверка остаётся серверной.
- Road Building позволяет поставить до двух бесплатных дорог в текущем ходу; неиспользованный credit очищает общий engine cleanup при успешном End Turn. Следующий собственный ход не получает старый credit; построенные дороги и обычная стоимость road сохраняются.
- Results: server winner/final VP, connected-player rematch с прежними tokens/compact pids/sequence reset, Back to Lobby через существующий leave_room. Выход останавливает auto-reconnect; сохранённый token остаётся для явного Join с прежним room/name.
- 108 web cases, 203 pytest, TypeScript/production/Docker build и 17 Chrome UX 2.1 cases проверены 2026-10-05. Scenario baseline 348/508 исторический для этого UI/server-metadata этапа; rules.py не менялся.

## Partially Implemented

- Seafarers: корабли, золото, пират и перемещение есть; полная семантика маршрутов и сценариев не завершена.
- Web UI: trade/dev/results/exit, room settings/colors, chat/timer и bank policy реализованы; отдельное меню, полный lobby/mobile redesign и полноценный game event feed остаются вне scope. Hidden bank/deck остаются закрыты: отказ Year of Plenty/пустой deck проверяет сервер, UI не знает будущих cards.
- Desktop online: диалоги развития и банка отключены.
- Очереди web/desktop теперь привязаны к room/match; отказ расходует seq и удаляется по ACK. Durable guest backend и Continue реализованы в 1B/1C; account auth, backup/retention и Qt offline save остаются отдельными вопросами.
- Старые ошибки TypeScript и секции setup.cfg устранены в рамках проверки контракта/тестов. Сценарный прогон по-прежнему даёт 348/508 успешных запусков: восемь сценариев действуют до обязательного броска. Правило не ослаблялось.

## Known Critical Problems

| Проблема | Статус и место |
| --- | --- |
| Production roll / grant_resources | Исправлено 2026-10-02, проверено через WebSocket |
| Чужой слот по имени | Исправлено; токен и единственный active_ws на слот |
| React Join с token на открытом WS | Исправлено 2026-10-02; повторный reconnect, отказ без fallback, другой room/name и create-room проверены |
| Откат карты в React lobby | Исправлено 2026-10-04; удалены встречные mapId effects, добавлены map_revision/pending ordering. Старые ответы, custom JSON, новый room и подтверждённый Start проверены двумя браузерными клиентами |
| Координаты | Исправлено существование vertex/edge/hex и land/sea; setup нельзя включить клиентским флагом после расстановки |
| Атомарность / Year of Plenty | Подтверждённые места исправлены; весь state сравнивается при отказе. Повторный discard тоже отклоняется |
| Скрытая информация | Персональные снимки; active hidden VP закрыты, final total VP раскрываются. Финальная policy проверена 2026-10-03; чужая res/dev hand и seed закрыты; bank counts закрыты в Hidden, Visible — принятое исключение 2026-10-06 |
| Пустые участники / новый матч | Исправлено; rematch с фактически подключённым составом, обновлённые pid, tokens и sequence проверен 2026-10-03, включая отключение host |
| Повторная кража pirate без события — P0 | Исправлено 2026-10-02: single-use pending, полная atomicity при отказе, WS replay и выбор фигуры обоими клиентами проверены |
| Offline-save | Ключи флагов и бесплатных дорог после JSON становятся строками |
| Seafarers rules | Остаются ограничения смешанных/закрытых маршрутов, Longest Trade Route и полноты отдельных сценариев |
| Остальные Base rules | Требуют отдельного исправления ничьи достижений, победа вне активного хода, детерминированная кража |
| Road Building lifecycle | Исправлено 2026-10-05: end_turn_cleanup очищает free_roads только после успешной проверки End Turn. 0/1/2 placements, следующий собственный ход, paid road cost, сохранение построек, atomic rejects и персональные server snapshots проверены в tests/test_road_building_lifecycle.py |
| Сетевой lifecycle | Persistence 1B реализована: locked durable commits, hashed guest ownership, restart recovery и replay protection. Automatic cleanup/общего WS rate limiting нет; chat limit 5/10s, рассылка последовательная |

Статусы таблицы отражают завершённую Phase 1, включая reconnect/pirate fixes и финальные продуктовые решения. Остальные перечисленные P1 остаются открытыми; исторические доказательства и текущая проверка — [[Результаты аудита]].

## Current Priority

1. Восстановить понимание проекта и поддерживать живую документацию.
2. Стабилизировать правила и серверную авторитетность.
3. Подготовить новый React UI, сохраняя игровое поведение.
4. Затем постепенно рефакторить архитектуру.

Production Hardening Phase 1 завершена в утверждённом scope. Game UI Phase 1 пересобрала match composition; Phase 2 добавила существующие trade/dev/endgame mechanics в web. Room settings/chat реализованы в UX 2.2; отдельный menu/general settings и полный lobby redesign остаются будущими задачами. Board3D Phase 1 реализовала отдельную visual foundation в принятом clean modern tabletop направлении. Fantasy/MMORPG-декор исключён, прежние references остаются historical. Desktop в Hardening Phase 1 получил совместимость с сетевыми данными, отображение доступности банка и согласование выбора robber/pirate по карте. Checkpoint: commit `fix: complete production hardening phase 1`, tag `hardening-phase-1`. Последующие commits сравнивать через `git diff hardening-phase-1..HEAD`; текущие незакоммиченные изменения — через `git diff hardening-phase-1`.

## Map / 3D preparation

- Есть JSON loader, materialization/shuffle и graph builder, но нет генерации topology и map editor.
- Все 12 пресетов имеют одинаковые 19 координат; Seafarers заменяет часть позиций на sea, готового архипелага нет.
- Snapshot используется обоими renderer; Phase 2 добавила персональный server legal с affordability/limits/free-build, move_ship destinations и robber/pirate targets/victims. Проверка команд остаётся в прежнем engine.
- Auto ports используют внешнюю границу всей сетки; у Seafarers часть портов недоступна с land. Map validator не доказывает игровую пригодность custom JSON. Подтверждённые детали — [[Карты и сценарии]]; исправления в этой задаче не выполнялись.
- Актуальный 2D reference просмотрен как layout/readability reference; оригинального файла не найдено, несуществующая PNG-ссылка не добавлена.

## Next Engineering Tasks

- Game UI Phase 2 закоммичен в `d9a1d07`, Road Building fix — `dcadcab`, Game UX 2.1 — `e9db7af` (локальный tag game-ux-2-1 не найден). Game / Room UX 2.2 — f70d845/game-ux-2-2; Game UX 2.3 завершён в проверенном scope, checkpoint message/tag указаны выше. Следующие gameplay/UI этапы требуют отдельной задачи и не начинаются автоматически.
- Дальнейшие UI phases, accessibility/low-end/mobile и gameplay P1 требуют отдельных задач. Историческое перекрытие road targets terrain decoration устранено в Polish 1.1; renderer/controller в Phase 2 не меняются.
- Открытый backlog: привести восемь старых сценариев к законному циклу roll → action → end, сохранив их assertions, и проверить выявленные ими расхождения.
- Дальнейшие ограничения Phase 1 и результаты — [[plans/server-authority-hardening]].
- Уточнить gameplay-композицию, состояния и visual tokens актуального clean tabletop направления в [[Design System]].
- Продолжать UI только по отдельной задаче; актуальная композиция и границы — [[plans/game-ui-redesign]]. Старый [[plans/web-ui-redesign|план React redesign]] остаётся историческим.
- Сохранить разграничение: зелёный pytest/build не заменяет полный набор сценариев и проверку правил.

## Production Infrastructure Phase 1

**Completed — 2026-10-04. Commit f754457 (Docker).** Пользователь называет checkpoint infrastructure-phase-1; локально такой tag при начале Board3D не найден, агент его не создавал. docker compose up --build запускает backend + web; браузер открывает http://localhost и соединяется через same-origin /ws. Health readiness и штатное завершение проверены.

Runtime diff ограничен GET /health в server_mp.py и общим URL resolver для App/WSClient. Engine, карты, gameplay, BoardView/layout/CSS, serialization и protocol/reconnect semantics не менялись. package-lock синхронизирован с уже существующим package.json для чистого npm ci; версии прежних packages сохранены. Server runtime requirements отделены от desktop/tests и точно закреплены.

Проверено в браузере: Host/Join/Start, все 8 setup placements и Roll, 9 successful ACK, обновления обоим игрокам, загрузка assets, отсутствие page errors и hardcoded backend address в bundle. Containers завершаются с exit 0; тестовый Compose остановлен. Images по docker image ls: backend 215 MB, web 93 MB. Persistence/TLS/auth/scaling не добавлены; npm dev/build advisories остаются вне scope. Полные пределы — [[Deployment]], исполненный план — [[plans/containerization]].

## Board3D Phase 1

**Completed — 2026-10-04. READY FOR CHECKPOINT.** GamePage → BoardRenderer → SVG BoardView или lazy Board3D → R3F scene. Оба получают один snapshot. coordinates.ts нормализует готовые centers/vertices в XZ; visual height независима от gameplay. Исходные tile index/vertex ID/edge pair сохранены; renderer не импортирует WSClient и не вычисляет legal/cost/rules.

Все 8 terrain, number tokens, 3:1/2:1 resource ports, owner-colored road/settlement/city и локальные ship/robber/pirate placeholders отображаются. Camera auto-fit учитывает actual bounds/aspect; orbit/zoom ограничены, pan отключён, Reset Camera доступен. Ambient/directional lighting и неглубокие hex meshes; frameloop=demand. 3D clicks лишь инспектируют hex. Обратное переключение в 2D позволяет продолжать placement и игру.

Зависимости закреплены: fiber 8.18.0, three/@types/three 0.180.0; React/Vite/TypeScript и прежние lock versions сохранены. Python, map JSON, protocol/serialization/reconnect и Docker architecture не менялись. Web runtime diff ограничен board3d/, новым BoardRenderer, подключением в GamePage, описанием q/r/null number и dependencies/tests.

Браузерная проверка: Base Standard — два React-клиента; Gold Haven — live protocol host и React participant, 4 sea/2 gold/9 ports, setup/Roll. Город/корабль и 50 hex проверены отдельно test snapshots, не полным gameplay. GPU resource cleanup и отсутствие idle frames подтверждены; low-end/mobile/full-match не проверены. Lazy chunk ~874 KB / ~235 KB gzip, Vite size warning остаётся.

Обнаруженный при Board3D откат lobby карты закрыт отдельным узким fix 2026-10-04, commit 5ff920a. Оба React-клиента выбирают Gold Haven через UI; workaround с protocol host больше не нужен. Этот fix предшествует Phase 2 и не входит в её diff. Plan и границы — [[plans/board3d]], визуальное направление — [[Design System]].

## Board3D Phase 2 — Interaction

**Completed — 2026-10-05. READY FOR CHECKPOINT в проверенном scope.** GamePage хранит общий controller через useBoardInteraction: инструмент, ship source, victim choice и ожидание ответа. BoardRenderer передаёт state + interaction в SVG или Three и рисует общие BoardControls. В renderer отсутствуют расчёты cost/geometry legality; click проверяет принадлежность серверному списку и отправляет прежнюю команду через WSClient. Фигуры появляются только из snapshot.

Персональный legal строится в engine/legal.py через прежний apply_cmd на изолированных копиях. Проверяются ресурсы, pieces, roll/setup/pending/free road, ship destinations и victims; у остальных получателей пустые списки. _snapshot_state требует pid получателя. Это подсказка UX: сервер повторно валидирует каждую команду. Секретные руки, seed и bank не добавлены; правила, command envelope, token/seq и lobby map ordering сохранены.

В 3D работают setup, settlement/road/city, ship/move ship, robber/pirate и явный выбор из нескольких victims. Selection сохраняется при смене renderer; новый матч сбрасывает его, новый snapshot удаляет недоступные source/victim, отказ снимает ожидание. SVG использует тот же controller и прошёл те же browser fixture cases плюс всю расстановку.

26 новых Python legal cases и 9 новых web controller cases; один старый WS setup test теперь читает снимок действующего игрока вместо host legal. Подтверждённых новых P0/blocker regressions нет. Известные ограничения engine, в частности mixed routes/ship movement и deterministic theft, не исправлялись. frameloop=demand сохранён; 0 idle frames, unmount освобождает geometry/texture и WebGL context. Lazy chunk 876.54 KB / 235.24 KB gzip с прежним size warning. Новых зависимостей и CSS redesign нет. Тестовый Compose после проверки остановлен; commit/tag не созданы. Точные пределы и fixtures — [[plans/board3d]].

## Board3D Phase 3 — Visual Polish

**Completed — 2026-10-05. READY FOR CHECKPOINT.** Diff от bcaf9d3 ограничен web/src/board3d, восемью visual regression tests, тремя заметками и screenshot evidence. GamePage/controller, SVG и Python не менялись. Renderer остаётся renderer, not rules engine.

Единый bevel и palette, различимые terrain silhouettes, крупные contrast tokens/ports, новые стилизованные road/house/city/ship/pawn/pirate pieces. Legal/hover/selected используют outline/ring/rails; translucent ghost строится только из server targets и не отправляет команд. Камера подгоняется по реальному контуру, не сбрасывается на обычном snapshot; navy canvas и нейтральный свет заменили большую светлую подложку. Координаты/IDs, default 2D и dependency versions сохранены.

65 web tests, TypeScript, production/Docker build и Chrome проверки прошли. 19/50 hex дают 0 idle frames, общую hex geometry и cleanup до 0 geometry/texture после 2D. Восемь screenshot evidence, Base/Gold live flow и контролируемые previews/movement описаны в [[Design System]] и [[plans/board3d]]. Нет подтверждённых новых blocker regressions; полная accessibility/mobile/low-end/нагрузка не проверена. Lazy chunk 881.25 KB / 237.40 KB gzip, прежний Vite warning остаётся. Предложены commit `feat: polish 3d board visuals` и tag `board3d-phase-3`; не созданы автоматически.

## Game UI Redesign Phase 1 — Game Screen Composition

**Completed — 2026-10-05. READY FOR CHECKPOINT.** Тёмный match-only shell: игроки/turn/публичные VP и counts сверху, central board, own resource hand слева снизу, contextual actions справа. Game info и log закрыты по умолчанию. Trade/dev формы не добавлены; их controls явно unavailable. Setup/build/ship/robber/pirate/victim/discard/gold используют прежние snapshot/controller/commands. Минимальные legal markers сохраняют hit areas; ports визуально меньше/темнее/ближе, IDs и engine placement не меняются. Dependency и Docker architecture без изменений.

Сцена занимает 80.7%, 79.1%, 75.8% высоты проверенных desktop viewports соответственно; сам Canvas — 75.9%, 73.3%, 68.6%. Это измерение layout, не обещание занимаемой островом площади или процента визуального внимания. Chrome screenshots и результаты/limits — [[Design System#Game UI Redesign Phase 1 — implemented composition]] и [[plans/game-ui-redesign]]. Docker остаётся запущен на http://localhost; перезапускался только web container, backend room state не сбрасывался.
