from __future__ import annotations

from app.engine import maps as map_loader
from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_setup_snake


def run(driver: GameDriver):
    data = map_loader.get_preset_map("base_standard")
    data = dict(data)
    data["rules"] = {
        "limits": {"roads": 2, "settlements": 2, "cities": 1},
    }
    g = engine_rules.build_game(seed=driver.seed, max_players=2, size=62.0, map_data=data)
    driver.replace_game(g)

    run_setup_snake(driver)

    g.phase = "main"
    g.turn = 0

    # road limit should be reached after setup (2 roads)
    driver.do({"type": "grant_resources", "pid": 0, "res": {"wood": 1, "brick": 1}})
    edges = driver.legal_road_edges(0)
    if not edges:
        driver.fail("no legal road edge to test limit", kind="assertion")
    action = {"type": "place_road", "pid": 0, "eid": edges[0]}
    res = driver.apply_action(action)
    driver.steps.append(dict(action))
    if res.get("ok", True):
        driver.fail("road limit not enforced", kind="assertion")

    # city limit: allow first upgrade, block second
    driver.do({"type": "grant_resources", "pid": 0, "res": {"wheat": 4, "ore": 6}})
    settlements = [vid for vid, (owner, level) in g.occupied_v.items() if owner == 0 and level == 1]
    if len(settlements) < 2:
        driver.fail("not enough settlements for city limit test", kind="assertion")
    res1 = driver.do({"type": "upgrade_city", "pid": 0, "vid": settlements[0]})
    if not res1.get("ok", False):
        driver.fail("first city upgrade failed", kind="assertion", details=res1)
    action = {"type": "upgrade_city", "pid": 0, "vid": settlements[1]}
    res2 = driver.apply_action(action)
    driver.steps.append(dict(action))
    if res2.get("ok", True):
        driver.fail("city limit not enforced", kind="assertion")

    return {"summary": driver.snapshot(), "steps": driver.steps}
