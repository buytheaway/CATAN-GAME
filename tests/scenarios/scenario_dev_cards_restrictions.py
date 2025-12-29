from __future__ import annotations

from typing import Any, Dict

from tests.harness.engine import GameDriver


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    g.phase = "main"
    g.turn = 0
    g.rolled = True

    # control deck: VP then knight
    g.dev_deck = ["knight", "victory_point"]

    # buy VP card and ensure VP increments
    driver.do({"type": "grant_resources", "pid": 0, "res": {"sheep": 1, "wheat": 1, "ore": 1}})
    res = driver.do({"type": "buy_dev", "pid": 0})
    if not res.get("ok"):
        driver.fail("buy dev failed", kind="assertion", details=res)
    if g.players[0].vp < 1:
        driver.fail("victory point dev did not add VP", kind="assertion")

    # cannot play VP card
    action = {"type": "play_dev", "pid": 0, "card": "victory_point"}
    driver.steps.append(dict(action))
    res = driver.apply_action(action)
    if res.get("ok"):
        driver.fail("victory point dev should not be playable", kind="assertion")

    # buy knight (new) and try to play same turn
    driver.do({"type": "grant_resources", "pid": 0, "res": {"sheep": 1, "wheat": 1, "ore": 1}})
    res = driver.do({"type": "buy_dev", "pid": 0})
    if not res.get("ok"):
        driver.fail("buy knight dev failed", kind="assertion", details=res)

    action = {"type": "play_dev", "pid": 0, "card": "knight"}
    driver.steps.append(dict(action))
    res = driver.apply_action(action)
    if res.get("ok"):
        driver.fail("new dev played on same turn", kind="assertion")

    # end turn to clear new flag
    driver.do({"type": "end_turn", "pid": 0})
    driver.do({"type": "end_turn", "pid": 1})

    # now play knight
    res = driver.do({"type": "play_dev", "pid": 0, "card": "knight"})
    if not res.get("ok"):
        driver.fail("playing knight failed after turn", kind="assertion", details=res)
    g.pending_action = None
    g.pending_pid = None

    # only one dev per turn
    g.players[0].dev_cards.append({"type": "monopoly", "new": False})
    action = {"type": "play_dev", "pid": 0, "card": "monopoly", "res": "wood"}
    driver.steps.append(dict(action))
    res = driver.apply_action(action)
    if res.get("ok"):
        driver.fail("multiple devs in a turn allowed", kind="assertion")

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
