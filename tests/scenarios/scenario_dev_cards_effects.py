from __future__ import annotations

from typing import Any, Dict

from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_setup_snake


def _end_round(driver: GameDriver):
    g = driver.game
    driver.do({"type": "end_turn", "pid": g.turn})
    if len(g.players) > 1:
        driver.do({"type": "end_turn", "pid": g.turn})


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    run_setup_snake(driver)

    g.phase = "main"
    g.turn = 0
    g.rolled = False

    # Monopoly: take from opponent
    driver.do({"type": "grant_resources", "pid": 1, "res": {"wood": 2}})
    g.players[0].dev_cards = [{"type": "monopoly", "new": False}]
    res = driver.do({"type": "play_dev", "pid": 0, "card": "monopoly", "r": "wood"})
    if not res.get("ok"):
        driver.fail("monopoly play failed", kind="assertion", details=res)
    if g.players[1].res.get("wood", 0) != 0:
        driver.fail("monopoly did not remove resources", kind="assertion")
    if g.players[0].res.get("wood", 0) < 2:
        driver.fail("monopoly did not grant resources", kind="assertion")
    _end_round(driver)

    # Year of Plenty: bank -> player
    g.players[0].dev_cards = [{"type": "year_of_plenty", "new": False}]
    before_bank = dict(g.bank)
    res = driver.do({"type": "play_dev", "pid": 0, "card": "year_of_plenty", "a": "ore", "qa": 1, "b": "wheat", "qb": 1})
    if not res.get("ok"):
        driver.fail("year_of_plenty play failed", kind="assertion", details=res)
    if g.bank["ore"] != before_bank["ore"] - 1 or g.bank["wheat"] != before_bank["wheat"] - 1:
        driver.fail("year_of_plenty bank mismatch", kind="assertion")
    _end_round(driver)

    # Road building: free roads without paying
    g.players[0].dev_cards = [{"type": "road_building", "new": False}]
    res = driver.do({"type": "play_dev", "pid": 0, "card": "road_building"})
    if not res.get("ok"):
        driver.fail("road_building play failed", kind="assertion", details=res)
    if g.free_roads.get(0, 0) != 2:
        driver.fail("road_building did not grant free roads", kind="assertion")
    before_res = dict(g.players[0].res)
    edges = driver.legal_road_edges(0)
    if not edges:
        driver.fail("no legal road edges for free road", kind="assertion")
    res = driver.do({"type": "place_road", "pid": 0, "eid": edges[0], "free": True})
    if not res.get("ok"):
        driver.fail("free road placement failed", kind="assertion", details=res)
    edges2 = driver.legal_road_edges(0)
    if not edges2:
        driver.fail("no second legal road edge for free road", kind="assertion")
    res = driver.do({"type": "place_road", "pid": 0, "eid": edges2[0], "free": True})
    if not res.get("ok"):
        driver.fail("second free road placement failed", kind="assertion", details=res)
    if g.players[0].res != before_res:
        driver.fail("free roads should not consume resources", kind="assertion")
    if g.free_roads.get(0, 0) != 0:
        driver.fail("free_roads counter not depleted", kind="assertion")
    _end_round(driver)

    # Knight: pending robber move + knights count
    g.players[0].dev_cards = [{"type": "knight", "new": False}]
    before_knights = g.players[0].knights_played
    res = driver.do({"type": "play_dev", "pid": 0, "card": "knight"})
    if not res.get("ok"):
        driver.fail("knight play failed", kind="assertion", details=res)
    if g.players[0].knights_played != before_knights + 1:
        driver.fail("knight count not incremented", kind="assertion")
    if g.pending_action != "robber_move":
        driver.fail("knight did not trigger robber move", kind="assertion")
    target = 1 if g.robber_tile != 1 else 0
    res = driver.do({"type": "move_robber", "pid": 0, "tile": target})
    if not res.get("ok"):
        driver.fail("robber move after knight failed", kind="assertion", details=res)

    return {"steps": driver.steps, "summary": driver.snapshot()}
