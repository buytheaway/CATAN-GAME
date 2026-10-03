---
tags: [catan, desktop]
---

# Desktop клиент

[[Точки входа]] · [[Игровой движок]] · [[Состояние игры]]

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

## Phase 1 compatibility — 2026-10-02

NetClient привязывает pending queue к room+match, очищает consumed entries на reconnect и сбрасывает команды на rematch. OnlineGameController использует you_pid из снимка и last consumed seq из токена, включая первый reconnect к начавшейся партии. Старые ACK/snapshots не меняют новую очередь; snapshot с меньшим tick игнорируется.

Чужие ресурсы не приходят: converter хранит public resource_count, hand_size использует его при выборе жертвы. Собственные dev_cards восстанавливаются из private view; online development UI остаётся отключённым. Банк в online отображает availability вместо точных остатков. Offline сохраняет полную сериализацию.

Общий Monopoly исправлен для Qt Player без pid. Queue/controller/Monopoly проверки — [test_net_client_sequence.py](../../tests/test_net_client_sequence.py). Это согласование протокола, не PySide redesign.
