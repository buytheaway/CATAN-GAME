"""A test-only two-island map exercises real board geometry and commands."""
from collections import deque
from copy import deepcopy

import pytest

from app.engine import rules
from app.engine.legal import board_legal_moves
from app.persistence.snapshots import dumps_snapshot, loads_snapshot


def island_game():
    data = {"version": 1, "name": "s1_two_island_fixture", "tiles": [
        {"q": 0, "r": 0, "terrain": "forest", "number": 5},
        {"q": 1, "r": 0, "terrain": "sea", "number": None},
        {"q": 2, "r": 0, "terrain": "fields", "number": 9}],
        "rules": {"enable_seafarers": True, "enable_move_ship": True}}
    g = rules.build_game(1, 2, map_data=data)
    home = {v for v, adjacent in g.vertex_adj_hexes.items() if 0 in adjacent}
    destination = {v for v, adjacent in g.vertex_adj_hexes.items() if 2 in adjacent}
    assert not home & destination  # Separate islands, with an actual sea hex.
    sea_edges = {e for e in g.edges if rules._edge_has_sea(g, e)}
    for anchor in sorted(home):
        queue = deque([(anchor, [])])
        visited = {anchor}
        while queue:
            vertex, path = queue.popleft()
            if vertex in destination and len(path) >= 2:
                g.phase, g.rolled = "main", True
                g.occupied_v[anchor] = (0, 1)
                g.players[0].vp = 1
                rules.apply_cmd(g, 0, {"type": "grant_resources", "res": {
                    "wood": 8, "sheep": 8, "brick": 2, "wheat": 2}})
                return g, vertex, path
            for edge in sorted(sea_edges):
                if vertex not in edge:
                    continue
                neighbor = edge[1] if edge[0] == vertex else edge[0]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [edge]))
    raise AssertionError("fixture has no sea connection between its islands")


def test_paid_ship_network_reaches_another_island_then_builds_without_scenario_bonus():
    g, destination, path = island_game()
    assert destination not in board_legal_moves(g, 0)["settlements"]
    for edge in path:
        assert list(edge) in board_legal_moves(g, 0)["ships"]
        rules.apply_cmd(g, 0, {"type": "build_ship", "eid": edge})
    assert destination in board_legal_moves(g, 0)["settlements"]
    before = deepcopy(g)
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": destination})
    assert g.players[0].vp == before.players[0].vp + 1
    assert g.occupied_v[destination] == (0, 1)
    assert g.occupied_ships == before.occupied_ships
    assert loads_snapshot(dumps_snapshot(g)) == g


@pytest.mark.parametrize("invalid", ["foreign_ships", "missing_resource", "near_opponent"])
def test_island_arrival_still_checks_ownership_resources_and_distance_atomically(invalid):
    g, destination, path = island_game()
    for edge in path:
        rules.apply_cmd(g, 0, {"type": "build_ship", "eid": edge})
    if invalid == "foreign_ships":
        g.occupied_ships = {edge: 1 for edge in g.occupied_ships}
        g.ships_built_this_turn = set()
    elif invalid == "missing_resource":
        g.players[0].res["wheat"] = 0
    else:
        neighbor = next(v for v in rules.edge_neighbors_of_vertex(g.edges, destination)
                        if v not in g.occupied_v)
        g.occupied_v[neighbor] = (1, 1)
    before = deepcopy(g)
    assert destination not in board_legal_moves(g, 0)["settlements"]
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": destination})
    assert g == before
