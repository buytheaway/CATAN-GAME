from __future__ import annotations

from typing import Any, Dict

from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_setup_snake


def _plan_discard(res: Dict[str, int], need: int) -> Dict[str, int]:
    plan = {r: 0 for r in res.keys()}
    remaining = need
    for r in sorted(res.keys()):
        if remaining <= 0:
            break
        take = min(res[r], remaining)
        if take > 0:
            plan[r] = take
            remaining -= take
    return plan


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    run_setup_snake(driver)

    g.phase = "main"
    g.turn = 0
    g.rolled = False

    driver.do({"type": "grant_resources", "pid": 0, "res": {"wood": 4, "brick": 4}})
    driver.do({"type": "grant_resources", "pid": 1, "res": {"wheat": 4, "sheep": 4}})

    before_sizes = [sum(p.res.values()) for p in g.players]
    res = driver.do({"type": "roll", "pid": 0, "roll": 7})
    if not res.get("ok"):
        driver.fail("roll 7 failed", kind="assertion", details=res)

    if g.pending_action != "discard":
        driver.fail("discard pending not set", kind="assertion")

    # move_robber should be rejected during discard
    bad = driver.apply_action({"type": "move_robber", "pid": 0, "tile": 1})
    if bad.get("ok"):
        driver.fail("move_robber allowed during discard", kind="assertion")

    # wrong discard sum should be rejected
    need0 = before_sizes[0] // 2
    wrong = _plan_discard(g.players[0].res, max(0, need0 - 1))
    bad = driver.apply_action({"type": "discard", "pid": 0, "discards": wrong})
    if bad.get("ok"):
        driver.fail("wrong discard accepted", kind="assertion")

    # correct discards for all required pids
    before_bank = g.bank.copy()
    total_discards: Dict[str, int] = {r: 0 for r in g.bank.keys()}
    for pid in range(len(g.players)):
        need = before_sizes[pid] // 2 if before_sizes[pid] > 7 else 0
        if need <= 0:
            continue
        plan = _plan_discard(g.players[pid].res, need)
        for r, q in plan.items():
            total_discards[r] += q
        res = driver.do({"type": "discard", "pid": pid, "discards": plan})
        if not res.get("ok"):
            driver.fail("discard failed", kind="assertion", details=res)

    if g.pending_action != "robber_move":
        driver.fail("robber move not pending after discards", kind="assertion")

    for r, q in total_discards.items():
        if g.bank[r] != before_bank[r] + q:
            driver.fail("bank not updated after discard", kind="assertion", details={"res": r, "expected": before_bank[r] + q, "actual": g.bank[r]})

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
