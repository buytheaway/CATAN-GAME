from __future__ import annotations

from typing import Any, Dict

from tests.harness.engine import GameDriver


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    g.phase = "main"
    g.turn = 0
    g.rolled = True

    driver.do({"type": "grant_resources", "pid": 0, "res": {"wood": 1}})
    res = driver.do({"type": "trade_offer_create", "pid": 0, "give": {"wood": 1}, "get": {"brick": 1}, "to_pid": 1})
    if not res.get("ok"):
        driver.fail("offer create failed", kind="assertion", details=res)

    offer_id = g.trade_offers[-1].offer_id
    res = driver.do({"type": "trade_offer_cancel", "pid": 0, "offer_id": offer_id})
    if not res.get("ok"):
        driver.fail("offer cancel failed", kind="assertion", details=res)

    offer = g.trade_offers[-1]
    if offer.status != "canceled":
        driver.fail("offer not canceled", kind="assertion", details={"status": offer.status})

    return {"steps": driver.steps, "summary": driver.snapshot()}
