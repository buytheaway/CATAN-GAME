"""Regression checks compare full state, including fields omitted by to_dict."""
from copy import deepcopy

import pytest

from app.engine import rules
from app.engine.state import RESOURCES


def main_game(map_id="base_standard"):
    g = rules.build_game(1, 2, map_id=map_id)
    g.phase = "main"
    g.turn = 0
    g.rolled = True
    return g


def rejected_unchanged(g, cmd, pid=0):
    before = deepcopy(g)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(g, pid, cmd)
    assert g == before


def totals(g):
    return {r: g.bank[r] + sum(p.res[r] for p in g.players) for r in RESOURCES}


@pytest.mark.parametrize("card,extra", [
    ("monopoly", {"r": "gold"}),
    ("year_of_plenty", {"a": "ore", "qa": 10, "b": "ore", "qb": 10}),
    ("year_of_plenty", {"a": "ore", "qa": 1, "b": "ore", "qb": 1}),
    ("year_of_plenty", {"a": "ore", "qa": 1, "b": "gold", "qb": 1}),
    ("year_of_plenty", {"a": "ore", "qa": -1, "b": "wood", "qb": 3}),
    ("year_of_plenty", {"a": "ore", "qa": 1, "b": "wood", "qb": None}),
    ("year_of_plenty", {"a": "ore", "qa": True, "b": "wood", "qb": 1}),
    ("unknown_card", {}),
])
def test_invalid_dev_effect_does_not_consume_card(card, extra):
    g = main_game()
    g.players[0].dev_cards = [{"type": card, "new": False}]
    g.bank["ore"] = 1
    rejected_unchanged(g, {"type": "play_dev", "card": card, **extra})
    # Desktop also invokes this helper directly.
    before = deepcopy(g)
    with pytest.raises(rules.RuleError):
        rules.play_dev(g, 0, card, **extra)
    assert g == before


@pytest.mark.parametrize("card", ["knight", "road_building", "monopoly", "year_of_plenty"])
@pytest.mark.parametrize("restriction", ["new", "used", "pending", "wrong_player"])
def test_dev_restrictions_are_atomic(card, restriction):
    g = main_game()
    g.players[0].dev_cards = [{"type": card, "new": restriction == "new"}]
    if restriction == "used":
        g.dev_played_turn[0] = True
    if restriction == "pending":
        g.pending_action = "robber_move"
        g.pending_pid = 0
    rejected_unchanged(g, {"type": "play_dev", "card": card, "r": "wood",
                           "a": "wood", "qa": 2}, pid=1 if restriction == "wrong_player" else 0)


def test_direct_dev_helpers_cannot_overwrite_pending_action():
    g = main_game()
    rules.apply_cmd(g, 0, {"type": "grant_resources", "res": {"sheep": 1, "wheat": 1, "ore": 1}})
    g.players[0].dev_cards = [{"type": "road_building", "new": False}]
    g.pending_action = "robber_move"
    before = deepcopy(g)
    for operation in (lambda: rules.buy_dev(g, 0), lambda: rules.play_dev(g, 0, "road_building")):
        with pytest.raises(rules.RuleError):
            operation()
        assert g == before


def test_plenty_aggregates_same_resource_and_conserves_supply():
    g = main_game()
    g.bank["ore"] = 2
    g.players[0].dev_cards = [{"type": "year_of_plenty", "new": False}]
    before = totals(g)
    rules.apply_cmd(g, 0, {"type": "play_dev", "card": "year_of_plenty",
                           "a": "ore", "qa": 1, "b": "ore", "qb": 1})
    assert g.bank["ore"] == 0
    assert g.players[0].res["ore"] == 2
    assert totals(g) == before


def test_monopoly_conserves_resources_without_using_bank():
    g = main_game()
    rules.apply_cmd(g, 1, {"type": "grant_resources", "res": {"wood": 4}})
    g.players[0].dev_cards = [{"type": "monopoly", "new": False}]
    before, bank = totals(g), dict(g.bank)
    rules.apply_cmd(g, 0, {"type": "play_dev", "card": "monopoly", "r": "wood"})
    assert g.players[0].res["wood"] == 4
    assert g.players[1].res["wood"] == 0
    assert g.bank == bank and totals(g) == before


def test_grant_fixture_validates_all_resources_before_mutation():
    g = main_game()
    g.bank["ore"] = 0
    rejected_unchanged(g, {"type": "grant_resources", "res": {"wood": 1, "ore": 1}})
    rejected_unchanged(g, {"type": "grant_resources", "res": {"wood": 1, "ore": "bad"}})


@pytest.mark.parametrize("ctype", ["place_settlement", "place_road", "upgrade_city", "build_ship", "move_ship"])
@pytest.mark.parametrize("coordinate", [99999, -1, None, True, 1.5, "1"])
def test_invalid_piece_coordinates_are_atomic(ctype, coordinate):
    g = main_game("seafarers_pirate_lanes")
    g.rules_config.enable_move_ship = True
    cmd = {"type": ctype, "vid": coordinate, "eid": [0, coordinate],
           "from_eid": [0, coordinate], "to_eid": [0, coordinate]}
    rejected_unchanged(g, cmd)


def test_setup_cannot_create_vertex_or_edge_outside_map():
    g = rules.build_game(1, 2)
    rejected_unchanged(g, {"type": "place_settlement", "vid": 99999, "setup": True})
    vid = next(v for v in sorted(g.vertices) if rules.can_place_settlement(g, 0, v, False))
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": vid})
    rejected_unchanged(g, {"type": "place_road", "eid": [vid, 99999], "setup": True})
    other = next(v for v in g.vertices if v != vid and tuple(sorted((vid, v))) not in g.edges)
    rejected_unchanged(g, {"type": "place_road", "eid": [vid, other]})
    assert not rules.can_place_road(g, 0, tuple(sorted((vid, other))))


def test_client_setup_flag_cannot_bypass_main_turn_rules():
    g = main_game()
    g.setup_idx = len(g.setup_order)
    rejected_unchanged(g, {"type": "place_settlement", "vid": min(g.vertices), "setup": True})
    rejected_unchanged(g, {"type": "place_road", "eid": list(min(g.edges)), "setup": True})


def test_sea_only_vertices_and_edges_reject_land_pieces():
    g = rules.build_game(1, 2, map_id="seafarers_pirate_lanes")
    vid = next(v for v, adj in g.vertex_adj_hexes.items()
               if adj and all(g.tiles[t].terrain == "sea" for t in adj))
    rejected_unchanged(g, {"type": "place_settlement", "vid": vid})
    e = next(e for e in g.edges if rules._edge_is_sea(g, e))
    assert not rules.can_place_road(g, 0, e)


def test_road_cannot_overlap_ship_or_extend_through_foreign_settlement():
    g = main_game()
    e = min(g.edges)
    g.occupied_v[e[0]] = (0, 1)
    g.occupied_ships[e] = 1
    assert not rules.can_place_road(g, 0, e)
    g.occupied_ships.clear()
    g.occupied_v[e[0]] = (1, 1)
    connected = next(ee for ee in g.edges if e[0] in ee and ee != e)
    g.occupied_e[connected] = 0
    assert not rules.can_place_road(g, 0, e)


@pytest.mark.parametrize("ctype", ["move_robber", "move_pirate"])
@pytest.mark.parametrize("tile", [99999, -1, None, True, 1.5, "1"])
def test_invalid_hex_coordinates_are_atomic(ctype, tile):
    g = main_game("seafarers_pirate_lanes")
    g.pending_action, g.pending_pid = "robber_move", 0
    rejected_unchanged(g, {"type": ctype, "tile": tile})


def test_robber_and_pirate_require_correct_hex_type():
    g = main_game("seafarers_pirate_lanes")
    sea = next(i for i, t in enumerate(g.tiles) if t.terrain == "sea")
    land = next(i for i, t in enumerate(g.tiles) if t.terrain != "sea")
    g.pending_action, g.pending_pid = "robber_move", 0
    rejected_unchanged(g, {"type": "move_pirate", "tile": land})
    rejected_unchanged(g, {"type": "move_robber", "tile": sea})


def test_failed_road_building_placement_preserves_free_roads():
    g = main_game()
    g.players[0].dev_cards = [{"type": "road_building", "new": False}]
    rules.apply_cmd(g, 0, {"type": "play_dev", "card": "road_building"})
    rejected_unchanged(g, {"type": "place_road", "eid": [0, 99999], "free": True})
    assert g.free_roads[0] == 2


@pytest.mark.parametrize("ctype", ["move_robber", "move_pirate"])
@pytest.mark.parametrize("victim", [0, 99999, True, "1"])
def test_invalid_victim_does_not_move_piece_or_steal(ctype, victim):
    g = main_game("seafarers_pirate_lanes")
    sea = ctype == "move_pirate"
    current = g.pirate_tile if sea else g.robber_tile
    tile = next(i for i, t in enumerate(g.tiles) if (t.terrain == "sea") == sea and i != current)
    g.pending_action, g.pending_pid = "robber_move", 0
    rejected_unchanged(g, {"type": ctype, "tile": tile, "victim": victim})


@pytest.mark.parametrize("ctype", ["place_road", "upgrade_city", "place_settlement", "build_ship"])
def test_insufficient_payment_does_not_change_valid_build_location(ctype):
    g = main_game("seafarers_simple_1")
    if ctype == "place_settlement":
        vid = next(v for v in sorted(g.vertices) if rules.can_place_settlement(g, 0, v, False))
        e = next(e for e in g.edges if vid in e)
        g.occupied_e[e] = 0
        cmd = {"type": ctype, "vid": vid}
    elif ctype == "upgrade_city":
        vid = min(g.vertices)
        g.occupied_v[vid] = (0, 1)
        cmd = {"type": ctype, "vid": vid}
    else:
        e = next(e for e in sorted(g.edges) if rules._edge_has_sea(g, e) and not rules._edge_is_sea(g, e))
        g.occupied_v[e[0]] = (0, 1)
        assert (rules.can_place_ship if ctype == "build_ship" else rules.can_place_road)(g, 0, e)
        cmd = {"type": ctype, "eid": list(e)}
    rejected_unchanged(g, cmd)


def test_gold_shortage_and_invalid_quantities_do_not_mutate():
    g = main_game("seafarers_gold_haven")
    g.pending_action, g.pending_pid = "choose_gold", 0
    g.pending_gold, g.pending_gold_queue = {0: 2}, [0]
    g.bank["ore"] = 1
    for qty in (2, 3, 0, -1, None, True):
        rejected_unchanged(g, {"type": "choose_gold", "res": "ore", "qty": qty})
    before = totals(g)
    rules.apply_cmd(g, 0, {"type": "choose_gold", "res": "ore", "qty": 1})
    assert g.bank["ore"] == 0 and totals(g) == before


def test_bank_trade_shortage_is_atomic():
    g = main_game()
    rules.apply_cmd(g, 0, {"type": "grant_resources", "res": {"wood": 8}})
    g.bank["ore"] = 1
    rejected_unchanged(g, {"type": "trade_bank", "give": "wood", "get": "ore", "get_qty": 2})
    before = totals(g)
    rules.apply_cmd(g, 0, {"type": "trade_bank", "give": "wood", "get": "ore", "get_qty": 1})
    assert g.bank["ore"] == 0 and totals(g) == before


def test_insufficient_trade_acceptance_preserves_offer_and_resources():
    g = main_game()
    rules.apply_cmd(g, 0, {"type": "grant_resources", "res": {"wood": 1}})
    rules.apply_cmd(g, 0, {"type": "trade_offer_create", "give": {"wood": 1}, "get": {"ore": 1}})
    rejected_unchanged(g, {"type": "trade_offer_accept", "offer_id": 1}, pid=1)
    rejected_unchanged(g, {"type": "trade_offer_create", "give": {"wood": 1, "ore": -1}, "get": {"brick": 1}})


def test_production_and_initial_resources_do_not_overdraw_bank():
    g = main_game()
    ti = next(i for i, t in enumerate(g.tiles) if t.number and t.terrain in rules.TERRAIN_TO_RES
              and rules.TERRAIN_TO_RES[t.terrain])
    r = rules.TERRAIN_TO_RES[g.tiles[ti].terrain]
    vids = [v for v, adj in g.vertex_adj_hexes.items() if ti in adj]
    g.occupied_v[vids[0]], g.occupied_v[vids[1]] = (0, 2), (1, 2)
    g.bank[r] = 1
    before = totals(g)
    rules.distribute_for_roll(g, g.tiles[ti].number)
    assert min(g.bank.values()) >= 0 and totals(g) == before

    g = rules.build_game(1, 2)
    g.bank = {r: 1 for r in RESOURCES}
    while g.phase == "setup":
        pid = g.turn
        if g.setup_need == "settlement":
            vid = next(v for v in sorted(g.vertices) if rules.can_place_settlement(g, pid, v, False))
            cmd = {"type": "place_settlement", "vid": vid}
        else:
            e = next(e for e in sorted(g.edges) if rules.can_place_road(g, pid, e, g.setup_anchor_vid))
            cmd = {"type": "place_road", "eid": list(e)}
        before = totals(g)
        rules.apply_cmd(g, pid, cmd)
        assert min(g.bank.values()) >= 0 and totals(g) == before


def test_duplicate_discard_is_rejected_without_mutation():
    g = main_game()
    for pid in (0, 1):
        rules.apply_cmd(g, pid, {"type": "grant_resources", "res": {"wood": 8}})
    g.rolled = False
    rules.apply_cmd(g, 0, {"type": "roll", "roll": 7})
    rules.apply_cmd(g, 0, {"type": "discard", "discards": {"wood": 4}})
    rejected_unchanged(g, {"type": "discard", "discards": {"wood": 4}})


@pytest.mark.parametrize("roll", [0, 1, 13, -7, None, True, "7"])
def test_trusted_engine_still_checks_dice_range(roll):
    g = main_game()
    g.rolled = False
    rejected_unchanged(g, {"type": "roll", "roll": roll})
