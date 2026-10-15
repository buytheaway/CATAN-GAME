from __future__ import annotations

from typing import Any, Dict

from app.engine import maps as map_loader
from app.engine import rules as engine_rules
from app.engine.state import RESOURCES
from tests.harness.engine import GameDriver
from tests.scenarios.utils import run_coastal_setup


def run(driver: GameDriver) -> Dict[str, Any]:
    data = map_loader.get_preset_map("seafarers_simple_1")
    data["rules"] = dict(data.get("rules", {}), enable_pirate=True)
    g = engine_rules.build_game(seed=driver.seed, max_players=2, size=62.0,
                               map_data=data, map_id="seafarers_simple_1")
    driver.replace_game(g)
    run_coastal_setup(driver, pid=1)
    # Actual setup/production and ordinary paid construction create the
    # victim's shipping connection. The current pirate is never teleported.
    driver.ensure_resources(1, {"wood": 2, "sheep": 1})
    driver.begin_turn(1)
    available = [e for e in sorted(g.edges) if engine_rules.can_place_ship(g, 1, e)]
    if not available:
        driver.fail("no legal ship edge after unblocked coastal setup")
    ship_edge = available[0]
    driver.do({"type": "build_ship", "pid": 1, "eid": list(ship_edge)})
    if g.occupied_ships.get(ship_edge) != 1:
        driver.fail("victim ship missing after accepted paid placement")
    pirate_tiles = [ti for ti in sorted(g.edge_adj_hexes.get(ship_edge, []))
                    if g.tiles[ti].terrain == "sea" and ti != g.pirate_tile]
    if not pirate_tiles:
        driver.fail("victim ship has no different adjacent sea target")
    pirate_tile = pirate_tiles[0]
    blocked_edges = [e for e in sorted(g.edges)
                     if pirate_tile in g.edge_adj_hexes.get(e, [])
                     and engine_rules.can_place_ship(g, 1, e)]
    if not blocked_edges:
        driver.fail("pirate fixture lacks a free connected edge to test blocking")

    driver.finish_turn()
    driver.advance_to(0)
    # Seven establishes the authoritative figure-choice obligation. Discard
    # commands are resolved normally, leaving the pirate move for this test.
    driver.do({"type": "roll", "pid": 0, "roll": 7})
    if g.pending_action == "discard":
        for pid, required in sorted(g.discard_required.items()):
            remaining, discards = required, {}
            for resource in RESOURCES:
                quantity = min(remaining, g.players[pid].res[resource])
                if quantity:
                    discards[resource] = quantity
                    remaining -= quantity
            if remaining:
                driver.fail("required discard exceeds actual fixture hand")
            driver.do({"type": "discard", "pid": pid, "discards": discards})
    if g.pending_action != "robber_move" or g.pending_pid != 0:
        driver.fail("Seven did not establish the current player's pirate choice")
    if 1 not in engine_rules._victims_for_pirate_tile(g, pirate_tile, 0):
        driver.fail("connected victim not eligible after legitimate discards")
    before_thief = sum(g.players[0].res.values())
    before_victim = sum(g.players[1].res.values())
    before_bank = dict(g.bank)
    driver.do({"type": "move_pirate", "pid": 0, "tile": pirate_tile, "victim": 1})
    if sum(g.players[0].res.values()) != before_thief + 1:
        driver.fail("pirate steal did not increase thief")
    if sum(g.players[1].res.values()) != before_victim - 1:
        driver.fail("pirate steal did not decrease victim")
    if g.bank != before_bank or g.pirate_tile != pirate_tile:
        driver.fail("pirate movement changed bank or failed to move the figure")
    if g.pending_action is not None or g.pending_pid is not None:
        driver.fail("accepted pirate move did not clear the mandatory choice")
    if any(engine_rules.can_place_ship(g, 1, e) for e in blocked_edges):
        driver.fail("pirate did not block previously legal adjacent ship edges")
    driver.reject({"type": "move_pirate", "pid": 0, "tile": pirate_tile, "victim": 1},
                  error="illegal", message="No robber/pirate move pending")
    return {"steps": driver.steps, "summary": driver.snapshot()}
