# Feature Matrix

| Feature | Status | Evidence | Code pointers | Notes |
| --- | --- | --- | --- | --- |
| Setup snake draft (N players) + 2 settlements/roads | PARTIAL | tests/scenarios/scenario_setup_snake.py (tests.run_all) | app/engine/rules.py:67 | Setup order implemented; starting resources from 2nd settlement not awarded. |
| Dice roll + resource distribution (robber blocks) | IMPLEMENTED | scenario_roll_distribution_basic, scenario_robber_7_flow (tests.run_all) | app/engine/rules.py:232 | Robber tile skips distribution. |
| Robber on 7: discard, move, steal | IMPLEMENTED | scenario_robber_7_flow (tests.run_all) | app/engine/rules.py:724 | Engine enforces discard + move robber + steal. |
| Build legality (road adjacency, settlement distance, city upgrade) | IMPLEMENTED | scenario_setup_snake + invariants (tests.run_all) | app/engine/rules.py:187 | Distance rule enforced in can_place_settlement. |
| Trade with bank 4:1 / 3:1 / 2:1 ports | IMPLEMENTED | scenario_ports_trade_rates (tests.run_all) | app/engine/rules.py:412 | Ports resolved by node ownership. |
| Player-to-player trade | MISSING | No engine cmd type for trade_player | app/engine/rules.py (apply_cmd dispatch) | No cmd type for player trades in engine or server. |
| Dev cards (buy + restrictions + effects) | IMPLEMENTED | scenario_dev_cards_restrictions (tests.run_all) | app/engine/rules.py:466 | Enforces new-card restriction + 1 per turn. |
| Achievements (Longest Road, Largest Army) | IMPLEMENTED | scenario_longest_road_award + scenario_largest_army_award (tests.run_all) | app/engine/rules.py:292 | Awards +2 VP and transfers. |
| Win condition + game over lock + victory overlay | IMPLEMENTED | scenario_win_condition_end_game + offline_ui_smoke.txt | app/engine/rules.py:344; app/ui_v6.py:691 | Overlay used instead of QMessageBox. |
| Server rooms + room code | IMPLEMENTED | tests/test_multiplayer_basic.py + tools/multiplayer_smoke.py | app/server_mp.py:59 | Room codes generated server-side. |
| Join/leave, player list, start match | IMPLEMENTED | tests/test_multiplayer_basic.py + multiplayer_smoke.txt | app/server_mp.py:72 | Leave supported; not directly tested. |
| Authoritative server uses engine | IMPLEMENTED | tools/engine_source_audit.txt | app/server_mp.py:15 | Server applies engine rules and broadcasts snapshots. |
| Snapshot tick/version monotonic | IMPLEMENTED | multiplayer_smoke.txt | app/server_mp.py:138 | Tick increments after valid cmd. |
| Seq/duplicate cmd handling | PARTIAL | server_mp seq checks; not explicitly tested | app/server_mp.py:31 | Seq gate exists; no explicit test coverage. |
| Reconnect (token) | MISSING | No token-based reconnect in server_mp.py | app/server_mp.py:72 | Reconnect by name only; no auth token. |
| Rematch without server restart | PARTIAL | server_mp rematch handler; not tested | app/server_mp.py:251 | Server supports rematch; no smoke test coverage. |
| Supports 2..4 now; architecture for 5..6 | PARTIAL | net_protocol max_players 2..6; lobby spinbox up to 6 | app/net_protocol.py:14; app/lobby_ui.py:34 | UI rendering for >2 not tested. |
| Main menu + single/multi/settings/exit | PARTIAL | app/main_menu.py | app/main_menu.py:150 | Multiplayer button uses placeholder LobbyWindow, not lobby_ui.LobbyWindow. |
| Lobby UI (host/join/start/rematch) | PARTIAL | app/lobby_ui.py (not wired in main menu) | app/lobby_ui.py:13 | Real lobby exists but not launched by main menu. |
| Trade UI works and shows correct rate | IMPLEMENTED | scenario_ports_trade_rates + offline_ui_smoke.txt | app/trade_ui.py:8 | Rate computed via engine player_ports/best_trade_rate. |
| Dev UI works and shows hand | IMPLEMENTED | scenario_dev_cards_restrictions + offline_ui_smoke.txt | app/dev_ui.py:39 | Uses dev_summary from game. |
| Sidebar resources/bank/VP panel | IMPLEMENTED | offline_ui_smoke.txt | app/ui_v6.py:953 | Resource chips + status panel wired. |
| Clickable dice (roll via dice buttons) | IMPLEMENTED | offline_ui_smoke.txt | app/ui_v6.py:1116 | Dice buttons call on_roll_click. |
| Ports visuals (ship + ratio + resource icon) | MISSING | Ports render as text badge only | app/ui_v6.py:1307 | No ship icon or resource badge rendering. |
| Pieces visuals (SVG/tinted models) | MISSING | Pieces drawn as basic shapes | app/ui_v6.py:1357 | No SVG assets for roads/settlements/cities. |
| Board polish (water/shadows/tokens) | PARTIAL | ui_v6 rendering | app/ui_v6.py:1262 | Gradient tiles + token shadows; no coastline/water effects. |
| Victory overlay (not QMessageBox) | IMPLEMENTED | offline_ui_smoke.txt | app/ui_v6.py:691 | Overlay shows on game over. |