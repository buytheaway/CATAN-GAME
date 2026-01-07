from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "tools" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

LOGS = {
    "pytest": REPORT_DIR / "pytest_q.txt",
    "run_all": REPORT_DIR / "run_all.txt",
    "no_hacks": REPORT_DIR / "no_hacks.txt",
    "grep_hacks": REPORT_DIR / "grep_hacks.txt",
    "offline_ui_smoke": REPORT_DIR / "offline_ui_smoke.txt",
    "multiplayer_smoke": REPORT_DIR / "multiplayer_smoke.txt",
    "engine_audit": REPORT_DIR / "engine_source_audit.txt",
}


def _run(cmd: List[str], log_path: Path) -> Tuple[int, str]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    log_path.write_text(output, encoding="utf-8")
    return proc.returncode, output


def _run_shell(cmd: str, log_path: Path) -> Tuple[int, str]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, shell=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    log_path.write_text(output, encoding="utf-8")
    return proc.returncode, output


def _find_line(path: Path, pattern: str) -> Optional[int]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return None
    for idx, line in enumerate(lines, 1):
        if pattern in line:
            return idx
    return None


def _find_regex_line(path: Path, pattern: str) -> Optional[int]:
    rx = re.compile(pattern)
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return None
    for idx, line in enumerate(lines, 1):
        if rx.search(line):
            return idx
    return None


def _apply_cmd_types() -> List[str]:
    rules = ROOT / "app" / "engine" / "rules.py"
    text = rules.read_text(encoding="utf-8", errors="replace")
    # isolate apply_cmd body
    m = re.search(r"def apply_cmd\(.*?\):(?P<body>[\s\S]*?)\n\s*def ", text)
    body = m.group("body") if m else text
    types = set(re.findall(r"ctype\s*==\s*\"(.*?)\"", body))
    # handle: if ctype in ("a", "b")
    for m2 in re.finditer(r"ctype\s*in\s*\(([^\)]*)\)", body):
        items = m2.group(1)
        for s in re.findall(r"\"(.*?)\"", items):
            types.add(s)
    return sorted(types)


def _engine_cmds() -> Dict[str, List[str]]:
    return {"engine.apply_cmd": _apply_cmd_types()}


def _grep_hacks() -> None:
    cmd = (
        'rg -n "QTimer\\.singleShot|runtime_patch|ports_bridge|findChild\\(|\\bGame\\.\\w+\\s*=\\s*" '
        'app -g "*.py" -g "!app/_legacy/**" -g "!app/_legacy_bak/**" -g "!app/_legacy_next/**"'
    )
    code, output = _run_shell(cmd, LOGS["grep_hacks"])
    if code == 1:
        LOGS["grep_hacks"].write_text("no matches\n", encoding="utf-8")
    elif code != 0:
        LOGS["grep_hacks"].write_text(output, encoding="utf-8")
        raise SystemExit(code)


def _summarize_log(path: Path, fallback: str = "(no output)") -> str:
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return fallback
    lines = text.splitlines()
    return lines[-1] if lines else text


def _status_line(code: int) -> str:
    return "PASS" if code == 0 else "FAIL"


def main() -> int:
    # Proof commands
    rc_pytest, _ = _run([sys.executable, "-m", "pytest", "-q"], LOGS["pytest"])
    rc_run_all, _ = _run([sys.executable, "-m", "tests.run_all"], LOGS["run_all"])
    rc_no_hacks, _ = _run([sys.executable, "-m", "pytest", "-q", "tests/test_no_hacks.py"], LOGS["no_hacks"])
    _grep_hacks()
    rc_engine, _ = _run([sys.executable, "tools/engine_source_audit.py"], LOGS["engine_audit"])
    rc_offline, _ = _run([sys.executable, "tools/offline_ui_smoke.py"], LOGS["offline_ui_smoke"])
    rc_mp, _ = _run([sys.executable, "tools/multiplayer_smoke.py"], LOGS["multiplayer_smoke"])

    # Evidence summary
    evidence_lines = [
        "# Feature Evidence",
        "",
        "Commands run:",
        f"- pytest -q -> {_status_line(rc_pytest)} ({LOGS['pytest'].as_posix()})",
        f"- python -m tests.run_all -> {_status_line(rc_run_all)} ({LOGS['run_all'].as_posix()})",
        f"- pytest -q tests/test_no_hacks.py -> {_status_line(rc_no_hacks)} ({LOGS['no_hacks'].as_posix()})",
        f"- rg hack scan -> {LOGS['grep_hacks'].as_posix()}",
        f"- python tools/engine_source_audit.py -> {_status_line(rc_engine)} ({LOGS['engine_audit'].as_posix()})",
        f"- python tools/offline_ui_smoke.py -> {_status_line(rc_offline)} ({LOGS['offline_ui_smoke'].as_posix()})",
        f"- python tools/multiplayer_smoke.py -> {_status_line(rc_mp)} ({LOGS['multiplayer_smoke'].as_posix()})",
        "",
        "Last-line summaries:",
        f"- pytest: {_summarize_log(LOGS['pytest'])}",
        f"- run_all: {_summarize_log(LOGS['run_all'])}",
        f"- no_hacks: {_summarize_log(LOGS['no_hacks'])}",
        f"- engine_audit: {_summarize_log(LOGS['engine_audit'])}",
        f"- offline_ui_smoke: {_summarize_log(LOGS['offline_ui_smoke'])}",
        f"- multiplayer_smoke: {_summarize_log(LOGS['multiplayer_smoke'])}",
        "",
    ]
    (REPORT_DIR / "feature_evidence.md").write_text("\n".join(evidence_lines), encoding="utf-8")

    # Code pointers
    ui_v6 = ROOT / "app" / "ui_v6.py"
    server_mp = ROOT / "app" / "server_mp.py"
    lobby_ui = ROOT / "app" / "lobby_ui.py"
    main_menu = ROOT / "app" / "main_menu.py"
    engine_rules = ROOT / "app" / "engine" / "rules.py"

    # Feature matrix (manual statuses + pointers)
    features = []

    # Base rules
    features.append({
        "Feature": "Setup snake draft (N players) + 2 settlements/roads",
        "Status": "PARTIAL",
        "Evidence": "tests/scenarios/scenario_setup_snake.py (tests.run_all)",
        "Code": f"app/engine/rules.py:{_find_line(engine_rules, 'make_setup_order')}",
        "Notes": "Setup order implemented; starting resources from 2nd settlement not awarded.",
    })
    features.append({
        "Feature": "Dice roll + resource distribution (robber blocks)",
        "Status": "IMPLEMENTED",
        "Evidence": "scenario_roll_distribution_basic, scenario_robber_7_flow (tests.run_all)",
        "Code": f"app/engine/rules.py:{_find_line(engine_rules, 'def distribute_for_roll')}",
        "Notes": "Robber tile skips distribution.",
    })
    features.append({
        "Feature": "Robber on 7: discard, move, steal",
        "Status": "IMPLEMENTED",
        "Evidence": "scenario_robber_7_flow (tests.run_all)",
        "Code": f"app/engine/rules.py:{_find_line(engine_rules, 'if ctype == "roll"')}",
        "Notes": "Engine enforces discard + move robber + steal.",
    })
    features.append({
        "Feature": "Build legality (road adjacency, settlement distance, city upgrade)",
        "Status": "IMPLEMENTED",
        "Evidence": "scenario_setup_snake + invariants (tests.run_all)",
        "Code": f"app/engine/rules.py:{_find_line(engine_rules, 'def can_place_settlement')}",
        "Notes": "Distance rule enforced in can_place_settlement.",
    })
    features.append({
        "Feature": "Trade with bank 4:1 / 3:1 / 2:1 ports",
        "Status": "IMPLEMENTED",
        "Evidence": "scenario_ports_trade_rates (tests.run_all)",
        "Code": f"app/engine/rules.py:{_find_line(engine_rules, 'def trade_with_bank')}",
        "Notes": "Ports resolved by node ownership.",
    })
    features.append({
        "Feature": "Player-to-player trade",
        "Status": "MISSING",
        "Evidence": "No engine cmd type for trade_player",
        "Code": "app/engine/rules.py (apply_cmd dispatch)",
        "Notes": "No cmd type for player trades in engine or server.",
    })
    features.append({
        "Feature": "Dev cards (buy + restrictions + effects)",
        "Status": "IMPLEMENTED",
        "Evidence": "scenario_dev_cards_restrictions (tests.run_all)",
        "Code": f"app/engine/rules.py:{_find_line(engine_rules, 'def buy_dev')}",
        "Notes": "Enforces new-card restriction + 1 per turn.",
    })
    features.append({
        "Feature": "Achievements (Longest Road, Largest Army)",
        "Status": "IMPLEMENTED",
        "Evidence": "scenario_longest_road_award + scenario_largest_army_award (tests.run_all)",
        "Code": f"app/engine/rules.py:{_find_line(engine_rules, 'def update_longest_road')}",
        "Notes": "Awards +2 VP and transfers.",
    })
    features.append({
        "Feature": "Win condition + game over lock + victory overlay",
        "Status": "IMPLEMENTED",
        "Evidence": "scenario_win_condition_end_game + offline_ui_smoke.txt",
        "Code": f"app/engine/rules.py:{_find_line(engine_rules, 'def check_win')}; app/ui_v6.py:{_find_line(ui_v6, 'class VictoryOverlay')}",
        "Notes": "Overlay used instead of QMessageBox.",
    })

    # Multiplayer
    features.append({
        "Feature": "Server rooms + room code",
        "Status": "IMPLEMENTED",
        "Evidence": "tests/test_multiplayer_basic.py + tools/multiplayer_smoke.py",
        "Code": f"app/server_mp.py:{_find_line(server_mp, 'def create_room')}",
        "Notes": "Room codes generated server-side.",
    })
    features.append({
        "Feature": "Join/leave, player list, start match",
        "Status": "IMPLEMENTED",
        "Evidence": "tests/test_multiplayer_basic.py + multiplayer_smoke.txt",
        "Code": f"app/server_mp.py:{_find_line(server_mp, 'join_room')}",
        "Notes": "Leave supported; not directly tested.",
    })
    features.append({
        "Feature": "Authoritative server uses engine",
        "Status": "IMPLEMENTED",
        "Evidence": "tools/engine_source_audit.txt",
        "Code": f"app/server_mp.py:{_find_line(server_mp, 'apply_cmd')}",
        "Notes": "Server applies engine rules and broadcasts snapshots.",
    })
    features.append({
        "Feature": "Snapshot tick/version monotonic",
        "Status": "IMPLEMENTED",
        "Evidence": "multiplayer_smoke.txt",
        "Code": f"app/server_mp.py:{_find_line(server_mp, 'room.tick')}",
        "Notes": "Tick increments after valid cmd.",
    })
    features.append({
        "Feature": "Seq/duplicate cmd handling",
        "Status": "PARTIAL",
        "Evidence": "server_mp seq checks; not explicitly tested",
        "Code": f"app/server_mp.py:{_find_line(server_mp, 'last_seq')}",
        "Notes": "Seq gate exists; no explicit test coverage.",
    })
    features.append({
        "Feature": "Reconnect (token)",
        "Status": "MISSING",
        "Evidence": "No token-based reconnect in server_mp.py",
        "Code": f"app/server_mp.py:{_find_line(server_mp, 'join_room')}",
        "Notes": "Reconnect by name only; no auth token.",
    })
    features.append({
        "Feature": "Rematch without server restart",
        "Status": "PARTIAL",
        "Evidence": "server_mp rematch handler; not tested",
        "Code": f"app/server_mp.py:{_find_line(server_mp, 'if mtype == "rematch"')}",
        "Notes": "Server supports rematch; no smoke test coverage.",
    })
    features.append({
        "Feature": "Supports 2..4 now; architecture for 5..6",
        "Status": "PARTIAL",
        "Evidence": "net_protocol max_players 2..6; lobby spinbox up to 6",
        "Code": f"app/net_protocol.py:14; app/lobby_ui.py:{_find_line(lobby_ui, 'setRange(2, 6)')}",
        "Notes": "UI rendering for >2 not tested.",
    })

    # UI/UX
    features.append({
        "Feature": "Main menu + single/multi/settings/exit",
        "Status": "PARTIAL",
        "Evidence": "app/main_menu.py",
        "Code": f"app/main_menu.py:{_find_line(main_menu, 'class MainMenuWindow')}",
        "Notes": "Multiplayer button uses placeholder LobbyWindow, not lobby_ui.LobbyWindow.",
    })
    features.append({
        "Feature": "Lobby UI (host/join/start/rematch)",
        "Status": "PARTIAL",
        "Evidence": "app/lobby_ui.py (not wired in main menu)",
        "Code": f"app/lobby_ui.py:{_find_line(lobby_ui, 'class LobbyWindow')}",
        "Notes": "Real lobby exists but not launched by main menu.",
    })
    features.append({
        "Feature": "Trade UI works and shows correct rate",
        "Status": "IMPLEMENTED",
        "Evidence": "scenario_ports_trade_rates + offline_ui_smoke.txt",
        "Code": f"app/trade_ui.py:{_find_line(ROOT / 'app' / 'trade_ui.py', 'class TradeDialog')}",
        "Notes": "Rate computed via engine player_ports/best_trade_rate.",
    })
    features.append({
        "Feature": "Dev UI works and shows hand",
        "Status": "IMPLEMENTED",
        "Evidence": "scenario_dev_cards_restrictions + offline_ui_smoke.txt",
        "Code": f"app/dev_ui.py:{_find_line(ROOT / 'app' / 'dev_ui.py', 'class DevDialog')}",
        "Notes": "Uses dev_summary from game.",
    })
    features.append({
        "Feature": "Sidebar resources/bank/VP panel",
        "Status": "IMPLEMENTED",
        "Evidence": "offline_ui_smoke.txt",
        "Code": f"app/ui_v6.py:{_find_line(ui_v6, 'class ResourcesPanel')}",
        "Notes": "Resource chips + status panel wired.",
    })
    features.append({
        "Feature": "Clickable dice (roll via dice buttons)",
        "Status": "IMPLEMENTED",
        "Evidence": "offline_ui_smoke.txt",
        "Code": f"app/ui_v6.py:{_find_line(ui_v6, 'self.d1.clicked.connect')}",
        "Notes": "Dice buttons call on_roll_click.",
    })
    features.append({
        "Feature": "Ports visuals (ship + ratio + resource icon)",
        "Status": "MISSING",
        "Evidence": "Ports render as text badge only",
        "Code": f"app/ui_v6.py:{_find_line(ui_v6, 'def _draw_ports')}",
        "Notes": "No ship icon or resource badge rendering.",
    })
    features.append({
        "Feature": "Pieces visuals (SVG/tinted models)",
        "Status": "MISSING",
        "Evidence": "Pieces drawn as basic shapes",
        "Code": f"app/ui_v6.py:{_find_line(ui_v6, 'draw roads')}",
        "Notes": "No SVG assets for roads/settlements/cities.",
    })
    features.append({
        "Feature": "Board polish (water/shadows/tokens)",
        "Status": "PARTIAL",
        "Evidence": "ui_v6 rendering",
        "Code": f"app/ui_v6.py:{_find_line(ui_v6, 'number token')}",
        "Notes": "Gradient tiles + token shadows; no coastline/water effects.",
    })
    features.append({
        "Feature": "Victory overlay (not QMessageBox)",
        "Status": "IMPLEMENTED",
        "Evidence": "offline_ui_smoke.txt",
        "Code": f"app/ui_v6.py:{_find_line(ui_v6, 'class VictoryOverlay')}",
        "Notes": "Overlay shows on game over.",
    })

    # Write feature matrix
    lines = ["# Feature Matrix", "", "| Feature | Status | Evidence | Code pointers | Notes |", "| --- | --- | --- | --- | --- |"]
    for f in features:
        lines.append(f"| {f['Feature']} | {f['Status']} | {f['Evidence']} | {f['Code']} | {f['Notes']} |")
    (REPORT_DIR / "feature_matrix.md").write_text("\n".join(lines), encoding="utf-8")

    # TODO list
    todos = [
        "# Feature TODO",
        "",
        "## Blockers (breaks gameplay)",
        "- Implement starting resources from 2nd settlement during setup.",
        "- Wire main menu Multiplayer button to real lobby_ui.LobbyWindow (current placeholder).",
        "",
        "## Multiplayer correctness",
        "- Add reconnect token/session handling (avoid name-based collisions).",
        "- Add explicit tests for seq/duplicate command handling and rematch flow.",
        "- Validate max_players rendering for >4 players in UI.",
        "",
        "## UX / Visual polish",
        "- Replace port text badges with ship + ratio + resource icon visuals.",
        "- Replace road/settlement/city shapes with SVG/tinted piece assets.",
        "- Add water/coastline shading to board for clearer map boundaries.",
        "",
        "## Nice-to-have",
        "- Player-to-player trade mechanics.",
        "- Expansion rules (Seafarers) and 5-6 player extension rules.",
    ]
    (REPORT_DIR / "feature_todo.md").write_text("\n".join(todos), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
