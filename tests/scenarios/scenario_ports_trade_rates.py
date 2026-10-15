from __future__ import annotations

from typing import Any, Dict

from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver
from tests.scenarios.utils import pick_port_vertex, run_setup_snake


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    port_vid, port_kind = pick_port_vertex(driver)
    port_vertices = {vid for edge, _kind in g.ports for vid in edge}

    def choose_vertex(current: GameDriver, pid: int) -> int:
        if pid == 0 and not current.game.occupied_v:
            return port_vid
        legal = current.legal_settlement_vertices(pid, require_road=False)
        # Do not accidentally give the host a second harbor while completing
        # the real snake: it could legitimately improve the expected rate.
        if pid == 0:
            legal = [vid for vid in legal if vid not in port_vertices]
        if not legal:
            current.fail("no legal non-harbor second settlement")
        return legal[0]

    run_setup_snake(driver, choose_vertex=choose_vertex)
    normalized_kind = port_kind.split(":", 2)[2] if port_kind.startswith("2:1:") else port_kind
    if engine_rules.player_ports(g, 0) != {normalized_kind}:
        driver.fail("player_ports does not match the single owned setup harbor")
    give_res = "wood"
    expected_rate = 4
    if "3:1" in port_kind:
        expected_rate = 3
    elif "2:1:" in port_kind:
        give_res = port_kind.split(":", 2)[2]
        expected_rate = 2
    rate = engine_rules.best_trade_rate(g, 0, give_res)
    if rate != expected_rate:
        driver.fail("trade rate mismatch", details={"rate": rate, "expected": expected_rate})
    for resource in engine_rules.RESOURCES:
        expected = 3 if normalized_kind == "3:1" else (2 if resource == normalized_kind else 4)
        if engine_rules.best_trade_rate(g, 0, resource) != expected:
            driver.fail("harbor rate for other resource mismatch", details={"resource": resource})

    get_res = "brick" if give_res != "brick" else "wood"
    driver.ensure_resources(0, {give_res: rate})
    before_bank = dict(g.bank)
    before_res = dict(g.players[0].res)
    result = driver.do({"type": "trade_bank", "pid": 0, "give": give_res,
                        "get": get_res, "get_qty": 1})
    if result.get("rate") != rate:
        driver.fail("executed trade did not use expected harbor rate")
    if g.bank[give_res] != before_bank[give_res] + rate or g.bank[get_res] != before_bank[get_res] - 1:
        driver.fail("harbor trade bank mismatch")
    if g.players[0].res[give_res] != before_res[give_res] - rate or g.players[0].res[get_res] != before_res[get_res] + 1:
        driver.fail("harbor trade hand mismatch")

    return {"steps": driver.steps, "summary": driver.snapshot()}
