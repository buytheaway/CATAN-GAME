"""Edge-trail scoring, achievement ownership and own-turn victory timing."""
from copy import deepcopy

import pytest

from app.engine import rules
from app.persistence.snapshots import dumps_snapshot, loads_snapshot
from tests.test_seafarers_ships import graph_game


def path(start, length):
    return [(i, i + 1) for i in range(start, start + length)]


@pytest.mark.parametrize("seafarers", [False, True])
def test_road_topologies_count_one_trail_not_connected_pieces(seafarers):
    # Three equal branches: only two branches can belong to one edge trail.
    edges = [(0, 1), (1, 2), (0, 3), (3, 4), (0, 5), (5, 6)]
    g = graph_game(edges, roads=edges)
    g.rules_config.enable_seafarers = seafarers
    assert rules.longest_road_length(g, 0) == 4
    # A loop may revisit its start vertex but never reuse an edge.
    loop = [(0, 1), (1, 2), (0, 2), (0, 3), (3, 4)]
    g = graph_game(loop, roads=loop)
    g.rules_config.enable_seafarers = seafarers
    assert rules.longest_road_length(g, 0) == 5
    # Two loops connected by a bridge cannot repeat that bridge.
    joined = [(0, 1), (1, 2), (0, 2), (2, 3), (3, 4), (4, 5), (3, 5)]
    g = graph_game(joined, roads=joined)
    g.rules_config.enable_seafarers = seafarers
    assert rules.longest_road_length(g, 0) == 7


@pytest.mark.parametrize("level", [None, 1, 2])
def test_mixed_route_transition_only_through_own_settlement_or_city(level):
    edges = path(0, 7)
    buildings = {} if level is None else {3: (0, level)}
    g = graph_game(edges, roads=edges[:3], ships=edges[3:], buildings=buildings)
    before = deepcopy(g)
    assert rules.longest_road_length(g, 0) == (4 if level is None else 7)
    assert g == before
    g.rules_config.enable_seafarers = False
    assert rules.longest_road_length(g, 0) == 3


@pytest.mark.parametrize("kind", ["road", "ship", "mixed"])
@pytest.mark.parametrize("level", [1, 2])
def test_opponent_building_splits_route_for_each_piece_kind(kind, level):
    edges = path(0, 6)
    roads = edges if kind == "road" else [] if kind == "ship" else edges[:3]
    ships = edges if kind == "ship" else [] if kind == "road" else edges[3:]
    g = graph_game(edges, roads=roads, ships=ships, buildings={3: (1, level)})
    assert rules.longest_road_length(g, 0) == 3
    g.occupied_v[3] = (0, level)
    assert rules.longest_road_length(g, 0) == 6


@pytest.mark.parametrize("seafarers", [False, True])
def test_qualifying_tie_retains_holder_then_transfer_and_loss_are_idempotent(seafarers):
    a, b = path(0, 6), path(20, 7)
    g = graph_game(a + b, roads=a)
    g.rules_config.enable_seafarers = seafarers
    rules.update_longest_road(g)
    assert (g.longest_road_owner, g.longest_road_len) == (0, 6)
    assert [p.vp for p in g.players] == [2, 0]
    g.occupied_e.update({edge: 1 for edge in b[:6]})
    rules.update_longest_road(g)
    assert g.longest_road_owner == 0 and [p.vp for p in g.players] == [2, 0]
    g.occupied_e[b[6]] = 1
    rules.update_longest_road(g)
    assert (g.longest_road_owner, g.longest_road_len) == (1, 7)
    assert [p.vp for p in g.players] == [0, 2]
    before = deepcopy(g)
    rules.update_longest_road(g)
    assert g == before
    g.occupied_v[23] = (0, 1)
    rules.update_longest_road(g)
    assert g.longest_road_owner == 0 and [p.vp for p in g.players] == [2, 0]
    g.occupied_v[3] = (1, 1)
    rules.update_longest_road(g)
    assert g.longest_road_owner is None and [p.vp for p in g.players] == [0, 0]


@pytest.mark.parametrize("seafarers", [False, True])
def test_tie_without_qualifying_holder_has_no_award(seafarers):
    a, b = path(0, 5), path(20, 5)
    g = graph_game(a + b, roads=a)
    g.rules_config.enable_seafarers = seafarers
    g.occupied_e.update({e: 1 for e in b})
    rules.update_longest_road(g)
    assert g.longest_road_owner is None and [p.vp for p in g.players] == [0, 0]


def test_ship_build_updates_mixed_route_vp_and_active_player_victory():
    edges = path(0, 5)
    g = graph_game(edges, roads=edges[:2], ships=edges[2:4], buildings={2: (0, 1)})
    g.players[0].vp, g.rules_config.target_vp = 8, 10
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": [4, 5]})
    assert (g.longest_road_owner, g.longest_road_len) == (0, 5)
    assert g.players[0].vp == 10 and g.game_over and g.winner_pid == 0
    restored = loads_snapshot(dumps_snapshot(g))
    assert restored == g and restored.ships_built_this_turn == {(4, 5)}


def test_moving_ship_recalculates_only_final_route_and_retains_tied_holder():
    a, b = path(0, 5), path(20, 5)
    g = graph_game(a + b + [(0, 8)], ships=a, buildings={0: (0, 1)})
    rules.update_longest_road(g)
    g.occupied_e.update({edge: 1 for edge in b})
    rules.update_longest_road(g)
    rules.apply_cmd(g, 0, {"type": "move_ship", "from_eid": [4, 5], "to_eid": [0, 8]})
    assert (g.longest_road_owner, g.longest_road_len) == (0, 5)
    assert [p.vp for p in g.players] == [2, 0]
    assert g.ship_moved_this_turn


@pytest.mark.parametrize("seafarers", [False, True])
def test_route_interruption_transfers_award_but_opponent_wins_only_on_own_turn(seafarers):
    a, b = path(0, 6), path(20, 5)
    g = graph_game(a + b, roads=a)
    g.rules_config.enable_seafarers = seafarers
    g.occupied_e.update({edge: 1 for edge in b})
    g.players[1].vp, g.rules_config.target_vp = 8, 10
    rules.update_longest_road(g)
    # An own settlement does not interrupt our route. Use an accepted opponent
    # settlement placed during that opponent's active turn to split P0's road.
    g.turn = 1
    rules.apply_cmd(g, 1, {"type": "grant_resources", "res": {r: 6 for r in g.bank}})
    g.occupied_e[(2, 3)] = 1
    rules.apply_cmd(g, 1, {"type": "place_settlement", "vid": 3})
    assert g.longest_road_owner == 1 and g.game_over and g.winner_pid == 1

    # P0's move transfers the award to waiting P1. Their 10 VP are deferred.
    if seafarers:
        g = graph_game(a + b + [(20, 26)], ships=a, buildings={0: (0, 1), 20: (0, 1)})
        g.occupied_e.update({edge: 1 for edge in b})
        g.players[1].vp, g.rules_config.target_vp = 8, 10
        rules.update_longest_road(g)
        rules.apply_cmd(g, 0, {"type": "move_ship", "from_eid": [5, 6], "to_eid": [20, 26]})
        assert g.longest_road_owner == 0  # Remaining 5 ties: incumbent retains.
        # Split the existing route through an actual opponent settlement.
        g.occupied_v[3] = (1, 1)
        rules.update_longest_road(g)
    else:
        g = graph_game(a + b, roads=a)
        g.rules_config.enable_seafarers = False
        g.occupied_e.update({edge: 1 for edge in b})
        g.players[1].vp, g.rules_config.target_vp = 8, 10
        rules.update_longest_road(g)
        g.occupied_v[3] = (1, 1)
        rules.update_longest_road(g)
    rules.check_win(g)
    assert g.longest_road_owner == 1 and g.players[1].vp == 10 and not g.game_over
    rules.apply_cmd(g, 0, {"type": "end_turn"})
    assert g.turn == 1 and not g.rolled and g.game_over and g.winner_pid == 1


def test_ship_movement_transfer_never_awards_an_off_turn_victory():
    a, b = path(0, 5), path(20, 5)
    g = graph_game(a + b + [(20, 26)], ships=a, buildings={0: (0, 1), 20: (0, 1)})
    rules.update_longest_road(g)
    g.occupied_e.update({edge: 1 for edge in b})
    g.players[1].vp, g.rules_config.target_vp = 8, 10
    rules.apply_cmd(g, 0, {"type": "move_ship", "from_eid": [4, 5], "to_eid": [20, 26]})
    assert g.longest_road_owner == 1 and g.players[1].vp == 10
    assert not g.game_over and g.winner_pid is None
    rules.apply_cmd(g, 0, {"type": "end_turn"})
    assert g.game_over and g.winner_pid == 1
