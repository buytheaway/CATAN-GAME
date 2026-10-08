"""Authoritative Seafarers placement, movement and maritime topology rules."""
from copy import deepcopy

import pytest

from app.engine import rules
from app.engine.legal import board_legal_moves
from app.engine.shipping import is_open_ship
from app.engine.state import BoardState, COST, GameState, PlayerState, RulesConfig, Tile


def graph_game(edges, *, ships=(), roads=(), buildings=None):
    """Small materialized coast graph; occupancy is an established game fixture.

    Land/sea adjacency is explicit so these tests exercise the ordinary command
    executor, not a substitute rules implementation. Resource funding conserves
    the bank plus player hands. Graph positions are immaterial to rule checks.
    """
    edges = {tuple(sorted(edge)) for edge in edges}
    vertices = {vertex: (float(vertex), 0.0) for edge in edges for vertex in edge}
    board = BoardState(
        tiles=[Tile(0, 0, "sea", None, (0.0, 0.0)),
               Tile(1, 0, "forest", 5, (1.0, 0.0)),
               Tile(2, 0, "sea", None, (2.0, 0.0))],
        vertices=vertices, edges=edges,
        vertex_adj_hexes={vertex: [0, 1] for vertex in vertices},
        edge_adj_hexes={edge: [0, 1] for edge in edges},
        occupied_ships={tuple(sorted(edge)): 0 for edge in ships},
        occupied_e={tuple(sorted(edge)): 0 for edge in roads},
        occupied_v=dict(buildings or {}),
    )
    g = GameState(
        seed=1, max_players=2, board=board, phase="main", rolled=True,
        players=[PlayerState(0, "P0"), PlayerState(1, "P1")],
        rules_config=RulesConfig(target_vp=99, enable_seafarers=True,
                                 enable_move_ship=True),
    )
    rules.apply_cmd(g, 0, {"type": "grant_resources", "res": {r: 6 for r in g.bank}})
    return g


def rejected_unchanged(g, command, pid=0):
    before = deepcopy(g)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(g, pid, command)
    assert g == before


def move_command(source, target):
    return {"type": "move_ship", "from_eid": list(source), "to_eid": list(target)}


def quiet_roll(g, pid):
    gold_numbers = {tile.number for tile in g.tiles if tile.terrain == "gold"}
    value = next(value for value in range(2, 13) if value != 7 and value not in gold_numbers)
    rules.apply_cmd(g, pid, {"type": "roll", "roll": value})


def finish_setup_with_gold_choices(g):
    while g.phase == "setup":
        if g.pending_action == "choose_gold":
            resource = next(resource for resource, quantity in g.bank.items() if quantity > 0)
            rules.apply_cmd(g, g.pending_pid, {"type": "choose_gold", "res": resource, "qty": 1})
            continue
        pid = g.turn
        if g.setup_need == "settlement":
            legal = [vertex for vertex in sorted(g.vertices)
                     if rules.can_place_settlement(g, pid, vertex, False)]
            coast = [vertex for vertex in legal
                     if any(g.tiles[tile].terrain == "sea" for tile in g.vertex_adj_hexes[vertex])]
            rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": (coast or legal)[0]})
        else:
            edge = next(edge for edge in sorted(g.edges)
                        if rules.can_place_road(g, pid, edge, g.setup_anchor_vid))
            rules.apply_cmd(g, pid, {"type": "place_road", "eid": list(edge)})


@pytest.mark.parametrize("level", [1, 2])
def test_road_and_ship_transition_requires_own_building(level):
    g = graph_game([(0, 1), (1, 2), (2, 3)], roads=[(0, 1), (1, 2)],
                   buildings={0: (0, 1)})
    rejected_unchanged(g, {"type": "build_ship", "eid": [2, 3]})
    g.occupied_v[2] = (0, level)
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": [2, 3]})
    assert g.occupied_ships[(2, 3)] == 0

    g = graph_game([(0, 1), (1, 2), (2, 3)], ships=[(0, 1), (1, 2)],
                   buildings={0: (0, 1)})
    rejected_unchanged(g, {"type": "place_road", "eid": [2, 3]})
    g.occupied_v[2] = (0, level)
    rules.apply_cmd(g, 0, {"type": "place_road", "eid": [2, 3]})
    assert g.occupied_e[(2, 3)] == 0


def test_foreign_building_blocks_ship_extension_but_other_endpoint_can_connect():
    g = graph_game([(0, 1), (1, 2), (2, 3), (3, 4)],
                   ships=[(0, 1), (1, 2)], buildings={0: (0, 1), 2: (1, 1)})
    rejected_unchanged(g, {"type": "build_ship", "eid": [2, 3]})
    g.occupied_ships[(3, 4)] = 0
    g.occupied_v[4] = (0, 1)
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": [2, 3]})
    assert g.occupied_ships[(2, 3)] == 0


def test_ship_arrival_allows_coastal_settlement_with_cost_and_base_compatibility():
    g = graph_game([(0, 1), (1, 2)], ships=[(0, 1), (1, 2)], buildings={0: (0, 1)})
    base = deepcopy(g)
    base.rules_config.enable_seafarers = False
    rejected_unchanged(base, {"type": "place_settlement", "vid": 2})
    before = deepcopy(g)
    assert 2 in board_legal_moves(g, 0)["settlements"]
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": 2})
    assert g.occupied_v[2] == (0, 1) and g.players[0].vp == before.players[0].vp + 1
    for resource, amount in COST["settlement"].items():
        assert g.players[0].res[resource] == before.players[0].res[resource] - amount
        assert g.bank[resource] == before.bank[resource] + amount


def test_ship_arrival_preserves_land_and_distance_requirements():
    g = graph_game([(0, 1), (1, 2), (2, 3)], ships=[(0, 1), (1, 2)],
                   buildings={0: (0, 1)})
    g.vertex_adj_hexes[2] = [0]
    rejected_unchanged(g, {"type": "place_settlement", "vid": 2})
    g.vertex_adj_hexes[2] = [0, 1]
    g.occupied_v[3] = (1, 1)
    rejected_unchanged(g, {"type": "place_settlement", "vid": 2})


def test_paid_ship_checks_cost_supply_terrain_and_shared_edge_occupancy():
    g = graph_game([(0, 1), (0, 2)], buildings={0: (0, 1)})
    command = {"type": "build_ship", "eid": [0, 1]}
    before = deepcopy(g)
    g.players[0].res["sheep"] = 0
    rejected_unchanged(g, command)
    g = deepcopy(before)
    g.rules_config.max_ships = 0
    rejected_unchanged(g, command)
    g = deepcopy(before)
    g.edge_adj_hexes[(0, 1)] = [1]
    rejected_unchanged(g, command)
    g = deepcopy(before)
    g.occupied_e[(0, 1)] = 1
    rejected_unchanged(g, command)
    g = deepcopy(before)
    rules.apply_cmd(g, 0, command)
    for resource, quantity in COST["ship"].items():
        assert g.players[0].res[resource] == before.players[0].res[resource] - quantity
        assert g.bank[resource] == before.bank[resource] + quantity
    rejected_unchanged(g, {"type": "place_road", "eid": [0, 1]})


def test_setup_ship_replaces_road_at_current_anchor_without_payment_or_turn_age():
    g = rules.build_game(1, 2, map_id="seafarers_gold_haven")
    vertex = next(v for v in sorted(g.vertices)
                  if rules.can_place_settlement(g, 0, v, False) and any(
                      v in edge and any(g.tiles[t].terrain == "sea" for t in g.edge_adj_hexes[edge])
                      and g.pirate_tile not in g.edge_adj_hexes[edge] for edge in g.edges))
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": vertex})
    legal = board_legal_moves(g, 0)
    assert legal["ships"] and all(vertex in edge for edge in legal["ships"])
    before = deepcopy(g)
    edge = legal["ships"][0]
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": edge, "setup": True})
    assert g.occupied_ships[tuple(edge)] == 0
    assert g.bank == before.bank and g.players[0].res == before.players[0].res
    assert g.setup_idx == 1 and g.turn == 1 and g.setup_need == "settlement"
    assert g.setup_anchor_vid is None and g.ships_built_this_turn == set()


def test_setup_ship_cannot_use_another_building_or_bypass_base_rules():
    g = graph_game([(0, 1), (3, 4)], buildings={0: (0, 1), 3: (0, 1)})
    g.phase, g.rolled = "setup", False
    g.setup_order, g.setup_idx = [0, 1, 1, 0], 0
    g.setup_need, g.setup_anchor_vid = "road", 0
    rejected_unchanged(g, {"type": "build_ship", "eid": [3, 4], "setup": True})
    g.rules_config.enable_seafarers = False
    rejected_unchanged(g, {"type": "build_ship", "eid": [0, 1], "setup": True})
    g.rules_config.enable_seafarers = True
    g.setup_need = "settlement"
    rejected_unchanged(g, {"type": "build_ship", "eid": [0, 1], "setup": True})


def test_road_building_can_pay_one_ship_and_one_road_before_roll():
    g = graph_game([(0, 1), (1, 2), (0, 3)], buildings={0: (0, 1)})
    g.rolled = False
    g.players[0].dev_cards = [{"type": "road_building", "new": False}]
    rules.apply_cmd(g, 0, {"type": "play_dev", "card": "road_building"})
    before = deepcopy(g)
    legal = board_legal_moves(g, 0)
    assert legal["road_free"] and [0, 1] in legal["ships"] and g == before
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": [0, 1], "free": True})
    rules.apply_cmd(g, 0, {"type": "place_road", "eid": [0, 3], "free": True})
    assert g.free_roads[0] == 0 and not g.rolled
    assert g.bank == before.bank and g.players[0].res == before.players[0].res
    assert g.ships_built_this_turn == {(0, 1)}
    rejected_unchanged(g, {"type": "build_ship", "eid": [1, 2], "free": True})


def test_rejected_free_ship_preserves_credit_and_end_turn_expires_remainder():
    g = graph_game([(0, 1), (0, 2)], buildings={0: (0, 1)})
    g.players[0].dev_cards = [{"type": "road_building", "new": False}]
    rules.apply_cmd(g, 0, {"type": "play_dev", "card": "road_building"})
    g.occupied_e[(0, 1)] = 1
    rejected_unchanged(g, {"type": "build_ship", "eid": [0, 1], "free": True})
    rejected_unchanged(g, {"type": "build_ship", "eid": [0, 2], "free": 1})
    assert g.free_roads[0] == 2
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": [0, 2], "free": True})
    assert g.free_roads[0] == 1
    rules.apply_cmd(g, 0, {"type": "end_turn"})
    assert g.free_roads[0] == 0 and g.ships_built_this_turn == set()
    assert g.occupied_ships == {(0, 2): 0}


def test_move_can_relocate_to_distant_own_coast_and_projection_matches_executor():
    g = graph_game([(0, 1), (0, 2), (3, 4)], ships=[(0, 1)],
                   buildings={0: (0, 1), 3: (0, 1)})
    before = deepcopy(g)
    legal = board_legal_moves(g, 0)["move_ship"]
    assert [3, 4] in legal["targets"]["0,1"] and g == before
    expected = []
    for edge in sorted(g.edges):
        try:
            rules.apply_cmd(deepcopy(g), 0, move_command((0, 1), edge))
        except rules.RuleError:
            continue
        expected.append(list(edge))
    assert legal["targets"]["0,1"] == expected
    rules.apply_cmd(g, 0, move_command((0, 1), (3, 4)))
    assert g.occupied_ships == {(3, 4): 0} and g.ship_moved_this_turn
    assert g.bank == before.bank and g.players[0].res == before.players[0].res


def test_move_validates_remaining_network_and_allows_retry_after_rejection():
    g = graph_game([(0, 1), (1, 2), (0, 3)], ships=[(0, 1)], buildings={0: (0, 1)})
    rejected_unchanged(g, move_command((0, 1), (1, 2)))
    assert [1, 2] not in board_legal_moves(g, 0)["move_ship"]["targets"]["0,1"]
    rules.apply_cmd(g, 0, move_command((0, 1), (0, 3)))
    assert g.occupied_ships == {(0, 3): 0}


def test_own_road_at_free_ship_end_does_not_close_shipping_route():
    g = graph_game([(0, 1), (1, 2), (0, 3)], ships=[(0, 1)], roads=[(1, 2)],
                   buildings={0: (0, 1)})
    assert is_open_ship(g, 0, (0, 1))
    rules.apply_cmd(g, 0, move_command((0, 1), (0, 3)))
    assert g.occupied_e == {(1, 2): 0} and g.occupied_ships == {(0, 3): 0}


def test_one_move_per_turn_applies_to_same_and_different_ships():
    g = graph_game([(0, 1), (0, 2), (3, 4), (3, 5)], ships=[(0, 1), (3, 4)],
                   buildings={0: (0, 1), 3: (0, 1)})
    rules.apply_cmd(g, 0, move_command((0, 1), (0, 2)))
    rejected_unchanged(g, move_command((0, 2), (0, 1)))
    rejected_unchanged(g, move_command((3, 4), (3, 5)))
    assert board_legal_moves(g, 0)["move_ship"] == {"sources": [], "targets": {}}
    rules.apply_cmd(g, 0, {"type": "end_turn"})
    assert not g.ship_moved_this_turn
    quiet_roll(g, 1)
    rules.apply_cmd(g, 1, {"type": "end_turn"})
    quiet_roll(g, 0)
    rules.apply_cmd(g, 0, move_command((3, 4), (3, 5)))
    assert g.occupied_ships == {(0, 2): 0, (3, 5): 0}


def test_newly_built_ship_ages_through_real_gold_haven_turn_cycle():
    g = rules.build_game(1, 2, map_id="seafarers_gold_haven")
    finish_setup_with_gold_choices(g)
    rules.apply_cmd(g, 0, {"type": "grant_resources", "res": {"wood": 2, "sheep": 2}})
    quiet_roll(g, 0)
    source = board_legal_moves(g, 0)["ships"][0]
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": source})
    target = next(edge for edge in sorted(g.edges)
                  if edge != tuple(source) and rules.can_place_ship(g, 0, edge))
    rejected_unchanged(g, move_command(source, target))
    assert source not in board_legal_moves(g, 0)["move_ship"]["sources"]
    rules.apply_cmd(g, 0, {"type": "end_turn"})
    assert g.ships_built_this_turn == set()
    quiet_roll(g, 1)
    rules.apply_cmd(g, 1, {"type": "end_turn"})
    quiet_roll(g, 0)
    legal = board_legal_moves(g, 0)["move_ship"]
    assert source in legal["sources"]
    destination = legal["targets"][",".join(map(str, source))][0]
    rules.apply_cmd(g, 0, move_command(source, destination))
    assert tuple(source) not in g.occupied_ships and g.occupied_ships[tuple(destination)] == 0


def test_pirate_blocks_ship_source_and_destination_without_spending_move():
    g = graph_game([(0, 1), (0, 2)], ships=[(0, 1)], buildings={0: (0, 1)})
    g.edge_adj_hexes[(0, 2)] = [1, 2]
    g.rules_config.enable_pirate = True
    g.pirate_tile = 0
    command = move_command((0, 1), (0, 2))
    rejected_unchanged(g, command)
    assert board_legal_moves(g, 0)["move_ship"]["sources"] == []
    g.pirate_tile = 2
    rejected_unchanged(g, command)
    g.pirate_tile = None
    rules.apply_cmd(g, 0, command)
    assert g.ship_moved_this_turn and g.occupied_ships == {(0, 2): 0}


def test_foreign_building_does_not_reopen_closed_line_but_open_branch_can_move():
    edges = [(0, 1), (1, 2), (2, 3), (3, 4), (2, 5), (0, 6)]
    g = graph_game(edges, ships=edges[:-1], buildings={0: (0, 1), 4: (0, 2), 2: (1, 1)})
    for source in edges[:4]:
        assert not is_open_ship(g, 0, source)
        rejected_unchanged(g, move_command(source, (0, 6)))
    assert is_open_ship(g, 0, (2, 5))
    rules.apply_cmd(g, 0, move_command((2, 5), (0, 6)))
    assert (2, 5) not in g.occupied_ships and g.occupied_ships[(0, 6)] == 0


def test_unanchored_circle_allows_every_ship_then_only_new_open_ends():
    circle = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (0, 5)]
    g = graph_game(circle + [(8, 9)], ships=circle, buildings={8: (0, 1)})
    assert all(is_open_ship(g, 0, edge) for edge in circle)
    rules.apply_cmd(g, 0, move_command((2, 3), (8, 9)))
    assert is_open_ship(g, 0, (1, 2)) and is_open_ship(g, 0, (3, 4))
    assert not is_open_ship(g, 0, (0, 1))


def test_circle_returning_to_one_own_building_allows_only_bordering_ships():
    circle = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (0, 5)]
    g = graph_game(circle + [(3, 6)], ships=circle, buildings={3: (0, 1), 0: (1, 1)})
    assert {edge for edge in circle if is_open_ship(g, 0, edge)} == {(2, 3), (3, 4)}
    rejected_unchanged(g, move_command((0, 1), (3, 6)))
    rules.apply_cmd(g, 0, move_command((2, 3), (3, 6)))
    assert g.occupied_ships[(3, 6)] == 0


def test_circle_with_two_own_buildings_is_closed_on_both_paths():
    circle = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (0, 5)]
    g = graph_game(circle + [(0, 6)], ships=circle, buildings={0: (0, 1), 3: (0, 2)})
    for edge in circle:
        assert not is_open_ship(g, 0, edge)
        rejected_unchanged(g, move_command(edge, (0, 6)))


def test_circle_attached_by_stem_does_not_make_stem_movable():
    circle = [(1, 2), (2, 3), (3, 4), (1, 4)]
    g = graph_game([(0, 1), *circle], ships=[(0, 1), *circle], buildings={0: (0, 1)})
    assert not is_open_ship(g, 0, (0, 1))
    assert all(is_open_ship(g, 0, edge) for edge in circle)
    g.occupied_v[3] = (0, 1)
    assert not any(is_open_ship(g, 0, edge) for edge in g.occupied_ships)


def test_side_circle_beside_closed_line_remains_open_without_freezing_component():
    closed = [(0, 1), (1, 2), (2, 3), (3, 4)]
    circle = [(5, 6), (6, 7), (7, 8), (5, 8)]
    ships = [*closed, (2, 5), *circle]
    g = graph_game(ships, ships=ships, buildings={0: (0, 1), 4: (0, 1)})
    assert not any(is_open_ship(g, 0, edge) for edge in [*closed, (2, 5)])
    assert all(is_open_ship(g, 0, edge) for edge in circle)
    g.occupied_v[7] = (0, 1)
    assert not any(is_open_ship(g, 0, edge) for edge in ships)
