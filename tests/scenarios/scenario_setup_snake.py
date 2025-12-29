from __future__ import annotations

from typing import Any, Dict

from tests.harness.engine import GameDriver


def run(driver: GameDriver) -> Dict[str, Any]:
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

    if g.phase != "main":
        driver.fail("setup did not end in main phase", kind="assertion", details={"phase": g.phase})

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
