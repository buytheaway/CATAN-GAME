---
tags: [catan, web, интерфейс]
---

# React интерфейс

[[Web клиент]] · [[Состояние игры]] · [[Стили и визуальные границы]] · [[Design System]]

Основные UI-границы: App, LobbyPage, fullscreen GamePage, GameTopBar/ContextPrompt/ResourceHand/GameOverlay в game/, BoardControls в dock, BoardRenderer, SVG BoardView и Board3D. Scene-компоненты находятся в board3d/. Action dock/player strip — JSX-блоки, не отдельные classes. TradeDialog, MainMenu и development-card формы в web отсутствуют.

Game UI Redesign Phase 1 verified 2026-10-05: 73 web tests, TypeScript, production/Docker build и Chrome. Default 3D; 2D сохранён. Новая композиция/HUD отделена от прежнего controller/network/gameplay. Scope, screenshots и limits — [[plans/game-ui-redesign]] и [[Design System#Game UI Redesign Phase 1 — implemented composition]].

Историческая проверка Board3D Phase 2 2026-10-05: общий controller перенесён из SVG в GamePage, оба renderer используют персональные server targets. 57 web cases, TypeScript/build, Docker и Chrome проверки проходят; детали и ограничения — [[plans/board3d]].

Контракт проверен 2026-10-02: UI-композиция не менялась в Phase 1. MatchState типизирован под персональный server snapshot, чужой player.res опционален, own res сохранена. BoardView Port соответствует текущему JSON `[edge, kind]`, pending_action/pending_pid допускают null. TypeScript проходит; отсутствие чужой руки обеспечивается сервером, а не JSX.

## Props и локальные данные

| Компонент | Кто создаёт | Props | Локальные данные |
| --- | --- | --- | --- |
| [App](../../web/src/App.tsx) | main.tsx | Нет | client, room, match, status, log, error |
| [LobbyPage](../../web/src/components/LobbyPage.tsx) | App | client, room, status, wsDefault, error | URL, имя, код, maxPlayers, pendingMapId, customLabel; отображаемый mapId = pending или room.map_id |
| [GamePage](../../web/src/components/GamePage.tsx) | App | client, match, room, status, log, error | Прежний useBoardInteraction; discard/gold fields, новый drawer=log/info/null |
| [BoardRenderer](../../web/src/components/BoardRenderer.tsx) | GamePage | state + interaction | mode=2d/3d, default 3d; lazy/failure boundary |
| [BoardControls](../../web/src/board/BoardControls.tsx) | GamePage action dock, оба режима | state + interaction | Только buildOpen/focus; tools/victim chooser вызывают прежние callbacks, собственного игрового selection нет |
| [BoardView](../../web/src/components/BoardView.tsx) | BoardRenderer, режим 2D | state + interaction | SVG presentation, selection берётся из controller |
| [Board3D](../../web/src/board3d/Board3D.tsx) | BoardRenderer, режим 3D | state geometry/occupancy + interaction | hovered tile index, reset camera; debug inspection footer удалён; InteractionOverlay3D хранит только hover |

## Экраны

App показывает LobbyPage до первого match и GamePage после его получения. Лобби до/после входа — один экран. Setup, обычный ход, discard и gold — состояния одного игрового экрана. Отдельный React-экран победы отсутствует.

## Данные UI-блоков

| Блок | Где | Данные и поведение |
| --- | --- | --- |
| Главное меню | Отдельного нет | Стартовый экран — LobbyPage |
| Connection | LobbyPage | URL, имя, код, число мест; Host/Join |
| Карта комнаты | LobbyPage | room.map_presets/id/meta/rules и map_revision, isHost, client.pendingMapId; setMap из onChange/FileReader |
| Участники лобби | LobbyPage | room.players, host_pid, connected |
| Turn/prompt и Game info | GameTopBar/ContextPrompt/GameOverlay | turn, snapshot/controller; raw tick/phase/pending/status/map/rules скрыты в закрытом info drawer |
| Ресурсы | ResourceHand | find(player.pid=youPid).res; пять glyph/name/count cards, отсутствующее значение = 0 |
| Roll / End Turn | GamePage | canRoll/canEnd; отправляют roll/end_turn |
| Gold Choice | GamePage | pending_gold[youPid], goldRes, goldQty; choose_gold |
| Discard | GamePage | discard_required[youPid], res, введённый discard; discard-команда |
| Игроки матча | GameTopBar | public pid/name/vp/resource_count/dev_count/turn, PLAYER_COLORS; без чтения чужой руки |
| Ошибки | LobbyPage и GamePage | error.message |
| Журнал | GameOverlay | log из App, закрыт по умолчанию; сетевые ошибки/сообщения клиента сохранены, engine event feed не добавлен |
| Trade / Dev | Формы отсутствуют | Dock controls disabled с объяснением; новые команды/формы не добавлены |
| Строительство и перемещения | BoardControls + оба renderer | interaction.action/targets/selection; server legal, исходные vertex/edge/tile IDs |
| Выбор жертвы | BoardControls | selection.victim.victims из personal legal, публичные player names; move_robber/move_pirate с victim |

Roll доступен в свой ход основной фазы до броска и без pending-action. End Turn зависит от своего хода, rolled и отсутствия pending-action. presentation.turnActions сохраняет эти прежние условия; проверки правил остаются на сервере.

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

BoardView рисует SVG markers; [InteractionOverlay3D](../../web/src/board3d/InteractionOverlay3D.tsx) — vertex rings/тонкие edge rails с невидимыми увеличенными hit surfaces. После Polish 1.1 HexTile3D подсвечивает настоящую плитку через pooled emissive material: второго tile outline mesh нет. Hover светлее, выбранный ship source/victim tile выделен янтарным. Terrain decoration исключён из raycasting, чтобы не перехватывать legal clicks. Оба renderer вызывают одинаковые callbacks. Three не импортирует SVG internals; общие PLAYER_COLORS/edgeId находятся в board/constants.ts. Coordinate mapping Phase 1 сохранён.

Путь: click → shared callback → GamePage.sendCmd → WSClient → server._apply_cmd → неизменный engine.apply_cmd → _snapshot_state с personal legal → App.setMatch → GamePage → оба renderer. Waiting блокирует повторные board clicks до ответа. Фигуры не создаются optimistic. Error снимает ожидание/source/victim и показывает существующий feedback; snapshot заново проверяет доступность selection. Новый room+match сбрасывает selection. При 2D↔3D сохраняются tool, ship source и victim choice; GameState и tick не меняются. Payloads/условия Roll/End/discard/gold сохранены; их представление перенесено в dock/choice overlays.

Проверено в Chrome 154 через production Docker: Base два клиента, 8 setup commands через 3D → Roll → road → End (tick 11); Gold Haven выбран через lobby, 3D setup, pirate после 7, ship и move ship [6,9]→[9,12], End; 2 хода/tick 15. Public state и pieces совпадают у клиентов, build mode/обычный turn/setup переживают переключение, 1440×1000/1280×720/1024×768 без horizontal overflow. Отдельные engine-built fixtures с mocked browser transport проверили SVG и 3D settlement/city/road/ship, move source/cancel/destination с переключением, robber/pirate с выбором второго из двух victims, free roads до Roll и rejected stale command без phantom piece. SVG fixture setup завершён всеми 8 кликами. Fixtures не означают естественное достижение этих состояний в короткой партии. Полная партия/mobile не проверялись.

## Композиция Phase 1

GamePage подключает один useBoardInteraction и передаёт один state/interaction в selector/renderers и BoardControls. HUD/presentation helpers только читают snapshot: нет стоимости/новых IDs/локальной GameState. GameSnapshot нормализует пересечённый TypeScript players array для итерации, добавляет уже существующие runtime game_over/last_roll в локальный UI тип; WS shape/семантика не меняются.

Build palette показывает только инструменты с существующими personal legal targets, не рассчитывает affordability. Turn/pending смена закрывает локальную palette; выбор инструмента/Cancel вызывает прежний controller. Setup автоматически следует setup_need. ContextPrompt описывает controller step, включая source/destination/victim/waiting, а не создаёт новую state machine. Game info и log — закрытые nonmodal drawers; Escape/close возвращают focus. Victim chooser тоже nonmodal, переключение renderer сохраняет выбор; discard/gold — mandatory modal с focus trap и прежними полями/payloads.

Реальные два клиента через Docker: Base setup/Roll/road/robber tick 21, Gold setup/Roll/ship/pirate tick 28; public snapshots совпали. Engine-built fixtures отдельно прошли оба renderer для четырёх build tools, move ship/cancel/destination, multiple victims, free roads и rejected commands без phantom pieces. Отдельно проверены drawer toggle/Escape/focus, selector/reset, choice focus trap и шесть длинных имён. 1920×1080/1440×900/1280×720 без page scroll/перекрытия HUD. Полная партия/mobile/low-end/a11y certification не проверялись. Существующий нюанс terrain decoration/road midpoint occlusion не исправлялся.

## Текущее дерево

Названия без угловых скобок — JSX-блоки, не самостоятельные компоненты.

```text
<App>
├── Если нет match: CATAN LAN Web + <LobbyPage> (без redesign)
│   ├── Connection / Host / Join / preset / custom JSON
│   └── Room / players / Start Match
└── Если есть match: <GamePage> → .game-shell
    ├── <GameTopBar>
    │   ├── Compact brand / room
    │   ├── Players strip: name / color / public VP & counts / Turn
    │   └── Goal / Game info / Event log buttons
    ├── Board stage
    │   ├── <ContextPrompt>
    │   ├── <BoardRenderer> + compact 2D/3D selector
    │   │   ├── 2D: <BoardView> → прежний SVG / targets / callbacks
    │   │   └── 3D default: lazy <Board3D>, Suspense / failure boundary
    │   │       ├── Compact Reset Camera
    │   │       └── <Canvas> / CameraRig / lights / VisualResources
    │   │           ├── HexTile3D → TerrainHints / NumberToken3D
    │   │           ├── Pieces3D / Port3D
    │   │           └── InteractionOverlay3D → targets / ghosts
    │   └── Error / disconnected feedback
    ├── Bottom HUD
    │   ├── <ResourceHand> → five own resource cards
    │   └── Action dock
    │       ├── Roll / disabled Trade & Dev / End Turn (ordinary turn)
    │       └── <BoardControls>
    │           ├── Setup cue / Build palette / Move Ship
    │           ├── Robber / Pirate / Cancel (contextual)
    │           └── <GameOverlay> victim chooser, when needed
    ├── <GameOverlay> Game info or Event log, when opened
    └── <GameOverlay> Gold Choice / Discard, when required
```
