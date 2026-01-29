# CATAN-GAME (Singleplayer Desktop Prototype)

How to run:
- Offline singleplayer (UI v6): double click `RUN_UI_V6.bat`
- Multiplayer: start `RUN_SERVER.bat`, then on each client run `RUN_CLIENT.bat` and use Multiplayer -> Host/Join
- Legacy/experimental: moved to `legacy_scripts/` (not supported, may be broken)

Note:
- Legacy code moved to `app/_legacy/` (not used by UI v6).

Core rules:
- Shared engine lives in `app/engine/` (pure Python). Offline UI and server use the same rules.

Controls:
- Setup phase: click highlighted vertex to place Settlement, then click highlighted edge to place Road
- Main phase: Roll -> Build (Road/Settlement/City) -> click highlighted place -> End

Testing:
- Install test deps: `pip install -r requirements-dev.txt`
- Full suite: `pytest -q` and `python -m tests.run_all`
- UI interactions (dev/trade/robber): `pytest -q tests/test_ui_interactions.py`
- Multiplayer smoke: `pytest -q tests/test_multiplayer_basic.py`
- Reports output: `tests/reports/report_<timestamp>.json` and `tests/reports/BUG_REPORT.md`

Windows build (PyInstaller):
- Install builder: `pip install pyinstaller`
- Build server: `powershell -ExecutionPolicy Bypass -File tools/build/build_server.ps1`
- Build client: `powershell -ExecutionPolicy Bypass -File tools/build/build_client.ps1`
- Output:
  - `dist/CatanServer/CatanServer.exe`
  - `dist/CatanClient/CatanClient.exe`
- Run:
  - Start `CatanServer.exe` (default port 8000)
- Start `CatanClient.exe` and connect via Multiplayer -> Host/Join
- 
LAN Web (browser client):
- Start server on LAN: `python -m app.server_mp` (host 0.0.0.0 by default)
- Web client dev server:
  - `cd web`
  - `npm install`
  - `npm run dev -- --host 0.0.0.0 --port 5173`
- Open from another PC: `http://<your-ip>:5173`
- WS URL default in `web/.env` (`VITE_WS_URL=ws://<server-ip>:8000/ws`)

NO HACKS policy:
- No `QTimer.singleShot` for "wait until UI ready"
- No `runtime_patch` or `ports_bridge`
- No monkey-patching via `Game.<name> = ...`
- No widget lookup via `findChild(...)`
