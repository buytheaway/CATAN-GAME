"""Road Building credits belong to the turn in which the card was played."""
from copy import deepcopy

import pytest

from app import server_mp as server
from app.engine import rules
from app.engine.legal import board_legal_moves
from tests.test_pirate_lifecycle import finish_setup


def return_hand_to_bank(g, pid):
    for resource, count in g.players[pid].res.items():
        g.bank[resource] += count
        g.players[pid].res[resource] = 0


@pytest.fixture
def game():
    g = rules.build_game(1, 2, map_id="base_standard")
    finish_setup(g)
    return_hand_to_bank(g, 0)
    g.dev_deck.remove("road_building")
    g.players[0].dev_cards.append({"type": "road_building", "new": False})
    assert g.turn == 0 and not g.rolled
    return g


def play_and_build(g, used):
    hand = dict(g.players[0].res)
    rules.apply_cmd(g, 0, {"type": "play_dev", "card": "road_building"})
    assert g.free_roads[0] == 2 and g.pending_action is None
    built = []
    for _ in range(used):
        edge = board_legal_moves(g, 0)["roads"][0]
        rules.apply_cmd(g, 0, {"type": "place_road", "eid": edge, "free": True})
        built.append(tuple(edge))
    assert g.free_roads[0] == 2 - used
    assert g.players[0].res == hand
    return built


def roll_and_end(g, pid):
    rules.apply_cmd(g, pid, {"type": "roll", "roll": 2})
    rules.apply_cmd(g, pid, {"type": "end_turn"})


@pytest.mark.parametrize("used", [0, 1, 2])
def test_credit_expires_at_end_turn_and_stays_expired_next_own_turn(game, used):
    original_roads = dict(game.occupied_e)
    built = play_and_build(game, used)
    expected_roads = {**original_roads, **{edge: 0 for edge in built}}
    assert game.occupied_e == expected_roads

    roll_and_end(game, 0)
    assert game.free_roads[0] == 0
    assert game.occupied_e == expected_roads
    assert not board_legal_moves(game, 0)["road_free"]

    roll_and_end(game, 1)
    assert game.turn == 0 and not game.rolled
    assert game.free_roads[0] == 0
    assert not board_legal_moves(game, 0)["road_free"]
    rules.apply_cmd(game, 0, {"type": "roll", "roll": 2})
    assert not board_legal_moves(game, 0)["road_free"]
    assert game.occupied_e == expected_roads


def test_expired_credit_cannot_replace_the_paid_road_cost(game):
    play_and_build(game, 1)
    roll_and_end(game, 0)
    roll_and_end(game, 1)
    rules.apply_cmd(game, 0, {"type": "roll", "roll": 2})
    return_hand_to_bank(game, 0)
    edge = next(e for e in sorted(game.edges) if rules.can_place_road(game, 0, e))
    assert board_legal_moves(game, 0)["roads"] == []

    before = deepcopy(game)
    with pytest.raises(rules.RuleError, match="No free roads available"):
        rules.apply_cmd(game, 0, {"type": "place_road", "eid": edge, "free": True})
    assert game == before
    with pytest.raises(rules.RuleError, match="Not enough resources"):
        rules.apply_cmd(game, 0, {"type": "place_road", "eid": edge})
    assert game == before

    rules.apply_cmd(game, 0, {"type": "grant_resources", "res": {"wood": 1, "brick": 1}})
    bank_before = dict(game.bank)
    rules.apply_cmd(game, 0, {"type": "place_road", "eid": edge})
    assert game.occupied_e[edge] == 0 and game.free_roads[0] == 0
    assert game.players[0].res["wood"] == game.players[0].res["brick"] == 0
    assert game.bank["wood"] == bank_before["wood"] + 1
    assert game.bank["brick"] == bank_before["brick"] + 1


@pytest.mark.parametrize("invalid", ["missing_edge", "occupied_edge", "invalid_free"])
def test_rejected_road_preserves_state_and_credit_remains_usable(game, invalid):
    play_and_build(game, 0)
    for remaining in (2, 1):
        legal_edge = board_legal_moves(game, 0)["roads"][0]
        cmd = {"type": "place_road", "eid": legal_edge, "free": True}
        if invalid == "missing_edge":
            cmd["eid"] = [-1, 9999]
        elif invalid == "occupied_edge":
            cmd["eid"] = next(iter(game.occupied_e))
        else:
            cmd["free"] = 1
        before = deepcopy(game)
        with pytest.raises(rules.RuleError):
            rules.apply_cmd(game, 0, cmd)
        assert game == before and game.free_roads[0] == remaining

        rules.apply_cmd(game, 0, {"type": "place_road", "eid": legal_edge, "free": True})
        assert game.occupied_e[tuple(legal_edge)] == 0
        assert game.free_roads[0] == remaining - 1


def test_rejected_end_turn_does_not_expire_unused_credit(game):
    play_and_build(game, 1)
    before = deepcopy(game)
    with pytest.raises(rules.RuleError, match="Must roll before actions"):
        rules.apply_cmd(game, 0, {"type": "end_turn"})
    assert game == before and game.free_roads[0] == 1
    edge = board_legal_moves(game, 0)["roads"][0]
    rules.apply_cmd(game, 0, {"type": "place_road", "eid": edge, "free": True})
    assert game.free_roads[0] == 0
    roll_and_end(game, 0)


def test_server_commands_and_personal_snapshots_expire_credit(game, monkeypatch):
    room = server.Room("ROADS", 2, 0, [server.PlayerSlot(pid=i) for i in range(2)],
                       status="in_match", game=game)
    monkeypatch.setattr(server, "_roll_dice", lambda: 2)
    assert server._apply_cmd(room, 0, {"type": "play_dev", "card": "road_building"}) is None
    state = server._snapshot_state(game, room, 0)
    assert state["free_roads"] == {"0": 2} and state["legal"]["road_free"]
    edge = state["legal"]["roads"][0]
    assert server._apply_cmd(room, 0, {"type": "place_road", "eid": edge, "free": True}) is None
    assert server._apply_cmd(room, 0, {"type": "roll"}) is None
    assert server._apply_cmd(room, 0, {"type": "end_turn"}) is None

    state = server._snapshot_state(game, room, 0)
    assert state["free_roads"] == {"0": 0} and not state["legal"]["road_free"]
    other = server._snapshot_state(game, room, 1)
    assert other["free_roads"] == {"1": 0} and not other["legal"]["road_free"]
    assert server._apply_cmd(room, 1, {"type": "roll"}) is None
    assert server._apply_cmd(room, 1, {"type": "end_turn"}) is None
    state = server._snapshot_state(game, room, 0)
    assert state["free_roads"] == {"0": 0} and not state["legal"]["road_free"]
    assert game.occupied_e[tuple(edge)] == 0
