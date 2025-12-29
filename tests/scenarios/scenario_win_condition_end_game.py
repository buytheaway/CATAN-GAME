from __future__ import annotations

from typing import Any, Dict

from tests.harness.engine import GameDriver


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    g.phase = "main"
    g.turn = 0
    g.rolled = True

    g.players[0].vp = 10
    g.winner_pid = 0
    g.game_over = True

    action = {"type": "place_road", "pid": 0, "eid": next(iter(g.edges))}
    driver.steps.append(dict(action))
    res = driver.apply_action(action)
    if res.get("ok"):
        driver.fail("action allowed after game over", kind="assertion")

    if not g.game_over or g.winner_pid is None:
        driver.fail("game_over state missing", kind="assertion")

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
