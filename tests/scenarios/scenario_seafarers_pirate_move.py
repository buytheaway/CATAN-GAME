from __future__ import annotations

from typing import Any, Dict, Tuple

from app.engine import maps as map_loader
from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver


def _edge_has_sea(g, e: Tuple[int, int]) -> bool:
    for ti in g.edge_adj_hexes.get(e, []):
        if g.tiles[ti].terrain == "sea":
            return True
    return False


def _edge_is_sea_only(g, e: Tuple[int, int]) -> bool:
    adj = g.edge_adj_hexes.get(e, [])
    if not adj:
        return False
    return all(g.tiles[ti].terrain == "sea" for ti in adj)


def _vertex_has_sea_edge(g, vid: int) -> bool:
    for e in g.edges:
        if vid not in e:
            continue
        if _edge_has_sea(g, e):
            return True
    return False


def _vertex_has_setup_road(g, vid: int) -> bool:
    for e in g.edges:
        if vid not in e:
            continue
        if not _edge_is_sea_only(g, e):
            return True
    return False


def run(driver: GameDriver) -> Dict[str, Any]:
    base = map_loader.get_preset_map("seafarers_simple_1")
    data = dict(base)
    rules = dict(base.get("rules", {}))
    rules["enable_pirate"] = True
    data["rules"] = rules

    g = engine_rules.build_game(seed=driver.seed, max_players=2, size=62.0, map_data=data, map_id="seafarers_simple_1")
    driver.replace_game(g)

    sea_vid = None
    for vid in sorted(g.vertices.keys()):
        if not engine_rules.can_place_settlement(g, 0, vid, require_road=False):
            continue
        if _vertex_has_sea_edge(g, vid) and _vertex_has_setup_road(g, vid):
            sea_vid = vid
            break
    if sea_vid is None:
        driver.fail("no legal sea-adjacent settlement", kind="assertion")

    used_sea = False
    for _ in range(len(g.setup_order)):
        pid = g.setup_order[g.setup_idx]
        if pid == 1 and not used_sea:
            vid = sea_vid
            used_sea = True
        else:
            vids = driver.legal_settlement_vertices(pid, require_road=False)
            if not vids:
                driver.fail("no legal settlement during setup", kind="assertion")
            vid = vids[0]
        res = driver.do({"type": "place_settlement", "pid": pid, "vid": vid, "setup": True})
        if not res.get("ok"):
            driver.fail("setup settlement failed", kind="assertion", details=res)

        anchor = int(g.setup_anchor_vid) if g.setup_anchor_vid is not None else vid
        edges = driver.legal_road_edges(pid, must_touch_vid=anchor)
        if not edges:
            driver.fail("no legal road during setup", kind="assertion")
        e = edges[0]
        res = driver.do({"type": "place_road", "pid": pid, "eid": [e[0], e[1]], "setup": True})
        if not res.get("ok"):
            driver.fail("setup road failed", kind="assertion", details=res)

    g.phase = "main"
    g.turn = 1
    g.rolled = False

    driver.do({"type": "grant_resources", "pid": 1, "res": {"wood": 2, "sheep": 1}})

    ship_edge = None
    for e in sorted(g.edges):
        if engine_rules.can_place_ship(g, 1, e):
            ship_edge = e
            break
    if ship_edge is None:
        driver.fail("no legal ship edge found", kind="assertion")

    res = driver.do({"type": "build_ship", "pid": 1, "eid": [ship_edge[0], ship_edge[1]]})
    if not res.get("ok"):
        driver.fail("build_ship failed", kind="assertion", details=res)

    # ensure victim has resources to steal
    if sum(g.players[1].res.values()) <= 0:
        driver.fail("victim has no resources", kind="assertion")

    # pick a sea tile adjacent to the ship
    pirate_tile = None
    for ti in g.edge_adj_hexes.get(ship_edge, []):
        if g.tiles[ti].terrain == "sea":
            pirate_tile = ti
            break
    if pirate_tile is None:
        driver.fail("no sea tile adjacent to ship", kind="assertion")
    if g.pirate_tile is not None and pirate_tile == int(g.pirate_tile):
        # pick another sea tile if possible
        for idx, t in enumerate(g.tiles):
            if t.terrain == "sea" and idx != int(g.pirate_tile):
                pirate_tile = idx
                break

    g.turn = 0
    before_thief = sum(g.players[0].res.values())
    before_victim = sum(g.players[1].res.values())
    res = driver.do({"type": "move_pirate", "pid": 0, "tile": pirate_tile, "victim": 1})
    if not res.get("ok"):
        driver.fail("move_pirate failed", kind="assertion", details=res)
    after_thief = sum(g.players[0].res.values())
    after_victim = sum(g.players[1].res.values())
    if after_thief != before_thief + 1:
        driver.fail("pirate steal did not increase thief", kind="assertion")
    if after_victim != before_victim - 1:
        driver.fail("pirate steal did not decrease victim", kind="assertion")

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
