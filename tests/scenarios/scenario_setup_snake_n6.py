from __future__ import annotations

from typing import Any, Dict

from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver

SEEDS = [1]


def _run_setup(driver: GameDriver, n_players: int) -> None:
    g = engine_rules.build_game(seed=driver.seed, max_players=n_players, size=58.0)
    driver.replace_game(g)

    second_settlement_gain = {pid: False for pid in range(n_players)}

    while g.phase == "setup":
        pid = g.setup_order[g.setup_idx]
        if g.setup_need == "settlement":
            legal = driver.legal_settlement_vertices(pid, require_road=False)
            if not legal:
                driver.fail("no legal settlement in setup", kind="assertion")
            before = sum(g.players[pid].res.values())
            res = driver.do({"type": "place_settlement", "pid": pid, "vid": legal[0], "setup": True})
            if not res.get("ok"):
                driver.fail("setup settlement failed", kind="assertion", details=res)
            count = sum(1 for _vid, (owner, lvl) in g.occupied_v.items() if owner == pid and lvl == 1)
            if count == 2:
                after = sum(g.players[pid].res.values())
                if after <= before:
                    driver.fail("no starting resources after 2nd settlement", kind="assertion", details={"pid": pid})
                second_settlement_gain[pid] = True
        else:
            anchor = g.setup_anchor_vid
            edges = driver.legal_road_edges(pid, must_touch_vid=anchor)
            if not edges:
                driver.fail("no legal road in setup", kind="assertion")
            res = driver.do({"type": "place_road", "pid": pid, "eid": edges[0], "setup": True})
            if not res.get("ok"):
                driver.fail("setup road failed", kind="assertion", details=res)

    for pid, gained in second_settlement_gain.items():
        if not gained:
            driver.fail("missing second settlement resources", kind="assertion", details={"pid": pid})

    current = g.turn
    res = driver.do({"type": "roll", "pid": current, "roll": 6})
    if not res.get("ok"):
        driver.fail("roll failed", kind="assertion", details=res)
    res = driver.do({"type": "end_turn", "pid": current})
    if not res.get("ok"):
        driver.fail("end_turn failed", kind="assertion", details=res)


def run(driver: GameDriver) -> Dict[str, Any]:
    _run_setup(driver, 6)
    return {"steps": driver.steps, "summary": driver.snapshot()}
