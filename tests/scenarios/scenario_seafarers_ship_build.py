from __future__ import annotations

from typing import Any, Dict, Tuple

from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver


def _edge_key(e: Tuple[int, int]) -> Tuple[int, int]:
    a, b = e
    return (a, b) if a < b else (b, a)


def _edge_has_sea(g, e: Tuple[int, int]) -> bool:
    ek = _edge_key(e)
    for ti in g.edge_adj_hexes.get(ek, []):
        if g.tiles[ti].terrain == "sea":
            return True
    return False


def _edge_is_sea_only(g, e: Tuple[int, int]) -> bool:
    ek = _edge_key(e)
    adj = g.edge_adj_hexes.get(ek, [])
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
    g = engine_rules.build_game(seed=driver.seed, max_players=2, size=62.0, map_id="seafarers_simple_1")
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
        if pid == 0 and not used_sea and engine_rules.can_place_settlement(g, pid, sea_vid, require_road=False):
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

    if g.phase != "main":
        driver.fail("setup did not finish", kind="assertion")

    driver.do({"type": "grant_resources", "pid": 0, "res": {"wood": 1, "sheep": 1}})

    ship_edge = None
    for e in sorted(g.edges):
        if engine_rules.can_place_ship(g, 0, e):
            ship_edge = e
            break
    if ship_edge is None:
        driver.fail("no legal ship edge found", kind="assertion")

    res = driver.do({"type": "build_ship", "pid": 0, "eid": [ship_edge[0], ship_edge[1]]})
    if not res.get("ok"):
        driver.fail("build_ship failed", kind="assertion", details=res)

    bad_edge = None
    for e in sorted(g.edges):
        if not _edge_has_sea(g, e):
            bad_edge = e
            break
    if bad_edge is not None:
        res = driver.apply_action({"type": "build_ship", "pid": 0, "eid": [bad_edge[0], bad_edge[1]]})
        if res.get("ok"):
            driver.fail("build_ship should fail on land edge", kind="assertion")

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
