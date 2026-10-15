from __future__ import annotations

from typing import Any, Dict

from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_setup_snake


def _play_knight(driver: GameDriver, pid: int) -> None:
    driver.advance_to(pid)
    driver.begin_turn(pid)
    driver.do({"type": "play_dev", "pid": pid, "card": "knight"})
    driver.resolve_pending()


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    run_setup_snake(driver)
    driver.buy_dev_cards(0, {"knight": 3})
    driver.finish_turn()
    driver.advance_to(0)
    base_vp0 = g.players[0].vp

    for count in range(1, 4):
        _play_knight(driver, 0)
        expected_owner = 0 if count == 3 else None
        expected_size = 3 if count == 3 else 0
        if (g.largest_army_owner, g.largest_army_size) != (expected_owner, expected_size):
            driver.fail("largest army minimum/award mismatch", details={"knights": count})
        if g.players[0].vp != base_vp0 + (2 if count == 3 else 0):
            driver.fail("largest army award VP mismatch", details={"knights": count})
        driver.finish_turn()

    driver.buy_dev_cards(1, {"knight": 4})
    driver.finish_turn()
    driver.advance_to(1)
    before_challenge = [player.vp for player in g.players]
    for count in range(1, 5):
        _play_knight(driver, 1)
        if count <= 3:
            if g.largest_army_owner != 0 or g.largest_army_size != 3:
                driver.fail("qualified holder lost army before strict exceed", details={"knights": count})
            if [player.vp for player in g.players] != before_challenge:
                driver.fail("army tie changed VP", details={"knights": count})
        else:
            expected_vp = [before_challenge[0] - 2, before_challenge[1] + 2]
            if (g.largest_army_owner, g.largest_army_size) != (1, 4):
                driver.fail("largest army did not transfer on strict exceed")
            if [player.vp for player in g.players] != expected_vp:
                driver.fail("largest army transfer VP mismatch", details={"expected": expected_vp})
        driver.finish_turn()

    return {"steps": driver.steps, "summary": driver.snapshot()}
