from __future__ import annotations

from typing import Any, Dict

from app.engine import maps as map_loader
from app.engine import rules as engine_rules
from app.engine.state import COST
from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_coastal_setup


def run(driver: GameDriver) -> Dict[str, Any]:
    data = map_loader.get_preset_map("seafarers_simple_1")
    data["rules"] = dict(data.get("rules", {}), enable_move_ship=True)
    g = engine_rules.build_game(seed=driver.seed, max_players=2, size=62.0,
                               map_data=data, map_id="seafarers_simple_1")
    driver.replace_game(g)
    run_coastal_setup(driver, pid=0)
    driver.ensure_resources(0, COST["ship"])
    driver.begin_turn(0)

    available = [e for e in sorted(g.edges) if engine_rules.can_place_ship(g, 0, e)]
    if len(available) < 2:
        driver.fail("coastal setup does not preserve two legal ship placements")
    ship_edge = available[0]
    driver.do({"type": "build_ship", "pid": 0, "eid": list(ship_edge)})
    targets = [e for e in sorted(g.edges)
               if engine_rules.can_place_ship(g, 0, e, excluded_edge=ship_edge)]
    if not targets:
        driver.fail("no independently connected target for moving ship")
    target = targets[0]
    command = {"type": "move_ship", "pid": 0,
               "from_eid": list(ship_edge), "to_eid": list(target)}
    driver.reject(command, error="illegal", message="Cannot move a ship built this turn")

    # The age restriction expires through the real intervening turns, not
    # by editing ships_built_this_turn, turn or rolled in a fixture.
    driver.finish_turn()
    driver.advance_to(0)
    driver.begin_turn(0)
    if ship_edge in g.ships_built_this_turn or g.ship_moved_this_turn:
        driver.fail("ship turn history did not reset on actual End Turn")
    before_hand, before_bank = dict(g.players[0].res), dict(g.bank)
    driver.do(command)
    if ship_edge in g.occupied_ships:
        driver.fail("ship not moved from origin")
    if g.occupied_ships.get(target) != 0:
        driver.fail("ship not moved to target with original ownership")
    if g.players[0].res != before_hand or g.bank != before_bank:
        driver.fail("moving a ship incorrectly charged resources")
    if not g.ship_moved_this_turn:
        driver.fail("accepted movement did not consume the per-turn entitlement")
    driver.reject({"type": "move_ship", "pid": 0,
                   "from_eid": list(target), "to_eid": list(ship_edge)},
                  error="illegal", message="Ship already moved this turn")
    return {"steps": driver.steps, "summary": driver.snapshot()}
