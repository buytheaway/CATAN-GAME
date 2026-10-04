---
tags: [catan, состояние]
updated: 2026-10-04
---

# Project State

Last verified: 2026-10-04 — Board3D Phase 1: 37 web tests, TypeScript, production build, Docker build/up и реальный Chrome на Base Standard/Gold Haven; coordinates/IDs/terrain/ports/pieces, toggle, camera/resize и setup→Roll. City/ship и 50 hex — engine-built snapshots с mocked transport. Python runtime не менялся: pytest сегодня повторно для Board3D не запускался; 158 passed относится к предыдущей infrastructure verification этого дня. Scenario suite не повторялась; исторический baseline от 2026-10-03: 348/508. Полная партия/mobile/нагрузка не проверялись. Подробности — [[plans/board3d]] и [[Deployment]].

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
- BoardRenderer сохраняет default 2D и добавляет lazy 3D Experimental на том же snapshot. Board3D только визуализирует, без gameplay/command logic; placement и robber/pirate остаются в 2D. Scope и проверка — [[plans/board3d]].
- Production roll принимает только `{type: "roll"}`; две кости генерирует сервер. CATAN_DEBUG_ROLLS больше не открывает публичный debug-путь.
- Публичный список команд исключает grant_resources. Helper остался в trusted engine для подготовки тестов и проверяет весь payload перед выдачей.
- Имя не даёт доступ к занятому слоту; reconnect требует существующий токен и отзывает старое соединение.
- React Join использует один transport helper для открытого и подключающегося WS: token выбранной пары room/name → reconnect, отсутствие token → join_room. Смена комнаты/игрока очищает прежний token в памяти; создание комнаты не использует старый token. Отклонённый reconnect очищает соответствующий cache без автоматического Join по имени.
- Каждый старт, включая rematch, включает только подключённых участников, минимум двух; pid уплотняются вместе с сетевыми привязками. Отключившийся прежний участник не создаёт пустое место в новом GameState. Подключённый host запускает rematch; если он отключён, это может сделать первый подключённый участник, который становится host после успешного старта.
- Reconnect token восстанавливает прежний слот до rematch. Сохранившиеся участники сохраняют token с новым pid; исключённый участник теряет доступ к слоту при новом матче. match_id увеличивается; tick, sequence и deduplication history сбрасываются.
- В снимке свои ресурсы/dev-cards и private choices; во время игры чужой VP исключает скрытые VP-карты. После game_over все players.vp содержат итоговые total VP для будущего экрана результатов; чужие res/dev_cards остаются закрытыми. Seed и точные остатки банка не передаются, колода перемешивается независимо от карты.
- Pirate использует одно разрешённое событие после 7/завершения discard либо Knight: pending `robber_move` позволяет выбрать land robber или sea pirate при enable_pirate. Успех закрывает pending и допускает максимум одну кражу; повтор без нового события отклоняется общим движком. React/PySide клики согласованы с этим событием.
- 37 web cases проходят (16 transport + 5 BoardView + 4 URL + 12 Board3D projection/geometry); TypeScript/production/Docker build проверены 2026-10-04. 158 pytest passed без skip — предыдущая infrastructure verification этого дня, не повторный запуск после добавления renderer. Это не подтверждение полной корректности CATAN.

## Partially Implemented

- Seafarers: корабли, золото, пират и перемещение есть; полная семантика маршрутов и сценариев не завершена.
- Web UI: отсутствуют формы торговли/карт развития, отдельное меню, результат партии и законченный путь выхода.
- Desktop online: диалоги развития и банка отключены.
- Очереди web/desktop теперь привязаны к room/match; отказ расходует seq и удаляется по ACK. Полноценная user auth, потеря состояния сервера и сохранения остаются отдельными вопросами.
- Старые ошибки TypeScript и секции setup.cfg устранены в рамках проверки контракта/тестов. Сценарный прогон по-прежнему даёт 348/508 успешных запусков: восемь сценариев действуют до обязательного броска. Правило не ослаблялось.

## Known Critical Problems

| Проблема | Статус и место |
| --- | --- |
| Production roll / grant_resources | Исправлено 2026-10-02, проверено через WebSocket |
| Чужой слот по имени | Исправлено; токен и единственный active_ws на слот |
| React Join с token на открытом WS | Исправлено 2026-10-02; повторный reconnect, отказ без fallback, другой room/name и create-room проверены |
| Координаты | Исправлено существование vertex/edge/hex и land/sea; setup нельзя включить клиентским флагом после расстановки |
| Атомарность / Year of Plenty | Подтверждённые места исправлены; весь state сравнивается при отказе. Повторный discard тоже отклоняется |
| Скрытая информация | Персональные снимки; active hidden VP закрыты, final total VP раскрываются. Финальная policy проверена 2026-10-03; чужая res/dev hand, точный bank и seed закрыты |
| Пустые участники / новый матч | Исправлено; rematch с фактически подключённым составом, обновлённые pid, tokens и sequence проверен 2026-10-03, включая отключение host |
| Повторная кража pirate без события — P0 | Исправлено 2026-10-02: single-use pending, полная atomicity при отказе, WS replay и выбор фигуры обоими клиентами проверены |
| Offline-save | Ключи флагов и бесплатных дорог после JSON становятся строками |
| Seafarers rules | Остаются ограничения смешанных/закрытых маршрутов, Longest Trade Route и полноты отдельных сценариев |
| Остальные Base rules | Требуют отдельного исправления ничьи достижений, победа вне активного хода, детерминированная кража |
| Сетевой lifecycle | Нет persistence/cleanup/rate limits; рассылка остаётся последовательной |

Статусы таблицы отражают завершённую Phase 1, включая reconnect/pirate fixes и финальные продуктовые решения. Остальные перечисленные P1 остаются открытыми; исторические доказательства и текущая проверка — [[Результаты аудита]].

## Current Priority

1. Восстановить понимание проекта и поддерживать живую документацию.
2. Стабилизировать правила и серверную авторитетность.
3. Подготовить новый React UI, сохраняя игровое поведение.
4. Затем постепенно рефакторить архитектуру.

Production Hardening Phase 1 завершена в утверждённом scope. Общий UI redesign не начат; Board3D Phase 1 реализует отдельную visual foundation в принятом clean modern tabletop направлении. Fantasy/MMORPG-декор исключён, прежние references остаются historical. Desktop в Hardening Phase 1 получил совместимость с сетевыми данными, отображение доступности банка и согласование выбора robber/pirate по карте. Checkpoint: commit `fix: complete production hardening phase 1`, tag `hardening-phase-1`. Последующие commits сравнивать через `git diff hardening-phase-1..HEAD`; текущие незакоммиченные изменения — через `git diff hardening-phase-1`.

## Map / 3D preparation

- Есть JSON loader, materialization/shuffle и graph builder, но нет генерации topology и map editor.
- Все 12 пресетов имеют одинаковые 19 координат; Seafarers заменяет часть позиций на sea, готового архипелага нет.
- Snapshot достаточен для визуального Board3D. Полный rule-free interaction потребует более точного server legal: affordability/limits/free-build, move_ship targets и robber/pirate targets.
- Auto ports используют внешнюю границу всей сетки; у Seafarers часть портов недоступна с land. Map validator не доказывает игровую пригодность custom JSON. Подтверждённые детали — [[Карты и сценарии]]; исправления в этой задаче не выполнялись.
- Актуальный 2D reference просмотрен как layout/readability reference; оригинального файла не найдено, несуществующая PNG-ссылка не добавлена.

## Next Engineering Tasks

- Следующий шаг: review/checkpoint Board3D Phase 1. Предлагаемые commit: feat: add experimental 3d board renderer; tag: board3d-phase-1. Агент не создаёт их автоматически.
- Board3D Phase 2 потребует отдельной задачи на interaction/controller и достаточный server legal contract. Не начат автоматически.
- Открытый backlog: привести восемь старых сценариев к законному циклу roll → action → end, сохранив их assertions, и проверить выявленные ими расхождения.
- Дальнейшие ограничения Phase 1 и результаты — [[plans/server-authority-hardening]].
- Уточнить gameplay-композицию, состояния и visual tokens актуального clean tabletop направления в [[Design System]].
- Подготовить и согласовать [[plans/web-ui-redesign|план React redesign]]; не переносить макеты в код автоматически.
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

Обнаружено существующее расхождение вне scope: LobbyPage mapId effects способны откатить выбор пресета и отправить set_map после старта; подтверждено до загрузки Board3D. Для Seafarers host задавал map через обычный protocol; React join не менял карту. LobbyPage сохранён. Plan, verification и Phase 2 границы — [[plans/board3d]], визуальное направление — [[Design System]].
