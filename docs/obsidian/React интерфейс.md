---
tags: [catan, web, интерфейс]
---

# React интерфейс

[[Web клиент]] · [[Состояние игры]] · [[Стили и визуальные границы]] · [[Design System]]

Основные UI-границы: App, LobbyPage, GamePage, BoardRenderer, SVG BoardView и экспериментальный Board3D. Scene-компоненты находятся в board3d/. Остальные панели — JSX-блоки внутри крупных компонентов. Отдельных ResourceCard, PlayerList, TradeDialog и MainMenu в web нет.

Board3D Phase 2 verified 2026-10-05: общий controller перенесён из SVG в GamePage, оба renderer используют персональные server targets. 57 web cases, TypeScript/build, Docker и Chrome проверки проходят; детали и ограничения — [[plans/board3d]].

Контракт проверен 2026-10-02: UI-композиция не менялась в Phase 1. MatchState типизирован под персональный server snapshot, чужой player.res опционален, own res сохранена. BoardView Port соответствует текущему JSON `[edge, kind]`, pending_action/pending_pid допускают null. TypeScript проходит; отсутствие чужой руки обеспечивается сервером, а не JSX.

## Props и локальные данные

| Компонент | Кто создаёт | Props | Локальные данные |
| --- | --- | --- | --- |
| [App](../../web/src/App.tsx) | main.tsx | Нет | client, room, match, status, log, error |
| [LobbyPage](../../web/src/components/LobbyPage.tsx) | App | client, room, status, wsDefault, error | URL, имя, код, maxPlayers, pendingMapId, customLabel; отображаемый mapId = pending или room.map_id |
| [GamePage](../../web/src/components/GamePage.tsx) | App | client, match, room, status, log, error | useBoardInteraction: action, shipSource, victim, waiting; discard, goldRes, goldQty |
| [BoardRenderer](../../web/src/components/BoardRenderer.tsx) | GamePage | state + interaction | mode=2d/3d, default 2d; lazy/failure boundary |
| [BoardControls](../../web/src/board/BoardControls.tsx) | BoardRenderer, оба режима | state + interaction | Общие tools/status/victim chooser; собственного selection нет |
| [BoardView](../../web/src/components/BoardView.tsx) | BoardRenderer, режим 2D | state + interaction | SVG presentation, selection берётся из controller |
| [Board3D](../../web/src/board3d/Board3D.tsx) | BoardRenderer, режим 3D | state geometry/occupancy + interaction | hovered/inspected tile index, reset camera; InteractionOverlay3D хранит только hover |

## Экраны

App показывает LobbyPage до первого match и GamePage после его получения. Лобби до/после входа — один экран. Setup, обычный ход, discard и gold — состояния одного игрового экрана. Отдельный React-экран победы отсутствует.

## Данные UI-блоков

| Блок | Где | Данные и поведение |
| --- | --- | --- |
| Главное меню | Отдельного нет | Стартовый экран — LobbyPage |
| Connection | LobbyPage | URL, имя, код, число мест; Host/Join |
| Карта комнаты | LobbyPage | room.map_presets/id/meta/rules и map_revision, isHost, client.pendingMapId; setMap из onChange/FileReader |
| Участники лобби | LobbyPage | room.players, host_pid, connected |
| Статус матча | GamePage | Код комнаты, tick, turn, phase, pending_action, status, rules_config |
| Ресурсы | GamePage | state.players[youPid].res; res-chip по каждому ресурсу |
| Roll / End Turn | GamePage | canRoll/canEnd; отправляют roll/end_turn |
| Gold Choice | GamePage | pending_gold[youPid], goldRes, goldQty; choose_gold |
| Discard | GamePage | discard_required[youPid], res, введённый discard; discard-команда |
| Игроки матча | GamePage | state.players: pid, name, vp |
| Ошибки | LobbyPage и GamePage | error.message |
| Журнал | GamePage | log из App; сетевые ошибки и сообщения клиента |
| Trade | UI отсутствует | Порты на поле не являются формой обмена |
| Строительство и перемещения | BoardControls + оба renderer | interaction.action/targets/selection; server legal, исходные vertex/edge/tile IDs |
| Выбор жертвы | BoardControls | selection.victim.victims из personal legal, публичные player names; move_robber/move_pirate с victim |

Roll доступен в свой ход основной фазы до броска и без pending-action. End Turn зависит от своего хода, rolled и отсутствия pending-action. GamePage рассчитывает эти условия.

## Выбор карты в lobby

Исправлено и проверено 2026-10-04. Раньше один effect возвращал локальный mapId к старому room.map_id, а второй отправлял изменившийся mapId обратно. Задержка room_state воспроизвела selector Gold Haven → Base и лишний set_map(Base) при подтверждении Gold Haven. Это происходило до загрузки Board3D.

Теперь путь: onChange/FileReader → WSClient.setMap → server set_map → Room.selected_map_* + map_revision → room_state → WSClient.handleMessage → App.setRoom → LobbyPage. Snapshot эффекты не отправляют set_map. Подтверждённый выбор берётся из Room; pendingMapId — только временное отображение последнего намерения пользователя.

WSClient держит один отправленный запрос и один последний queued выбор. Пока подтверждается A, быстрый выбор B виден в selector; ACK A отправляет B, не возвращая selector на A. ACK распознаётся по росту map_revision; обычный presence broadcast не завершает ожидание. Меньшая revision той же комнаты и ответы других комнат отбрасываются до onRoomState. Это порядок выбора карты, не общая версия players/status комнаты.

Start Match disabled до подтверждения последнего выбора; startMatch также защищён в клиенте. Отказ с detail.request_type=set_map завершает только map request: queued выбор отправляется либо selector возвращается к подтверждённому состоянию. Disconnect/Host/Join сбрасывают map intentions; reconnect получает текущую карту сервера. Custom ID имеет собственную option; завершившееся чтение файла прежней комнаты игнорируется, customLabel сбрасывается при смене room.

Проверки: 8 новых transport cases и 3 LobbyPage render/handler cases, live Python map tests, production Chrome с двумя независимыми React contexts и реальными server messages. Задержка ACK и повтор старых frames контролировались браузерным test harness без изменения runtime; обычные Host/Join/map/Start прошли на Gold Haven и custom JSON. Полный web набор: 48 passed; TypeScript/build проходят. Сетевой контракт — [[Сервер и протокол]].

## Поле

BoardView получает геометрию, фигуры, правила и состояние хода. SVG-слои: гексы и номера → дороги/корабли → поселения/города → разбойник/пират → интерактивные рёбра/вершины → порты. Порядок влияет на наложение и обработку кликов.

[interaction.ts](../../web/src/board/interaction.ts) строит общий highlight model по legal.pid=youPid и выбранному инструменту. onVertexClick → place_settlement/upgrade_city; onEdgeClick → place_road/build_ship либо source → destination → move_ship; onTileClick → move_robber/move_pirate. Membership в серверных списках — единственная клиентская проверка цели; локальных canPlace* fallback больше нет. Без personal legal нет целей/команд. Setup автоматически выбирает settlement/road по setup_need; free=true берётся из legal.road_free.

[useBoardInteraction](../../web/src/board/useBoardInteraction.ts) хранит selection в GamePage. [BoardControls](../../web/src/board/BoardControls.tsx) рисует прежние tools и небольшую панель victims. При нескольких victims click сначала открывает выбор без команды; при одной жертве её pid передаётся явно, при нуле поле victim опускается. Список берётся с сервера, клиент не вычисляет кражу или ownership rules.

BoardView рисует SVG markers; [InteractionOverlay3D](../../web/src/board3d/InteractionOverlay3D.tsx) — vertex rings/edge prisms, HexTile3D — tile outline. Hover усиливает подсветку, выбранный ship source/victim tile выделен янтарным. Оба renderer вызывают одинаковые callbacks. Three не импортирует SVG internals; общие PLAYER_COLORS/edgeId находятся в board/constants.ts. Coordinate mapping Phase 1 сохранён.

Путь: click → shared callback → GamePage.sendCmd → WSClient → server._apply_cmd → неизменный engine.apply_cmd → _snapshot_state с personal legal → App.setMatch → GamePage → оба renderer. Waiting блокирует повторные board clicks до ответа. Фигуры не создаются optimistic. Error снимает ожидание/source/victim и показывает существующий feedback; snapshot заново проверяет доступность selection. Новый room+match сбрасывает selection. При 2D↔3D сохраняются tool, ship source и victim choice; GameState и tick не меняются. Sidebar Roll/End/discard/gold сохранён.

Проверено в Chrome 154 через production Docker: Base два клиента, 8 setup commands через 3D → Roll → road → End (tick 11); Gold Haven выбран через lobby, 3D setup, pirate после 7, ship и move ship [6,9]→[9,12], End; 2 хода/tick 15. Public state и pieces совпадают у клиентов, build mode/обычный turn/setup переживают переключение, 1440×1000/1280×720/1024×768 без horizontal overflow. Отдельные engine-built fixtures с mocked browser transport проверили SVG и 3D settlement/city/road/ship, move source/cancel/destination с переключением, robber/pirate с выбором второго из двух victims, free roads до Roll и rejected stale command без phantom piece. SVG fixture setup завершён всеми 8 кликами. Fixtures не означают естественное достижение этих состояний в короткой партии. Полная партия/mobile не проверялись.

## Текущее дерево

Названия без угловых скобок — блоки JSX, а не самостоятельные компоненты.

```text
<App>
├── Заголовок CATAN LAN Web
├── Если нет match: <LobbyPage>
│   ├── Connection
│   │   ├── URL / имя / код / число мест
│   │   ├── Пресет / загрузка JSON
│   │   ├── Host / Join
│   │   └── Статус / ошибка
│   └── Room
│       ├── Код / карта / правила
│       ├── Участники
│       └── Start Match
└── Если есть match: <GamePage>
    ├── <BoardRenderer>
    │   ├── 2D / 3D Experimental selector
    │   ├── 2D: <BoardView> → SVG клетки / фигуры / targets / порты
    │   ├── 3D: lazy <Board3D>, Suspense / failure boundary
    │   │   ├── Camera toolbar / Reset Camera
    │   │   ├── <Canvas> → CameraRig / lights / HexTile3D
    │   │   │   ├── TerrainHints / NumberToken3D
    │   │   │   ├── Pieces3D: road / settlement / city / ship / robber / pirate
    │   │   │   ├── Port3D
    │   │   │   └── InteractionOverlay3D: vertex / edge targets
    │   │   └── Interaction hint / inspected tile
    │   └── <BoardControls>
    │       ├── Settlement / Road / City / Ship / Move Ship / Robber / Pirate
    │       ├── Waiting / target hint / Cancel move
    │       └── Choose player, если несколько victims
    └── Sidebar
        ├── Статус / ошибка
        ├── My Resources
        ├── Roll / End Turn
        ├── Gold Choice, если требуется
        ├── Discard Required, если требуется
        ├── Players
        └── Log
```
