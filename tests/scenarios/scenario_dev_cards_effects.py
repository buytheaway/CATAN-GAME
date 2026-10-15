from __future__ import annotations

from typing import Any, Dict

from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_setup_snake


def _end_round(driver: GameDriver) -> None:
    driver.finish_turn()
    driver.advance_to(0)
    driver.begin_turn(0)


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    run_setup_snake(driver)

    # Real cards from this seed's untouched deck, normal costs, and maturation.
    driver.buy_dev_cards(0, {"monopoly": 1, "year_of_plenty": 1,
                             "road_building": 1, "knight": 1})
    _end_round(driver)

    # Supply the opponent through production/trades, never inventory edits.
    driver.finish_turn()
    driver.ensure_resources(1, {"wood": 2})
    driver.finish_turn()
    driver.advance_to(0)
    driver.begin_turn(0)
    before_wood = g.players[0].res["wood"]
    victim_wood = g.players[1].res["wood"]
    driver.do({"type": "play_dev", "pid": 0, "card": "monopoly", "r": "wood"})
    if g.players[1].res["wood"] != 0 or g.players[0].res["wood"] != before_wood + victim_wood:
        driver.fail("monopoly transfer mismatch", details={"victim_wood": victim_wood})
    _end_round(driver)

    # Year of Plenty transfers exactly two available cards from bank to hand.
    before_bank = dict(g.bank)
    before_res = dict(g.players[0].res)
    driver.do({"type": "play_dev", "pid": 0, "card": "year_of_plenty",
               "a": "ore", "qa": 1, "b": "wheat", "qb": 1})
    for resource in ("ore", "wheat"):
        if g.bank[resource] != before_bank[resource] - 1 or g.players[0].res[resource] != before_res[resource] + 1:
            driver.fail("year_of_plenty transfer mismatch", details={"resource": resource})
    _end_round(driver)

    # Free roads use real legal edges, consume two credits, and preserve hand.
    driver.do({"type": "play_dev", "pid": 0, "card": "road_building"})
    if g.free_roads.get(0, 0) != 2:
        driver.fail("road_building did not grant free roads")
    before_res = dict(g.players[0].res)
    before_roads = len(g.occupied_e)
    for remaining in (1, 0):
        edges = driver.legal_road_edges(0)
        if not edges:
            driver.fail("no legal road edge for free road")
        driver.do({"type": "place_road", "pid": 0, "eid": edges[0], "free": True})
        if g.free_roads.get(0, 0) != remaining:
            driver.fail("free road credit mismatch", details={"remaining": remaining})
    if g.players[0].res != before_res or len(g.occupied_e) != before_roads + 2:
        driver.fail("free roads must preserve resources and create two roads")
    _end_round(driver)

    # Resolve the Knight's real mandatory robber choice.
    before_knights = g.players[0].knights_played
    driver.do({"type": "play_dev", "pid": 0, "card": "knight"})
    if g.players[0].knights_played != before_knights + 1 or g.pending_action != "robber_move":
        driver.fail("knight count/pending mismatch")
    old_robber = g.robber_tile
    driver.resolve_pending()
    if g.pending_action is not None or g.robber_tile == old_robber:
        driver.fail("knight robber choice did not complete")

    return {"steps": driver.steps, "summary": driver.snapshot()}
