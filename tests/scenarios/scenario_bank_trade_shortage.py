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

    # drain bank ore by granting to other player
    if g.bank.get("ore", 0) > 0:
        driver.do({"type": "grant_resources", "pid": 1, "res": {"ore": int(g.bank.get("ore", 0))}})

    # give player 0 enough wood to attempt a 4:1 trade
    driver.do({"type": "grant_resources", "pid": 0, "res": {"wood": 4}})

    res = driver.apply_action({"type": "trade_bank", "pid": 0, "give": "wood", "get": "ore", "get_qty": 1})
    if res.get("ok"):
        driver.fail("trade should fail when bank lacks resource", kind="assertion", details=res)

    return {"steps": driver.steps, "summary": driver.snapshot()}
