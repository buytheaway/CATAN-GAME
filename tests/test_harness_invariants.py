"""Check the scenario oracle, without repairing or mutating the supplied state."""
from copy import deepcopy

import pytest

from app.engine.state import GameState, PlayerState
from tests.harness.invariants import check_invariants


def army_state(counts, owner, size):
    game = GameState(seed=1, players=[
        PlayerState(pid, f"P{pid}", knights_played=count)
        for pid, count in enumerate(counts)
    ])
    game.largest_army_owner, game.largest_army_size = owner, size
    if owner is not None:
        game.players[owner].vp = 2
    return game


@pytest.mark.parametrize("counts,owner", [((3, 3), 0), ((3, 3), 1), ((4, 4, 4), 2)])
def test_army_oracle_accepts_qualified_incumbent_on_two_and_three_way_ties(counts, owner):
    game = army_state(counts, owner, max(counts))
    before = deepcopy(game)
    assert check_invariants(game) == []
    assert game == before


def test_army_oracle_accepts_unawarded_tie_and_three_knight_minimum():
    for counts, owner, size in (((3, 3), None, 3), ((2, 2), None, 0), ((3, 4), 1, 4)):
        game = army_state(counts, owner, size)
        before = deepcopy(game)
        assert check_invariants(game) == []
        assert game == before


@pytest.mark.parametrize("counts,owner,size", [
    ((2, 2), 0, 2),       # Unqualified holder.
    ((3, 4), 0, 3),       # Challenger strictly exceeds the holder.
    ((3, 2), None, 3),    # A unique qualified leader is missing its award.
    ((4, 4), 1, 3),       # Retained holder with an obsolete achievement counter.
])
def test_army_oracle_still_rejects_invalid_ownership_and_counters(counts, owner, size):
    game = army_state(counts, owner, size)
    before = deepcopy(game)
    failures = check_invariants(game)
    assert [failure["code"] for failure in failures] == ["largest_army"]
    assert game == before


@pytest.mark.parametrize("seafarers,junction,owner,length", [
    (False, True, None, 0),  # Base does not count ships.
    (True, False, None, 0),  # Seafarers still requires an owned junction.
    (True, True, 0, 5),
])
def test_route_oracle_counts_mixed_roads_and_ships_only_through_own_building(
        seafarers, junction, owner, length):
    game = GameState(seed=1, players=[PlayerState(0, "P0"), PlayerState(1, "P1")])
    game.rules_config.enable_seafarers = seafarers
    game.vertices = {vid: (float(vid), 0.0) for vid in range(6)}
    game.edges = {(vid, vid + 1) for vid in range(5)}
    game.occupied_e = {(0, 1): 0, (1, 2): 0}
    game.occupied_ships = {(2, 3): 0, (3, 4): 0, (4, 5): 0}
    game.occupied_v = {2: (0, 1)} if junction else {}
    game.longest_road_owner, game.longest_road_len = owner, length
    before = deepcopy(game)
    assert check_invariants(game) == []
    assert game == before

    if owner is None:
        game.longest_road_owner, game.longest_road_len = 0, 5
    else:
        # Without the player's coastal building, the two kinds do not join.
        game.occupied_v = {}
    failures = check_invariants(game)
    assert [failure["code"] for failure in failures] == ["longest_road"]
    assert failures[0]["details"]["expected_owner"] is None


def test_route_oracle_preserves_a_tied_incumbent_and_rejects_trailing_holder():
    game = GameState(seed=1, players=[PlayerState(0, "P0"), PlayerState(1, "P1")])
    game.vertices = {vid: (float(vid), 0.0) for vid in range(13)}
    game.edges = {(vid, vid + 1) for vid in range(5)} | {(vid, vid + 1) for vid in range(6, 12)}
    game.occupied_e = ({(vid, vid + 1): 0 for vid in range(5)}
                       | {(vid, vid + 1): 1 for vid in range(6, 11)})
    game.longest_road_owner, game.longest_road_len = 1, 5
    before = deepcopy(game)
    assert check_invariants(game) == []
    assert game == before

    # A tie without a holder does not pick a player arbitrarily. Unlike the
    # Army's unawarded tie counter, unawarded route length is recorded as zero.
    game.longest_road_owner, game.longest_road_len = None, 0
    assert check_invariants(game) == []

    game.occupied_e[(11, 12)] = 1
    game.longest_road_owner = 0
    failures = check_invariants(game)
    assert [failure["code"] for failure in failures] == ["longest_road"]
    assert failures[0]["details"]["expected_owner"] == 1
    assert failures[0]["details"]["expected_len"] == 6
