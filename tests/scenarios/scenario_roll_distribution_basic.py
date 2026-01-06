from __future__ import annotations

from typing import Any, Dict

from app.engine.state import RESOURCES, TERRAIN_TO_RES
from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_setup_snake


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    run_setup_snake(driver)

    g.phase = "main"
    g.turn = 0
    g.rolled = False

    # pick a roll number that exists
    roll = None
    for t in g.tiles:
        if t.number is not None:
            roll = int(t.number)
            break
    if roll is None:
        driver.fail("no numbered tiles", kind="assertion")

    # record pre-roll resources
    before = [p.res.copy() for p in g.players]

    res = driver.do({"type": "roll", "pid": 0, "roll": roll})
    if not res.get("ok"):
        driver.fail("roll failed", kind="assertion", details=res)

    # compute expected gains from all tiles with number
    gains = [{r: 0 for r in RESOURCES} for _ in g.players]
    for vid, (owner, level) in g.occupied_v.items():
        for ti in g.vertex_adj_hexes.get(vid, []):
            tile = g.tiles[ti]
            if tile.number != roll:
                continue
            if ti == g.robber_tile:
                continue
            res_name = TERRAIN_TO_RES.get(tile.terrain)
            if not res_name:
                continue
            gains[owner][res_name] += 2 if level == 2 else 1

    for pid, p in enumerate(g.players):
        for r in RESOURCES:
            expected = before[pid][r] + gains[pid][r]
            actual = p.res[r]
            if actual != expected:
                driver.fail("resource distribution mismatch", kind="assertion", details={
                    "pid": pid,
                    "res": r,
                    "expected": expected,
                    "actual": actual,
                    "roll": roll,
                })

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
