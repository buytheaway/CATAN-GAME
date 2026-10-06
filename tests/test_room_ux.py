"""Room policies through the shared executor, plus real WebSocket delivery."""
import asyncio
from collections import Counter
from copy import deepcopy

import pytest
import websockets

from app import net_protocol, server_mp as server
from app.engine import rules
from app.room_options import COLORS, RoomSettings, shuffled_bag
from tests.test_pirate_lifecycle import finish_setup
from tests.test_server_authority import live_server
from tests.test_multiplayer_basic import _send, _send_cmd, _recv_type, _recv_error, _recv_cmd_ack


@pytest.fixture
def lobby(monkeypatch):
    manager = server.RoomManager()
    monkeypatch.setattr(server, "manager", manager)
    room = manager.create_room("Host", 4)
    for name in ("Bob", "Carol", "Dave"):
        manager.join_room(room.room_code, name)
    return room


@pytest.mark.parametrize("starter", range(4))
def test_server_random_starter_rotates_setup_and_first_main_turn(lobby, monkeypatch, starter):
    monkeypatch.setattr(server.secrets, "randbelow", lambda count: starter if count == 4 else 0)
    server._set_player_color(lobby, 0, "purple")
    server._start_match(lobby)
    forward = [(starter + i) % 4 for i in range(4)]
    assert lobby.game.turn == starter
    assert lobby.game.setup_order == forward + forward[::-1]
    finish_setup(lobby.game)
    assert lobby.game.turn == starter and lobby.game.phase == "main"
    assert lobby.players[0].color == "purple"


def test_host_policy_and_rematch_reselect_with_compact_pids_and_retained_colors(lobby, monkeypatch):
    colors = {p.name: p.color for p in lobby.players}
    tokens = {p.name: p.reconnect_token for p in lobby.players}
    server._set_room_settings(lobby, 0, {"starting_player": "host", "dice_mode": "balanced", "target_vp": 12})
    server._start_match(lobby)
    assert lobby.game.turn == 0 and lobby.game.rules_config.target_vp == 12
    lobby.players[0].connected = False
    lobby.game.game_over = True
    lobby.dice_bag = [(1, 1)] * 20
    server._start_match(lobby)
    assert lobby.host_pid == lobby.game.turn == 0
    assert [p.name for p in lobby.players] == ["Bob", "Carol", "Dave"]
    assert [p.pid for p in lobby.players] == [0, 1, 2]
    assert all(p.color == colors[p.name] and p.reconnect_token == tokens[p.name] for p in lobby.players)
    assert lobby.game.rules_config.target_vp == 12 and lobby.settings.dice_mode == "balanced"
    assert not lobby.dice_bag and lobby.timer is None and lobby.tick == 0
    lobby.game.game_over = True
    lobby.settings = RoomSettings(starting_player="random")  # Test the next policy without a public in-match edit.
    monkeypatch.setattr(server.secrets, "randbelow", lambda count: count - 1)
    server._start_match(lobby)
    assert lobby.game.turn == 2 and lobby.game.setup_order == [2, 0, 1, 1, 0, 2]


def test_six_auto_colors_unique_rejected_selection_atomic_and_reconnect_retains(lobby):
    manager = server.manager
    six = manager.create_room("Six", 6)
    for i in range(5):
        manager.join_room(six.room_code, str(i))
    assert {p.color for p in six.players} == set(COLORS)
    before = deepcopy(six)
    with pytest.raises(rules.RuleError):
        server._set_player_color(six, 0, six.players[1].color)
    assert six == before
    old, new = server.ClientConn(object()), server.ClientConn(object())
    manager.connections.update({old.ws: old, new.ws: new})
    manager.bind_player(old, six, 0)
    token, color = six.players[0].reconnect_token, six.players[0].color
    manager.leave_room(old)
    manager.bind_player(new, six, 0)
    assert six.players[0].reconnect_token == token and six.players[0].color == color
    server._set_player_color(lobby, 0, "green")
    assert lobby.players[0].color == "green"


@pytest.mark.parametrize("patch", [{"turn_timer": True}, {"turn_timer": 45}, {"target_vp": 2},
                                  {"dice_mode": "loaded"}, {"starting_pid": 2}, {"target_vp": 12, "bot": True}])
def test_invalid_settings_are_atomic(lobby, patch):
    before = deepcopy(lobby)
    with pytest.raises(rules.RuleError):
        server._set_room_settings(lobby, 0, patch)
    assert lobby == before


def test_settings_authority_lock_and_public_projection(lobby):
    before = deepcopy(lobby)
    with pytest.raises(rules.RuleError):
        server._set_room_settings(lobby, 1, {"target_vp": 12})
    assert lobby == before
    server._set_room_settings(lobby, 0, {"target_vp": 12, "dice_mode": "balanced"})
    public = net_protocol.room_state_message(lobby)
    assert public["settings"]["target_vp"] == 12 and public["settings"]["dice_mode"] == "balanced"
    assert all("reconnect_token" not in p for p in public["players"])
    server._start_match(lobby)
    before = deepcopy(lobby)
    for action in (lambda: server._set_room_settings(lobby, 0, {"turn_timer": 60}),
                   lambda: server._set_player_color(lobby, 0, "purple")):
        with pytest.raises(rules.RuleError):
            action()
        assert lobby == before


def test_balanced_full_bags_have_exact_ordered_outcomes_and_2d6_weights():
    expected = {(a, b) for a in range(1, 7) for b in range(1, 7)}
    for _ in range(20):
        bag = shuffled_bag()
        assert len(bag) == 36 and set(bag) == expected
        assert Counter(sum(pair) for pair in bag) == {total: 6 - abs(7 - total) for total in range(2, 13)}


@pytest.fixture
def timed(lobby, monkeypatch):
    lobby.players[2].connected = lobby.players[3].connected = False
    server._set_room_settings(lobby, 0, {"starting_player": "host", "turn_timer": 30})
    server._start_match(lobby)
    finish_setup(lobby.game)
    clock = {"now": 100.0, "wall": 1000.0}
    monkeypatch.setattr(server.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(server.time, "time", lambda: clock["wall"])
    monkeypatch.setattr(server, "_roll_dice", lambda: (3, 5))
    server._sync_timer(lobby)
    return lobby, clock


def test_balanced_consumes_only_accepted_rolls_and_replaces_at_twelve(timed, monkeypatch):
    room, _ = timed
    room.settings = RoomSettings(dice_mode="balanced")
    complete = [(a, b) for a in range(1, 7) for b in range(1, 7)]
    bags = [complete[::-1], complete]
    calls = [0]
    def fresh_bag():
        bag = list(bags[min(calls[0], 1)])
        calls[0] += 1
        return bag
    monkeypatch.setattr(server, "shuffled_bag", fresh_bag)
    g = room.game
    for roll_index in range(24):
        g.rolled, g.pending_action = False, None  # Isolate bag draws from unrelated robber choices.
        expected = (roll_index // 6 + 1, roll_index % 6 + 1)
        assert server._apply_cmd(room, 0, {"type": "roll"}) is None
        assert room.dice == expected and g.last_roll == sum(expected)
        assert len(room.dice_bag) == 35 - roll_index
    before = deepcopy(g), list(room.dice_bag), room.roll_count
    assert server._apply_cmd(room, 1, {"type": "roll"}) is not None
    assert (g, room.dice_bag, room.roll_count) == before
    g.rolled, g.pending_action = False, None
    assert server._apply_cmd(room, 0, {"type": "roll", "dice": [1, 1]}) is not None
    assert room.roll_count == 24 and len(room.dice_bag) == 12
    assert server._apply_cmd(room, 0, {"type": "roll"}) is None
    assert room.dice == (6, 6) and len(room.dice_bag) == 35
    assert room.dice_algorithm == "balanced_v1"
    assert "dice_bag" not in server._snapshot_state(g, room, 0)


def test_random_does_not_read_or_change_balanced_bag(timed, monkeypatch):
    room, _ = timed
    room.dice_bag = [(1, 1)] * 36
    monkeypatch.setattr(server, "shuffled_bag", lambda: pytest.fail("Random used Balanced"))
    assert server._apply_cmd(room, 0, {"type": "roll"}) is None
    assert room.dice == (3, 5) and len(room.dice_bag) == 36


def test_timer_auto_roll_then_twenty_second_grace_then_end(timed):
    room, clock = timed
    initial = room.timer.deadline_ms
    clock["now"] = 129
    asyncio.run(server._process_room_timer(room))
    assert not room.game.rolled and room.timer.deadline_ms == initial
    clock["now"] = 130
    asyncio.run(server._process_room_timer(room))
    assert room.game.rolled and room.dice == (3, 5) and room.roll_count == 1
    assert room.timer.stage == "grace" and room.timer.deadline == 150
    assert room.tick == 1 and room.players[0].last_seq_applied == 0
    clock["now"] = 150
    asyncio.run(server._process_room_timer(room))
    assert room.game.turn == 1 and not room.game.rolled
    assert room.timer.pid == 1 and room.timer.deadline == 180 and room.tick == 2


def test_manual_roll_preserves_turn_deadline_and_expiry_ends(timed):
    room, clock = timed
    timer = room.timer
    assert server._apply_cmd(room, 0, {"type": "roll"}) is None
    server._sync_timer(room)
    assert room.timer is timer
    clock["now"] = 130
    asyncio.run(server._process_room_timer(room))
    assert room.game.turn == 1 and room.roll_count == 1


@pytest.mark.parametrize("pending", ["discard", "robber_move", "choose_gold", "future_mandatory_choice", "road_building"])
def test_expired_mandatory_actions_are_not_automatically_chosen(timed, pending):
    room, clock = timed
    room.game.rolled = True
    if pending == "road_building":
        room.game.players[0].dev_cards = [{"type": "road_building", "new": False}]
        assert server._apply_cmd(room, 0, {"type": "play_dev", "card": "road_building"}) is None
    else:
        room.game.pending_action = pending
    before = deepcopy(room.game)
    clock["now"] = 130
    asyncio.run(server._process_room_timer(room))
    assert room.game == before and room.timer.stage == "blocked"
    assert room.tick == 1
    clock["now"] = 10000
    asyncio.run(server._process_room_timer(room))
    assert room.game == before and room.tick == 1


def test_automatic_seven_blocks_then_resolved_robber_allows_end(timed, monkeypatch):
    room, clock = timed
    monkeypatch.setattr(server, "_roll_dice", lambda: (3, 4))
    clock["now"] = 130
    asyncio.run(server._process_room_timer(room))
    assert room.game.pending_action == "robber_move" and room.timer.stage == "grace"
    clock["now"] = 150
    before = deepcopy(room.game)
    asyncio.run(server._process_room_timer(room))
    assert room.game == before and room.timer.stage == "blocked"
    tile = server._legal_moves(room.game, 0)["robber_tiles"][0]
    assert server._apply_cmd(room, 0, {"type": "move_robber", "tile": tile}) is None
    asyncio.run(server._process_room_timer(room))
    assert room.game.turn == 1 and room.timer.pid == 1


def test_timer_projection_reconnect_and_wall_clock_do_not_change_authority(timed):
    room, clock = timed
    timer = room.timer
    old, replacement = server.ClientConn(object()), server.ClientConn(object())
    server.manager.connections.update({old.ws: old, replacement.ws: replacement})
    server.manager.bind_player(old, room, 0)
    deadline, bag = timer.deadline, list(room.dice_bag)
    clock["now"], clock["wall"] = 110, 900
    server.manager.bind_player(replacement, room, 0)
    state = server._snapshot_state(room.game, room, 0)
    assert state["turn_timer"]["remaining_ms"] == 20000
    assert state["turn_timer"]["server_time_ms"] == 900000
    assert room.timer.deadline == deadline and room.dice_bag == bag
    assert old.room_code is None and old.pid is None


def test_timer_off_setup_game_over_rematch_and_destruction_clear(timed):
    room, clock = timed
    room.game.game_over = True
    before = deepcopy(room.game)
    clock["now"] = 10000
    asyncio.run(server._process_room_timer(room))
    assert room.timer is None and room.game == before and room.tick == 0
    server._start_match(room)
    server._sync_timer(room)
    assert room.timer is None  # New setup never auto-places.
    finish_setup(room.game)
    room.settings = RoomSettings(turn_timer=0)
    server._sync_timer(room)
    assert server._snapshot_state(room.game, room, 0)["turn_timer"] is None
    room.settings = RoomSettings(turn_timer=60)
    server._sync_timer(room)
    assert room.timer is not None
    server.manager.destroy_room(room.room_code)
    assert room.timer is None and room.room_code not in server.manager.rooms


def test_single_scheduler_is_cancelled_on_shutdown(lobby, monkeypatch):
    tasks = []
    async def waiting_loop():
        tasks.append(asyncio.current_task())
        await asyncio.Event().wait()
    monkeypatch.setattr(server, "_timer_loop", waiting_loop)
    async def run():
        async with server.lifespan(server.app):
            await asyncio.sleep(0)
            assert len(tasks) == 1 and not tasks[0].done()
        assert tasks[0].cancelled()
        assert all(room.timer is None for room in server.manager.rooms.values())
    asyncio.run(run())


def test_chat_limits_order_plain_text_rate_and_bounded_history(lobby, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    for text in (" ", "x" * 501):
        before = deepcopy(lobby)
        with pytest.raises(rules.RuleError):
            server._append_chat(lobby, 0, text)
        assert lobby == before
    for i in range(5):
        server._append_chat(lobby, 0, "  <script>alert(1)</script>  ")
    assert lobby.chat_history[0]["text"] == "<script>alert(1)</script>"
    assert [m["id"] for m in lobby.chat_history] == [1, 2, 3, 4, 5]
    before = deepcopy(lobby)
    with pytest.raises(rules.RuleError, match="Wait before"):
        server._append_chat(lobby, 0, "sixth")
    assert lobby == before
    for i in range(55):
        now[0] += 10
        server._append_chat(lobby, i % 2, f"message {i}")
    assert len(lobby.chat_history) == 50 and lobby.chat_revision == 60
    assert [m["id"] for m in lobby.chat_history] == list(range(11, 61))
    assert net_protocol.room_state_message(lobby)["chat_history"] == lobby.chat_history


@pytest.mark.parametrize("visibility", ["visible", "hidden"])
def test_bank_policy_preserves_all_other_personal_privacy(lobby, visibility):
    server._set_room_settings(lobby, 0, {"bank_visibility": visibility, "starting_player": "host"})
    server._start_match(lobby)
    g = lobby.game
    g.players[1].dev_cards = [{"type": "victory_point", "new": False}]
    g.players[1].vp = 1
    g.pending_gold, g.discard_required = {0: 1, 1: 2}, {0: 2, 1: 4}
    before = deepcopy(g)
    state = server._snapshot_state(g, lobby, 0)
    assert g == before
    assert "seed" not in state and "dev_deck" not in state and "dice_bag" not in state
    assert "res" not in state["players"][1] and "dev_cards" not in state["players"][1]
    assert state["players"][1]["vp"] == 0
    assert state["pending_gold"] == {"0": 1} and state["discard_required"] == {"0": 2}
    if visibility == "visible":
        assert state["bank"] == g.bank
        state["bank"]["wood"] = -1
        assert g.bank["wood"] == 19
    else:
        assert "bank" not in state and state["bank_available"] == {r: True for r in rules.RESOURCES}


def test_live_settings_colors_chat_reconnect_lock_and_balanced_authority(live_server):
    async def latest(ws, request_id):
        while (message := await _recv_type(ws, "room_state")).get("request_id") != request_id:
            pass
        return message
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            await _send(a, {"type": "create_room", "name": "Host", "max_players": 2})
            initial = await _recv_type(a, "room_state")
            token = await _recv_type(a, "reconnect_token")
            assert initial["settings"] == {"dice_mode": "random", "starting_player": "random", "turn_timer": 0,
                                            "bank_visibility": "visible", "target_vp": 10, "discard_threshold": 7}
            await _send(b, {"type": "join_room", "room_code": initial["room_code"], "name": "Bob"})
            await _recv_type(b, "room_state")
            await _recv_type(b, "reconnect_token")
            await _recv_type(a, "room_state")
            await _send(b, {"type": "set_settings", "settings": {"turn_timer": 60}, "request_id": "forbidden"})
            error = await _recv_error(b, "forbidden")
            assert error["detail"]["request_id"] == "forbidden"
            await _send(a, {"type": "set_settings", "request_id": "settings", "settings": {
                "dice_mode": "balanced", "turn_timer": 60, "target_vp": 12}})
            for ws in (a, b):
                assert (await latest(ws, "settings"))["settings"]["turn_timer"] == 60
            await _send(b, {"type": "set_color", "color": "orange", "request_id": "color"})
            for ws in (a, b):
                assert (await latest(ws, "color"))["players"][1]["color"] == "orange"
            await _send(a, {"type": "chat", "text": "<b>hello</b>"})
            for ws in (a, b):
                chat = await _recv_type(ws, "chat_state")
                assert chat["chat_history"][0]["text"] == "<b>hello</b>" and chat["chat_revision"] == 1
            await _send(a, {"type": "start_match", "starting_pid": 0})  # This field has no authority.
            matches = [await _recv_type(ws, "match_state") for ws in (a, b)]
            room = server.manager.rooms[initial["room_code"]]
            assert room.game.rules_config.target_vp == 12
            finish_setup(room.game)
            server._sync_timer(room)
            actor, other = (a, b) if room.game.turn == 0 else (b, a)
            before = deepcopy(room.game), list(room.dice_bag)
            cid = await _send_cmd(actor, room.match_id, 1, {"type": "roll", "dice": [6, 6]})
            await _recv_error(actor, "invalid")
            assert not (await _recv_cmd_ack(actor, cid))["applied"]
            assert (room.game, room.dice_bag) == before
            cid = await _send_cmd(actor, room.match_id, 2, {"type": "roll"})
            pairs = [(await _recv_type(ws, "match_state"))["state"]["dice"] for ws in (a, b)]
            assert pairs[0] == pairs[1] and sum(pairs[0]) == room.game.last_roll
            assert len(room.dice_bag) == 35 and (await _recv_cmd_ack(actor, cid))["applied"]
            await _send(a, {"type": "set_settings", "settings": {"dice_mode": "random"}})
            await _recv_error(a, "invalid")
            timer, bag = deepcopy(room.timer), list(room.dice_bag)
            async with websockets.connect(live_server) as replacement:
                await _send(replacement, {"type": "reconnect", "room_code": room.room_code,
                                          "reconnect_token": token["reconnect_token"]})
                restored = await _recv_type(replacement, "room_state")
                await _recv_type(replacement, "reconnect_token")
                state = (await _recv_type(replacement, "match_state"))["state"]
                assert restored["chat_history"][0]["text"] == "<b>hello</b>"
                assert state["turn_timer"]["deadline_ms"] == timer.deadline_ms
                assert room.dice_bag == bag and restored["players"][1]["color"] == "orange"
                await _send(a, {"type": "chat", "text": "stolen owner"})
                await _recv_error(a, "forbidden")
    asyncio.run(run())
