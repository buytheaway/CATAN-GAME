---
tags: [catan, desktop]
---

# Desktop клиент

[[Точки входа]] · [[Игровой движок]] · [[Состояние игры]]

## Unsupported fog path — S2B-2B.1

Implemented **2026-10-09**: Qt does not support the trusted fog foundation. `_convert_base_state` rejects before projecting actual terrain; `_ui_game_to_engine_dict` rejects before building a save. Its call now sits inside `_save_game`'s existing error handler, so refusal is logged without overwriting the selected file. `_load_game` uses the gated shared offline decoder and logs refusal before replacing/redrawing the existing game; it does not rewrite the file.

Three new [real offscreen Qt cases](../../tests/test_fog_desktop.py) cover conversion, save-to-existing-file and load-from-real-file safety. No alternate Qt fog model, gameplay rule, desktop renderer or PostgreSQL-format migration is added. Existing Base, ship-history/F3 and non-fog scenario round-trips remain in the full regression suite. Trusted fog restoration belongs only to the private codec; public availability is **DISABLED**. [[plans/seafarers-fog]]

## Scenario persistence — S2B-1

Verified **2026-10-09**. Qt Game now keeps a copy of the shared ScenarioState; `_convert_base_state` and `_ui_game_to_engine_dict` preserve its rules/home/award ledger through actual `_save_game`/`_load_game`. No scenario rule/award calculation is added to Qt. Shared engine still decides legality and VP. A real offscreen Qt file round-trip plus accepted city command preserves existing island bonus without awarding again, including S1 ship-turn history; full pytest **881 passed**. Base/old saves retain disabled scenario defaults. Desktop scenario configuration UI and visible full-match acceptance were not added; PostgreSQL remains a separate trusted codec. Details — [[Состояние игры#Scenario persistence — S2B-1]].

## Локальный режим

```text
main_menu.main()
→ MainMenuWindow._launch_game(config)
→ game_launcher.start_game(config)
→ ui_v6.MainWindow
→ ui_v6.build_board(seed, size, ...)
→ engine.rules.build_game(...)
→ ui_v6._convert_base_state(base)
```

`GameConfig` в [config.py](../../app/config.py) содержит режим, карту, тему, масштаб, fullscreen и настройки бота.

`build_game` создаёт обычные Python-координаты. `_convert_base_state` преобразует их в QPointF и отдельную Qt-модель `ui_v6.Game`. Поэтому `ui_v6.Game` и `engine.state.GameState` — разные классы.

`MainWindow._apply_cmd(cmd, pid)` передаёт действие общему движку. Некоторые диалоги вызывают `buy_dev`, `play_dev` и `trade_with_bank` через методы UI-модели напрямую. Бот находится в ui_v6 и действует за pid=1; человек — за pid=0.

## Сетевой режим

| Файл | Класс / метод | Роль |
| --- | --- | --- |
| [lobby_ui.py](../../app/lobby_ui.py) | `_on_host`, `_on_join`, `_on_connected` | Собирают параметры и отправляют создание/вход в комнату |
| [net_client.py](../../app/net_client.py) | NetClient | QWebSocket, токен, seq, очередь и сигналы |
| lobby_ui.py | `_on_match_state` | Создаёт окно игры и OnlineGameController |
| [online_controller.py](../../app/online_controller.py) | `_send_cmd`, `cmd_roll` | Переводит UI-действия в сетевые команды |
| online_controller.py | `_on_match_state`, `apply_snapshot` | Создаёт Qt-модель из сетевого снимка и обновляет окно |

OnlineGameController применяет серверные данные; локальный бот в сетевом окне отключён. При чтении пути первой загрузки снимка учитывай, что контроллер создаётся внутри обработчика lobby и подписывается на тот же сигнал.

Сохранения доступны в offline: `_save_game` и `_load_game`. Они используют отдельный `_offline_hidden` для колоды, рук и флагов. Особенности восстановления описаны в [[Результаты аудита]].

## Ship lifecycle persistence — F3

**Исправлено и проверено 2026-10-08.** [ui_v6.py](../../app/ui_v6.py): Qt-модель `Game` объявляет `ships_built_this_turn` (set edge tuples) и `ship_moved_this_turn` (bool). `_convert_base_state` копирует оба значения из общего GameState; `_ui_game_to_engine_dict` записывает их в корень offline JSON как список пар и bool, с теми же именами, которые читает общий `engine.serialize.from_dict`. Отдельных копий этих полей в `_offline_hidden` нет.

Путь восстановления: `MainWindow._load_game` → чтение JSON → `engine.serialize.from_dict` → `_convert_base_state` → Qt `Game`. Qt не вычисляет историю и не определяет правила движения. Уже построенные корабли и оба ограничения сохраняются; отклонённый ход их не изменяет. Общий `rules.end_turn_cleanup` сбрасывает историю, оставляя корабли на карте; после наступления следующего собственного хода обычное разрешённое движение снова работает.

Старый save без истории использует существующую политику общего decoder: для main Seafarers с разрешённым перемещением выставляется `ship_moved_this_turn=True` до End Turn, в том числе до Roll. Точная история не восстанавливается; повторное сохранение сохраняет защитный флаг. Base и setup не получают эту блокировку. Это не конверсия правил/VP и не перевод Qt на PostgreSQL codec или F2 ruleset metadata; прочие ограничения старого save остаются отдельными задачами.

При реальной загрузке обнаружен дополнительный сбой: `scene.clear()` удаляет C++ items, а старые `overlay_nodes/edges/hex` и `piece_items` ещё ссылались на них. `_load_game` очищает эти четыре коллекции перед перерисовкой; иначе save/load завершался `Internal C++ object ... already deleted`.

Доказательства: [test_desktop_ship_persistence.py](../../tests/test_desktop_ship_persistence.py), **8 cases**, PySide6/Qt **6.10.1**, offscreen. Настоящие `QApplication`, `MainWindow`, Qt-координаты, `_save_game`, `_load_game`, файловый JSON и `_apply_cmd`; заменён только выбор пути в файловых диалогах. Проверены новый корабль, повторное движение, legacy история до/после Roll с повторным save, End Turn/следующий собственный ход, валидное движение, Base setup/main. Полный pytest с изолированной PostgreSQL — **757 passed, 0 skipped**. Видимые нативные файловые диалоги и полная ручная Qt-партия не проверялись. Общий движок, web и durable persistence не изменены.

## Phase 1 compatibility — 2026-10-02

NetClient привязывает pending queue к room+match, очищает consumed entries на reconnect и сбрасывает команды на rematch. OnlineGameController использует you_pid из снимка и last consumed seq из токена, включая первый reconnect к начавшейся партии. Старые ACK/snapshots не меняют новую очередь; snapshot с меньшим tick игнорируется.

Чужие ресурсы не приходят: converter хранит public resource_count, hand_size использует его при выборе жертвы. Собственные dev_cards восстанавливаются из private view; online development UI остаётся отключённым. Банк в online отображает availability вместо точных остатков. Offline сохраняет полную сериализацию.

Общий Monopoly исправлен для Qt Player без pid. Queue/controller/Monopoly проверки — [test_net_client_sequence.py](../../tests/test_net_client_sequence.py). Это согласование протокола, не PySide redesign.
