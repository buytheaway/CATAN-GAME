from __future__ import annotations

from typing import Any, Dict

from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_setup_snake


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    run_setup_snake(driver)

    g.phase = "main"
    g.turn = 0
    g.rolled = False

    # ensure hands are <= 7 (no discard)
    for pid, p in enumerate(g.players):
        if sum(p.res.values()) > 7:
            driver.fail("unexpected hand >7 before roll 7", kind="assertion", details={"pid": pid, "hand": sum(p.res.values())})

    res = driver.do({"type": "roll", "pid": 0, "roll": 7})
    if not res.get("ok"):
        driver.fail("roll 7 failed", kind="assertion", details=res)

    if g.pending_action != "robber_move":
        driver.fail("robber_move not pending when no discards needed", kind="assertion", details={"pending": g.pending_action})
    if g.discard_required:
        driver.fail("discard_required should be empty when no discards needed", kind="assertion")

    # move robber and ensure pending cleared
    target = 1 if g.robber_tile != 1 else 0
    res = driver.do({"type": "move_robber", "pid": 0, "tile": target})
    if not res.get("ok"):
        driver.fail("move_robber failed", kind="assertion", details=res)
    if g.pending_action is not None:
        driver.fail("pending_action not cleared after move_robber", kind="assertion")

    return {"steps": driver.steps, "summary": driver.snapshot()}
