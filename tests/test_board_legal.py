from copy import deepcopy

import pytest

from app import server_mp as server
from app.engine import rules
from app.engine.legal import board_legal_moves
from app.engine.state import COST
from tests.test_pirate_lifecycle import finish_setup


@pytest.fixture
def funded():
    g = rules.build_game(1, 2, map_id="seafarers_gold_haven")
    finish_setup(g)
    g.players[0].res = {r: 9 for r in g.players[0].res}
    g.rolled = True
    # Extend a real road network until it reaches a legal settlement vertex.
    for _ in range(8):
        if any(rules.can_place_settlement(g, 0, v, True) for v in g.vertices):
            break
        edge = next(e for e in sorted(g.edges) if rules.can_place_road(g, 0, e))
        rules.apply_cmd(g, 0, {"type": "place_road", "eid": edge})
    assert any(rules.can_place_settlement(g, 0, v, True) for v in g.vertices)
    return g


@pytest.mark.parametrize("field,cost", [("settlements", "settlement"), ("roads", "road"),
                                       ("cities", "city"), ("ships", "ship")])
def test_affordable_targets_disappear_when_a_required_resource_is_missing(funded, field, cost):
    g = funded
    assert board_legal_moves(g, 0)[field]
    g.players[0].res[next(iter(COST[cost]))] = 0
    before = deepcopy(g)
    assert board_legal_moves(g, 0)[field] == []
    assert g == before


@pytest.mark.parametrize("field,limit", [("settlements", "max_settlements"), ("roads", "max_roads"),
                                        ("cities", "max_cities"), ("ships", "max_ships")])
def test_piece_limits_remove_targets_even_with_resources(funded, field, limit):
    assert board_legal_moves(funded, 0)[field]
    setattr(funded.rules_config, limit, 0)
    assert board_legal_moves(funded, 0)[field] == []


def test_required_roll_and_free_road_command_are_projected_by_engine(funded):
    g = funded
    g.rolled = False
    assert board_legal_moves(g, 0)["roads"] == []
    g.free_roads[0] = 2
    legal = board_legal_moves(g, 0)
    assert legal["road_free"] and legal["roads"]
    assert legal["cities"] == legal["ships"] == legal["settlements"] == []
    probe = deepcopy(g)
    rules.apply_cmd(probe, 0, {"type": "place_road", "eid": legal["roads"][0], "free": True})
    assert probe.free_roads[0] == 1 and g.free_roads[0] == 2


def test_setup_has_only_the_current_step_and_anchor_without_charging_resources():
    g = rules.build_game(1, 2)
    for _ in range(8):
        pid = g.turn
        before = deepcopy(g)
        legal = board_legal_moves(g, pid)
        other = board_legal_moves(g, 1 - pid)
        assert other["settlements"] == other["roads"] == other["cities"] == other["ships"] == []
        assert g == before
        if g.setup_need == "settlement":
            assert legal["settlements"] and not legal["roads"]
            rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": legal["settlements"][0]})
        else:
            assert legal["roads"] and not legal["settlements"]
            assert all(g.setup_anchor_vid in e for e in legal["roads"])
            rules.apply_cmd(g, pid, {"type": "place_road", "eid": legal["roads"][0]})
    assert g.phase == "main"


def test_city_targets_only_own_settlements_and_seafarers_flag_controls_ships(funded):
    legal = board_legal_moves(funded, 0)
    assert set(legal["cities"]) == {v for v, p in funded.occupied_v.items() if p == (0, 1)}
    assert legal["ships"]
    funded.rules_config.enable_seafarers = False
    assert board_legal_moves(funded, 0)["ships"] == []


@pytest.mark.parametrize("pending", ["discard", "choose_gold", "robber_move"])
def test_pending_actions_suppress_normal_build_and_move_targets(funded, pending):
    funded.pending_action, funded.pending_pid = pending, 0
    legal = board_legal_moves(funded, 0)
    assert legal["settlements"] == legal["roads"] == legal["cities"] == legal["ships"] == []
    assert legal["move_ship"]["sources"] == []
    assert bool(legal["robber_tiles"]) == (pending == "robber_move")


def test_robber_and_pirate_targets_victims_are_personal_and_do_not_mutate(funded):
    g = funded
    g.pending_action, g.pending_pid = "robber_move", 0
    before = deepcopy(g)
    legal = board_legal_moves(g, 0)
    assert legal["robber_tiles"] == [i for i, t in enumerate(g.tiles) if t.terrain != "sea" and i != g.robber_tile]
    assert legal["pirate_tiles"] == [i for i, t in enumerate(g.tiles) if t.terrain == "sea" and i != g.pirate_tile]
    for tile in legal["robber_tiles"]:
        assert legal["robber_victims"][str(tile)] == rules._victims_for_tile(g, tile, 0)
    other = board_legal_moves(g, 1)
    assert other["robber_tiles"] == other["pirate_tiles"] == []
    assert other["robber_victims"] == other["pirate_victims"] == {}
    assert g == before
    g.rules_config.enable_pirate = False
    assert board_legal_moves(g, 0)["pirate_tiles"] == []


def test_ship_sources_and_destinations_match_current_executor(funded):
    g = funded
    source = board_legal_moves(g, 0)["ships"][0]
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": source})
    before = deepcopy(g)
    movement = board_legal_moves(g, 0)["move_ship"]
    assert movement["sources"]
    expected = []
    for edge in sorted(g.edges):
        try:
            rules.apply_cmd(deepcopy(g), 0, {"type": "move_ship", "from_eid": source, "to_eid": list(edge)})
        except rules.RuleError:
            continue
        expected.append(list(edge))
    assert movement["targets"][",".join(map(str, source))] == expected
    assert g == before
    for vertex in source:
        g.occupied_v[vertex] = (0, 1)
    assert source not in board_legal_moves(g, 0)["move_ship"]["sources"]


@pytest.mark.parametrize("pid", [0, 1])
def test_personal_snapshot_does_not_reveal_another_players_affordability(funded, pid):
    room = server.Room("TEST", 2, 0, [])
    before = deepcopy(funded)
    state = server._snapshot_state(funded, room, pid)
    assert state["legal"]["pid"] == pid
    assert "res" not in state["players"][1 - pid] and "seed" not in state
    if pid != funded.turn:
        assert not any(state["legal"][key] for key in ("settlements", "roads", "cities", "ships", "robber_tiles", "pirate_tiles"))
        funded.players[0].res = {r: 0 for r in funded.players[0].res}
        assert server._snapshot_state(funded, room, pid)["legal"] == state["legal"]
    else:
        assert funded == before


def test_execution_revalidates_an_affordable_hint_after_state_changes(funded):
    road = board_legal_moves(funded, 0)["roads"][0]
    funded.players[0].res = {r: 0 for r in funded.players[0].res}
    room = server.Room("TEST", 2, 0, [], game=funded)
    before = deepcopy(funded)
    error = server._apply_cmd(room, 0, {"type": "place_road", "eid": road})
    assert error["code"] == "illegal" and funded == before


def test_game_over_has_no_board_targets(funded):
    funded.game_over = True
    legal = board_legal_moves(funded, 0)
    assert legal["settlements"] == legal["roads"] == legal["cities"] == legal["ships"] == []
    assert legal["robber_tiles"] == legal["pirate_tiles"] == []


@pytest.mark.parametrize("field,command,coordinate", [
    ("settlements", "place_settlement", "vid"), ("roads", "place_road", "eid"),
    ("cities", "upgrade_city", "vid"), ("ships", "build_ship", "eid"),
])
def test_build_target_lists_equal_all_commands_the_executor_accepts(funded, field, command, coordinate):
    before = deepcopy(funded)
    legal = board_legal_moves(funded, 0)
    candidates = sorted(funded.vertices if coordinate == "vid" else funded.edges)
    expected = []
    for value in candidates:
        value = list(value) if coordinate == "eid" else value
        try:
            rules.apply_cmd(deepcopy(funded), 0, {"type": command, coordinate: value})
        except rules.RuleError:
            continue
        expected.append(value)
    assert legal[field] == expected
    assert funded == before


@pytest.mark.parametrize("kind", ["robber", "pirate"])
def test_projected_victims_allow_explicit_choice_without_stealing_from_another_player(kind):
    g = rules.build_game(1, 3, map_id="seafarers_gold_haven")
    finish_setup(g)
    for pid in (1, 2):
        rules.apply_cmd(g, pid, {"type": "grant_resources", "res": {"wood": 5, "sheep": 5}})
    if kind == "pirate":
        for _ in range(5):
            for pid in (1, 2):
                g.turn, g.rolled = pid, True
                edges = [e for e in sorted(g.edges) if rules.can_place_ship(g, pid, e)]
                if edges:
                    rules.apply_cmd(g, pid, {"type": "build_ship", "eid": list(edges[0])})
    g.turn, g.rolled = 0, False
    g.players[0].dev_cards = [{"type": "knight", "new": False}]
    rules.apply_cmd(g, 0, {"type": "play_dev", "card": "knight"})
    before = deepcopy(g)
    legal = board_legal_moves(g, 0)
    tile = next(int(t) for t, victims in legal[kind + "_victims"].items() if victims == [1, 2])
    assert g == before
    rules.apply_cmd(g, 0, {"type": "move_" + kind, "tile": tile, "victim": 2})
    assert g.players[1].res == before.players[1].res
    assert sum(g.players[0].res.values()) == sum(before.players[0].res.values()) + 1
    assert sum(g.players[2].res.values()) == sum(before.players[2].res.values()) - 1
    assert g.pending_action is None
