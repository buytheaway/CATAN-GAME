from __future__ import annotations

from typing import Any, Dict

from app import ui_v6
from app.runtime_patch import ensure_game_api
from tests.harness.engine import GameDriver


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game

    # place a settlement on a port endpoint (setup rules)
    port_vid = None
    port_kind = None
    for edge, kind in g.ports:
        for vid in edge:
            if not ui_v6.can_place_settlement(g, 0, vid, require_road=False):
                continue
            g.setup_need = "settlement"
            g.phase = "setup"
            res = driver.do({"type": "place_settlement", "pid": 0, "vid": vid, "setup": True})
            if res.get("ok"):
                port_vid = vid
                port_kind = kind
                break
        if port_vid is not None:
            break

    if port_vid is None:
        driver.fail("no legal port settlement", kind="assertion")

    g.phase = "main"
    g.turn = 0
    g.rolled = False

    ensure_game_api(g, override_ports=True, override_trade=True)
    ports = g.player_ports(0)
    if not ports:
        driver.fail("player_ports empty after port settlement", kind="assertion")

    give_res = "wood"
    expected_rate = 4
    if port_kind and "3:1" in port_kind:
        expected_rate = 3
    elif port_kind and "2:1:" in port_kind:
        give_res = port_kind.split(":", 2)[2]
        expected_rate = 2

    rate = g.best_trade_rate(0, give_res)
    if rate != expected_rate:
        driver.fail("trade rate mismatch", kind="assertion", details={"rate": rate, "expected": expected_rate})

    # fund and trade
    give_qty = rate * 1
    driver.do({"type": "grant_resources", "pid": 0, "res": {give_res: give_qty}})
    before_bank = g.bank.copy()
    res = driver.do({"type": "trade_bank", "pid": 0, "give": give_res, "get": "brick", "get_qty": 1})
    if not res.get("ok"):
        driver.fail("trade failed", kind="assertion", details=res)

    if g.bank[give_res] != before_bank[give_res] + give_qty:
        driver.fail("bank give mismatch", kind="assertion")
    if g.bank["brick"] != before_bank["brick"] - 1:
        driver.fail("bank get mismatch", kind="assertion")

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
