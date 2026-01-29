from __future__ import annotations

from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver


def run(driver: GameDriver):
    g = engine_rules.build_game(seed=driver.seed, max_players=2, size=62.0, map_id="base_12vp")
    driver.replace_game(g)

    g.players[0].vp = 11
    engine_rules.check_win(g)
    if g.game_over:
        driver.fail("game ended before target_vp", kind="assertion")

    g.players[0].vp = 12
    engine_rules.check_win(g)
    if not g.game_over or g.winner_pid != 0:
        driver.fail("game did not end at target_vp", kind="assertion", details={"winner": g.winner_pid})

    return {"summary": driver.snapshot(), "steps": driver.steps}
