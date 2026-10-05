---
tags: [catan, дизайн, концепт]
updated: 2026-10-06
---

# Design System

[[00 Главная]] · [[React интерфейс]] · [[Стили и визуальные границы]] · [[plans/game-ui-redesign]]

## Game / Room UX 2.2 — implemented room policy and HUD

Implemented and verified **2026-10-06**, based on e9db7af. The user separately accepted room settings, unique colors, server timer, chat and optional visible bank. Their concept-only status in the earlier 2.1 reference describes that earlier phase. Current direction remains clean modern tabletop, board primary, compact overlays, no new fantasy/commercial art or dashboard redesign.

- Lobby retains existing map/custom JSON/connection layout. The Room column adds compact dark native selects for Dice, Starting player, Turn timer, Bank counts and Target VP, six color swatches and a collapsible chat. Read-only/occupied/locked controls are explicit; pending intent waits for authoritative confirmation. Alignment/contrast fixes are scoped to these controls rather than a full lobby/menu redesign.
- Player colors red/blue/orange/white/green/purple are independent of pid/turn order and used consistently in top HUD, SVG, Three pieces/ghosts and chat indicators. White stays readable against navy. Geometry/terrain/camera/IDs and the shared interaction controller remain intact.
- Current player shows a compact turn label plus countdown. 10s amber and 5s stronger accent, no flashing screen; Off omits the timer. An expired mandatory state shows Action required; no invented auto-placement.
- The closed right drawer has Game Log / Chat tabs. Chat is plain text with name/color/time, a scrollable bounded history and a 500-character input. Game Log remains real existing transport information, not an invented authoritative engine feed. Mandatory/results overlays keep priority.
- Bank is collapsed by default and uses existing resource icons. Visible shows real snapshot counts; Hidden shows availability/counts hidden. Development deck/count stays hidden. Exact bank in Visible is a deliberate casual-product privacy tradeoff, especially in two-player games.

119 web tests, 234 pytest, TypeScript, production/Docker builds and 19 Chrome 154 E2E cases pass. Two new room flows verify Visible/Hidden, Balanced outcomes, starter policies, white/orange real meshes, countdown, plain-text chat, refresh/deadline/history and rematch. Existing Base/Gold cases and desktop match sizes 1920×1080, 1440×900, 1280×720 remain green. Browser screenshots use first-match engine-built fixtures; no claim of a natural full match/mobile/low-end test. Timer auto-expiry is verified with server clock tests rather than a long browser wait. No new runtime dependencies; existing lazy Three size warning remains.

Actual Chrome evidence (not concept art):

| Evidence | State shown |
| --- | --- |
| [roomux-lobby.png](../design/references/game-ux-2-2/roomux-lobby.png) | Host settings, locked occupied colors, room chat, connected participants |
| [roomuxhidden-lobby.png](../design/references/game-ux-2-2/roomuxhidden-lobby.png) | Host/Hidden policy and the same lobby controls |
| [roomux-bank-visible.png](../design/references/game-ux-2-2/roomux-bank-visible.png) | Compact timer/current player, public bank counts, selected piece colors |
| [roomux-bank-hidden.png](../design/references/game-ux-2-2/roomux-bank-hidden.png) | Hidden policy without exact resource counts |
| [roomux-chat-visible.png](../design/references/game-ux-2-2/roomux-chat-visible.png) · [roomux-chat-hidden.png](../design/references/game-ux-2-2/roomux-chat-hidden.png) | Separate chat tab rendering literal HTML text safely |
| [roomux-rematch-visible.png](../design/references/game-ux-2-2/roomux-rematch-visible.png) · [roomux-rematch-hidden.png](../design/references/game-ux-2-2/roomux-rematch-hidden.png) | New setup/match, retained colors/settings, timer absent until main |
| [verification.json](../design/references/game-ux-2-2/verification.json) | Date/browser, 19 passing cases, 78 command attempts, 7 expected rejections; no tokens/private snapshots |

Scope/data authority/limits — [[React интерфейс#Game / Room UX 2.2 — settings, colors, timer and chat]] and [[plans/game-ui-redesign#Game / Room UX 2.2 — Match Settings, Timer and Chat]]. Earlier phase descriptions below are historical.

Status: Clean modern tabletop accepted 2026-10-04. Game / Room UX 2.2 implemented/verified 2026-10-06 after Game UX 2.1. Match uses direct actions, hand trading, server dice/timer, chat and optional public bank; room settings/colors are implemented. Full lobby/menu/general settings/mobile redesign and final cross-screen tokens remain future work. Earlier mockup/phase descriptions and AI images retain their dated historical status.

## Game UX 2.1 — implemented direct tabletop UX

Verified 2026-10-05, based on `dcadcab`. The supplied mockup informs hierarchy, hand/dock placement, visible dice, richer board and compact secondary log/bank information. Its exact art, decorative ocean environment, chat, settings, avatars/bots and visible bank counts are concepts rather than accepted implemented features. The original image is available in the conversation; no nonexistent repository image is linked. Earlier Colonist references are UX references only. The implementation stays dark modern tabletop with native SVG marks/basic Three geometry, no commercial assets or new dependencies.

- Base dock: Roll, Road, Settlement, City, Dev Card, End Turn. Seafarers adds Ship only if server rules enable ships and max_ships > 0. Setup retains only the required Settlement/Road. Build dropdown and dock Trade button are removed. Contextual movement/victim/cancel controls still use the shared controller.
- Cost strips appear on hover/focus, including keyboard focus on disabled actions. One presentation mapping supplies quantities; missing resources use reduced opacity. Free road/setup previews say Free placement. Server legal/executor remains authoritative.
- Dev Card in dock buys with one existing buy_dev intent; owned dev mini-cards open Play/inspect. No optimistic card; new/one-play/passive VP remain unchanged.
- Click a resource hand card to add Give and open a nonmodal tray above the hand. Repeated clicks increment up to own count; clicking selected Give decrements. Five shared resource cards build Want, with independent removal. Targets are Everyone, connected players or Bank. Draft copies never subtract actual hand. Bank ratio comes from owned port endpoints; exact 4/3/2:1 batches and invalid-combination feedback use the same tray. Incoming/own offers remain compact cards with existing accept/reject/cancel lifecycle.
- Two ivory pip dice stay in the dock. Only server dice=[a,b] supplies faces; a legacy sum cannot supply a guessed pair. A new roll_count drives a finite 950ms procedural 3D bounce/rotation, ending at known orientations; reduced motion skips it. Final pair remains after End Turn and resets on rematch. Scene returns to demand-rendered idle.
- Each port has two visible branches/posts to the exact existing edge vertices. Placards stay compact; auto-port placement defects are not altered. Static coastline uses supplied edge adjacency, not new topology. Forest clusters, wheat rows, sheep/grass, clay mounds, low-poly peaks, dunes/stones, gold nuggets and quiet sea waves are denser; number tokens remain clear. Small piece plinth/roof/deck/band details preserve IDs/ownership/placement.
- Canvas uses the available board stage; camera fits actual tile/decor/port footprint. Base land grew about 17.1%, 17.3%, 19.1% in width at 1920×1080, 1440×900, 1280×720 (height 17.4%, 17.6%, 19.4%). Both maps fit without permanent HUD occlusion or port/piece clipping. Comparison uses the same Base preset/topology with separately generated terrain, not pixel-identical board art.
- Event log stays a closed right drawer; its collapsible Bank availability shows public available/empty, not invented quantities. Engine event feed/chat is still absent; real transport messages remain the log source.

108 web tests, 203 pytest, TypeScript, production/Docker builds and 17 Chrome 154 E2E cases pass. Real nginx/WebSocket commands exercise bank/player trade, direct paid roads/settlement/city, buy/private play, all dev restrictions, privacy, rematch/reconnect and Gold Haven ship/move/pirate. Prepared states are test fixtures; ordinary setup uses unprepared state. Idle adds zero frames after dice; low-end FPS, mobile, 50-tile live scene and a full naturally played match were not re-certified in this step. Existing lazy Three chunk warning remains (887.59 KB / 239.17 KB gzip).

These are actual Chrome screenshots and measurement evidence, not generated art or additional mockups:

| Evidence | What it shows |
| --- | --- |
| [before-base-1280.png](../design/references/game-ux-2-1/before-base-1280.png) | Before changes, previous production Base framing |
| [base-1920.png](../design/references/game-ux-2-1/base-1920.png) · [base-1440.png](../design/references/game-ux-2-1/base-1440.png) · [base-1280.png](../design/references/game-ux-2-1/base-1280.png) | Larger board, direct Base dock, real paid pieces, port branches |
| [city-cost.png](../design/references/game-ux-2-1/city-cost.png) | Exact City quantities on hover |
| [resource-trade-tray.png](../design/references/game-ux-2-1/resource-trade-tray.png) | Nonmodal hand-driven Give/Want, selected counts/removal |
| [bank-tray-3.png](../design/references/game-ux-2-1/bank-tray-3.png) | Same tray with actual owned 3:1 port ratio |
| [incoming-trade.png](../design/references/game-ux-2-1/incoming-trade.png) | Targeted offer on the other client |
| [dice-rolling.png](../design/references/game-ux-2-1/dice-rolling.png) · [dice-reduced-motion.png](../design/references/game-ux-2-1/dice-reduced-motion.png) | Confirmed 4+5 visualized in 3D / immediately in HUD |
| [gold-haven-1920.png](../design/references/game-ux-2-1/gold-haven-1920.png) · [gold-haven-1440.png](../design/references/game-ux-2-1/gold-haven-1440.png) · [gold-haven-1280.png](../design/references/game-ux-2-1/gold-haven-1280.png) | Real Seafarers preset: sea/gold, Ship/move and pirate |
| [log-bank-drawer.png](../design/references/game-ux-2-1/log-bank-drawer.png) | Secondary availability without hidden bank counts |
| [metrics.json](../design/references/game-ux-2-1/metrics.json) | Before/after framing, actual Three calls/triangles, clipping/HUD checks |

Flow and boundaries — [[React интерфейс#Game UX 2.1 — direct actions, hand trade and dice]], implementation/verification limits — [[plans/game-ui-redesign#Game UX 2.1 — Direct Actions / Trade Hand / Dice / Board Readability]]. Phase 2 modal/Build descriptions below are historical.

## Game UI Phase 2 — implemented actions and results

Implemented and verified 2026-10-05, based on clean 9c6c820. Existing dark navy/graphite tabletop/HUD preserved. Board/terrain/pieces/controller were not redesigned. Forms are native React/CSS under web/src/game/ with existing GameOverlay/GameIcon; no new runtime dependencies, commercial assets, fantasy card art or confetti.

- Trade: compact 540px maximum modal, Bank / Players tabs. Bank shows give/receive and owned 4/3/2:1 ratio. Player offer uses parallel Give/Want steppers, target/Everyone, readable resource terms and accept/reject/cancel. Incoming offers use the existing right-side nonmodal drawer. Broadcast Reject explicitly says it closes the whole offer. To edit, cancel then send a replacement.
- Personal dev mini-hand sits beside the bottom-left resource hand: small icon/name/count cards, ready accent and accessible unavailable reason. Own types/new only; opponent strip retains public count. Details/buy/pickers use a 470px maximum modal. VP stays passive with no Play button. Knight/roads return to the same board targets; Road Building prompt advances from the server free counter.
- Year of Plenty selects exactly two; Monopoly selects one resource. Exact bank/deck counts stay hidden: server refusal keeps choices and shows the actual error. No generated card/resource history or optimistic hand changes.
- Results: 480px maximum modal over the existing board, server winner/final VP/standings, Rematch and Back to Lobby. No particles or new menu screen. Final VP reveal does not reveal opponents' cards/resources. Disconnected host/rematch minimum and compact pids follow the server, not a new UI rules engine.

92 web tests, 186 pytest, TypeScript, production/Docker build and 14 real Chrome 154 E2E cases pass. E2E prepares rare states only in an isolated Docker backend; actual commands/privacy/ACK/validation remain real. Ordinary production backend separately passed two-client Base setup/Roll/End/2D↔3D. Desktop 1280×720, 1440×900, 1024×768 checked for no horizontal scroll/hand-dock overlap; demand rendering remains idle without additional frames. Full naturally played match/mobile/low-end/a11y certification are not claimed. Three lazy chunk retains its existing size warning.

These images are actual Chrome screenshots from prepared engine states through real WebSocket, not additional accepted mockups or naturally completed full matches:

| Evidence | State |
| --- | --- |
| [bank-3.png](../design/references/game-ui-phase2/bank-3.png) | Owned generic port, authoritative 3:1 exchange |
| [incoming-trade.png](../design/references/game-ui-phase2/incoming-trade.png) | Other client's targeted offer and off-turn response |
| [private-development-hand.png](../design/references/game-ui-phase2/private-development-hand.png) | Five own types, passive VP detail; public opponent count |
| [match-results.png](../design/references/game-ui-phase2/match-results.png) | Winning VP purchase, revealed final scores and rematch/exit |

Interaction/protocol boundaries — [[React интерфейс#Trade / Development Cards / Endgame — Phase 2]], verification/gaps — [[plans/game-ui-redesign#Phase 2 — Trade / Development Cards / Endgame]]. Older unavailable Trade/Dev descriptions below describe Phase 1 only.

## Polish 1.1 visual evidence

Implemented renderer polish, verified 2026-10-05 in Chrome 154 headless through Docker production frontend. Composition/HUD unchanged. Actual tile surface gets subtle emissive feedback; no flat second hex. Static per-tile variations distinguish repeated forest/fields/pasture/hills/mountains/desert/gold; sea stays quiet. Slightly deeper/bevelled pieces retain original centers and TILE_TOP. Ports use small dark placards and docks attached to snapshot edges; auto-port placement errors are intentionally preserved. Full horizontal orbit with constrained vertical tilt, zoom and reset. Decorative terrain does not intercept legal targets.

These are screenshots of implemented prepared snapshots, including an artificial offset 50-hex engine fixture, not new map presets or final design concepts. Base/Gold live two-client gameplay was verified separately. 76 web tests/TS/build/Docker passed; frameloop=demand gave 0 extra idle frames for Base/Gold/50 and unmount released geometry/textures/context. Mobile/low-end FPS/full-match remain unverified. Detailed scope and evidence limits: [[plans/board3d#Game UI / Board3D Polish 1.1]].

| Evidence | What it shows |
| --- | --- |
| [base-default.png](../design/references/game-ui-polish-1-1/base-default.png) | Base, 1920×1080: terrain, pieces, docks, board framing |
| [base-hover.png](../design/references/game-ui-polish-1-1/base-hover.png) | Subtle actual surface feedback; no extra hex |
| [base-rotated-180.png](../design/references/game-ui-polish-1-1/base-rotated-180.png) | Opposite camera side, rear piece details |
| [base-build-targets.png](../design/references/game-ui-polish-1-1/base-build-targets.png) | Thin road targets, hidden enlarged hit surfaces |
| [base-1280.png](../design/references/game-ui-polish-1-1/base-1280.png) | Base at 1280×720; ports/HUD contained |
| [seafarers.png](../design/references/game-ui-polish-1-1/seafarers.png) | Gold Haven: sea, gold, ship, pirate, ports |
| [seafarers-move-ship.png](../design/references/game-ui-polish-1-1/seafarers-move-ship.png) | Selected ship source and move targets |
| [50-default.png](../design/references/game-ui-polish-1-1/50-default.png) | Offset 50-hex fixture default auto-fit |

## Reference versus accepted design

**Design mockups are references, not final implementation specifications.**

Перед реализацией конкретного экрана дизайн может быть уточнён. Отличие текущего React UI от reference не означает автоматически, что код ошибочен. Изображения служат источником отдельных идей, но не задают gameplay, протокол или обязательный список функций. Принятие пользователем изображения как reference не равно утверждению каждой кнопки, надписи и числа. Актуальное направление ниже имеет приоритет над стилистикой старых AI-макетов.

Текст AI-макетов не является точной спецификацией игровых правил. Gameplay определяется [[Спецификация пользователя]], [[Правила Base Game]], [[Правила Seafarers]] и [[Инварианты движка]]. Ни правила, ни исходники не изменялись при анализе.

В описании ниже **наблюдение** означает видимое в изображении; **UX-интерпретация** — предполагаемое назначение, требующее проверки; **Concept / TBD** — неутверждённое решение. Статичные изображения не доказывают hover, animation, keyboard interaction, сохранение настроек или доступность.

## Product Direction

**Актуальное требование пользователя, 2026-10-04: современный чистый clean stylized tabletop.** 3D нужен прежде всего игровому полю. UI вокруг карты функционален, читаем и не перегружает поле. Fantasy/MMORPG-стилистика, массивные золотые рамки, свечи, таверны, RPG portraits и декоративное средневековое окружение исключены.

- Board — главный объект; terrain, number tokens, игровые фигуры, ports и legal placement должны читаться сразу.
- Информация о текущем ходе и действиях заметна без перекрытия клеток. Цвет дополняется формой, иконкой и текстом.
- Ресурсы и личные карты отделены от публичных данных соперников; их секретность обеспечивает server snapshot.
- Для match Phase 1 пользователь принял направление: компактные игроки сверху, resource hand слева снизу, action dock справа снизу, secondary drawers и dark unified board stage. Реализованные размеры/цвета — текущие match styles, не окончательные cross-screen tokens.
- Старые dark/gold AI-макеты сохранены ниже как исторические observations/reference. Их декоративный стиль не является текущей целью.

### Base Game board

Один компактный остров, слегка объёмные hex tiles, clean stylized tabletop. Forest/hills/fields/pasture/mountains различаются по цвету и форме/иконке. Number tokens крупные и читаемые с выбранного ракурса. Roads/settlements/cities — простые игровые фигурки на соответствующих edges/vertices. Реалистичный город на каждом hex не нужен. Море спокойно и не отвлекает; для Base оно может быть визуальным окружением без добавления sea tiles в engine.

### Seafarers board

Та же визуальная система и тот же UI вокруг игры. Добавляются sea hexes, несколько островов, ships, pirate, gold field и maritime ports. Fog/unexplored показываются только при фактической поддержке выбранного сценария: сейчас такой модели в engine нет. Поставляемые Seafarers presets имеют один связный land core; несколько островов — направление для будущих custom/generated карт, не описание уже готового сценария. Отдельная fantasy/pirate theme не создаётся.

### Board3D Phase 1 — visual foundation checkpoint

Python GameState → player-specific snapshot → WSClient/App React state → GamePage → BoardRenderer → Board3D → Three.js scene. **Renderer, not rules engine.** Board3D получает геометрию/occupied data, не получает WSClient или command callbacks и не вычисляет стоимость, legal targets либо игровые решения. model.ts — read-only projection позиций для meshes, без альтернативной модели партии. Hover/click возвращает только исходный tile index в локальную подпись; GameState и network tick не меняются.

BoardRenderer предлагает 2D / 3D Experimental. По умолчанию 2D; SVG BoardView и его gameplay handlers сохранены. В 3D доступны визуальный просмотр и существующие sidebar actions; для placement/robber/pirate требуется вернуться в 2D. Полный interaction остаётся Phase 2.

```text
web/src/board3d/
  Board3D.tsx
  HexTile3D.tsx
  TerrainHints.tsx
  Pieces3D.tsx         # Road/Settlement/City/Ship/Robber/Pirate placeholders
  Port3D.tsx
  NumberToken3D.tsx
  CameraRig.tsx
  coordinates.ts
  materials.ts
  model.ts
  types.ts
  board3d.css
```

coordinates.ts: server X / state.size → Three X; server Y / state.size → Three Z; visual elevation → Three Y. Centers имеют приоритет, q/r — fallback при отсутствии center. Radius гекса = 1 scene unit. Ориентация совпадает с pointy-top server grid; игровой graph/IDs не пересоздаются. Фигуры используют исходные vertex/edge IDs и PLAYER_COLORS (после Phase 2 общий board/constants.ts). Порт остаётся связанным с исходным edge; небольшой внешний offset label — только оформление. Ошибки auto-port placement не исправлялись.

Закреплены @react-three/fiber 8.18.0, Three.js 0.180.0 и dev @types/three 0.180.0. React/React DOM 18.3.1, Vite 5.4.21 и TypeScript 5.9.3 сохранены; версии прежних lockfile packages не изменились. Fiber 8 соответствует React 18 ([официальная compatibility](https://r3f.docs.pmnd.rs/getting-started/introduction), проверено 2026-10-04). OrbitControls берётся из Three.js; drei, внешние 3D assets и font downloads отсутствуют. Board3D загружается отдельным lazy chunk только после выбора 3D.

**Visual language Phase 1:** неглубокие настоящие шестигранные meshes, контрастные верхние площадки/боковины и видимые зазоры. Forest — зелёный + простые деревья; hills — clay + небольшие холмы; pasture — светло-зелёный + sheep hint; fields — светлое золото + wheat; mountains — холодный серый + peaks; desert — песочный + низкие dunes; sea — спокойный голубой + статичные wave marks; gold — более тёмный gold terrain + faceted nuggets. Цвет и силуэт работают вместе. Это проверенная экспериментальная палитра поля, не окончательные токены всего UI.

NumberToken3D — светлый настольный token с CanvasTexture-числом; 6/8 выделены красным. Port3D показывает 3:1 либо 2:1 + название ресурса. Pieces3D содержит простые owner-colored placeholders. Камера — perspective three-quarter top-down, bounds/aspect auto-fit, ограниченный orbit/zoom и Reset Camera; pan отключён. Ambient fill + directional light, ограниченные мягкие shadows; без cinematic окружения, воды/React state animation каждый кадр и postprocessing.

**Verified 2026-10-04:** production Docker в реальном Chrome: Base Standard (два React-клиента) и Seafarers Gold Haven (protocol host + React join), live snapshots, 8 setup placements + Roll для каждой карты, возврат 3D→2D; meshes/terrain/numbers/ports/occupancy сверены со snapshot. Все 19 Base hex инспектированы без cmd/state changes. Zoom/orbit/reset и desktop 1440×1000, 1280×720, 1024×768 проверены без horizontal overflow. City/ship и смещённая 50-hex карта дополнительно проверены через engine-built test snapshots с mocked browser transport, не через полный gameplay.

37 web tests (25 прежних + 12 pure geometry/projection cases), TypeScript, production build и Docker build проходят. В покое frameloop=demand даёт 0 дополнительных кадров; unmount освобождает geometry/texture и WebGL context. Около 180–190 main-pass draw calls на 19 hex, 352 на test 50; это наблюдение на проверенном GPU, не гарантия low-end FPS. Lazy 3D chunk ~874 KB / ~235 KB gzip; Vite size warning сохраняется. Полная партия/mobile/fallback на слабых устройствах не проверены.

**Lobby limitation resolved separately:** Phase 1 обнаружила откат mapId старым room_state. Fix 5ff920a удалил встречные effects и добавил server-authoritative map_revision/pending ordering; два React-клиента теперь выбирают Gold Haven через обычный UI. При текущей Phase 2 workaround не применяется. Исторические действия/пределы — [[plans/board3d]].

### Board3D Phase 2 — implemented interaction

Verified 2026-10-05. **Renderer, not rules engine** сохраняется: GamePage.useBoardInteraction передаёт одинаковые targets/selection/callbacks в SVG и Three. Targets приходят из персонального server legal; cost, piece limits, phase и shipping/victim rules не копируются в TypeScript. Финальные фигуры всегда берутся из snapshot. Общие BoardControls используют существующие кнопки; HUD, lobby, trade/dev UI и CSS не redesign'ились.

- Legal vertex — компактное зелёное кольцо/полупрозрачная hit surface; city marker выше существующего settlement.
- Legal edge — небольшой полупрозрачный prism между исходными vertices; ship source marker выше placeholder sail.
- Legal tile — лёгкий outline/emissive accent. Hover усиливает marker; selected ship source и выбранный victim tile — янтарные. Никаких particles, fantasy effects или continuous animation.
- Setup следует server setup_need автоматически. Move ship: source → destinations → команда; source можно отменить кликом/Cancel. Несколько victims открывают небольшую общую Choose player панель до отправки команды.
- Switching сохраняет tool/source/victim; waiting убирает доступные board clicks. Error снимает transient selection, существующий feedback показывает отказ; optimistic permanent pieces нет.

Production Chrome + Docker: Base и Gold Haven, оба через normal lobby, два клиента, полная 3D setup и main road/ship/pirate actions. Раздельные fixtures проверили settlement/city/move ship/victim choice/free-road/rejection в SVG и 3D; это контролируемые состояния, не полная естественная партия. Desktop resize проходит, 0 новых idle frames; frameloop=demand. Web 57/57, pytest 186/186, TypeScript/production/Docker build проходят. Lazy Three chunk 876.54 KB / 235.24 KB gzip; прежний size warning и low-end/mobile ограничения остаются.

Visual polish Phase 3 реализован отдельной задачей ниже. Известные gameplay P1 относятся к engine backlog и не являются graphics polish. Полный scope — [[plans/board3d]], controller path — [[React интерфейс]], contract — [[Сервер и протокол]].

### Board3D Phase 3 — accepted visual polish

**Accepted:** clean modern tabletop 3D, stylized board pieces, readable tokens. **Rejected/historical:** fantasy/MMORPG/tavern, cinematic castles, massive gold frames and decorative particles. These restrictions apply to the board; surrounding HUD redesign is not implemented.

All hexes share a shallow bevelled mesh, the original pointy-top orientation and logical surface height. Forest: green with three faceted trees. Fields: bright wheat with three short planting rows. Pasture: light green with a white sheep silhouette. Hills: clay with two rounded elevations. Mountains: cool gray with two snowy low-poly peaks. Desert: pale sand with low dunes. Gold: muted bronze with gray rock and bright angular nuggets, distinct from wheat rows. Sea: calm blue with static curved wave marks. No downloaded models/photos/fonts or water simulation.

Number tokens have larger ivory faces, dark numerals, printed probability dots and a restrained red 6/8 accent. Ports keep the exact snapshot edge and 3:1 / 2:1 + resource text; a colored rim and short dock support the label. Road is a bevelled rectangular board piece; settlement a gabled house; city an asymmetric house/tower silhouette, not a scaled settlement. Ships have a shaped owner-colored hull and low triangular sail. Robber is a dark pawn; pirate a distinct dark hull/flag marker.

Legal vertices use pale translucent rings; edges use fine rails; tiles use an outline without a green fill. Hover is white and stronger; selected is amber with additional end brackets/thicker outline. Cursor indicates selectable targets. Hovering a server-approved settlement/city/road/ship target shows a translucent owner-colored preview using the final piece geometry. Preview has no raycast, sends no command and vanishes on leave/waiting/changed targets. Source/victim/action and commands still belong to the unchanged shared controller.

Camera is a higher three-quarter perspective with framing from actual tile rims/port labels, limited orbit/zoom, no pan and Reset Camera. Ordinary snapshots do not reset orbit. Neutral navy background, ambient/hemisphere fill and one soft directional light replace the pale visible rectangular stage. No continuous animation or postprocessing; frameloop=demand remains.

**Verified 2026-10-05:** Chrome 154 on Windows / ANGLE / RTX 5050. Live two-client Base/Gold Haven flows and separate engine-built snapshots for city, previews, move-ship states and an offset 50-hex map. SVG/3D interactions, resize, camera and cleanup passed. Deuteranopia emulation was visually inspected: terrain silhouettes, numbers and marker shapes remain readable; all-six-player ownership patterns and formal accessibility certification remain future work. 65 web tests, TypeScript, production/Docker build pass. Idle adds zero frames on 19 and 50 hex; shared tile geometry is one instance; unmount returns geometry/texture counts to zero. Main-pass calls: Base 293, Gold 267, 50-hex 505. Lazy Three chunk 881.25 KB / 237.40 KB gzip; existing Vite size warning remains. Details/limits — [[plans/board3d]].

#### Phase 3 visual evidence

These are inspected screenshots of the implemented renderer, not design concepts. Prepared states use the unchanged engine with trusted test funding and mocked browser transport; they do not certify a full natural production game. Temporary harnesses and raw snapshots remain outside the repository.

| State | Screenshot |
| --- | --- |
| Base Standard: road, settlements, city, robber, tokens and ports | [base-standard](../design/references/board3d-phase3/base-standard.png) |
| Base city targets and hovered upgrade preview | [base-build-highlight](../design/references/board3d-phase3/base-build-highlight.png) |
| Gold Haven: sea, gold, ships and pirate | [seafarers-gold-haven](../design/references/board3d-phase3/seafarers-gold-haven.png) |
| Selected ship source and movement destinations | [ship-selected](../design/references/board3d-phase3/ship-selected.png) |
| Offset 50-hex map, all eight terrains, default fit | [board-50-fit](../design/references/board3d-phase3/board-50-fit.png) |
| Hovered settlement preview | [settlement-preview](../design/references/board3d-phase3/settlement-preview.png) |
| Hovered ship preview | [ship-preview](../design/references/board3d-phase3/ship-preview.png) |
| Base with Chrome deuteranopia emulation | [deuteranopia-check](../design/references/board3d-phase3/deuteranopia-check.png) |

Геометрия snapshot уже достаточна. Ограничения server legal для полного rule-free interaction и готовность generator — [[Карты и сценарии#Готовность к Board3D]] и [[Карты и сценарии#Будущий Random Map Generator — предложение, не реализация]].

## Game UI Redesign Phase 1 — implemented composition

Verified 2026-10-05. Primary reference is the user-attached screenshot together with explicit hierarchy/layout requirements. The screenshot itself still shows the old blue/cream dashboard; its literal card layout is rejected in favor of the user's stated fullscreen tabletop composition. No missing reference asset was invented. [Before dashboard layout](../design/references/game-ui-redesign-phase1/before-dashboard-layout.png) is an actual inspected pre-change Chrome capture, not a new concept.

- Board first: full-width dark navy stage between compact HUD rows; no right dashboard column/card around Canvas, no giant in-match title. Stage heights: 872/1080, 712/900, 546/720 (80.7/79.1/75.8%); Canvas reserves 52px for prompt/view controls. Island uses existing actual-footprint auto-fit; no hardcoded preset or coordinate changes.
- Top: name, numbered ownership/color marker, public VP/resource_count/dev_count, text Turn indicator; compact room/goal and info/log buttons. Opponent res/dev cards/hidden VP are not derived or displayed. Six long names at 1280 are truncated with full title; current turn remains readable.
- Bottom-left: five resource cards with native SVG glyph/name/count, including zeros; only own res. Bottom-right: Roll/Build/Trade/Dev Card/End, contextual legal build palette, ship move, robber/pirate and cancel. Trade/dev remain disabled with an accessible explanation because forms are not implemented in this phase.
- Context prompt comes from snapshot/controller (setup, roll, build, ship source/destination, movement/victims, pending choices). Raw phase/tick/pending/map description/connection flags are in Game info. Failed commands and lost connection retain readable feedback.
- Log/info are nonmodal overlay drawers, initially closed; close button/Escape restore focus. Log still receives the existing App transport/error log, not a newly invented engine event feed. Mandatory discard/gold overlays preserve fields/payloads, trap Tab and cannot be dismissed with Escape. Victim chooser is a compact nonmodal drawer so renderer switching remains available.
- View: compact 2D/3D, default 3D with existing lazy/error fallback; unobtrusive Reset button with camera help. SVG remains interactive. Legal targets are still gated by the unchanged controller/tool/required setup step. Smaller translucent Three rings/rails/outlines brighten on hover; selected ship source keeps amber brackets. Original hit areas remain intact.
- Ports: compact dark face/resource-colored rim and label; visual center pulled toward the existing anchor. Snapshot edge/kind, engine placement and topology are unchanged. Terrain/piece art, camera directions, lighting/resource lifecycle/controller are preserved.

### Phase 1 visual evidence

Actual Chrome 154 / ANGLE / NVIDIA RTX 5050 screenshots; inspected visually. Main/build/Seafarers screenshots use existing engine-built prepared snapshots and mocked browser transport to show useful states consistently. Setup screenshot is a real two-client room. Evidence does not certify a full naturally played match.

| State | Screenshot |
| --- | --- |
| Base 1920×1080 | [base-1920](../design/references/game-ui-redesign-phase1/base-1920.png) |
| Base 1440×900 | [base-1440](../design/references/game-ui-redesign-phase1/base-1440.png) |
| Base 1280×720 | [base-1280](../design/references/game-ui-redesign-phase1/base-1280.png) |
| Real room setup | [base-setup](../design/references/game-ui-redesign-phase1/base-setup.png) |
| City build mode | [base-build](../design/references/game-ui-redesign-phase1/base-build.png) |
| Gold Haven sea/gold/ships/pirate | [seafarers](../design/references/game-ui-redesign-phase1/seafarers.png) |
| Selected ship destination flow | [seafarers-move-ship](../design/references/game-ui-redesign-phase1/seafarers-move-ship.png) |
| Log drawer | [log-open](../design/references/game-ui-redesign-phase1/log-open.png) |
| Technical information drawer | [game-info](../design/references/game-ui-redesign-phase1/game-info.png) |
| Retained SVG renderer | [base-2d](../design/references/game-ui-redesign-phase1/base-2d.png) |
| Gold choice / discard | [gold-choice](../design/references/game-ui-redesign-phase1/gold-choice.png), [discard-choice](../design/references/game-ui-redesign-phase1/discard-choice.png) |

73 web tests, TypeScript, production build and Docker frontend build pass. Real two-client Base setup/Roll/road/robber and Gold Haven setup/Roll/ship/pirate agree on public state; both renderers also tested with real-engine fixture execution for all build tools, ship move/cancel, victims, free roads and rejection without permanent optimistic pieces. Drawer/keyboard/focus, renderer switch, zoom/reset, no-scroll/visible controls at all three target sizes passed. Idle remains demand-driven; unmount frees geometries/textures/context. Lazy Three chunk ~881 KB / 237 KB gzip retains Vite size warning. Backend, protocol, shared interaction, maps, terrain/piece models, dependencies and Docker architecture unchanged. Full-match/mobile/low-end/a11y certification is outside verification. Existing mountain/tree decoration can occlude a road midpoint; another visible point/orbit works, and this interaction issue was not fixed here. Details — [[plans/game-ui-redesign]].

## Screens

| Экран | Reference | Текущая реализация web |
| --- | --- | --- |
| Main Menu | Левая часть lobby-concept | Отдельного нет |
| Multiplayer Lobby | lobby-concept | LobbyPage с более простым набором функций |
| Match | User Phase 1 reference + explicit composition requirements; older AI images historical | Fullscreen GamePage, GameTopBar/ResourceHand, dock/drawers + BoardRenderer, unchanged shared interaction |
| Rules / Help | rules-help-concept | Отдельного нет |
| Settings | settings-concept | Отдельного нет |
| Map Editor | Только пункт меню на lobby-concept; экран не показан | Есть загрузка JSON, редактора нет |
| Victory / Results | Часть modals-concept | Отдельного React-экрана нет |

Текущее дерево и props описаны в [[React интерфейс]]. Таблица не объявляет новые функции реализованными или обязательными.

## In-game UI

Текущие реализованные match blocks описаны выше. Исторические AI-макеты дополнительно показывают development cards, trade, achievements/recent events и другие состояния; это не список готовых web-функций. Trade/dev формы, достижения и результаты не входят в Phase 1. Gold/discard/pirate показаны через реальный snapshot/controller с компактными overlays/controls.

Публичные данные игроков и личная рука визуально разделены. Это полезная UX-интерпретация, но секретность должна обеспечиваться серверным snapshot, а не расположением панели. Существующие данные — [[Состояние игры]].

## Visual Tokens

Ниже — наблюдения **исторических AI-макетов**, не токены актуального clean tabletop направления. Золотые рамки и декоративное окружение не переносить в новый UI; окончательные токены остаются TBD.

| Группа | Наблюдение | Неутверждённые значения |
| --- | --- | --- |
| Colors | Тёмные поверхности, золото/янтарь, светлый текст, цветные ресурсы и маркеры игроков | HEX, палитра состояний, контраст — TBD |
| Typography | Крупные serif-подобные заголовки, меньший текст пояснений | Семейства, начертания, размеры, line-height — TBD |
| Spacing | Панели сгруппированы, разделены рамками/линиями | Шкала отступов, gutters, breakpoint — TBD |
| Panels | Тёмная поверхность поверх сценического фона | Материал, прозрачность и плотность — TBD |
| Borders | Тонкие тёплые рамки, усиленная золотая выбранная рамка, орнамент углов | Толщина и радиусы — TBD |
| Shadows | Объём и отделение фигур/панелей от фона | Параметры теней/свечения — TBD |
| Buttons | Золотые важные, тёмные вторичные, зелёный Start Match | Полная primary/secondary/destructive-семантика — TBD |
| States | Active/selected — золото; ready/available — зелёный; disabled — приглушённый | Hover/focus/loading/error, допустимость действий — TBD |
| Animations | Статичный reference не показывает поведение | Длительность, easing, reduced motion — TBD |

Не выводить точные px, font family или цветовые коды из визуального впечатления. Разрешение оригинала — свойство файла, а не требуемый размер UI. Текущие CSS-значения не автоматически становятся токенами redesign.

# Design References

### Layout / readability reference — 2D gameplay

Reference: скриншот, приложенный пользователем к задаче анализа карт 2026-10-04. Изображение просмотрено в сообщении; оригинальный файл среди доступных файлов вложений не найден. Ожидаемый путь `docs/design/references/board-layout-reference-2d.png` пока **не существует**; ссылка/embed не добавлены и PNG не создавался из уменьшенного отображения.

Status: **Layout / readability reference**, не финальная visual specification. Исходное вложение сообщено как 2357×1237; отображение в сообщении уменьшено до 2048×1075.

**Экран / состояние.** Gameplay: Your Turn, построенные roads/settlements/cities, robber, dice, personal hand/action controls. Журнал содержит события броска и перемещения разбойника. Точный шаг текущего turn по статичному изображению не устанавливается.

**Видимые UI-блоки.** Крупный остров в центре на спокойном синем море; цветные terrain hexes с символами; большие светлые number tokens с выделением сильных чисел; фигурки яркого цвета; ports вокруг острова с ratio/resource. Справа event log/chat и набор карточек. Внизу personal hand, trade/build/end-turn controls, Your Turn/timer и карточка игрока. Слева utility icons и ranked/profile banner.

**Key ideas пользователя.** Board primary focus; мгновенно различимые hex/terrain; большие numbers; читаемые roads/settlements/cities; ports непосредственно на поле; очевидный legal placement; функциональный UI вокруг board. Скриншот не показывает выбранное строительство/legal markers, поэтому их точный стиль — требование пользователя, а не наблюдение.

**UX-интерпретация.** Контрастные tokens отделяют number от terrain; цвет/форма различают фигуры; ports читаются возле связанного участка берега; журнал вынесен за board; personal hand/actions собраны в нижней зоне. Поле сохраняет больше пространства, чем вспомогательные блоки.

**Concept / TBD.** Точные панели/ширины, ranked/profile, chat, timer, изображения карт, рисованные порты и literal palette не приняты как обязательные функции/стиль. Актуальный дизайн — clean stylized tabletop с 3D board, а не pixel-perfect копия этого 2D reference.

## Historical AI screen references

Оригиналы следующих шести AI-mockups находятся в `docs/design/references/`; ссылки ведут на существующие файлы. Семь прежних вложений дали шесть уникальных изображений: вложения 5 и 6 полностью одинаковы и представлены одним gameplay-concept; альтернативный gameplay сохранён отдельно. **Fantasy/MMORPG/medieval tavern decorative direction: Rejected / historical.** Их полезные UX observations можно рассматривать отдельно; dark wood, gold frames и cinematic окружение не реализованы. Актуальное clean modern tabletop направление выше имеет приоритет.

## Gameplay

Reference: [gameplay-concept.png](../design/references/gameplay-concept.png)

Status: Reviewed reference; not accepted final specification.

**Экран / состояние.** Матч четырёх игроков; Alex явно выделен как текущий игрок через Your turn. Видны постройки, разбойник, ресурсы, development cards и события. Кости уже имеют значения, но статичная сцена не устанавливает точный шаг roll/build и доступность кнопок.

**UI-блоки и layout.** Верхний общий header: CATAN, название карты, правила, число игроков, round/turn, иконки игроков/settings/help. Центр — большой остров в море. Слева вертикальные карточки всех игроков с avatar, цветным маркером, VP и маленькими счётчиками фигур; ниже отдельный dice-блок. Справа собственный профиль, пять ресурсных карточек, development hand, achievements и recent events. Внизу под картой Build, Trade, Dev Card и End Turn.

**Иерархия и стиль.** Иллюстрированная объёмная карта — главный объект. На тёмных боковых панелях выделены золотые VP/active-player frame; наиболее яркая нижняя кнопка — End Turn. Местность, фигурки и порты выглядят предметно; общий фон — стол, карты и компас. Тёплый UI контрастирует с синим морем.

**Навигация и взаимодействие.** Верхние icon-controls обозначают переходы к общим функциям; нижняя полоса обозначает действия матча. Ресурсные и development cards читаются как элементы личного состояния. Действительно ли вся карточка нажимается и как выбирается клетка, не показано.

**Модальные состояния.** Открытых окон нет. Названия Build/Trade/Dev Card связываются с примерами на modals-concept, но точный переход и фокус после закрытия TBD.

**Повторяющиеся паттерны.** Avatar + цвет игрока, карточка ресурса + число, золотая выбранная рамка, иконка + короткая подпись, тёмный контейнер с секциями, цветные точки событий.

**UX-интерпретация.** Соперники отделены от собственной руки; карта остаётся центральной; общие действия собраны в одной зоне. Текущий ход обозначен и рамкой, и словами. События вынесены в sidebar, а не поверх клеток.

**Concept / TBD.** Положение и ширины панелей, формат round/turn, выбранные счётчики фигур, avatars, deck art, ракурсы и реальные ассеты. Числа VP/карт и карта не являются требованиями к правилам. Не подтверждены стоимость/disabled действий, hover клеток, выбор жертвы, touch/keyboard, zoom/pan и мобильная раскладка.

### Gameplay — alternative layout

Reference: [gameplay-concept-alt.png](../design/references/gameplay-concept-alt.png)

**Экран / состояние.** Второй вариант того же направления: четыре игрока, свой ход Alex, карта и боковые панели. Это альтернативная композиция, а не доказанное отдельное gameplay-состояние.

**UI-блоки и layout.** Сохранены левый roster, нижний левый dice-блок, центр-карта, правая личная панель и верхний header. Отличия: справа добавлен отдельный ряд Settlements/Roads/Cities; ресурсы и development hand имеют заголовки; показана обратная сторона карты. В нижней полосе перед действиями есть дополнительный Your turn с краткой подсказкой.

**Иерархия / стиль.** Более явная группировка личного состояния; активный ход повторяется в roster и action bar. Золотой End Turn и тёмные вспомогательные кнопки сохраняются. Объёмная сцена и дерево остаются общими.

**Навигация / интерактивность.** Верхние icon-controls здесь players/settings; help-книга присутствует в первом варианте, но не в этом. Build/Trade/Dev Card/End Turn остаются. Обратная сторона development card не доказывает отдельное действие покупки/раскрытия.

**Модальные состояния / паттерны.** Окон нет; повторяет остальные gameplay-паттерны и секционные счётчики справа.

**UX-интерпретация.** Нижняя текстовая подсказка может уменьшить неопределённость «что сейчас делать»; повтор active turn усиливает ориентирование. Значения в разных частях рисунка не следует трактовать как согласованную модель данных.

**Concept / TBD.** Ни один gameplay-вариант не выбран окончательно. Нужны решения о повторении счётчиков/VP, составе header, роли скрытой карты, количестве карточек и прокрутке боковой панели. Изменение layout не меняет контракт команды.

## Lobby

Reference: [lobby-concept.png](../design/references/lobby-concept.png)

Status: Reviewed reference; not accepted final specification.

**Экран / состояние.** Составной main menu + multiplayer lobby. Видны список участников, host, ready/not ready и возможность Start Match. Create Room/Join Room одновременно с заполненной комнатой делают этап входа неоднозначным: это концептуальная сборка, не точная state machine.

**UI-блоки и layout.** Слева крупный logo и вертикальное меню Play, Multiplayer, Solo, Load Game, Map Editor, Rules, Settings. Центр/фон — порт и декоративное поле. Справа большое lobby-окно: header с room code/copy/public, слева карточки игроков и invite-slots, справа scenario-carousel и settings, снизу chat/input и колонка Create/Join/Invite/Start. Сверху справа — профиль, level/progress и icon-controls.

**Иерархия и стиль.** Выбранный Play и scenario обведены золотом. Оранжево-золотой Create Room и зелёный Start Match различаются визуально; остальные действия тёмные. Иллюстративный фон задаёт атмосферу, данные комнаты заключены в читаемую тёмную панель.

**Навигация и взаимодействие.** Sidebar обозначает разделы продукта; scenario стрелки/dots — просмотр вариантов; dropdown — map preset/bot difficulty/public; copy — room code; меню игрока, invite и chat — предполагаемые controls.

**Модальные состояния.** Открытых окон нет. Advanced Settings и Invite обозначают возможные дальнейшие действия, но формат окна/перехода не показан.

**Паттерны.** Avatar/цвет/host/ready, декоративная scenario-card, icon+label, gold selected border, chat с цветом автора, яркая важная кнопка.

**UX-интерпретация.** Игроки, сценарий и социальное общение доступны в одном контексте; host и готовность видимы рядом с именем; room code доступен для передачи. Условия запуска из готовности не выводятся только из зелёной кнопки.

**Concept / TBD.** Ready workflow, public rooms, friends/invites, accounts/levels, chat, invite-capacity, bot difficulty, Load Game и Map Editor — концепты, не подтверждение backend-функций. Подпись Players 4/4 рядом с invite-слотами и необычные числа на декоративном поле нельзя переносить в логику. Требуют уточнения границы main menu/lobby, пустая комната, joining/reconnect/error, права host, disabled Start, mobile и управление фокусом.

## Modals

Reference: [modals-concept.png](../design/references/modals-concept.png)

Status: Reviewed reference collection; not one simultaneous application state.

**Экран / layout.** Лист из восьми обозначенных примеров: Trade, Build, Development Cards, Discard, Robber/Pirate, Victory, Toasts и Leave confirmation. Окна показаны рядом для сравнения; реальная overlay-композиция не определена.

**Общий стиль и иерархия.** Тёмные framed-panels, золотой заголовок/иконка, close в углу, визуальные предметы и действия внизу. Важная кнопка чаще золотая, вторичная тёмная, недоступная приглушена. Яркая иллюстрация объясняет тип ситуации. Широкие списки строек и карточные выборы используют тот же язык, что gameplay sidebar.

| Пример | Видимые блоки и интерактивность | UX-интерпретация и неподтверждённые детали |
| --- | --- | --- |
| Trade | Your Offer / You Want, ресурсные карточки с числами и +/−, message field, Decline / Send Offer / Accept Trade | Двусторонний обмен читается сравнением колонок; кнопки разных стадий объединены в одном примере. Режим отправки/приёма, ресурсы и total value не задают правило оценки сделки; Trade здесь не подтверждает bank-mode |
| Build | Список Road / Settlement / City / Ship / Development Card, иллюстрация, стоимость, Available/Requires Settlement | Стоимость и ограничение рядом с вариантом помогают выбрать действие. Не показаны выбор строки, подтверждение, переход к полю и affordability; подписи не заменяют engine |
| Development Cards | Пять типов, выбранный Knight, help-значки, описание и Play Card | Selected-карта даёт подробности внизу. Наличие примеров типов не означает, что игрок ими владеет; ограничения новых карт/VP и текст Knight должны браться из спецификации |
| Discard | Семёрка, ресурсная композиция, карточки +/−, счётчик selected/required, Cancel / Discard Cards | Счётчик объясняет объём выбора; пример «7 cards, discard 3» не утверждает порог сброса. Cancel/X не освобождает от обязательного pending-action |
| Robber / Pirate | Заголовок Move the Robber, мини-карта, пояснение о выборе клетки и жертвы, Cancel / disabled Continue | Предполагается пошаговый выбор; сама подсветка/selected tile не показана. Пират назван в подписи коллекции, но отдельного pirate-state на рисунке нет |
| Victory | Сценическая иллюстрация, имя победителя, ranking/VP, Play Again / Back to Lobby | Отделяет результат от дальнейшей навигации. «5 Victory Points» — пример текста, не целевой VP; хозяин реванша и статусы подключений TBD |
| Toasts | Четыре компактных уведомления, icon, краткий текст, time, close; зелёная/синяя/красная/золотая рамки | События различаются видом и цветом; timing, stacking, live region и связь цвета с игроком/типом ещё не определены |
| Leave confirmation | Заголовок, предупреждение, Cancel / Leave Game, close | Дополнительное подтверждение потенциальной потери прогресса. Утверждение о потере прогресса не описывает фактическую reconnect/save-политику |

**Навигация / состояния.** X, Cancel, main confirmation и переходы после победы повторяются. Close/Escape/backdrop, modal stacking, блокировка фона и возврат фокуса не показаны. На листе есть disabled Continue — это наблюдение состояния, не критерий его доступности.

**Повторяющиеся паттерны.** Gold-title + icon, card selection, cost-icons, footer с secondary/primary, текст причины недоступности, короткие alerts.

**Concept / TBD.** Правила dismiss для обязательных действий, отдельные типы trade, gold-choice, movement pirate, keyboard/touch и подтверждения. Destructive-семантика не унифицирована: Leave Game и Discard тоже золотые; красный встречается в уведомлении Knight, а не как единый стиль разрушительной кнопки. Перечень всех будущих модалок и технологии реализации не утверждены.

## Settings

Reference: [settings-concept.png](../design/references/settings-concept.png)

Status: Reviewed reference; not accepted final specification.

**Экран / состояние.** General Settings с выбранной категорией General. Хотя слева есть отдельные Gameplay/Graphics/Audio/etc., центральная General-страница уже показывает несколько этих групп; окончательная структура разделов не определена.

**UI-блоки и layout.** Sidebar слева: General, Gameplay, Graphics, Audio, Controls, Accessibility, Network. Справа широкая тёмная поверхность с General Settings и scenic-banner. Ниже двухколоночные группы: Language & Interface / Display, Visuals & Animations / Audio, Accessibility / Network & Chat. Нижний footer: Reset to Defaults слева, Cancel и Apply справа. В header — CATAN и icon-controls.

**Иерархия / стиль.** Gold-active sidebar, золотые section-title/icons, светлые подписи и приглушённые пояснения. Dropdowns тёмные, sliders с тёплым заполнением, checked-checkbox золотой; disabled frame-rate option приглушён. Дерево/настольные предметы обрамляют экран, а hero-banner содержит море и поселение.

**Навигация / интерактивность.** Sidebar категории, selects языка/режима/качества, sliders масштаба и громкости, checkboxes подсказок/анимаций/accessibility/chat. Footer обозначает сброс, отмену и применение.

**Модальные состояния.** Открытых confirmation-окон нет. Подтверждение reset и реакция на несохранённые изменения не показаны.

**Паттерны / UX-интерпретация.** Настройки сгруппированы по задаче и имеют icon+label; подписи помогают понять переключатель. Apply/Cancel предполагают отложенное применение, но точная persistence/preview-семантика неизвестна. Disabled-состояние показывает зависимость опций, не доказанную функционально.

**Concept / TBD.** Browser-поддержка resolution/VSync/FPS/graphics/voice chat не гарантирована наличием controls. Не определены локальная/room/server-область настроек, возможные gameplay-изменения, автосохранение, reset scope, i18n, доступность и адаптивность. Colorblind/Subtitles/High Contrast показаны как идеи функций, а не реализованные гарантии.

## Rules & Help

Reference: [rules-help-concept.png](../design/references/rules-help-concept.png)

Status: Reviewed reference; gameplay copy unverified.

**Экран / состояние.** Справка Rules & Help; Base Game выделен слева, Seafarers представлен отдельной правой колонкой одновременно. Страница не показывает, что происходит после выбора Seafarers в sidebar.

**UI-блоки и layout.** Header CATAN / Rules & Help и close. Узкий sidebar с иллюстрированными Base Game/Seafarers. Центр: Base Game banner, Goal/Win Condition, Setup/Turn Flow, Build Costs, Placement Rules/Victory Bonuses. Справа: Seafarers banner и карточки Ships, Ship Cost, Placement, Open Routes, Fog, Gold, Pirate, Scenarios. Внизу на всю ширину Resource Quick Reference и Action Order.

**Иерархия / стиль.** Крупные gold-title и нумерованные секции, тёмные карточки, компактные иллюстрации маршрутов и предметные cost-icons. Верхние сценические banners различают базовую и морскую тему. Нижняя памятка упрощает повторное обращение к информации.

**Навигация / интерактивность.** Sidebar и close выглядят controls. Шаги/карточки могут быть только информационными: hover, ссылки, поиск и раскрытие не показаны. Нет видимого поиска или back-control, поэтому их нельзя считать частью reference.

**Модальные состояния.** Страница закрывается через X, но overlay над матчем или отдельный маршрут из рисунка не установлен. Нет дополнительных открытых окон.

**Паттерны / UX-интерпретация.** Правила объясняются одновременно текстом, номером шага и схемой; стоимость повторяет ресурсные карточки других экранов. Разделение Base/Seafarers даёт ориентирование; короткая памятка служит быстрым справочником.

**Concept / TBD.** Содержание и формулировки AI-текста не авторитетны: цель, выдача ресурсов, fog/gold/pirate и названия ресурсов сверяются с выбранным сценарием/спецификацией. Одновременные колонки, прокрутка длинного материала, телефонная раскладка, локализация, содержание обучения и сохранение контекста матча ещё не согласованы.

## Shared UX patterns and open decisions

Следующий список фиксирует наблюдения старых AI-references. Полезные группировки/UX-идеи можно рассматривать отдельно; gold/frame/dark-wood styling не является требованием нового дизайна.

1. **Active turn:** gold-frame + текст Your turn; альтернативный gameplay повторяет подсказку снизу. Активность нельзя обозначать исключительно цветом.
2. **Primary / secondary:** золото для важного действия, тёмная поверхность для вспомогательного; зелёный Start Match — отдельный видимый вариант. Универсальная семантика и destructive-вариант TBD.
3. **Card selection:** gold-outline на выбранном scenario/development/menu; ресурс содержит glyph и count. Реальные focus/hover-состояния TBD.
4. **Grouped information:** roster слева, personal state справа, section headings и разделители внутри. Конкретная плотность/дублирование информации TBD.
5. **Modal language:** общие рамки, heading/icon, close и footer; правила закрытия должны учитывать обязательные engine-состояния.
6. **Consistency across screens:** повтор тёмного/золотого и предметных иконок; lobby richly illustrated, settings плотнее, rules более информационный. Единообразие не требует одинаковой плотности всех экранов.
7. **Accessibility / responsive:** изображения не подтверждают contrast ratio, screen reader, tab order, reduced motion, разные масштабы и mobile. Всё требует отдельного решения/проверки.

Reference-analysis сохранён; новое clean tabletop направление принято качественно. Точные layouts/tokens/assets и реализация остаются отдельными задачами. Не делать pixel-perfect перенос и не выводить новый gameplay из текста/чисел макета.
