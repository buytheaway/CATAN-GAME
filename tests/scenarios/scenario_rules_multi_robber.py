from __future__ import annotations

from app.engine import rules as engine_rules
from app.engine import to_dict, from_dict
from app.engine.state import TERRAIN_TO_RES
from tests.harness.engine import GameDriver


def _find_vertex_with_unique_roll(g, pid: int):
    for vid in sorted(g.vertices.keys()):
        if not engine_rules.can_place_settlement(g, pid, vid, require_road=False):
            continue
        adj = g.vertex_adj_hexes.get(vid, [])
        for ti in adj:
            t = g.tiles[ti]
            if t.number is None:
                continue
            roll = t.number
            if all(g.tiles[other].number != roll for other in adj if other != ti):
                res = TERRAIN_TO_RES.get(t.terrain)
                if res:
                    return vid, ti, roll, res
    return None


def run(driver: GameDriver):
    g = engine_rules.build_game(seed=driver.seed, max_players=2, size=62.0, map_id="base_20vp_multi_robbers")
    driver.replace_game(g)

    if int(getattr(g.rules_config, "robber_count", 1)) != 2:
        driver.fail("robber_count not applied from rules", kind="assertion")
    if len(getattr(g, "robbers", [])) != 2:
        driver.fail("robbers list length mismatch", kind="assertion")

    found = _find_vertex_with_unique_roll(g, 0)
    if not found:
        driver.fail("no suitable vertex for multi-robber test", kind="assertion")
    vid, tile, roll, res = found

    driver.do({"type": "place_settlement", "pid": 0, "vid": vid, "setup": True})
    g.phase = "main"
    g.turn = 0
    g.rolled = False

    other_tile = tile + 1 if tile + 1 < len(g.tiles) else max(0, tile - 1)
    g.robber_tile = other_tile
    g.robbers = [other_tile, tile]

    before = int(g.players[0].res.get(res, 0))
    driver.do({"type": "roll", "pid": 0, "roll": int(roll)})
    after = int(g.players[0].res.get(res, 0))
    if after != before:
        driver.fail("robber did not block resources from secondary robber", kind="assertion", details={"before": before, "after": after})

    snapshot = to_dict(g)
    g2 = from_dict(snapshot)
    if len(getattr(g2, "robbers", [])) != 2:
        driver.fail("robbers not preserved in serialization", kind="assertion")

    return {"summary": driver.snapshot(), "steps": driver.steps}
