from __future__ import annotations

import os
from typing import Any, Dict

from PySide6 import QtWidgets

from app.config import GameConfig
from app import ui_v6
from tests.harness.engine import GameDriver
from tests.harness.invariants import check_invariants

SEEDS = list(range(1, 6))


def run(driver: GameDriver) -> Dict[str, Any]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    w = ui_v6.MainWindow(config=GameConfig(bot_enabled=True, bot_difficulty=1))
    w.hide()
    g = w.game
    driver.replace_game(g)

    g.phase = "main"
    g.pending_action = None
    g.turn = 1
    g.rolled = False

    steps = []
    for i in range(50):
        w._bot_turn()
        step = {"type": "bot_turn", "turn": i}
        steps.append(step)
        driver.steps.append(dict(step))
        failures = check_invariants(g, driver.expected_totals)
        if failures:
            driver.fail("invariants failed during bot run", kind="invariant", details={"failures": failures})
        # force next bot turn
        g.turn = 1
        g.rolled = False
        g.pending_action = None

    w.close()

    return {
        "steps": steps,
        "summary": driver.snapshot(),
    }
