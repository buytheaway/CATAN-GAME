from __future__ import annotations

from typing import Any, Dict

from app.engine import rules as engine_rules
from app.engine.state import COST
from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_coastal_setup


def run(driver: GameDriver) -> Dict[str, Any]:
    g = engine_rules.build_game(seed=driver.seed, max_players=2, size=62.0,
                               map_id="seafarers_simple_1")
    driver.replace_game(g)
    run_coastal_setup(driver, pid=0)
    driver.ensure_resources(0, COST["ship"])
    driver.begin_turn(0)

    available = [e for e in sorted(g.edges) if engine_rules.can_place_ship(g, 0, e)]
    if not available:
        driver.fail("no legal ship edge after verified coastal setup", details={"seed": driver.seed})
    ship_edge = available[0]
    before_hand, before_bank = dict(g.players[0].res), dict(g.bank)
    driver.do({"type": "build_ship", "pid": 0, "eid": list(ship_edge)})
    if g.occupied_ships.get(ship_edge) != 0:
        driver.fail("paid ship missing or owned by another player")
    for resource, quantity in COST["ship"].items():
        if (g.players[0].res[resource] != before_hand[resource] - quantity
                or g.bank[resource] != before_bank[resource] + quantity):
            driver.fail("paid ship cost not conserved", details={"resource": resource})

    # A connected, unoccupied land edge isolates terrain validation from
    # occupancy and connection failures. Rejection must preserve all state.
    land_edges = [e for e in sorted(g.edges)
                  if not engine_rules._edge_has_sea(g, e)
                  and engine_rules.can_place_road(g, 0, e)]
    if not land_edges:
        driver.fail("no connected free land edge for invalid ship assertion")
    driver.reject({"type": "build_ship", "pid": 0, "eid": list(land_edges[0])},
                  error="illegal", message="Ship not allowed")
    return {"steps": driver.steps, "summary": driver.snapshot()}
