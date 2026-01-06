from __future__ import annotations

from typing import List, Tuple

from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver


def run_setup_snake(driver: GameDriver) -> None:
    g = driver.game
    for pid in g.setup_order:
        legal = driver.legal_settlement_vertices(pid, require_road=False)
        if not legal:
            driver.fail("no legal settlement in setup", kind="assertion")
        chosen_vid = legal[0]
        res = driver.do({"type": "place_settlement", "pid": pid, "vid": chosen_vid, "setup": True})
        if not res.get("ok"):
            driver.fail("setup settlement failed", kind="assertion", details=res)
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
