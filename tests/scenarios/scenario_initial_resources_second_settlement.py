from __future__ import annotations

from typing import Any, Dict

from app.engine import rules as engine_rules
from app.engine.state import TERRAIN_TO_RES
from tests.harness.engine import GameDriver


def _pick_settlement_with_resources(driver: GameDriver, pid: int) -> int:
    g = driver.game
    for vid in g.vertices.keys():
        if not engine_rules.can_place_settlement(g, pid, vid, require_road=False):
            continue
        tiles = g.vertex_adj_hexes.get(vid, [])
        for ti in tiles:
            res = TERRAIN_TO_RES.get(g.tiles[ti].terrain)
            if res:
                return vid
    raise ValueError("no legal settlement with resources")


def _expected_grant(g, vid: int) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for ti in g.vertex_adj_hexes.get(vid, []):
        res = TERRAIN_TO_RES.get(g.tiles[ti].terrain)
        if not res:
            continue
        if int(g.bank.get(res, 0)) <= 0:
            continue
        out[res] = int(out.get(res, 0)) + 1
    return out


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game

    # first settlement for pid 0: no resources granted
    pid0 = g.setup_order[g.setup_idx]
    vid1 = _pick_settlement_with_resources(driver, pid0)
    before = dict(g.players[pid0].res)
    res = driver.do({"type": "place_settlement", "pid": pid0, "vid": vid1, "setup": True})
    if not res.get("ok"):
        driver.fail("first settlement failed", kind="assertion", details=res)
    after = dict(g.players[pid0].res)
    if after != before:
        driver.fail("resources granted on first settlement", kind="assertion", details={"before": before, "after": after})

    # road for pid0
    edges = driver.legal_road_edges(pid0, must_touch_vid=vid1)
    if not edges:
        driver.fail("no legal road for first settlement", kind="assertion")
    res = driver.do({"type": "place_road", "pid": pid0, "eid": edges[0], "setup": True})
    if not res.get("ok"):
        driver.fail("first road failed", kind="assertion", details=res)

    # advance setup for pid1 twice
    for _ in range(2):
        pid = g.setup_order[g.setup_idx]
        vid = _pick_settlement_with_resources(driver, pid)
        res = driver.do({"type": "place_settlement", "pid": pid, "vid": vid, "setup": True})
        if not res.get("ok"):
            driver.fail("setup settlement failed", kind="assertion", details=res)
        edges = driver.legal_road_edges(pid, must_touch_vid=vid)
        if not edges:
            driver.fail("no legal road in setup", kind="assertion")
        res = driver.do({"type": "place_road", "pid": pid, "eid": edges[0], "setup": True})
        if not res.get("ok"):
            driver.fail("setup road failed", kind="assertion", details=res)

    # second settlement for pid0 should grant resources
    pid = g.setup_order[g.setup_idx]
    if pid != pid0:
        driver.fail("unexpected setup order", kind="assertion", details={"pid": pid})
    vid2 = _pick_settlement_with_resources(driver, pid0)

    # induce bank shortage for one expected resource
    expected = _expected_grant(g, vid2)
    if not expected:
        driver.fail("no expected resources for second settlement", kind="assertion")
    shortage_res = next(iter(expected.keys()))
    g.players[1].res[shortage_res] += g.bank[shortage_res]
    g.bank[shortage_res] = 0
    expected[shortage_res] = 0

    before = dict(g.players[pid0].res)
    bank_before = dict(g.bank)
    res = driver.do({"type": "place_settlement", "pid": pid0, "vid": vid2, "setup": True})
    if not res.get("ok"):
        driver.fail("second settlement failed", kind="assertion", details=res)

    for r, qty in expected.items():
        if g.players[pid0].res[r] != before.get(r, 0) + qty:
            driver.fail("initial resources mismatch", kind="assertion", details={"res": r, "expected": before.get(r, 0) + qty, "actual": g.players[pid0].res[r]})
        if g.bank[r] != bank_before.get(r, 0) - qty:
            driver.fail("bank update mismatch", kind="assertion", details={"res": r, "expected": bank_before.get(r, 0) - qty, "actual": g.bank[r]})
        if g.bank[r] < 0:
            driver.fail("bank went negative", kind="assertion", details={"res": r, "value": g.bank[r]})

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
