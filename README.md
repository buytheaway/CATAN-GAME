# CATAN-GAME (Singleplayer Desktop Prototype)

How to run:
- Offline singleplayer (UI v6): double click `RUN_UI_V6.bat`
- Multiplayer: start `RUN_SERVER.bat`, then on each client run `RUN_CLIENT.bat` and use Multiplayer -> Host/Join
- Legacy/experimental: moved to `legacy_scripts/` (not supported, may be broken)

Note:
- Legacy code moved to `app/_legacy/` (not used by UI v6).

Controls:
- Setup phase: click highlighted vertex to place Settlement, then click highlighted edge to place Road
- Main phase: Roll -> Build (Road/Settlement/City) -> click highlighted place -> End

Testing:
- Scenario suite + reports: `python -m tests.run_all`
- UI smoke (pytest): `pytest -q`
- Multiplayer smoke: `pytest -q tests/test_multiplayer_basic.py`
- Reports output: `tests/reports/report_<timestamp>.json` and `tests/reports/BUG_REPORT.md`
