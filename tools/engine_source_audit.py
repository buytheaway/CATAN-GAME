from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGET_FILES = {
    "ui_v6": ROOT / "app" / "ui_v6.py",
    "server_mp": ROOT / "app" / "server_mp.py",
    "online_controller": ROOT / "app" / "online_controller.py",
}

RULE_FUNCS = [
    "best_trade_rate",
    "trade_with_bank",
    "distribute_for_roll",
    "update_longest_road",
    "update_largest_army",
    "check_win",
    "buy_dev",
    "play_dev",
]


def _read(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _extract_defs(lines: list[str]) -> dict[str, dict]:
    defs: dict[str, dict] = {}
    for i, line in enumerate(lines):
        if line.lstrip().startswith("def "):
            indent = len(line) - len(line.lstrip())
            name = line.strip().split()[1].split("(")[0]
            body = []
            for j in range(i + 1, len(lines)):
                nxt = lines[j]
                if nxt.strip() == "":
                    body.append(nxt)
                    continue
                cur_indent = len(nxt) - len(nxt.lstrip())
                if cur_indent <= indent and nxt.lstrip().startswith("def "):
                    break
                if cur_indent <= indent and nxt.lstrip().startswith("class "):
                    break
                if cur_indent < indent and nxt.strip():
                    break
                body.append(nxt)
            defs[name] = {"line": i + 1, "body": "\n".join(body)}
    return defs


def _audit_ui(lines: list[str]) -> list[str]:
    issues: list[str] = []
    defs = _extract_defs(lines)
    for name in RULE_FUNCS:
        if name in defs:
            body = defs[name]["body"]
            if "engine_rules" not in body:
                issues.append(f"ui_v6.py:{defs[name]['line']}: local rule impl '{name}' without engine_rules")
    if "engine_rules.apply_cmd" not in "\n".join(lines):
        issues.append("ui_v6.py: missing engine_rules.apply_cmd usage")
    return issues


def _audit_server(lines: list[str]) -> list[str]:
    issues: list[str] = []
    text = "\n".join(lines)
    if "apply_cmd" not in text:
        issues.append("server_mp.py: apply_cmd not found")
    if "to_dict" not in text:
        issues.append("server_mp.py: to_dict not found")
    return issues


def _audit_controller(lines: list[str]) -> list[str]:
    issues: list[str] = []
    text = "\n".join(lines)
    if "apply_snapshot" not in text:
        issues.append("online_controller.py: apply_snapshot not found")
    return issues


def main() -> int:
    issues: list[str] = []

    ui_lines = _read(TARGET_FILES["ui_v6"])
    issues.extend(_audit_ui(ui_lines))

    server_lines = _read(TARGET_FILES["server_mp"])
    issues.extend(_audit_server(server_lines))

    controller_lines = _read(TARGET_FILES["online_controller"])
    issues.extend(_audit_controller(controller_lines))

    if issues:
        print("FAIL: engine source audit failed")
        for item in issues:
            print("-", item)
        return 1

    print("PASS: engine source audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
