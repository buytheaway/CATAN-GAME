---
tags: [catan, web, интерфейс]
---

# React интерфейс

## Product shell and auth UX — 2026-10-08

App still creates one WSClient, subscribes to the same room/match callbacks and restores the same current-game pointer. With no match it now renders [PageShell](../../web/src/shell/PageShell.tsx) → account/connection header + LobbyPage. LobbyPage branches into Home when room is null, or pre-match Room otherwise. GamePage stays in the same `.app.app--match` wrapper with its previous props/controller/scene layout.

Home reuses AccountGames and RecentGames discovery. Both use presentation-only [GameCard](../../web/src/shell/GameCard.tsx): room code, public map, own name/color, counts/online/lifecycle/winner and callbacks. Guest inspection, credential removal only after confirmed invalidation, account Continue/claim and transient failure retention remain in existing controllers. Host/Join forms retain setName/connect/host and loadToken/connect/join ordering. Advanced server URL stays available for guests; signed-in games use the existing same-origin account policy. Map presets/custom JSON/rules are in Room; no invented pre-host config or extra API is added.

Room uses actual slots/host/presence/color plus PlayerColors; map handler/FileReader keeps its room/status guard and original setMap payload. MatchSettings is grouped into Victory & discard, Dice & timer, Game and Bank; selects have exact accessible labels. Pending map/settings/color still come from WSClient; Start waits for confirmation, host, lobby, connection and at least two connected named players. The header reads the confirmed target override. Chat uses unchanged RoomChat callbacks/history, styled only inside the shell. Back to home disconnects through existing leaveRoom, clears local display/log and retains recoverable bindings.

AuthProvider and [api.ts](../../web/src/auth/api.ts) keep their HTTP/cookie/session/claim behavior. AccountControls adds explanatory helpers and [validation.ts](../../web/src/auth/validation.ts), checked against app/auth/passwords.py: username ASCII 3–32 with case-insensitive server normalization; display_name 1–32 trimmed Unicode code points without category-C characters; password 10–128 code points / ≤512 UTF-8 bytes, never trimmed. No email login. Removing display/password HTML maxLength avoids rejecting valid astral Unicode by UTF-16 length. Server remains authoritative and field errors identify username/display/password; credentials, origin, session and network errors stay global.

Confirmed UI bug fixed: register mode previously persisted after successful registration/logout, so signed-out Sign In reopened Create account. Launch now resets to Login; the real browser regression covers registration → logout → incorrect login → successful login. Focus trap includes busy periods with all controls disabled, preserves Escape/restore and aria-busy/invalid/describedby. Specific past user credentials were not available, so their exact rejected attempt is not diagnosed beyond the verified username/email/display-name contract.

Verified 2026-10-08: **178 web tests**, TS/build; [product-shell.cjs](../../web/e2e/product-shell.cjs) tests real auth/rooms/recovery/preset/custom JSON/settings/chat/Start plus explicit unavailable/invalid failures. New dist was served to the isolated browser only; existing backend/nginx/container state stayed running. Screenshots and limits — [[Design System#Product / UX / Visual Polish — Phase 1]]. No Python, WS contract, database, Board3D/assets or active-match composition changes.

## Board3D terrain assets — 2026-10-07

GamePage → BoardRenderer → Board3D → HexTile3D → [TerrainHexVisual.tsx](../../web/src/board3d/TerrainHexVisual.tsx). Snapshot projection/controller/legal callbacks remain unchanged. HexTile3D keeps the original simple hex as an invisible hit mesh and retains tileIndex; GLB children ignore raycasting. Vertex/edge targets and piece anchors are still separate and authoritative snapshot IDs reach the existing controller.

[terrainAssets.ts](../../web/src/board3d/terrainAssets.ts) selects eight assets/resource aliases, caches one Promise per canonical terrain and clones only scene nodes. Geometry/materials are shared; unmount/terrain-change effects ignore late replies. Pending/failed loads use TerrainHints and the original hex material palette locally, including unknown-type fallback; failed loads warn once and stay cached until page reload. No Suspense/error from one asset can remove the whole board. Sea assets do not create extra map tiles.

NumberToken3D/visual resource pool add a shared readable badge layer, with no per-terrain height changes or material edits to the GLBs. Hex feedback uses a thin ring; coordinates.ts only expands conservative visual camera heights. UI/controller/rules/protocol/auth stay unchanged. Verified: 169 web tests, TS/build, production Chrome Base/Gold placement/events/hover/camera/reconnect/fallback; limits and performance — [[plans/board3d#Terrain GLB integration — visual scope]].

## Auth Phase 1 — account and guest UI

Implemented/verified **2026-10-07**: 162 web tests, 564 pytest, TS/production/Docker and 10 Chrome/Nginx/PG auth flows. [AuthUI.tsx](../../web/src/auth/AuthUI.tsx) adds AuthProvider, compact AccountControls/Register/Login dialog, AccountGames and explicit Save to account. [api.ts](../../web/src/auth/api.ts) makes same-origin/no-store requests with an 8s timeout and safe error messages; opaque session is HttpOnly and never accessible to this code. [auth.css](../../web/src/auth/auth.css) scopes dark auth UI; lobby/board/trade/dev-card composition is preserved.

App → AuthProvider → LobbyPage (AccountGames + guest Recent Games + unchanged Create/Join) or GamePage (AccountControls in GameTopBar). Forms have username/password and registration display name, focus/Escape handling, busy state and no password persistence. Signed-in Host/Join uses account display_name and site's WS origin; guest name/manual-server controls remain. Active cards show only safe owned-room metadata; different browser needs only login, not local guest storage. Failed /me/Active Games does not delete guest bindings. Stale bootstrap responses cannot overwrite a later login/logout.

Account Continue → WSClient.continueAccount → account_continue(room_code) with browser cookie → server seat_identity → same room/personal snapshot/controller. Account current pointer stores only ownership:"account", room_code and server_url in sessionStorage; pid/match/session token stay out of storage. Refresh restores that pointer. Server pid/name/epoch/consumed seq update current client identity and pending replay; new match resets old commands. Confirmed session_expired/seat_not_owned/unauthenticated/seat_taken_over stops retry/fallback, clears current pointer and leaves the match UI; transient DB/network failure preserves intent. The old browser after takeover can explicitly Continue again, never auto-fight the new owner.

Login/Register never claim browser guest games. Save to account in current AccountControls or a guest Recent card submits session + that exact guest proof; current socket's hello nonce is included only for its room. Server commit confirms ownership/revocation, then only that guest proof is removed; unrelated games remain. Current matching socket receives account identity and stays usable without pid/state/name changes. Account Active Games is then the recovery source, including another browser. Claim retries for the same confirmed owner/proof are idempotent. Guest Recent schema/version/bounds/migration remain unchanged.

Vite default WS now uses the page's /ws proxy along with /api so cookie and WS share the origin. Explicit VITE_WS_URL/manual guest overrides remain available; cross-origin account cookie transport is not supported. No localStorage JWT/session, profile/history/login-required gameplay. Limits and backend security — [[Сервер и протокол#Auth Phase 1 — HTTP and WS ownership]], [[plans/persistence-auth#Auth Phase 1 — completed 2026-10-07]].

## Persistence 1C — Recent Games and Continue

Implemented/verified **2026-10-06**: 150 web cases, TS/production/Docker builds и 10 Chrome/Nginx/PG checks; full pytest 535. [RecentGames.tsx](../../web/src/components/RecentGames.tsx) находится над lobby-grid, поэтому Connection/Room не получают лишние пустые grid tracks. Scoped [recentGames.css](../../web/src/components/recentGames.css) оформляет компактные dark cards; match UI/Board3D не менялись.

[recentGames.ts](../../web/src/recentGames.ts) — version-1 local guest discovery, max 10, ordered by last successful reconnect time. Entry: room_code/token/name hint/last_seen_at, optional server_url. Exact hand/dev/snapshot/DB IDs/pid не сохраняются. Legacy keys мигрируют после безопасной записи; overflow proofs сохраняются в прежних ключах до появления места в bounded списке; rematch не создаёт entry по новому pid. Known manual-server credentials проверяются только на своём сервере; карточки используют API backend сайта. Legacy без endpoint относится к default backend.

RecentGames effect запускает один bounded batch HTTP с AbortController/8s timeout; StrictMode/unmount cleanup не позволяет позднему ответу менять экран. Available card отображает только server map/name/color/participants/presence/status, optional public winner. Cache name не authoritative. Invalid removes only that proof, temporary 503/429/offline/invalid response keeps it and shows Retry. Loading confined to section, Host/Join remain interactive. Никаких tokens в DOM/URL/transport log.

Click Continue → WSClient.continueGame → existing queued Join intent → reconnect(code,token) → normal room_state → reconnect_token(pid/epoch/consumed seq) → personalized match_state → App/GamePage. Lobby и game_over используют прежние экраны. Verified token corrects stale nickname/own pid and republishes identity for lobby host permissions. Continue never falls back to name join. Manual Host/Join cancels an unfinished refresh reconnect, including an already open but unverified socket; old callbacks cannot overwrite the new room or remove its proof. Selected WS URL is honored. Changing servers clears previous room revisions, match/sequence and pending commands, even if room code/epoch happen to match.

App запускает restoreCurrentGame один раз после установки callbacks, guarded useRef. Current pointer в sessionStorage содержит room/name/server, без token/pid, и разрешается через localStorage proof. Refresh той же вкладки auto reconnect; новый вход без pointer показывает Recent. Successful proof updates last_seen_at; permanent rejection clears selected proof/pointer and stops retries, outages keep proof with existing bounded backoff. Explicit leave clears pointer and client state, preserving Recent. New verified connection retains existing single-active-socket takeover.

Browser-local only: cleared/blocked storage cannot recover by nickname; neutral text states the limit. No account/login/history/cross-device recovery. Details and repeatable checks — [[plans/persistence-auth#Persistence Phase 1C — completed 2026-10-06]], [[Сервер и протокол#Recent game inspection — Persistence 1C]].

## Game UX 2.3 — current playtest feedback flow

Verified **2026-10-06**: 128 web tests, 266 pytest, TypeScript/production/Docker builds, 27 real Chrome cases. SVG/shared controller/Ship/matching-ACK пути сохранены. Актуальная композиция ниже заменяет прежние top strip, target select, modal-first play и numeric discard; секции 2.2/2.1/Phase 2 описывают исторические этапы.

[GamePage](../../web/src/components/GamePage.tsx) держит один snapshot, board controller и local TradeDraft. GameTopBar теперь только brand/goal/info/log, ContextPrompt визуально в свободном центре header; right aside содержит PlayerStrip (public color/name/VP/card/dev counts/turn/timer), collapsible GameLog/RoomChat и BankSummary (open default). Чужая рука не нужна для sidebar. ResourceHand — фиксированные пять ResourceCard со stack/count, own DevelopmentHand рядом.

Hand click → local Give/Want tray. **Bank** отправляет existing trade_bank только при допустимом displayed ratio; **Offer to Players** отправляет existing trade_offer_create/to_pid=null. Target dropdown отсутствует, offer accept/decline/cancel прежние. Draft не списывает hand; matching ACK закрывает/retry сохраняет input/error. Knight/Road Building click → request.submit(play_dev) → прежние server pending/free_roads → shared board controller. Monopoly/Plenty открывают только необходимый picker; VP — passive info, newly bought/action unavailable — disabled с reason. Чужие card types не передаются.

[DiscardPicker](../../web/src/game/DiscardPicker.tsx) получает только own res/required, локально выбирает карты и удаляет выбор, показывает selected/required; Confirm только при точной сумме. Отправляет прежний discard command, server error оставляет retry. [MatchSettings](../../web/src/components/RoomSettings.tsx) показывает host-controlled threshold; participant read-only, match locked. RulesConfig default 7, >threshold и floor(hand/2) исполняет engine.

[GameLog](../../web/src/game/GameEvents.tsx) читает recipient-filtered `state.game_events`, App transport log остаётся в collapsed Connection details, Chat отдельно. [CardFlights](../../web/src/game/CardFlights.tsx) читает только confirmed event details, отслеживает match/id/connection, пропускает initial/reconnect/rematch history. Bank↔hand для production/trade/discard/buy; theft victim→thief. Own exact faces, observer generic backs; никакого client delta theft inference. DOM animations конечные (900ms, production после settle), max 30 glyphs, timers cleaned, reduced motion skip.

DiceRoll3D: 600ms roll +300ms settle, hold до 2100ms, fade до 2500ms, затем compact exact DiceHUD; конечные transforms/invalidate без React frame state/physics. Robber — 420ms old→new movement, reduced instant. Static DecorativeOcean не имеет game IDs/targets и не меняет camera game bounds. TerrainHints — dispatcher независимых terrain visuals в board3d/terrain/. Port3D сохраняет оба vertex IDs. Camera auto-fit использует projected real footprint, размер viewport и offsets; 2D renderer и payloads не менялись.

[TestTools](../../web/src/game/TestTools.tsx) получает personalized test_tools=true только host явно enabled lobby room на test-enabled server; named ActionSubmit/ACK/feedback, только main. На OFF/normal room кнопки и команды запрещены. No accounts/raw editor. Live socket automatic token reconnect уже существовал; page refresh хранит token, ordinary Join восстанавливает матч, нового identity flow нет.

Evidence/limits — [[Design System#Game UX 2.3 — implemented playtest feedback]], [[plans/game-ui-redesign#Game UX 2.3 — Playtest Feedback Pass]].

[[Web клиент]] · [[Состояние игры]] · [[Стили и визуальные границы]] · [[Design System]]

Last verified **2026-10-06 — Game / Room UX 2.2**: 119 web tests, 234 pytest, TypeScript/production/Docker builds и 19 Chrome cases. Двухклиентские настройки/цвета/Balanced/countdown/Visible и Hidden bank/chat/refresh/rematch проходят. Результаты ниже относятся к прежним этапам; текущие limits — [[plans/game-ui-redesign#Game / Room UX 2.2 — Match Settings, Timer and Chat]].

## Game / Room UX 2.2 — settings, colors, timer and chat

LobbyPage сохраняет исходный map/custom JSON flow. Room card добавляет [MatchSettings / PlayerColors](../../web/src/components/RoomSettings.tsx); отдельный компактный Chat раскрывается по запросу. Настройки получают Room.settings, connected/isHost/status и WSClient.pendingSettings; only host+lobby editable. Target VP 3..30, исходный preset может иметь другую цель и честно показывается собственной option. Цвет получает own pid, room.players[].color и pendingColor; занятый цвет disabled, сервер повторно валидирует. Старт disabled до подтверждения карты и всех config requests.

UI → WSClient.setSettings/setColor → server Room validation → room_state с config_revision/request_id → App.room → lobby. Pending значения только визуальные: presence не подтверждает их, меньшая revision не откатывает состояние, disconnect/new room очищают pending, reconnect получает текущий Room. В одном WS более поздний подтверждённый запрос завершает предыдущие pending intents; подтверждение не основано на совпадении полей или timestamp. Прежние map_revision/queue/request error boundaries остаются.

[TurnTimer](../../web/src/game/TurnTimer.tsx) получает snapshot turn_timer текущего игрока. performance.now интерполирует server remaining_ms с обновлением раз в 250ms, интервал очищается при смене/unmount/blocked. Off не показывает timer, ≤10s warning, ≤5s stronger warning; blocked показывает Action required. UI не запускает Roll/End и не определяет deadline.

Event log drawer теперь имеет Game Log / Chat. Game Log сохраняет прежний App.log, полного engine event feed нет. [RoomChat](../../web/src/game/RoomChat.tsx) получает server history и connected, отправляет client.sendChat(text). История/name/color/time/order серверные, без optimistic messages и без HTML rendering; только draft живёт в React. WSClient.chat_state обновляет room history с chat_revision и сохраняет более новую историю при старом room_state. Чат отделён от gameplay seq и остаётся через refresh/rematch. Results/mandatory overlays сохраняют прежний приоритет и не открывают drawer.

BankSummary получает bank_available и только при snapshot room_settings.bank_visibility=visible — bank counts. По умолчанию закрыт, использует прежние icons. Hidden не вычисляет количества. Deck/count/order по-прежнему скрыты. Foreign exact hands/active hidden VP/private choices UI не запрашивает.

[board/colors.ts](../../web/src/board/colors.ts) разрешает public color ID независимо от pid; SVG, Three pieces/ghosts и top HUD используют одинаковую palette. Legacy pid palette — fallback только для old/offline snapshots. Snapshot players[].color — presentation, не identity/turn policy. Controller, legal targets, renderer geometry, terrain, trading/dev payloads и card/resource authority не изменены.

Новые UI границы:

| Блок | Данные | Локальное состояние |
| --- | --- | --- |
| MatchSettings | Room.settings + pendingSettings/isHost/status | Никакой альтернативной config model |
| PlayerColors | room.players, own pid, pendingColor | Только optimistic selection из WSClient |
| TurnTimer | authoritative remaining/deadline/stage | Visual elapsed и cleanup interval |
| RoomChat | history/name/color/id/time, connected | Draft текста; сервер владеет историей |
| Game Log / Bank | App.log, bank_available, optional public bank | Выбранная вкладка, раскрытие блока |

Browser: два реальных React contexts через nginx/WS, white/orange actual Three materials, four Balanced rolls на каждый bank flow, countdown между snapshots, literal HTML chat, both-client public bank policy, unchanged deadline/history/color после refresh, rematch reset и первый seq=1. Server auto-expiry/grace/mandatory lifecycle проверен fake-clock pytest; естественный полный матч/mobile/low-end не сертифицированы. Evidence — [[Design System#Game / Room UX 2.2 — implemented room policy and HUD]].

Основные UI-границы: App, LobbyPage, fullscreen GamePage, GameTopBar/ContextPrompt/ResourceHand/BankSummary/GameOverlay, ActionButton/DiceHUD и TradePanel/DevelopmentCards/Endgame в game/, BoardControls в dock, BoardRenderer, SVG BoardView и Board3D. Scene-компоненты находятся в board3d/. Action dock/player strip — JSX-блоки, не отдельные classes. MainMenu пока отсутствует.

Предыдущая verification 2026-10-05 — Game UX 2.1: 108 web tests, 203 pytest, TypeScript, production/Docker builds и 17 Chrome E2E cases. Прямой dock, hand-driven trade и server dice сохраняют общий controller/legal/ACK/privacy. Base/Gold на 1920×1080, 1440×900, 1280×720, включая paid road/settlement/city, ship/move/pirate, reduced motion и idle rendering. Engine не менялся; server добавил только dice/roll_count metadata. Проверки и пределы — [[plans/game-ui-redesign#Game UX 2.1 — Direct Actions / Trade Hand / Dice / Board Readability]]. Предыдущие результаты ниже исторические.

Game UI Phase 2 verified 2026-10-05: 92 web tests, 186 pytest, TypeScript, production/Docker build и 14 реальных Chrome E2E cases. Trade/dev/results используют существующие commands/snapshot и общий board controller; backend/protocol/renderer не изменены. Prepared games проходят через настоящий WebSocket в отдельном test stack; обычный production backend отдельно проверен setup/Roll/End/2D↔3D двумя клиентами. Подробности — [[plans/game-ui-redesign#Phase 2 — Trade / Development Cards / Endgame]].

Game UI Redesign Phase 1 verified 2026-10-05: 73 web tests, TypeScript, production/Docker build и Chrome. Default 3D; 2D сохранён. Новая композиция/HUD отделена от прежнего controller/network/gameplay. Scope, screenshots и limits — [[plans/game-ui-redesign]] и [[Design System#Game UI Redesign Phase 1 — implemented composition]].

Историческая проверка Board3D Phase 2 2026-10-05: общий controller перенесён из SVG в GamePage, оба renderer используют персональные server targets. 57 web cases, TypeScript/build, Docker и Chrome проверки проходят; детали и ограничения — [[plans/board3d]].

Контракт проверен 2026-10-02: UI-композиция не менялась в Phase 1. MatchState типизирован под персональный server snapshot, чужой player.res опционален, own res сохранена. BoardView Port соответствует текущему JSON `[edge, kind]`, pending_action/pending_pid допускают null. TypeScript проходит; отсутствие чужой руки обеспечивается сервером, а не JSX.

## Props и локальные данные

| Компонент | Кто создаёт | Props | Локальные данные |
| --- | --- | --- | --- |
| [App](../../web/src/App.tsx) | main.tsx | Нет | client, room, match, status, log, error |
| [LobbyPage](../../web/src/components/LobbyPage.tsx) | App | client, room, status, wsDefault, error | URL, имя, код, maxPlayers, pendingMapId, customLabel; отображаемый mapId = pending или room.map_id |
| [GamePage](../../web/src/components/GamePage.tsx) | App | client, match, room, status, log, error, onBackToLobby | Прежний useBoardInteraction; gold fields / separate DiscardPicker; drawer=log/info/dev/test/null, logTab=game/chat, controlled tradeDraft, selectedDev, dismissedOffers, useGameCommand waiting и useDicePresentation |
| [TradePanel / IncomingTrades](../../web/src/game/TradePanel.tsx) | GamePage | state, pid, draft/onChange/connected targets, submit, waiting, error, onClose; incoming также offers | TradePanel — controlled nonmodal tray; Give/Want/target в GamePage, balances/offers только из snapshot |
| [ActionButton](../../web/src/game/ActionButton.tsx) | BoardControls / GamePage | action, label, resources, disabled/selected/free/reason, onClick | Только hover/focus cost preview из costs.ts |
| [DiceHUD](../../web/src/game/DiceHUD.tsx) | GamePage | exact faces, finite roll visual, legacy total | useDicePresentation хранит previous match/counter, reduced-motion preference и 2580ms cleanup timer; результат не вычисляет |
| [DevelopmentHand / DevelopmentPanel](../../web/src/game/DevelopmentCards.tsx) | GamePage | state, pid; hand onCard, panel selected/submit/waiting/error/onClose/onBoardPlay | selected type, Year of Plenty counts, Monopoly resource; own cards/new из snapshot |
| [Endgame](../../web/src/game/Endgame.tsx) | GamePage при game_over | state, pid, room, connected, matchKey, error, onRematch/onLobby | Только ожидание rematch; winner/scores/pids не вычисляются локально |
| [BoardRenderer](../../web/src/components/BoardRenderer.tsx) | GamePage | state + interaction + diceRoll | mode=2d/3d, default 3d; lazy/failure boundary |
| [BoardControls](../../web/src/board/BoardControls.tsx) | GamePage action dock, оба режима | state + interaction + own resources | Direct tools/cost preview/context/victim callbacks; Build menu и собственный selection отсутствуют |
| [BoardView](../../web/src/components/BoardView.tsx) | BoardRenderer, режим 2D | state + interaction | SVG presentation, selection берётся из controller |
| [Board3D](../../web/src/board3d/Board3D.tsx) | BoardRenderer, режим 3D | state geometry/occupancy + interaction + optional diceRoll | hovered tile index, reset camera; InteractionOverlay3D хранит только hover; DiceRoll3D обновляет transforms в конечной анимации |

## Экраны

App показывает LobbyPage без match и GamePage при его наличии. Лобби до/после входа — один экран. Setup, обычный ход, discard/gold, trade/dev dialogs и results — состояния одного игрового экрана. Back to Lobby явно завершает локальное соединение/очищает App match; новая комната или явный Join доступны через прежнее lobby.

## Данные UI-блоков

| Блок | Где | Данные и поведение |
| --- | --- | --- |
| Главная / бренд | PageShell + Home branch LobbyPage | Brand, account/connection status, hero, Continue/account/guest recovery |
| Host / Join | LobbyPage | Имя, отдельные формы числа мест/кода; manual URL в Advanced connection; существующие WS intents |
| Карта комнаты | LobbyPage | room.map_presets/id/meta/rules и map_revision, isHost, client.pendingMapId; setMap из onChange/FileReader |
| Участники лобби | LobbyPage | room.players, host_pid, connected |
| Turn/prompt и Game info | GameTopBar/ContextPrompt/GameOverlay | turn, snapshot/controller; raw tick/phase/pending/status/map/rules скрыты в закрытом info drawer |
| Ресурсы | ResourceHand / ResourceCard | find(player.pid=youPid).res; пять cards, отсутствующее значение = 0; click создаёт/увеличивает local Give draft, руку не списывает |
| Roll / End Turn | GamePage | canRoll/canEnd; отправляют roll/end_turn |
| Gold Choice | GamePage | pending_gold[youPid], goldRes, goldQty; choose_gold |
| Discard | DiscardPicker | discard_required[youPid], own res, local card selection; прежняя discard-команда |
| Игроки матча | PlayerStrip | public pid/name/color/vp/resource_count/dev_count/turn и optional turn_timer; без чтения чужой руки |
| Ошибки | LobbyPage и GamePage | error.message |
| Журнал / банк | GameLog / RoomChat / BankSummary | personalized game_events, отдельный чат/connection log; bank_available и optional Visible counts, open bank / collapsible log |
| Trade | TradePanel / IncomingTrades / TradeOffers | own res, ports/occupied_v, bank_available, public offers, players/turn/rolled/pending; bank/create/accept/decline/cancel |
| Development cards | GamePage ActionButton / DevelopmentHand / DevelopmentPanel | Dock buy_dev; own dev_cards/new, dev_played_turn/free_roads, bank_available и turn/pending для private play/inspect/pickers |
| Dice | DiceHUD / DiceRoll3D | Только server dice и roll_count; last_roll — legacy total, не источник выдуманных граней |
| Results | Endgame | game_over, winner_pid, final players.vp, room connected/host; существующие rematch/leave_room |
| Строительство и перемещения | BoardControls + оба renderer | interaction.action/targets/selection; server legal, исходные vertex/edge/tile IDs |
| Выбор жертвы | BoardControls | selection.victim.victims из personal legal, публичные player names; move_robber/move_pirate с victim |

Roll доступен в свой ход основной фазы до броска и без pending-action. End Turn зависит от своего хода, rolled и отсутствия pending-action. presentation.turnActions сохраняет эти прежние условия; проверки правил остаются на сервере.

## Game UX 2.1 — direct actions, hand trade and dice

Dock сразу показывает Road/Settlement/City; Ship появляется только по enable_seafarers=true и положительному max_ships. Инструменты используют только counts из personal legal, нулевые доступны для просмотра стоимости, но disabled. Setup показывает лишь обязательный инструмент. Hover/focus ActionButton читает один [costs.ts](../../web/src/game/costs.ts); missing quantity приглушена, free — из legal.road_free/setup. BoardControls вызывает прежний onSelectAction, renderer callback → shared controller → WSClient; стоимости в renderer нет.

Dock Dev Card → useGameCommand.submit({type:buy_dev}) → один cmd_id/ACK. Повторный click до собственного результата подавляется существующим pending ref. Private DevelopmentHand → DevelopmentPanel Play/inspect, без второй кнопки покупки. Карты и ресурсы появляются/списываются только из snapshot; new/one-play/VP/Plenty/Monopoly ограничения сохранены. Roll и End также проходят через этот matching-ACK helper с прежними payloads/availability.

ResourceHand click → addHandResource → GamePage.tradeDraft → TradePanel (немодальный Trade Tray над рукой). Give capped own count; Want строится пятью ResourceCard, выбранные обе стороны можно уменьшать. Target = Everyone/connected pid/Bank; disconnect делает прежний target недоступным. Snapshot/actual hand не мутируется. BankDraftReason показывает owned 4/3/2:1, допускает только один тип с каждой стороны и give=rate×get_qty; server отдельно проверяет фактический банк/руку. Все trade command names и offer lifecycle прежние. Matching successful ACK закрывает tray; отказ сохраняет draft/error. Escape/close закрывают без команд; turn/pending/match change сбрасывают local tray. Incoming offers и creator cancel остаются compact cards.

Server Roll → Room.dice/roll_count → personal match_state → App.setMatch → useDicePresentation → постоянный DiceHUD и optional BoardRenderer.diceRoll → DiceRoll3D. serverDice принимает только две целые грани 1..6, не разбивает сумму. Начальная загрузка/new match не анимируют исторический бросок. В той же партии увеличение counter запускает 950ms детерминированную траекторию уже известных граней, включая одинаковые пары подряд. Стабильные face primitives/counter не перезапускают её от других snapshot. Three useFrame обновляет только transforms, invalidate вызывается лишь до конца; final orientation соответствует face, после cleanup scene idle. Reduced motion отменяет анимацию. 2D показывает те же faces с коротким HUD transition, 3D рисует объёмные dice; switch не отправляет команду.

Public dice metadata живёт в Room, не в альтернативной игровой модели. Engine по-прежнему получает сумму; privacy, identity, sequencing и maps неизменны. Новый renderer использует прежние geometry/material pools: terrain/piece детали статичны; Port3D branches сохраняют оба original vertex ID, coastline использует supplied edge_adj_hexes. Camera/Canvas fit — только визуальная геометрия. Границы протокола — [[Сервер и протокол#Authoritative dice faces — Game UX 2.1]].

Текущие 17 real Chrome cases включают прежние 14 trade/dev/results/reconnect/setup проверок плюс direct builds/tray/layout, exact/repeated/reduced-motion dice/refresh и Gold Haven ship/move/pirate. Prepared states — только test initializer, commands и snapshots настоящие; без full-match/mobile/low-end certification. Runner — [web/e2e/README.md](../../web/e2e/README.md), evidence — [[Design System#Game UX 2.1 — implemented direct tabletop UX]]. Следующая секция описывает Phase 2 исторически; актуальные modal/menu boundaries изменены выше.

## Trade / Development Cards / Endgame — Phase 2

[actions.ts](../../web/src/game/actions.ts) — чистые presentation helpers: лучший отображаемый maritime ratio по public ports и own ownership, disabled reasons, целочисленные количества, self-only dev grouping, public offer audience, server winner standings и rematch hint. Это не альтернативный GameState/executor; сервер повторно проверяет всё. MatchState лишь типизирует уже существующие trade_offers/game_over/winner_pid/free_roads/dev_played_turn, wire shape не меняется.

Путь нового действия: GamePage → TradePanel/DevelopmentPanel → useGameCommand.submit → WSClient.sendCmd → серверный apply_cmd → player-specific snapshot → App.setMatch → UI. [useGameCommand](../../web/src/game/useGameCommand.ts) привязывает ожидание к конкретному cmd_id. Чужой snapshot не завершает собственный запрос; matching ACK снимает waiting. При reconnect consumed intent без известного результата снимает ожидание с applied=null, не изображая успех. Choices остаются редактируемыми после отказа; ресурсы/карты/pieces никогда не генерируются optimistic.

- Bank: existing trade_bank/give/get/get_qty=1, ratio 4/3/2. Players: trade_offer_create/give/get/to_pid, accept/decline/cancel по offer_id. Off-turn recipient использует свою hand; состав creator hand не угадывается. Targeted terms уже публичны в server snapshot. Broadcast Reject закрывает предложение для всех; change = cancel + новое, disconnect сам по себе не закрывает offer, end turn закрывает активные.
- Buy: existing buy_dev, стоимость показана 1 Ore/Sheep/Wheat. Hand/type/new приходит только владельцу. Старые карты можно играть до Roll; new, already-played и pending блокируют Play. Passive VP без кнопки Play. Покупка разрешена после сыгранной карты, если серверные условия соблюдены.
- Knight: play_dev/card=knight → existing robber_move → shared targets/victim callbacks. Road Building: play_dev/card=road_building → personal free_roads/legal.road_free → тот же place_road/free=true. Prompt показывает 1/2 и 2/2. Автовыбор road выполняется после reconciliation board waiting, чтобы не восстановить старый waiting и не заблокировать вторую дорогу; free counter не уменьшается в React.
- Year of Plenty: ровно две карты, existing a/qa/b/qb. bank_available сообщает только есть/нет: две одинаковые при остатке одной отклоняются сервером, picker сохраняется. Monopoly: existing play_dev/card=monopoly/r, изменение hand только из snapshot. Engine events не передаются: клиент не сочиняет trade/dev историю; прежний log сохраняет реальные transport/error messages.
- Results: game_over показывает winner_pid и итоговые players.vp. Активные controls скрыты, engine также блокирует команды. Rematch вызывает прежний server flow, hint читает connected/host, новый match сбрасывает UI state. Потеря соединения снимает rematch waiting для явной повторной попытки; произвольный timeout/optimistic new match не используется. Back to Lobby вызывает existing leave_room + WSClient cleanup; auto-reconnect остановлен, token cache сохранён для Join с прежними room/name (lobby Name по умолчанию Player).

E2E runner и test-only initializer: [web/e2e/README.md](../../web/e2e/README.md). Проверены 4/3/2:1, отказ/retry/atomicity, targeted/broadcast accept/reject/cancel/end, buy/aging/new/one-play restrictions, Knight, обе free roads до Roll, Year of Plenty retry, Monopoly, active/final VP privacy, win/post-game rejection, rematch с connected/disconnected host, потерянный rematch, refresh/token/new pid/sequence и leave/rejoin. Desktop 1280×720/1440×900/1024×768 без горизонтального scroll/hand-dock overlap; mobile/full natural game не заявляются. Known engine gaps — [[Project State]].

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

BoardView рисует SVG markers; [InteractionOverlay3D](../../web/src/board3d/InteractionOverlay3D.tsx) — vertex rings/тонкие edge rails с невидимыми увеличенными hit surfaces. После Polish 1.1 HexTile3D подсвечивает настоящую плитку через pooled emissive material: второго tile outline mesh нет. Hover светлее, выбранный ship source/victim tile выделен янтарным. Terrain decoration исключён из raycasting, чтобы не перехватывать legal clicks. Оба renderer вызывают одинаковые callbacks. Three не импортирует SVG internals; edgeId находится в board/constants.ts, public color mapping — в board/colors.ts (PLAYER_COLORS остаётся legacy fallback). Coordinate mapping Phase 1 сохранён.

Путь: click → shared callback → GamePage.sendCmd → WSClient → server._apply_cmd → неизменный engine.apply_cmd → _snapshot_state с personal legal → App.setMatch → GamePage → оба renderer. Waiting блокирует повторные board clicks до ответа. Фигуры не создаются optimistic. Error снимает ожидание/source/victim и показывает существующий feedback; snapshot заново проверяет доступность selection. Новый room+match сбрасывает selection. При 2D↔3D сохраняются tool, ship source и victim choice; GameState и tick не меняются. Payloads/условия Roll/End/discard/gold сохранены; их представление перенесено в dock/choice overlays.

Проверено в Chrome 154 через production Docker: Base два клиента, 8 setup commands через 3D → Roll → road → End (tick 11); Gold Haven выбран через lobby, 3D setup, pirate после 7, ship и move ship [6,9]→[9,12], End; 2 хода/tick 15. Public state и pieces совпадают у клиентов, build mode/обычный turn/setup переживают переключение, 1440×1000/1280×720/1024×768 без horizontal overflow. Отдельные engine-built fixtures с mocked browser transport проверили SVG и 3D settlement/city/road/ship, move source/cancel/destination с переключением, robber/pirate с выбором второго из двух victims, free roads до Roll и rejected stale command без phantom piece. SVG fixture setup завершён всеми 8 кликами. Fixtures не означают естественное достижение этих состояний в короткой партии. Полная партия/mobile не проверялись.

## Композиция Phase 1

GamePage подключает один useBoardInteraction и передаёт один state/interaction в selector/renderers и BoardControls. HUD/presentation helpers только читают snapshot: нет стоимости/новых IDs/локальной GameState. GameSnapshot нормализует пересечённый TypeScript players array для итерации, добавляет уже существующие runtime game_over/last_roll в локальный UI тип; WS shape/семантика не меняются.

Build palette показывает только инструменты с существующими personal legal targets, не рассчитывает affordability. Turn/pending смена закрывает локальную palette; выбор инструмента/Cancel вызывает прежний controller. Setup автоматически следует setup_need. ContextPrompt описывает controller step, включая source/destination/victim/waiting, а не создаёт новую state machine. Game info и log — закрытые nonmodal drawers; Escape/close возвращают focus. Victim chooser тоже nonmodal, переключение renderer сохраняет выбор; discard/gold — mandatory modal с focus trap и прежними полями/payloads.

Реальные два клиента через Docker: Base setup/Roll/road/robber tick 21, Gold setup/Roll/ship/pirate tick 28; public snapshots совпали. Engine-built fixtures отдельно прошли оба renderer для четырёх build tools, move ship/cancel/destination, multiple victims, free roads и rejected commands без phantom pieces. Отдельно проверены drawer toggle/Escape/focus, selector/reset, choice focus trap и шесть длинных имён. 1920×1080/1440×900/1280×720 без page scroll/перекрытия HUD. Полная партия/mobile/low-end/a11y certification не проверялись. Существующий нюанс terrain decoration/road midpoint occlusion не исправлялся.

## Текущее дерево

```text
App / AuthProvider (existing cookie/ownership/claim flows)
├── PageShell (no match) → Brand / connection status / AccountControls
│   └── LobbyPage
│       ├── Home → hero / AccountGames + RecentGames → GameCard / identity / Host + Join forms
│       └── Room → code/map/presence / players + PlayerColors / Start / RoomChat / map + MatchSettings
│           └── Enable Test Room (only host, flag ON, lobby)
└── GamePage → one snapshot / useBoardInteraction / useGameCommand
    ├── GameTopBar → brand / goal / info / event button
    ├── ContextPrompt → header center, pointer-events none
    ├── BoardRenderer → compact 2D/3D/reset
    │   ├── BoardView → original SVG + shared callbacks
    │   └── Board3D / Canvas / CameraRig / VisualResources
    │       ├── DecorativeOcean / Coastline (static, no game IDs)
    │       ├── HexTile3D → TerrainHexVisual (GLBs; TerrainHints fallback) + NumberToken3D
    │       ├── Pieces3D / Port3D / finite DiceRoll3D
    │       └── InteractionOverlay3D → same legal / targets / ghosts
    ├── Right sidebar
    │   ├── PlayerStrip → public players / TurnTimer
    │   ├── Collapsible GameLog / RoomChat + connection details
    │   ├── BankSummary → real visible counts or hidden backs/availability
    │   └── Test Tools button (authorized test host only)
    ├── Bottom HUD
    │   ├── TradePanel / TradeOffers (when opened/present)
    │   ├── ResourceHand → five stack ResourceCard
    │   ├── DevelopmentHand → direct play / necessary picker / passive VP
    │   └── DiceHUD / Roll / Dev Card buy / End / shared BoardControls
    ├── CardFlights → personalized events, finite CSS, no state mutations
    ├── GameOverlay Info / victim chooser / gold choice
    ├── DiscardPicker → mandatory own-card selection
    ├── IncomingTrades / DevelopmentPanel (Monopoly/Plenty/VP only)
    ├── TestTools → named validated commands (authorized test host only)
    └── Endgame → winner / final VP / rematch / leave
```
