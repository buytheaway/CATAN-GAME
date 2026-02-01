# CATAN-GAME (Singleplayer Desktop Prototype)

How to run:
- Offline singleplayer (UI v6): double click `RUN_UI_V6.bat`
- Multiplayer: start `RUN_SERVER.bat`, then on each client run `RUN_CLIENT.bat` and use Multiplayer -> Host/Join
- Legacy/experimental: moved to `legacy_scripts/` (not supported, may be broken)

Note:
- Legacy code moved to `app/_legacy/` (not used by UI v6).

Core rules:
- Shared engine lives in `app/engine/` (pure Python). Offline UI and server use the same rules.

Maps / presets / custom:
- Preset maps live in `app/assets/maps/` (base_* and seafarers_*).
- Community presets: `community_balanced_a/b/c` (balanced layouts with no adjacent 6/8).
- Seafarers presets: `seafarers_simple_*`, `seafarers_gold_haven`, `seafarers_pirate_lanes`.
- Offline: Singleplayer dialog has a preset dropdown + "Load map file..." for custom JSON.
- Multiplayer (desktop): host can pick preset or load a custom map file in the lobby before start.
- Multiplayer (web): host can pick preset or upload a custom JSON (Set Custom).
- Map schema: see `docs/maps_schema.md`.

Controls:
- Setup phase: click highlighted vertex to place Settlement, then click highlighted edge to place Road
- Main phase: Roll -> Build (Road/Settlement/City) -> click highlighted place -> End
- Seafarers maps: Ship/Move Ship/Pirate actions appear when enabled by the map rules; Gold prompts appear when a gold tile triggers
- UX/Controls quick guide: see `docs/ux_controls.md`
- Save/Load (offline): use the Save/Load buttons in the top bar (JSON files)

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

Linux/macOS build (PyInstaller):
- Build must be run on the target OS (no cross-build).
- Install builder: `pip install pyinstaller`
- Linux:
  - `bash tools/build/build_server_linux.sh`
  - `bash tools/build/build_client_linux.sh`
- macOS:
  - `bash tools/build/build_server_mac.sh`
  - `bash tools/build/build_client_mac.sh`
- Output:
  - `dist/CatanServer/` and `dist/CatanClient/`

LAN Web (browser client):
- Start server on LAN: `python -m app.server_mp` (host 0.0.0.0 by default)
- Optional env override: `CATAN_HOST=0.0.0.0 CATAN_PORT=8000 python -m app.server_mp`
- Web client dev server:
  - `cd web`
  - `npm install`
  - `npm run dev -- --host 0.0.0.0 --port 5173`
- One-command helper:
  - `powershell -ExecutionPolicy Bypass -File tools/run_lan.ps1`
  - Check ports: `powershell -ExecutionPolicy Bypass -File tools/check_lan.ps1`
- Open from another PC: `http://<your-ip>:5173`
- Create `web/.env.local` for LAN (see `web/.env.example`):
  - `VITE_WS_URL=ws://192.168.0.24:8000/ws`
  - Replace with your Wi-Fi IPv4 (from `ipconfig`)
- Local dev default remains `web/.env` (127.0.0.1)
- Web UI now includes an interactive board (click-to-place) for core actions.

Seafarers (MVP + extended):
- Enabled via maps whose rules contain `enable_seafarers: true`.
- Ships, move_ship, pirate, gold are driven by map rules (see `docs/maps_schema.md`).

NO HACKS policy:
- No `QTimer.singleShot` for "wait until UI ready"
- No `runtime_patch` or `ports_bridge`
- No monkey-patching via `Game.<name> = ...`
- No widget lookup via `findChild(...)`
