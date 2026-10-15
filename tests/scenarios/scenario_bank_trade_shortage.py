from __future__ import annotations

from typing import Any, Dict

from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    # P0 has forest production but no mountain. Only P1 can produce ore,
    # making the final shortage card reachable through normal sole-recipient
    # production without grants, resource edits or a seed-specific vertex ID.
    while g.phase == "setup":
        pid = g.setup_order[g.setup_idx]
        legal = sorted(driver.legal_settlement_vertices(pid, require_road=False))
        if pid == 0:
            legal = [vid for vid in legal
                     if any(g.tiles[ti].terrain == "forest" for ti in g.vertex_adj_hexes[vid])
                     and all(g.tiles[ti].terrain != "mountains" for ti in g.vertex_adj_hexes[vid])]
        elif not any(owner == 1 for owner, _ in g.occupied_v.values()):
            legal = [vid for vid in legal
                     if any(g.tiles[ti].terrain == "mountains" for ti in g.vertex_adj_hexes[vid])]
        if not legal:
            driver.fail("no legal production opening for bank-shortage fixture")
        vid = legal[0]
        driver._accepted({"type": "place_settlement", "pid": pid, "vid": vid, "setup": True})
        edges = sorted(driver.legal_road_edges(pid, must_touch_vid=vid))
        if not edges:
            driver.fail("no anchored road for bank-shortage opening")
        driver._accepted({"type": "place_road", "pid": pid, "eid": edges[0], "setup": True})

    wood_roll = next(g.tiles[ti].number for vid, (pid, _) in g.occupied_v.items() if pid == 0
                     for ti in g.vertex_adj_hexes[vid] if g.tiles[ti].terrain == "forest")
    ore_roll = next(g.tiles[ti].number for vid, (pid, _) in g.occupied_v.items() if pid == 1
                    for ti in g.vertex_adj_hexes[vid] if g.tiles[ti].terrain == "mountains")
    rate = engine_rules.best_trade_rate(g, 0, "wood")
    for _ in range(20):
        if g.players[0].res["wood"] >= rate:
            break
        driver.begin_turn(roll=wood_roll)
        driver.finish_turn()
    if g.players[0].res["wood"] < rate:
        driver.fail("wood production did not fund a normal maritime trade")

    if g.rolled:
        driver.finish_turn()
    for _ in range(20):
        if g.bank["ore"] == 0:
            break
        driver.begin_turn(roll=ore_roll)
        driver.finish_turn()
    if g.bank["ore"] != 0 or g.players[1].res["ore"] != driver.expected_totals["ore"]:
        driver.fail("ordinary production did not drain ore into the sole recipient")
    while g.turn != 0:
        driver.begin_turn(roll=ore_roll)
        driver.finish_turn()
    driver.begin_turn(0, roll=ore_roll)
    if g.players[0].res["wood"] < rate:
        driver.fail("bank-shortage rejection lacks its normal trade payment")
    driver.reject({"type": "trade_bank", "pid": 0, "give": "wood", "get": "ore", "get_qty": 1},
                  error="illegal", message="Bank has not enough resources")

    return {"steps": driver.steps, "summary": driver.snapshot()}
