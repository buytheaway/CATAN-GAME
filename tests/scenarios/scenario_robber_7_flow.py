from __future__ import annotations

from typing import Any, Dict

from app.engine.state import RESOURCES, TERRAIN_TO_RES
from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_setup_snake


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    run_setup_snake(driver)

    # Build both discard-sized hands with recorded production and paid trades.
    # Funding P1 can affect P0's cards during intervening ordinary turns, so
    # check both hands before the controlled Seven rather than assuming them.
    for _ in range(20):
        driver.ensure_resources(0, {"wood": 4, "brick": 4})
        driver.ensure_resources(1, {"wheat": 4, "sheep": 4})
        if all(sum(p.res.values()) > 7 for p in g.players):
            break
    if not all(sum(p.res.values()) > 7 for p in g.players):
        driver.fail("normal production did not prepare both discard-sized hands")
    driver.finish_turn()  # P1 has rolled; P0 now has a fresh unrolled turn.
    if g.turn != 0 or g.rolled:
        driver.fail("Seven fixture did not reach P0's next ordinary turn")

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
            if (ti != g.robber_tile and g.tiles[ti].number is not None
                    and TERRAIN_TO_RES.get(g.tiles[ti].terrain)):
                target_tile = ti
                break
        if target_tile is not None:
            break
    if target_tile is None:
        driver.fail("no victim tile for robber", kind="assertion")

    before_p0 = g.players[0].res.copy()
    before_p1 = g.players[1].res.copy()
    before_bank = dict(g.bank)
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
    if g.robber_tile != target_tile or g.pending_action is not None or g.bank != before_bank:
        driver.fail("robber placement did not complete or theft changed the bank")

    # ensure robber blocks production on target tile
    roll = g.tiles[target_tile].number
    if roll is not None:
        driver.finish_turn()  # A second roll requires the next player's turn.
        before = [p.res.copy() for p in g.players]
        bank_before = dict(g.bank)
        demands = {resource: {} for resource in RESOURCES}
        blocked = set(g.robbers or [g.robber_tile])
        for vid, (owner, level) in g.occupied_v.items():
            for ti in g.vertex_adj_hexes[vid]:
                tile = g.tiles[ti]
                resource = TERRAIN_TO_RES.get(tile.terrain)
                if ti not in blocked and tile.number == roll and resource:
                    demands[resource][owner] = demands[resource].get(owner, 0) + level
        gains = [{resource: 0 for resource in RESOURCES} for _ in g.players]
        for resource, recipients in demands.items():
            available = bank_before[resource]
            if len(recipients) > 1 and sum(recipients.values()) > available:
                continue
            for owner, quantity in recipients.items():
                gains[owner][resource] = min(quantity, available)
        res = driver.do({"type": "roll", "pid": g.turn, "roll": int(roll)})
        if not res.get("ok"):
            driver.fail("roll after robber failed", kind="assertion", details=res)
        # The blocked hex contributes zero, while other matching unblocked
        # hexes still produce under the ordinary aggregate shortage rule.
        for owner, player in enumerate(g.players):
            for resource in RESOURCES:
                expected = before[owner][resource] + gains[owner][resource]
                if player.res[resource] != expected:
                    driver.fail("robber production mismatch", details={"pid": owner, "res": resource,
                                "expected": expected, "actual": player.res[resource], "roll": roll})
        for resource in RESOURCES:
            expected = bank_before[resource] - sum(gain[resource] for gain in gains)
            if g.bank[resource] != expected:
                driver.fail("robber production bank mismatch", details={"res": resource,
                            "expected": expected, "actual": g.bank[resource]})

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
