---
tags: [catan, планы, сеть]
---

# Goal

Привести публичные команды и снимки к [[Инварианты движка]] без изменения утверждённых игровых правил.

# Current State

[[Project State]]: Phase 1 Completed, 2026-10-03, READY FOR CHECKPOINT. Production command boundary, slot ownership, персональные snapshots и подтверждённые atomicity defects исправлены; финальные VP/rematch product decisions проверены. Путь: клиент sendCmd → websocket_endpoint → _apply_cmd → apply_cmd → snapshot. Исходные дефекты перечислены в датированной проверке ниже.

# Files / Systems Affected

app/server_mp.py, app/net_protocol.py, app/engine/rules.py, state.py, serialize.py; согласование с web/src/wsClient.ts и desktop net_client/online_controller; тестовые фикстуры и негативные сетевые проверки.

# Invariants That Must Not Break

Только сервер определяет исход; секреты видит допустимый получатель; отказ не меняет game; координаты валидны; банк неотрицателен; команды соответствуют pid/room/match. Сохранить общий Python engine и согласованность обоих клиентов.

# Implementation Steps

1. Зафиксировать негативные воспроизведения и допустимый публичный список команд.
2. Изолировать тестовую выдачу ресурсов и генерацию кубиков от публичного клиентского ввода.
3. Уточнить токенную идентификацию и число реальных участников.
4. Проверять геометрию и полный эффект до изменения состояния.
5. Согласовать public/private snapshots, секретную колоду и новый матч/seq.
6. Проверить клиенты, сценарии и сохранения; обновить актуальные заметки по результатам.

# Validation

Негативные серверные команды не изменяют состояние; новый клиент не занимает чужой слот; две стороны проходят setup/roll/end; новый матч и reconnect не ломают seq; скрытые данные отсутствуют у чужого получателя. После изменения выполнить профильные и необходимые существующие проверки, не подменяя правила ради зелёного результата.

# Status

**Phase 1 Completed — 2026-10-03.** Подтверждённых открытых P0 и новых blocker-level regressions в проверенном scope нет. Прежние 160 scenario failures сохранены и не означают новых регрессий этого этапа. Checkpoint: `fix: complete production hardening phase 1`, tag `hardening-phase-1`. Redesign, Docker, Phase 2 и отдельные P1 вне scope.

## Проверка до исправлений — 2026-10-02

Все десять пунктов повторно сверены с кодом до изменений:

| Пункт | Статус | Место / воспроизведение |
| --- | --- | --- |
| Клиентский roll | VERIFIED | server_mp._apply_cmd принял roll=12 без debug |
| grant_resources | VERIFIED | _apply_cmd выдал ресурсы неактивному игроку |
| Владение слотом | VERIFIED | RoomManager.join_room вернул слот по совпавшему имени |
| Координаты | VERIFIED | apply_cmd принял vid/tile=99999; can_place_road разрешил ребро вне графа. move_pirate уже проверяет диапазон и sea |
| Dev validation после mutation | VERIFIED | play_dev израсходовал Monopoly при неверном ресурсе |
| Банк Year of Plenty | VERIFIED | qa=10/qb=10 одного ресурса при запасе 19 → −1 |
| Приватность | VERIFIED | _snapshot_state содержит точную чужую res |
| Атомарность отказа | VERIFIED | grant_resources частично выдал wood перед отказом на ore; Monopoly тоже меняет state при отказе |
| Пустые места | VERIFIED | _start_match создал 4 PlayerState при 2 участниках |
| seq/cmd_id | VERIFIED | Endpoint учитывает до применения; отказ получает applied=false и использованный seq |

## Минимальные решения этапа

- Production WS принимает только намерение roll; сервер генерирует две кости. Deterministic roll остаётся прямым trusted engine API для offline/test, без debug-переключателя в публичном WS.
- Явный список multiplayer-команд исключает test helper grant_resources.
- Для отказов исправлять конкретную валидацию перед mutation; тестировать весь GameState через deepcopy/dataclass equality, включая скрытые поля.
- Использовать vertices/edges/tiles текущего BoardState, запретить клиентское переопределение setup.
- Новый join занимает свободное место только в lobby; имя уникально в комнате, reconnect требует токен. Новый владелец соединения отзывает старую привязку.
- При каждом старте включить только подключённых участников, сделать pid последовательными и обновить привязки/токены. Финальная rematch policy утверждена 2026-10-03: прежние отключённые участники не блокируют новый матч; старый full-composition barrier удалён.
- Отправлять каждому pid отдельный snapshot: собственная рука и choices, чужие публичные счётчики. Не передавать seed, из которого восстанавливается колода.
- Сохранить consumed-sequence семантику отказов: ACK является окончательным результатом; фиксировать seq после получения результата, проверить duplicate/reconnect. Очереди клиентов привязать к room/match, а не переносить в rematch.
- Выполнить pytest, существующие сценарии, TypeScript и Vite build; прошлые failures не скрывать ослаблением правил.

## Implementation result

Production boundary, конкретные atomic validation места, coordinate membership, token slot ownership, per-player views и actual-player composition реализованы. В seq сохранена consumed-on-rejection семантика; запись перенесена после engine outcome, оба клиента проверены на lost ACK/reconnect/rematch. В snapshots скрыты точный банк/seed; desktop показывает bank availability, а не выдуманные counts. Shared Python сохранён, CSS/redesign не менялись.

Регрессии: 124 новых pytest cases + 7 web transport cases. Весь pytest: 133 passed; TypeScript/build/diff check passed. Существующий scenario runner: 348/508 passed, 160 прежних pre-roll failures в 8 группах. Подробная проверка и пределы — [[Результаты аудита]].

Узкое React reconnect исправление проверено 2026-10-02: до правок реальный WSClient отправил join_room с сохранённым token на открытом WS и получил not_found. Решение перенесено в общий sendJoinIntent: reconnect/обычный Join одинаково выбираются до и после открытия сокета. Проверены room/name cache isolation, create-room, repeated reconnect, invalid token без fallback/retry loop и новый match_id. Добавлены 9 transport tests и 1 pytest integration driver с реальным FastAPI; итог 134 pytest passed, 16 transport tests passed, TypeScript/build passed. Integration driver требует Node с native WebSocket и web dependencies; здесь выполнен, не skipped. Browser DOM e2e не проводился. Изменён только web transport runtime; сервер, protocol shape, gameplay, VP visibility, rematch и unique-name policy сохранены.

## Remaining scope / next recommendation

Phase 1 не закрывает всю корректность CATAN: Seafarers mixed/closed routes и Longest Trade Route, achievements ties, active-turn victory, random stealing, offline-save flags и server lifecycle остаются. Account auth/spectators/storage не добавлены.

Ровно следующий рекомендуемый шаг: привести восемь старых сценариев к законному turn flow, сохранив intended assertions, затем выявить оставшиеся failures правил. Не выполнять автоматически. Полный redesign и инфраструктурные изменения требуют отдельных задач.

## Pirate P0 follow-up — completed 2026-10-02

До исправления на legally placed Seafarers board две соседние ship/sea позиции позволили три команды move_pirate подряд без pending и до roll: украдены wood, wood, sheep. Проверки enable_pirate/main/turn/sea/victim не требовали triggering event, а существующий pending gate запрещал pirate как альтернативу robber.

Узкое решение: сохранить существующее имя `robber_move`, разрешить им две команды и потребовать его с правильным pending_pid в pirate branch. После полной валидации tile/victim выполняются движение, максимум одна кража и очистка pending. Trigger — 7 после discard либо Knight; feature gate сценария сохранён. Pirate sea/ship mechanics отделены от robber land/building mechanics. React/PySide получили только согласование map-click handlers, доступности pirate и подсказки; CSS/layout не менялись.

Добавлено 15 engine cases, 4 desktop handler cases, 1 real WS case и 5 React render/click cases. Полный pytest: 154 passed, web: 21 passed. In-memory scenario runner: до и после 348/508 passed, 160 одинаковых отказов в восьми прежних сценариях; все failure details совпадают. TypeScript/build после этого fix не запускались: web DTO/command/snapshot shape сохранён. Это не browser DOM e2e и не полноценная ручная партия.

Runtime scope: rules.py, ui_v6.py, BoardView.tsx. Server/transport/serialization/config не менялись. Запрошенные excluded topics не исправлялись, следующая задача не начата. Этот follow-up закрывает повторяемую pirate theft, но не доказывает поддержку всех Seafarers scenarios.

## Final product decisions and verification — 2026-10-03

VP: active opponent score исключает hidden VP cards; после game_over total VP всех игроков раскрывается. Текущее to_player_dict уже соответствовало решению, runtime serialization не менялась. Реальный WS test проверяет legal VP purchases, выигрыш через production buy_dev и финальные snapshots победителя и проигравшего, сохраняя остальные секреты.

Rematch: состав берётся из named+connected slots на момент старта, минимум два игрока. Убран барьер подключения всего прежнего состава. При отключении host право запуска получает первый подключённый участник; host изменяется только после успешного создания нового GameState. Остальная существующая фильтрация/remapping/token/sequence модель сохранена. До rematch прежние tokens работают; при старте исключённый token теряет доступ, сохранённые tokens получают новые pid. Runtime этого финального шага изменён только в app/server_mp.py.

Добавлены четыре WS/lifecycle regressions в tests/test_server_authority.py. Полный доступный набор: 158 pytest passed (без skips, включая реальный WSClient/FastAPI), 21 web case passed, TypeScript check и production Vite build passed. Все 508 scenario runs сравнены до/после: 348 passed / 160 прежних failures, совпадают все failure details. Assertions/rules старых сценариев не менялись; runner не записывал reports. Нагрузочная проверка, browser DOM e2e и полная ручная LAN-партия не выполнялись.

Phase 1 завершена в утверждённых границах. Seafarers routes/Longest Trade Route, deterministic theft, achievements/active-turn victory, save/load и server persistence остаются отдельными P1. Следующая задача не запускается автоматически.
