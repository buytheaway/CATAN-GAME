from __future__ import annotations

from typing import Any, Dict

from app.engine.rules import COST
from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_setup_snake


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    run_setup_snake(driver)
    checked_new_knight = False

    # Draw real cards and check a new Knight immediately: later funding may
    # legally end its purchase turn, so cannot defer this assertion.
    required = {"victory_point", "knight", "monopoly"}
    while not required.issubset({card["type"] for card in g.players[0].dev_cards}):
        if not g.dev_deck:
            driver.fail("real deck exhausted before restriction fixture was ready")
        driver.ensure_resources(0, COST["dev"])
        before_vp = g.players[0].vp
        result = driver.do({"type": "buy_dev", "pid": 0})
        card = result.get("card")
        if g.players[0].vp != before_vp + int(card == "victory_point"):
            driver.fail("development purchase VP mismatch", details={"card": card})
        if card == "victory_point":
            driver.reject({"type": "play_dev", "pid": 0, "card": "victory_point"},
                          error="illegal", message="Victory Point cards are passive")
        if card == "knight" and not checked_new_knight:
            driver.reject({"type": "play_dev", "pid": 0, "card": "knight"},
                          error="illegal", message="Cannot play this card now (new or missing)")
            checked_new_knight = True

    if not checked_new_knight:
        driver.fail("new Knight rejection was not exercised")
    driver.finish_turn()
    driver.advance_to(0)
    driver.begin_turn(0)
    driver.do({"type": "play_dev", "pid": 0, "card": "knight"})
    driver.resolve_pending()
    driver.reject({"type": "play_dev", "pid": 0, "card": "monopoly", "r": "wood"},
                  error="illegal", message="Already played a dev card this turn")

    return {"steps": driver.steps, "summary": driver.snapshot()}
