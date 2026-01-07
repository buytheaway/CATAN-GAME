from __future__ import annotations

from typing import Any, Dict

from tests.harness.engine import GameDriver


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    g.phase = "main"
    g.turn = 0
    g.rolled = True

    # fund players
    driver.do({"type": "grant_resources", "pid": 0, "res": {"wood": 2}})
    driver.do({"type": "grant_resources", "pid": 1, "res": {"brick": 1}})

    res = driver.do({"type": "trade_offer_create", "pid": 0, "give": {"wood": 2}, "get": {"brick": 1}, "to_pid": 1})
    if not res.get("ok"):
        driver.fail("offer create failed", kind="assertion", details=res)

    offer_id = g.trade_offers[-1].offer_id
    res = driver.do({"type": "trade_offer_accept", "pid": 1, "offer_id": offer_id})
    if not res.get("ok"):
        driver.fail("offer accept failed", kind="assertion", details=res)

    if g.players[0].res["wood"] != 0 or g.players[0].res["brick"] != 1:
        driver.fail("trade result mismatch for p0", kind="assertion")
    if g.players[1].res["wood"] != 2 or g.players[1].res["brick"] != 0:
        driver.fail("trade result mismatch for p1", kind="assertion")

    return {"steps": driver.steps, "summary": driver.snapshot()}
