"""Dice faces are public server presentation data, not a new engine roll rule."""
from copy import deepcopy

import pytest

from app import server_mp as server
from app.match_rulesets import CURRENT_RULESET
from app.engine import rules
from tests.test_pirate_lifecycle import finish_setup


@pytest.fixture
def room():
    g = rules.build_game(1, 2, map_id="base_standard")
    finish_setup(g)
    return server.Room("DICE", 2, 0, [server.PlayerSlot(pid=i) for i in range(2)],
                       status="in_match", game=g, ruleset_id=CURRENT_RULESET,
                       settings=server.RoomSettings(bank_visibility="hidden"))


def test_generation_preserves_the_two_independent_server_faces(monkeypatch):
    values, bounds = iter([1, 4]), []

    def randbelow(bound):
        bounds.append(bound)
        return next(values)

    monkeypatch.setattr(server.secrets, "randbelow", randbelow)
    assert server._roll_dice() == (2, 5)
    assert bounds == [6, 6]


def test_faces_match_both_snapshots_and_do_not_change_engine_sum_behavior(room, monkeypatch):
    monkeypatch.setattr(server, "_roll_dice", lambda: (3, 5))
    expected = deepcopy(room.game)
    rules.apply_cmd(expected, 0, {"type": "roll", "roll": 8})
    assert server._apply_cmd(room, 0, {"type": "roll"}) is None
    assert room.game == expected
    for pid in (0, 1):
        state = server._snapshot_state(room.game, room, pid)
        assert state["dice"] == [3, 5] and state["last_roll"] == 8
        assert state["roll_count"] == 1
        assert "bank" not in state and "seed" not in state
        assert "res" not in state["players"][1 - pid]

    assert server._apply_cmd(room, 0, {"type": "end_turn"}) is None
    state = server._snapshot_state(room.game, room, 0)
    assert state["last_roll"] is None and state["dice"] == [3, 5]
    assert state["roll_count"] == 1
    assert server._apply_cmd(room, 1, {"type": "roll"}) is None
    assert room.dice == (3, 5) and room.roll_count == 2


@pytest.mark.parametrize("invalid", ["other_player", "already_rolled", "setup", "pending", "client_faces"])
def test_rejected_roll_preserves_game_and_previous_dice_metadata(room, monkeypatch, invalid):
    monkeypatch.setattr(server, "_roll_dice", lambda: (6, 6))
    room.dice, room.roll_count = (2, 3), 7
    pid, cmd = 0, {"type": "roll"}
    if invalid == "other_player":
        pid = 1
    elif invalid == "already_rolled":
        room.game.rolled = True
    elif invalid == "setup":
        room.game.phase = "setup"
    elif invalid == "pending":
        room.game.pending_action = "robber_move"
    else:
        cmd["dice"] = [1, 1]
    before = deepcopy(room.game)
    assert server._apply_cmd(room, pid, cmd) is not None
    assert room.game == before
    assert room.dice == (2, 3) and room.roll_count == 7


def test_new_match_resets_dice_without_changing_connected_identity():
    manager = server.RoomManager()
    room = manager.create_room("Alice", 2)
    assert manager.join_room(room.room_code, "Bob") is room
    server._start_match(room)
    identities = [(p.name, p.reconnect_token) for p in room.players]
    room.dice, room.roll_count = (4, 5), 12
    previous_match = room.match_id
    room.game.game_over = True
    server._start_match(room)
    assert room.match_id == previous_match + 1 and room.tick == 0
    assert room.dice is None and room.roll_count == 0
    assert [(p.name, p.reconnect_token) for p in room.players] == identities
    assert room.game.last_roll is None and not room.game.rolled
