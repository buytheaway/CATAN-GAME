from __future__ import annotations

from app.engine import maps as map_loader
from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_setup_snake


def run(driver: GameDriver):
    data = dict(map_loader.get_preset_map("base_standard"))
    data["rules"] = {"limits": {"roads": 2, "settlements": 2, "cities": 1}}
    g = engine_rules.build_game(seed=driver.seed, max_players=2, size=62.0, map_data=data)
    driver.replace_game(g)
    run_setup_snake(driver)
    driver.begin_turn(0)

    # Reject a connected third road for its actual limit, not pre-Roll.
    driver.ensure_resources(0, engine_rules.COST["road"])
    edges = driver.legal_road_edges(0)
    if not edges:
        driver.fail("no connected unoccupied road edge to test limit")
    driver.reject({"type": "place_road", "pid": 0, "eid": edges[0]},
                  error="illegal", message="Road limit reached")

    # First city upgrade succeeds at normal cost; second rejects atomically.
    settlements = sorted(vid for vid, (owner, level) in g.occupied_v.items() if owner == 0 and level == 1)
    if len(settlements) != 2:
        driver.fail("setup did not create two own settlements")
    driver.ensure_resources(0, engine_rules.COST["city"])
    before_bank = dict(g.bank)
    before_res = dict(g.players[0].res)
    driver.do({"type": "upgrade_city", "pid": 0, "vid": settlements[0]})
    for resource, quantity in engine_rules.COST["city"].items():
        if g.players[0].res[resource] != before_res[resource] - quantity or g.bank[resource] != before_bank[resource] + quantity:
            driver.fail("first city upgrade cost mismatch", details={"resource": resource})
    driver.ensure_resources(0, engine_rules.COST["city"])
    driver.reject({"type": "upgrade_city", "pid": 0, "vid": settlements[1]},
                  error="illegal", message="City limit reached")
    if g.occupied_v[settlements[0]] != (0, 2) or g.occupied_v[settlements[1]] != (0, 1):
        driver.fail("city limit changed existing pieces")

    return {"summary": driver.snapshot(), "steps": driver.steps}
