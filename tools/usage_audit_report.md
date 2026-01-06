# Usage Audit Report

## Summary

- Entry modules: app.main_menu, app.server_mp
- Reachable files: 17
- Unreachable files: 7
- Ambiguous imports: 34

## Top Unused Candidates

- app\board.py (unreachable from entrypoints)
- app\client_cli.py (unreachable from entrypoints)
- app\expansions\__init__.py (unreachable from entrypoints)
- app\expansions\base.py (unreachable from entrypoints)
- app\expansions\seafarers_stub.py (unreachable from entrypoints)
- app\ports_bridge.py (unreachable from entrypoints)
- app\runtime_patch.py (unreachable from entrypoints)

## Risky Files (high fan-in or dynamic imports)

- app\theme.py (imported by 5)
- app\__init__.py (imported by 4)
- app\config.py (imported by 4)
- app\ui_v6.py (imported by 3)
- app\net_client.py (imported by 2)
- app\online_controller.py (imported by 1)
- app\game_launcher.py (imported by 1)
- app\lobby_ui.py (imported by 1)
- app\rules_engine.py (imported by 1)
- app\net_protocol.py (imported by 1)

## Dynamic Imports

- app.board: <syntax_error>
- app.client_cli: <syntax_error>
- app.expansions.base: <syntax_error>
- app.expansions.seafarers_stub: <syntax_error>
- app.expansions: <syntax_error>

## Suggested Safe Actions

- Move unreachable files to `app/_legacy/` (no deletions).
- Keep ambiguous imports until resolved.
- Refactor hack patterns (see `tools/hacks_report.md`).

## Runtime Evidence

- USED: 17
- SAFE_UNUSED: 7
- MAYBE_UNUSED: 0

### USED
- app\__init__.py
- app\assets_loader.py
- app\config.py
- app\dev_hand_overlay.py
- app\dev_ui.py
- app\game_launcher.py
- app\lobby_ui.py
- app\main_menu.py
- app\net_client.py
- app\net_protocol.py
- app\online_controller.py
- app\rules_engine.py
- app\server_mp.py
- app\theme.py
- app\trade_ui.py
- app\ui_tweaks.py
- app\ui_v6.py

### SAFE_UNUSED
- app\board.py
- app\client_cli.py
- app\expansions\__init__.py
- app\expansions\base.py
- app\expansions\seafarers_stub.py
- app\ports_bridge.py
- app\runtime_patch.py

### MAYBE_UNUSED
- none
