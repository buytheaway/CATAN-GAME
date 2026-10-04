---
tags: [catan, web, интерфейс]
---

# React интерфейс

[[Web клиент]] · [[Состояние игры]] · [[Стили и визуальные границы]] · [[Design System]]

Основные UI-границы: App, LobbyPage, GamePage, BoardRenderer, SVG BoardView и экспериментальный Board3D. Scene-компоненты находятся в board3d/. Остальные панели — JSX-блоки внутри крупных компонентов. Отдельных ResourceCard, PlayerList, TradeDialog и MainMenu в web нет.

Board3D Phase 1 verified 2026-10-04: renderer selector и отдельная visual scene добавлены без миграции command/controller logic. 37 web cases, TypeScript/build и Docker/browser checks проходят; детали и ограничения — [[plans/board3d]].

Контракт проверен 2026-10-02: UI-композиция не менялась в Phase 1. MatchState типизирован под персональный server snapshot, чужой player.res опционален, own res сохранена. BoardView Port соответствует текущему JSON `[edge, kind]`, pending_action/pending_pid допускают null. TypeScript проходит; отсутствие чужой руки обеспечивается сервером, а не JSX.

## Props и локальные данные

| Компонент | Кто создаёт | Props | Локальные данные |
| --- | --- | --- | --- |
| [App](../../web/src/App.tsx) | main.tsx | Нет | client, room, match, status, log, error |
| [LobbyPage](../../web/src/components/LobbyPage.tsx) | App | client, room, status, wsDefault, error | URL, имя, код, maxPlayers, pendingMapId, customLabel; отображаемый mapId = pending или room.map_id |
| [GamePage](../../web/src/components/GamePage.tsx) | App | client, match, room, status, log, error | selectedAction, discard, goldRes, goldQty |
| [BoardRenderer](../../web/src/components/BoardRenderer.tsx) | GamePage | Прежние BoardViewProps, тот же state | mode=2d/3d, default 2d; lazy/failure boundary |
| [BoardView](../../web/src/components/BoardView.tsx) | BoardRenderer, режим 2D | state, youPid, selectedAction, onSendCmd, onSelectAction | moveFrom |
| [Board3D](../../web/src/board3d/Board3D.tsx) | BoardRenderer, режим 3D | state geometry/occupancy, без command callbacks | hovered/inspected tile index, reset camera version; read-only render projection |

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
| Строительство | BoardView | Выбранный инструмент, legal, turn, phase, occupied_* |

Roll доступен в свой ход основной фазы до броска и без pending-action. End Turn зависит от своего хода, rolled и отсутствия pending-action. GamePage рассчитывает эти условия.

## Выбор карты в lobby

Исправлено и проверено 2026-10-04. Раньше один effect возвращал локальный mapId к старому room.map_id, а второй отправлял изменившийся mapId обратно. Задержка room_state воспроизвела selector Gold Haven → Base и лишний set_map(Base) при подтверждении Gold Haven. Это происходило до загрузки Board3D.

Теперь путь: onChange/FileReader → WSClient.setMap → server set_map → Room.selected_map_* + map_revision → room_state → WSClient.handleMessage → App.setRoom → LobbyPage. Snapshot эффекты не отправляют set_map. Подтверждённый выбор берётся из Room; pendingMapId — только временное отображение последнего намерения пользователя.

WSClient держит один отправленный запрос и один последний queued выбор. Пока подтверждается A, быстрый выбор B виден в selector; ACK A отправляет B, не возвращая selector на A. ACK распознаётся по росту map_revision; обычный presence broadcast не завершает ожидание. Меньшая revision той же комнаты и ответы других комнат отбрасываются до onRoomState. Это порядок выбора карты, не общая версия players/status комнаты.

Start Match disabled до подтверждения последнего выбора; startMatch также защищён в клиенте. Отказ с detail.request_type=set_map завершает только map request: queued выбор отправляется либо selector возвращается к подтверждённому состоянию. Disconnect/Host/Join сбрасывают map intentions; reconnect получает текущую карту сервера. Custom ID имеет собственную option; завершившееся чтение файла прежней комнаты игнорируется, customLabel сбрасывается при смене room.

Проверки: 8 новых transport cases и 3 LobbyPage render/handler cases, live Python map tests, production Chrome с двумя независимыми React contexts и реальными server messages. Задержка ACK и повтор старых frames контролировались браузерным test harness без изменения runtime; обычные Host/Join/map/Start прошли на Gold Haven и custom JSON. Полный web набор: 48 passed; TypeScript/build проходят. Сетевой контракт — [[Сервер и протокол]].

## Поле

BoardView получает геометрию, фигуры, правила и состояние хода. SVG-слои: гексы и номера → дороги/корабли → поселения/города → разбойник/пират → интерактивные рёбра/вершины → порты. Порядок влияет на наложение и обработку кликов.

`handleVertexClick` отправляет поселение или город; `handleEdgeClick` — дорогу, корабль или его перемещение; `handleTileClick` — разбойника/пирата. `canPlace*` использует legal сервера либо локальные упрощённые проверки.

selectedAction хранит GamePage, хотя кнопки инструмента находятся в BoardView. Перемещение корабля хранит промежуточный moveFrom внутри BoardView.

Board3D сохраняет IDs и отображает snapshot, без legal/cost/turn checks. Terrain/number meshes, ports и placeholder pieces не отправляют команды. Hover/click только инспектирует tile index; placement/robber/pirate требуют 2D. Sidebar Roll/End Turn остаётся в GamePage и работает с тем же client. При переключении renderer перемонтируется; незавершённый локальный moveFrom SVG сбрасывается, selectedAction в GamePage сохраняется. GameState этим не меняется.

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
    │   ├── 2D: <BoardView>
    │   │   ├── Выбранное действие
    │   │   ├── SVG: клетки / фигуры / подсветка / порты
    │   │   └── Settlement / Road / City / Ship / Move Ship / Pirate
    │   └── 3D: lazy <Board3D>, Suspense / failure boundary
    │       ├── Camera toolbar / Reset Camera
    │       ├── <Canvas> → CameraRig / lights / HexTile3D
    │       │   ├── TerrainHints / NumberToken3D
    │       │   ├── Pieces3D: road / settlement / city / ship / robber / pirate
    │       │   └── Port3D
    │       └── View-only notice / inspected tile
    └── Sidebar
        ├── Статус / ошибка
        ├── My Resources
        ├── Roll / End Turn
        ├── Gold Choice, если требуется
        ├── Discard Required, если требуется
        ├── Players
        └── Log
```
