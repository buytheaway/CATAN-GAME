from __future__ import annotations

from typing import Any, Dict

from tests.harness.engine import GameDriver


def _add_knight(g, pid: int):
    g.players[pid].dev_cards.append({"type": "knight", "new": False})


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    g.phase = "main"
    g.turn = 0
    g.rolled = True

    # player 0 plays 3 knights across turns
    for _ in range(3):
        _add_knight(g, 0)
        res = driver.do({"type": "play_dev", "pid": 0, "card": "knight"})
        if not res.get("ok"):
            driver.fail("knight play failed", kind="assertion", details=res)
        g.pending_action = None
        g.pending_pid = None
        driver.do({"type": "end_turn", "pid": 0})
        driver.do({"type": "end_turn", "pid": 1})

    if g.largest_army_owner != 0 or g.largest_army_size < 3:
        driver.fail("largest army not awarded", kind="assertion", details={
            "owner": g.largest_army_owner,
            "size": g.largest_army_size,
        })

    # player 1 surpasses
    g.turn = 1
    g.phase = "main"
    for _ in range(4):
        _add_knight(g, 1)
        res = driver.do({"type": "play_dev", "pid": 1, "card": "knight"})
        if not res.get("ok"):
            driver.fail("knight play failed p1", kind="assertion", details=res)
        g.pending_action = None
        g.pending_pid = None
        driver.do({"type": "end_turn", "pid": 1})
        driver.do({"type": "end_turn", "pid": 0})

    if g.largest_army_owner != 1:
        driver.fail("largest army did not transfer", kind="assertion", details={"owner": g.largest_army_owner})

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
