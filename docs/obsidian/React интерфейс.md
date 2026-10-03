---
tags: [catan, web, интерфейс]
---

# React интерфейс

[[Web клиент]] · [[Состояние игры]] · [[Стили и визуальные границы]] · [[Design System]]

В текущем приложении четыре крупных React-компонента. Остальные панели — JSX-блоки внутри них. Отдельных компонентов ResourceCard, PlayerList, TradeDialog и MainMenu в web нет.

Контракт проверен 2026-10-02: UI-композиция не менялась в Phase 1. MatchState типизирован под персональный server snapshot, чужой player.res опционален, own res сохранена. BoardView Port соответствует текущему JSON `[edge, kind]`, pending_action/pending_pid допускают null. TypeScript проходит; отсутствие чужой руки обеспечивается сервером, а не JSX.

## Props и локальные данные

| Компонент | Кто создаёт | Props | Локальные данные |
| --- | --- | --- | --- |
| [App](../../web/src/App.tsx) | main.tsx | Нет | client, room, match, status, log, error |
| [LobbyPage](../../web/src/components/LobbyPage.tsx) | App | client, room, status, wsDefault, error | URL, имя, код, maxPlayers, mapId, customLabel; lastSentMap в ref |
| [GamePage](../../web/src/components/GamePage.tsx) | App | client, match, room, status, log, error | selectedAction, discard, goldRes, goldQty |
| [BoardView](../../web/src/components/BoardView.tsx) | GamePage | state, youPid, selectedAction, onSendCmd, onSelectAction | moveFrom |

## Экраны

App показывает LobbyPage до первого match и GamePage после его получения. Лобби до/после входа — один экран. Setup, обычный ход, discard и gold — состояния одного игрового экрана. Отдельный React-экран победы отсутствует.

## Данные UI-блоков

| Блок | Где | Данные и поведение |
| --- | --- | --- |
| Главное меню | Отдельного нет | Стартовый экран — LobbyPage |
| Connection | LobbyPage | URL, имя, код, число мест; Host/Join |
| Карта комнаты | LobbyPage | room.map_presets/id/meta/rules, isHost; setMap |
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

## Поле

BoardView получает геометрию, фигуры, правила и состояние хода. SVG-слои: гексы и номера → дороги/корабли → поселения/города → разбойник/пират → интерактивные рёбра/вершины → порты. Порядок влияет на наложение и обработку кликов.

`handleVertexClick` отправляет поселение или город; `handleEdgeClick` — дорогу, корабль или его перемещение; `handleTileClick` — разбойника/пирата. `canPlace*` использует legal сервера либо локальные упрощённые проверки.

selectedAction хранит GamePage, хотя кнопки инструмента находятся в BoardView. Перемещение корабля хранит промежуточный moveFrom внутри BoardView.

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
    ├── <BoardView>
    │   ├── Выбранное действие
    │   ├── SVG: клетки / фигуры / подсветка / порты
    │   └── Settlement / Road / City / Ship / Move Ship / Pirate
    └── Sidebar
        ├── Статус / ошибка
        ├── My Resources
        ├── Roll / End Turn
        ├── Gold Choice, если требуется
        ├── Discard Required, если требуется
        ├── Players
        └── Log
```
