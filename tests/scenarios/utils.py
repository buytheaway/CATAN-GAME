from __future__ import annotations

from typing import List, Tuple

from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver


def run_setup_snake(driver: GameDriver, *, choose_vertex=None, choose_route=None) -> None:
    g = driver.game
    while g.phase == "setup":
        driver.resolve_pending()
        pid = g.setup_order[g.setup_idx]
        legal = driver.legal_settlement_vertices(pid, require_road=False)
        if not legal:
            driver.fail("no legal settlement in setup", kind="assertion")
        chosen_vid = choose_vertex(driver, pid) if choose_vertex else legal[0]
        res = driver.do({"type": "place_settlement", "pid": pid, "vid": chosen_vid, "setup": True})
        if not res.get("ok"):
            driver.fail("setup settlement failed", kind="assertion", details=res)
        driver.resolve_pending()
        if choose_route:
            res = driver.do(choose_route(driver, pid, chosen_vid))
            if not res.get("ok"):
                driver.fail("setup route failed", kind="assertion", details=res)
            continue
        edges = driver.legal_road_edges(pid, must_touch_vid=chosen_vid)
        if not edges:
            driver.fail("no legal road in setup", kind="assertion")
        road = edges[0]
        res = driver.do({"type": "place_road", "pid": pid, "eid": road, "setup": True})
        if not res.get("ok"):
            driver.fail("setup road failed", kind="assertion", details=res)


def pick_port_vertex(driver: GameDriver) -> Tuple[int, str]:
    g = driver.game
    for edge, kind in g.ports:
        for vid in edge:
            if engine_rules.can_place_settlement(g, 0, vid, require_road=False):
                return vid, kind
    raise ValueError("no legal port vertex found")


def run_coastal_setup(driver: GameDriver, *, pid: int, initial_ship: bool = False) -> int:
    """Build a real snake opening with two available, unblocked ship anchors.

    Select from the materialized board on each seed. A separate land road
    leaves both sea edges free; the second settlement supplies missing ship
    resources through normal production. No fixture mutates board or hands.
    """
    from app.engine.state import TERRAIN_TO_RES

    g = driver.game
    plan = {}

    def resources_at(vertex):
        return {TERRAIN_TO_RES.get(g.tiles[ti].terrain)
                for ti in g.vertex_adj_hexes.get(vertex, []) if ti != g.robber_tile}

    def choose_vertex(drv, actor):
        legal = sorted(drv.legal_settlement_vertices(actor, require_road=False))
        if actor != pid:
            return legal[0]
        if not plan:
            candidates = []
            for vertex in legal:
                sea = [e for e in sorted(g.edges) if vertex in e
                       and engine_rules._edge_has_sea(g, e)
                       and e not in g.occupied_e and e not in g.occupied_ships
                       and not engine_rules._edge_blocked_by_pirate(g, e)]
                roads = [e for e in sorted(g.edges) if vertex in e
                         and not engine_rules._edge_has_sea(g, e)
                         and e not in g.occupied_e and e not in g.occupied_ships]
                if len(sea) >= 2 and roads:
                    score = len(resources_at(vertex) & {"wood", "sheep"})
                    candidates.append((-score, vertex, sea, roads))
            if not candidates:
                drv.fail("no legal unblocked coastal opening with reserved sea edges",
                         details={"pid": pid, "seed": drv.seed, "pirate_tile": g.pirate_tile})
            _, vertex, sea, roads = min(candidates, key=lambda item: (item[0], item[1]))
            plan.update(anchor=vertex, sea=sea, road=roads[0])
            return vertex
        produced = set().union(*(resources_at(v) for v, (owner, _) in g.occupied_v.items()
                                 if owner == pid))
        missing = {"wood", "sheep"} - produced
        return min(legal, key=lambda v: (-len(resources_at(v) & missing), v))

    def choose_route(drv, actor, anchor):
        if actor == pid and anchor == plan["anchor"]:
            kind = "build_ship" if initial_ship else "place_road"
            edge = plan["sea"][0] if initial_ship else plan["road"]
        else:
            kind = "place_road"
            edges = sorted(drv.legal_road_edges(actor, must_touch_vid=anchor))
            if not edges:
                drv.fail("no legal anchored road in coastal setup")
            edge = edges[0]
        return {"type": kind, "pid": actor, "eid": list(edge), "setup": True}

    run_setup_snake(driver, choose_vertex=choose_vertex, choose_route=choose_route)
    free = [e for e in plan["sea"] if engine_rules.can_place_ship(g, pid, e)]
    if len(free) < (1 if initial_ship else 2):
        driver.fail("completed setup consumed or blocked its reserved sea edges")
    return plan["anchor"]
