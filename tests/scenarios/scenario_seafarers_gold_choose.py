from __future__ import annotations

from typing import Any, Dict

from app.engine import maps as map_loader
from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver


def run(driver: GameDriver) -> Dict[str, Any]:
    base = map_loader.get_preset_map("base_standard")
    data = dict(base)
    tiles = [dict(t) for t in base.get("tiles", [])]
    if not tiles:
        driver.fail("no tiles in base map", kind="assertion")
    tiles[0] = dict(tiles[0])
    tiles[0]["terrain"] = "gold"
    tiles[0]["number"] = 6
    data["tiles"] = tiles
    rules = dict(base.get("rules", {}))
    rules["enable_gold"] = True
    data["rules"] = rules

    g = engine_rules.build_game(seed=driver.seed, max_players=2, size=62.0, map_data=data, map_id="gold_test")
    driver.replace_game(g)

    gold_vid = None
    for vid in sorted(g.vertices.keys()):
        if 0 not in g.vertex_adj_hexes.get(vid, []):
            continue
        if not engine_rules.can_place_settlement(g, 0, vid, require_road=False):
            continue
        gold_vid = vid
        break

    if gold_vid is None:
        driver.fail("no legal gold-adjacent settlement", kind="assertion")

    used_gold = False
    for _ in range(len(g.setup_order)):
        pid = g.setup_order[g.setup_idx]
        if pid == 0 and not used_gold:
            vid = gold_vid
            used_gold = True
        else:
            vids = driver.legal_settlement_vertices(pid, require_road=False)
            if not vids:
                driver.fail("no legal settlement during setup", kind="assertion")
            vid = vids[0]
        res = driver.do({"type": "place_settlement", "pid": pid, "vid": vid, "setup": True})
        if not res.get("ok"):
            driver.fail("setup settlement failed", kind="assertion", details=res)

        anchor = int(g.setup_anchor_vid) if g.setup_anchor_vid is not None else vid
        edges = driver.legal_road_edges(pid, must_touch_vid=anchor)
        if not edges:
            driver.fail("no legal road during setup", kind="assertion")
        e = edges[0]
        res = driver.do({"type": "place_road", "pid": pid, "eid": [e[0], e[1]], "setup": True})
        if not res.get("ok"):
            driver.fail("setup road failed", kind="assertion", details=res)

    g.phase = "main"
    g.turn = 0
    g.rolled = False

    res = driver.do({"type": "roll", "pid": 0, "roll": 6})
    if not res.get("ok"):
        driver.fail("roll failed", kind="assertion", details=res)
    if g.pending_action != "choose_gold":
        driver.fail("gold pending not triggered", kind="assertion", details={"pending": g.pending_action})
    need = int(g.pending_gold.get(0, 0))
    if need <= 0:
        driver.fail("no gold pending for player", kind="assertion")

    before_bank = int(g.bank.get("wood", 0))
    before_player = int(g.players[0].res.get("wood", 0))
    res = driver.do({"type": "choose_gold", "pid": 0, "res": "wood", "qty": need})
    if not res.get("ok"):
        driver.fail("choose_gold failed", kind="assertion", details=res)
    if int(g.players[0].res.get("wood", 0)) != before_player + need:
        driver.fail("player gold gain mismatch", kind="assertion")
    if int(g.bank.get("wood", 0)) != before_bank - need:
        driver.fail("bank gold spend mismatch", kind="assertion")

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
