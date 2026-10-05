---
tags: [catan, состояние]
updated: 2026-10-05
---

# Project State

Last verified: 2026-10-05 — Game UX 2.1 после `dcadcab`: 108/108 web tests, полный pytest 203/203, TypeScript, production/Docker build и 17 Chrome 154 E2E cases проходят. Direct build actions, Ship только при server-enabled ships, cost preview, one-click buy_dev, resource-hand Trade Tray, точные server dice и конечная 950ms 3D-анимация, two-endpoint port docks, более насыщенные terrain/pieces. Base и Gold Haven проверены на 1920×1080, 1440×900, 1280×720; размер Base land относительно baseline вырос примерно на 17–19%. Engine/rules/legal/serialization privacy/maps/dependencies не менялись; server добавляет публичные Room.dice/roll_count в snapshot. Сценарии не повторялись: последний реальный результат 348/508 ниже. Prepared states используют настоящие commands/ACK/engine, full natural match/mobile/low-end FPS не сертифицированы. Scope/evidence — [[plans/game-ui-redesign#Game UX 2.1 — Direct Actions / Trade Hand / Dice / Board Readability]] и [[Design System#Game UX 2.1 — implemented direct tabletop UX]]. READY FOR CHECKPOINT; commit/tag не создавались автоматически.

Предыдущая verification, 2026-10-05 — Road Building lifecycle fix после Game UI Phase 2 (`d9a1d07`): полный pytest 195/195 passed, включая 9 новых regression cases. Сценарии до/после: 348/508 passed, те же 160 отказов в восьми сценариях с `Must roll before actions`; outcomes и failure details совпали. Успешный End Turn теперь обнуляет неиспользованный free_roads заканчивающего ход игрока; построенные дороги остаются, legal.road_free=false после End и на следующем собственном ходу. Runtime diff — одна строка в engine.rules.end_turn_cleanup; UI/protocol/legal architecture/maps не менялись. Web/build/browser проверки не повторялись: frontend не затронут. Подробности — [[Инварианты движка#Road Building lifecycle — verified 2026-10-05]].

Предыдущая verification, 2026-10-05 — Game UI Phase 2: 92/92 web tests, 186/186 pytest, TypeScript, production web build, Docker build и 14 Chrome 154 E2E cases прошли. Добавлены bank/player trade, личная dev hand/все пять карт, итоговые VP/winner/results, rematch и явный выход. Prepared games проверены через настоящий WebSocket в отдельном Docker stack; обычный production backend отдельно прошёл двухклиентский Base setup/Roll/End/2D↔3D (tick 10). Backend/rules/protocol/board/controller/maps/dependencies не менялись. Scenario suite не повторялась: 348/508 — исторический baseline. Полная естественная партия, mobile и low-end FPS не сертифицированы. Детали/limits — [[plans/game-ui-redesign#Phase 2 — Trade / Development Cards / Endgame]] и [[Design System#Game UI Phase 2 — implemented actions and results]].

Предыдущая verification, 2026-10-05 — Board3D Polish 1.1: 76/76 web tests, TypeScript, production build, Docker frontend build/up и Chrome 154 headless прошли. Hover использует emissive настоящей плитки; azimuth свободный 360°, tilt/zoom/reset сохранены. Terrain имеет стабильные небольшие вариации, порты — compact dock/placard; декоративные meshes больше не перехватывают legal hits. Base/Gold/50-hex fixture: framing, отсутствие page scroll, 0 дополнительных idle frames, cleanup при 2D switch. Два live React-клиента: Base — setup/Roll/road/robber, 4 хода/tick 18; Gold — setup/Roll/ship/pirate, 17 ходов/tick 50. Move ship и multiple victims дополнительно проверены engine-built fixtures в обоих renderer. Python/protocol/maps/controller/HUD/dependencies не менялись; pytest/scenarios не повторялись. Evidence/limits — [[plans/board3d#Game UI / Board3D Polish 1.1]] и [[Design System#Polish 1.1 visual evidence]].

Предыдущая UI verification, 2026-10-05: Game UI Redesign Phase 1 — 73/73 web tests (65 прежних + 8 UI cases), TypeScript, production/Docker build. Fullscreen match shell, compact HUD/hand/dock, закрытые drawers и default 3D; SVG сохранён. Desktop 1920×1080, 1440×900, 1280×720, шесть длинных имён, drawer/Escape/focus и modal focus trap проверены. Исторические Python результаты: 186 pytest и 348/508 scenarios. Подробнее — [[plans/game-ui-redesign]].

Map/design analysis: 2026-10-04 — код checkpoint `hardening-phase-1` (`3cd8812`), построение всех 12 карт в памяти, повторяемость seed, topology/ports/snapshot/legal и границы map validation. В рамках этого анализа полный test/build/scenario набор не повторялся, runtime и зависимости не менялись; последующая Docker verification указана выше. Подробности — [[Карты и сценарии]] и [[Design System]].

[[00 Главная]] · [[Architecture Decisions]] · [[Результаты аудита]]

## Phase 1 Status

**Completed — 2026-10-03. Checkpoint: `3cd8812`, tag `hardening-phase-1`.** Утверждённые решения VP visibility/rematch закреплены тестами; открытых подтверждённых P0 и новых blocker-level regressions в проверенном scope нет. Это завершение Production Hardening Phase 1, не всей реализации правил CATAN. Прежние 160 сценарных отказов и отдельные P1 остаются за пределами этапа.

## Current Architecture

Общий Python-движок обслуживает локальный PySide-клиент и FastAPI WebSocket-сервер. React/TypeScript получает снимки партии и отправляет намерения. Комнаты живут в памяти процесса. Qt и browser имеют отдельные представления состояния. Multiplayer теперь использует отдельный player-specific snapshot; trusted/offline to_dict сохранён.

Docker production-like: Browser → Nginx (React dist, /ws, /health) → один FastAPI worker → тот же engine. Только web port опубликован; оба containers non-root, без host mounts. Локальный Python + Vite workflow сохранён. Инструкции — [[Deployment]].

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
- В снимке свои ресурсы/dev-cards и private choices; во время игры чужой VP исключает скрытые VP-карты. После game_over все players.vp содержат итоговые total VP для действующего экрана результатов; чужие res/dev_cards остаются закрытыми. Seed и точные остатки банка не передаются, колода перемешивается независимо от карты.
- Pirate использует одно разрешённое событие после 7/завершения discard либо Knight: pending `robber_move` позволяет выбрать land robber или sea pirate при enable_pirate. Успех закрывает pending и допускает максимум одну кражу; повтор без нового события отклоняется общим движком. React/PySide клики согласованы с этим событием.
- Trade начинается кликом по собственной resource card: локальный немодальный Give/Want tray над рукой, targets Everyone/connected player/Bank. Bank 4:1/3:1/2:1 по собственным port endpoints, включая прежние batch exchanges; targeted/broadcast offer, accept/reject/cancel и отмена при end turn сохранены. Состав рук не изменяется до snapshot. Изменение offer = cancel + новое предложение; broadcast Reject закрывает offer для всех согласно существующему engine. Закрытый log drawer содержит сворачиваемую bank availability без точных counts.
- Direct Road/Settlement/City и Dev Card в dock; Ship полностью скрыт без enable_seafarers/положительного max_ships. Setup показывает только обязательный инструмент. Стоимость — один presentation config; доступные цели/команды проверяет прежний shared controller/server legal.
- Dev cards: dock Dev Card отправляет один buy_dev напрямую; own hand/type/count/new появляется только после snapshot. Клик по своей карте открывает Play/inspect: Knight через общий robber/pirate controller, две бесплатные дороги, Year of Plenty picker, Monopoly picker и passive VP. UI объясняет new/one-play/turn/pending restrictions; окончательная проверка остаётся серверной.
- Road Building позволяет поставить до двух бесплатных дорог в текущем ходу; неиспользованный credit очищает общий engine cleanup при успешном End Turn. Следующий собственный ход не получает старый credit; построенные дороги и обычная стоимость road сохраняются.
- Results: server winner/final VP, connected-player rematch с прежними tokens/compact pids/sequence reset, Back to Lobby через существующий leave_room. Выход останавливает auto-reconnect; сохранённый token остаётся для явного Join с прежним room/name.
- 108 web cases, 203 pytest, TypeScript/production/Docker build и 17 Chrome UX 2.1 cases проверены 2026-10-05. Scenario baseline 348/508 исторический для этого UI/server-metadata этапа; rules.py не менялся.

## Partially Implemented

- Seafarers: корабли, золото, пират и перемещение есть; полная семантика маршрутов и сценариев не завершена.
- Web UI: trade/dev/results/exit реализованы; отдельное меню, lobby/settings/mobile redesign и полноценный game event feed остаются вне scope. Точный bank/deck отсутствует в personal snapshot: сервер может отклонить попытку взять две одинаковые карты при остатке одной или покупку из пустой колоды.
- Desktop online: диалоги развития и банка отключены.
- Очереди web/desktop теперь привязаны к room/match; отказ расходует seq и удаляется по ACK. Полноценная user auth, потеря состояния сервера и сохранения остаются отдельными вопросами.
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
| Скрытая информация | Персональные снимки; active hidden VP закрыты, final total VP раскрываются. Финальная policy проверена 2026-10-03; чужая res/dev hand, точный bank и seed закрыты |
| Пустые участники / новый матч | Исправлено; rematch с фактически подключённым составом, обновлённые pid, tokens и sequence проверен 2026-10-03, включая отключение host |
| Повторная кража pirate без события — P0 | Исправлено 2026-10-02: single-use pending, полная atomicity при отказе, WS replay и выбор фигуры обоими клиентами проверены |
| Offline-save | Ключи флагов и бесплатных дорог после JSON становятся строками |
| Seafarers rules | Остаются ограничения смешанных/закрытых маршрутов, Longest Trade Route и полноты отдельных сценариев |
| Остальные Base rules | Требуют отдельного исправления ничьи достижений, победа вне активного хода, детерминированная кража |
| Road Building lifecycle | Исправлено 2026-10-05: end_turn_cleanup очищает free_roads только после успешной проверки End Turn. 0/1/2 placements, следующий собственный ход, paid road cost, сохранение построек, atomic rejects и персональные server snapshots проверены в tests/test_road_building_lifecycle.py |
| Сетевой lifecycle | Нет persistence/cleanup/rate limits; рассылка остаётся последовательной |

Статусы таблицы отражают завершённую Phase 1, включая reconnect/pirate fixes и финальные продуктовые решения. Остальные перечисленные P1 остаются открытыми; исторические доказательства и текущая проверка — [[Результаты аудита]].

## Current Priority

1. Восстановить понимание проекта и поддерживать живую документацию.
2. Стабилизировать правила и серверную авторитетность.
3. Подготовить новый React UI, сохраняя игровое поведение.
4. Затем постепенно рефакторить архитектуру.

Production Hardening Phase 1 завершена в утверждённом scope. Game UI Phase 1 пересобрала match composition; Phase 2 добавила существующие trade/dev/endgame mechanics в web. Lobby/menu/settings остаются будущими задачами. Board3D Phase 1 реализовала отдельную visual foundation в принятом clean modern tabletop направлении. Fantasy/MMORPG-декор исключён, прежние references остаются historical. Desktop в Hardening Phase 1 получил совместимость с сетевыми данными, отображение доступности банка и согласование выбора robber/pirate по карте. Checkpoint: commit `fix: complete production hardening phase 1`, tag `hardening-phase-1`. Последующие commits сравнивать через `git diff hardening-phase-1..HEAD`; текущие незакоммиченные изменения — через `git diff hardening-phase-1`.

## Map / 3D preparation

- Есть JSON loader, materialization/shuffle и graph builder, но нет генерации topology и map editor.
- Все 12 пресетов имеют одинаковые 19 координат; Seafarers заменяет часть позиций на sea, готового архипелага нет.
- Snapshot используется обоими renderer; Phase 2 добавила персональный server legal с affordability/limits/free-build, move_ship destinations и robber/pirate targets/victims. Проверка команд остаётся в прежнем engine.
- Auto ports используют внешнюю границу всей сетки; у Seafarers часть портов недоступна с land. Map validator не доказывает игровую пригодность custom JSON. Подтверждённые детали — [[Карты и сценарии]]; исправления в этой задаче не выполнялись.
- Актуальный 2D reference просмотрен как layout/readability reference; оригинального файла не найдено, несуществующая PNG-ссылка не добавлена.

## Next Engineering Tasks

- Game UI Phase 2 закоммичен в `d9a1d07`, Road Building fix — `dcadcab`. Game UX 2.1 завершён в проверенном scope, READY FOR CHECKPOINT; предложены commit `feat: improve direct game actions trade and dice UX` и tag `game-ux-2-1`. Они не создаются автоматически. Следующие gameplay/UI этапы требуют отдельной задачи.
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
