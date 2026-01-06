from __future__ import annotations

import os
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
EXCLUDE_DIRS = {"_legacy", "_legacy_bak", "_legacy_next"}

BANNED_PATTERNS = {
    "QTimer.singleShot": re.compile(r"QTimer\.singleShot"),
    "runtime_patch": re.compile(r"\bruntime_patch\b"),
    "ports_bridge": re.compile(r"\bports_bridge\b"),
    "monkey_patch": re.compile(r"\bGame\.\w+\s*=\s*"),
    "findChild": re.compile(r"\bfindChild\s*\("),
}

TEXT_LOOKUP = re.compile(r"\.text\(\)")


def _iter_py_files():
    for root, dirs, files in os.walk(APP_DIR):
        rel = Path(root).relative_to(APP_DIR)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            dirs[:] = []
            continue
        for name in files:
            if name.endswith(".py"):
                yield Path(root) / name


def test_no_hacks():
    violations: list[str] = []
    for path in _iter_py_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        for label, pattern in BANNED_PATTERNS.items():
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    violations.append(f"{path}:{i}: banned {label}: {line.strip()}")

        if TEXT_LOOKUP.search(text):
            if "findChild" in text or "findChildren" in text:
                for i, line in enumerate(lines, 1):
                    if ".text()" in line:
                        violations.append(f"{path}:{i}: suspicious widget lookup: {line.strip()}")

    if violations:
        joined = "\n".join(violations)
        raise AssertionError(f"Banned hack patterns found:\n{joined}")
