"""Room configuration, recipient privacy and explicitly isolated debug authority."""
import asyncio
from copy import deepcopy

import pytest
import websockets

from app import game_events, server_mp as server
from app.engine import rules
from app.engine.serialize import from_dict, to_dict
from app.engine.state import RESOURCES
from tests.test_pirate_lifecycle import finish_setup
from tests.test_server_authority import live_server, start_trio
from tests.test_multiplayer_basic import _send, _recv_type, _recv_error, _recv_cmd_ack


@pytest.fixture
def room(monkeypatch):
    manager = server.RoomManager()
    monkeypatch.setattr(server, "manager", manager)
    room = manager.create_room("Host", 3)
    for name in ("Victim", "Observer"):
        manager.join_room(room.room_code, name)
    server._set_room_settings(room, 0, {"starting_player": "host", "bank_visibility": "hidden"})
    server._start_match(room)
    finish_setup(room.game)
    return room


@pytest.mark.parametrize("threshold,size,expected", [(7, 7, 0), (7, 8, 4), (7, 9, 4),
                                                        (10, 10, 0), (10, 11, 5), (3, 4, 2)])
def test_threshold_strict_greater_and_original_half_formula(room, monkeypatch, threshold, size, expected):
    g = room.game
    g.rules_config.discard_threshold = threshold
    for p in g.players:
        p.res = {r: size if r == "wood" else 0 for r in RESOURCES}
    monkeypatch.setattr(server, "_roll_dice", lambda: (6, 1))
    assert server._apply_cmd(room, 0, {"type": "roll"}) is None
    assert g.discard_required == ({pid: expected for pid in range(3)} if expected else {})
    assert g.pending_action == ("discard" if expected else "robber_move")


def test_threshold_lobby_authority_lock_serialization_and_rematch(room):
    lobby = server.manager.create_room("New Host", 2)
    server.manager.join_room(lobby.room_code, "Guest")
    assert lobby.settings.discard_threshold == 7
    with pytest.raises(rules.RuleError):
        server._set_room_settings(lobby, 1, {"discard_threshold": 12})
    server._set_room_settings(lobby, 0, {"discard_threshold": 12})
    server._start_match(lobby)
    assert lobby.game.rules_config.discard_threshold == 12
    assert from_dict(to_dict(lobby.game)).rules_config.discard_threshold == 12
    with pytest.raises(rules.RuleError):
        server._set_room_settings(lobby, 0, {"discard_threshold": 4})
    lobby.game.game_over = True
    server._start_match(lobby)
    assert lobby.game.rules_config.discard_threshold == lobby.settings.discard_threshold == 12


@pytest.mark.parametrize("value", [True, 0, -1, 51, 7.5, "7", None])
def test_invalid_threshold_is_atomic(room, value):
    lobby = server.manager.create_room("Lobby", 2)
    before = deepcopy(lobby)
    with pytest.raises(rules.RuleError):
        server._set_room_settings(lobby, 0, {"discard_threshold": value})
    assert lobby == before
    with pytest.raises(rules.RuleError):
        rules.parse_rules_config({"discard_threshold": value})


def prepare_theft(room):
    g = room.game
    tile = next(i for i, t in enumerate(g.tiles) if i != g.robber_tile and t.terrain != "sea")
    vertex = next(v for v, adjacent in g.vertex_adj_hexes.items() if tile in adjacent)
    g.occupied_v = {vertex: (1, 1)}
    for p in g.players:
        p.res = {r: 0 for r in RESOURCES}
    g.players[1].res["brick"] = 3
    g.pending_action, g.pending_pid = "robber_move", 0
    return tile


@pytest.mark.parametrize("explicit_victim", [True, False])
def test_theft_exact_only_thief_victim_and_real_implicit_victim(room, explicit_victim):
    tile = prepare_theft(room)
    cmd = {"type": "move_robber", "tile": tile, **({"victim": 1} if explicit_victim else {})}
    assert server._apply_cmd(room, 0, cmd) is None
    for pid in range(3):
        s = server._snapshot_state(room.game, room, pid)
        theft = s["game_events"][-1]
        assert theft["type"] == "theft" and theft["actor_pid"] == 0 and theft["victim_pid"] == 1
        assert theft["quantity"] == 1 and "_private" not in theft
        if pid in (0, 1):
            assert theft["resource"] == "brick"
        else:
            assert "resource" not in theft and "brick" not in str(s["game_events"])
        assert "bank" not in s and "seed" not in s
        assert all("res" not in p and "dev_cards" not in p for p in s["players"] if p["pid"] != pid)


def test_production_exact_only_recipient_and_bank_visibility_independent(room, monkeypatch):
    g = room.game
    tile = next(i for i, t in enumerate(g.tiles) if i != g.robber_tile and t.terrain == "forest")
    vertex = next(v for v, adjacent in g.vertex_adj_hexes.items() if tile in adjacent)
    g.occupied_v = {vertex: (1, 1)}
    total = g.tiles[tile].number
    monkeypatch.setattr(server, "_roll_dice", lambda: (max(1, total - 6), min(6, total - 1)))
    assert server._apply_cmd(room, 0, {"type": "roll"}) is None
    for pid in range(3):
        events = server._snapshot_state(g, room, pid)["game_events"]
        produced = next(e for e in events if e["type"] == "production" and e["player_pid"] == 1)
        if pid == 1:
            assert produced["resources"]["wood"] >= 1
        else:
            assert "resources" not in produced


def test_private_purchase_discard_and_bounded_history_no_deck_types(room):
    g = room.game
    g.rolled = True
    for r in RESOURCES:
        g.players[0].res[r] = 4
    assert server._apply_cmd(room, 0, {"type": "buy_dev"}) is None
    own = game_events.project(room, 0)[-1]
    other = game_events.project(room, 2)[-1]
    assert own["paid"] == {"sheep": 1, "wheat": 1, "ore": 1}
    assert "paid" not in other and "card" not in other and "gained" not in other
    for _ in range(game_events.EVENT_LIMIT + 3):
        game_events.record(room, "debug", 0, action="example")
    assert len(room.game_events) == game_events.EVENT_LIMIT
    room.game.game_over = True
    server._start_match(room)
    assert room.game_events == [] and room.event_serial == 0


@pytest.mark.parametrize("enabled,test_room,pid", [(False, True, 0), (True, False, 0), (True, True, 1)])
def test_debug_denied_without_all_three_authorities(room, monkeypatch, enabled, test_room, pid):
    monkeypatch.setattr(server, "TEST_TOOLS_ENABLED", enabled)
    room.test_mode = test_room
    before = deepcopy(room)
    error = server._apply_cmd(room, pid, {"type": "test_action", "action": "set_next_dice", "dice": [6, 1]})
    assert error["code"] == "forbidden" and room == before


@pytest.mark.parametrize("fields", [
    {"action": "set_next_dice", "dice": [0, 6]}, {"action": "set_next_dice", "dice": [True, 6]},
    {"action": "give_dev", "player": 0, "card": "dragon"},
    {"action": "give_resources", "player": 0, "resource": "wood", "amount": 100},
    {"action": "remove_resources", "player": 0, "resource": "wood", "amount": 100},
    {"action": "force_turn", "player": -1}, {"action": "set_vp", "player": 0, "vp": 99},
    {"action": []}, {"action": "set_next_dice", "dice": [6, 1], "python": "anything"},
])
def test_rejected_debug_preserves_complete_room(room, monkeypatch, fields):
    monkeypatch.setattr(server, "TEST_TOOLS_ENABLED", True)
    room.test_mode = True
    before = deepcopy(room)
    assert server._apply_cmd(room, 0, {"type": "test_action", **fields})
    assert room == before


def test_named_debug_actions_conserve_cards_force_once_and_reset_on_rematch(room, monkeypatch):
    monkeypatch.setattr(server, "TEST_TOOLS_ENABLED", True)
    room.test_mode = True
    def debug(action, **fields):
        assert server._apply_cmd(room, 0, {"type": "test_action", "action": action, **fields}) is None
        assert room.game_events[-1]["type"] == "debug"
    totals = {r: room.game.bank[r] + sum(p.res[r] for p in room.game.players) for r in RESOURCES}
    debug("give_resources", player=1, resource="wood", amount=2)
    debug("remove_resources", player=1, resource="wood", amount=1)
    assert totals == {r: room.game.bank[r] + sum(p.res[r] for p in room.game.players) for r in RESOURCES}
    debug("give_dev", player=0, card="knight")
    assert {"type": "knight", "new": False} in room.game.players[0].dev_cards
    debug("force_turn", player=1)
    debug("set_next_dice", dice=[4, 5])
    before = deepcopy(room)
    assert server._apply_cmd(room, 0, {"type": "roll"}) and room == before
    assert server._apply_cmd(room, 1, {"type": "roll"}) is None
    assert room.dice == (4, 5) and room.next_test_dice is None
    debug("set_vp", player=1, vp=room.game.rules_config.target_vp - 1)
    room.game.game_over = True
    room.next_test_dice = (6, 6)
    server._start_match(room)
    assert room.test_mode and room.next_test_dice is None and not room.game_events


def test_real_ws_test_flag_lobby_lock_ownership_and_personal_capability(live_server, monkeypatch):
    monkeypatch.setattr(server, "TEST_TOOLS_ENABLED", True)
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b, websockets.connect(live_server) as c:
            room, _ = await start_trio([a, b, c])
            # A normal room stays protected on a development server.
            await _send(a, {"type": "enable_test_mode"})
            await _recv_error(a, "forbidden")
            finish_setup(room.game)
            await _send(a, {"type": "cmd", "match_id": 1, "seq": 1, "cmd_id": "no-cheat",
                            "cmd": {"type": "test_action", "action": "set_next_dice", "dice": [6, 1]}})
            await _recv_error(a, "forbidden")
            assert not (await _recv_cmd_ack(a, "no-cheat"))["applied"]
            assert not server._snapshot_state(room.game, room, 0)["test_tools"]
    asyncio.run(run())
