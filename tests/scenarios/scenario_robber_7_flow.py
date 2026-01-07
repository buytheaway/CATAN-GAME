from __future__ import annotations

from typing import Any, Dict

from app.engine.state import TERRAIN_TO_RES
from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_setup_snake


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    run_setup_snake(driver)

    g.phase = "main"
    g.turn = 0
    g.rolled = False

    # grant resources to force discard
    driver.do({"type": "grant_resources", "pid": 0, "res": {"wood": 4, "brick": 4}})
    driver.do({"type": "grant_resources", "pid": 1, "res": {"wheat": 4, "sheep": 4}})

    before_sizes = [sum(p.res.values()) for p in g.players]
    res = driver.do({"type": "roll", "pid": 0, "roll": 7})
    if not res.get("ok"):
        driver.fail("roll 7 failed", kind="assertion", details=res)

    if g.pending_action != "discard":
        driver.fail("discard should be pending after roll 7", kind="assertion", details={"pending": g.pending_action})

    def _plan_discard(pid: int, need: int) -> Dict[str, int]:
        pres = g.players[pid].res
        plan = {r: 0 for r in pres.keys()}
        remaining = need
        for r in sorted(pres.keys()):
            if remaining <= 0:
                break
            take = min(pres[r], remaining)
            if take > 0:
                plan[r] = take
                remaining -= take
        return plan

    for pid in range(len(g.players)):
        need = before_sizes[pid] // 2 if before_sizes[pid] > 7 else 0
        if need <= 0:
            continue
        discards = _plan_discard(pid, need)
        res = driver.do({"type": "discard", "pid": pid, "discards": discards})
        if not res.get("ok"):
            driver.fail("discard failed", kind="assertion", details=res)

    if g.pending_action != "robber_move":
        driver.fail("robber move not pending after discards", kind="assertion", details={"pending": g.pending_action})

    # pick a tile adjacent to player 1 to test stealing
    target_tile = None
    for vid, (owner, _lvl) in g.occupied_v.items():
        if owner != 1:
            continue
        for ti in g.vertex_adj_hexes.get(vid, []):
            if ti != g.robber_tile:
                target_tile = ti
                break
        if target_tile is not None:
            break
    if target_tile is None:
        driver.fail("no victim tile for robber", kind="assertion")

    before_p0 = g.players[0].res.copy()
    before_p1 = g.players[1].res.copy()
    res = driver.do({"type": "move_robber", "pid": 0, "tile": target_tile, "victim": 1})
    if not res.get("ok"):
        driver.fail("move robber failed", kind="assertion", details=res)

    # verify one resource moved if victim had any
    if sum(before_p1.values()) > 0:
        delta_p0 = sum(g.players[0].res.values()) - sum(before_p0.values())
        delta_p1 = sum(g.players[1].res.values()) - sum(before_p1.values())
        if not (delta_p0 == 1 and delta_p1 == -1):
            driver.fail("robber steal mismatch", kind="assertion", details={
                "delta_p0": delta_p0,
                "delta_p1": delta_p1,
            })

    # ensure robber blocks production on target tile
    roll = g.tiles[target_tile].number
    if roll is not None:
        g.rolled = False
        g.last_roll = None
        before = [p.res.copy() for p in g.players]
        res = driver.do({"type": "roll", "pid": 0, "roll": int(roll)})
        if not res.get("ok"):
            driver.fail("roll after robber failed", kind="assertion", details=res)
        # any adjacent settlements on that tile should not gain
        for vid, (owner, level) in g.occupied_v.items():
            if target_tile not in g.vertex_adj_hexes.get(vid, []):
                continue
            res_name = TERRAIN_TO_RES.get(g.tiles[target_tile].terrain)
            if not res_name:
                continue
            if g.players[owner].res[res_name] != before[owner][res_name]:
                driver.fail("robber did not block production", kind="assertion", details={
                    "pid": owner,
                    "res": res_name,
                    "before": before[owner][res_name],
                    "after": g.players[owner].res[res_name],
                })

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
