import asyncio
import json
import os
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest
import websockets

from app import net_protocol, server_mp as server
from app.engine import rules
from tests.test_pirate_lifecycle import begin_movement, finish_setup, pirate_game, pirate_targets
from tests.test_multiplayer_basic import (
    _find_free_port, _recv_cmd_ack, _recv_error, _recv_type,
    _send, _send_cmd, _start_server,
)


@pytest.fixture
def live_server(monkeypatch):
    monkeypatch.setattr(server, "manager", server.RoomManager())
    port = _find_free_port()
    process, thread = _start_server(port)
    yield f"ws://127.0.0.1:{port}/ws"
    process.should_exit = True
    thread.join(timeout=5)


async def start_pair(a, b, capacity=4):
    await _send(a, {"type": "create_room", "name": "Alice", "max_players": capacity})
    room = await _recv_type(a, "room_state")
    await _recv_type(a, "reconnect_token")
    await _send(b, {"type": "join_room", "room_code": room["room_code"], "name": "Bob"})
    await _recv_type(b, "room_state")
    await _recv_type(b, "reconnect_token")
    await _recv_type(a, "room_state")
    await _send(a, {"type": "start_match"})
    await _recv_type(a, "room_state")
    token_a = await _recv_type(a, "reconnect_token")
    ms_a = await _recv_type(a, "match_state")
    await _recv_type(b, "room_state")
    token_b = await _recv_type(b, "reconnect_token")
    ms_b = await _recv_type(b, "match_state")
    return server.manager.rooms[room["room_code"]], token_a, token_b, ms_a, ms_b


async def start_trio(clients):
    await _send(clients[0], {"type": "create_room", "name": "Alice", "max_players": 4})
    state = await _recv_type(clients[0], "room_state")
    await _recv_type(clients[0], "reconnect_token")
    for client, name in zip(clients[1:], ("Bob", "Carol")):
        await _send(client, {"type": "join_room", "room_code": state["room_code"], "name": name})
        await _recv_type(client, "room_state")
        await _recv_type(client, "reconnect_token")
    await _send(clients[0], {"type": "start_match"})
    tokens = []
    for client in clients:
        while (await _recv_type(client, "room_state"))["status"] != "in_match":
            pass
        tokens.append(await _recv_type(client, "reconnect_token"))
        await _recv_type(client, "match_state")
    return server.manager.rooms[state["room_code"]], tokens


def test_lobby_map_revision_final_preset_reconnect_and_start(live_server):
    async def latest_map(ws, map_id):
        while (state := await _recv_type(ws, "room_state"))["map_id"] != map_id:
            pass
        return state

    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            await _send(a, {"type": "create_room", "name": "Alice", "max_players": 2})
            first = await _recv_type(a, "room_state")
            token = await _recv_type(a, "reconnect_token")
            code = first["room_code"]
            assert first["map_revision"] == 0
            await _send(b, {"type": "join_room", "room_code": code, "name": "Bob"})
            await _recv_type(b, "room_state")
            await _recv_type(b, "reconnect_token")
            await _recv_type(a, "room_state")
            await _send(a, {"type": "set_map", "map_id": "base_12vp"})
            await _send(a, {"type": "set_map", "map_id": "seafarers_gold_haven"})
            final_a = await latest_map(a, "seafarers_gold_haven")
            final_b = await latest_map(b, "seafarers_gold_haven")
            assert final_a["map_revision"] == final_b["map_revision"] == 2
            async with websockets.connect(live_server) as replacement:
                await _send(replacement, {"type": "reconnect", "room_code": code,
                                          "reconnect_token": token["reconnect_token"]})
                restored = await _recv_type(replacement, "room_state")
                await _recv_type(replacement, "reconnect_token")
                assert restored["map_id"] == "seafarers_gold_haven"
                assert restored["map_revision"] == 2
                await _send(replacement, {"type": "start_match"})
                started = await _recv_type(replacement, "room_state")
                assert started["map_revision"] == 2
                for ws in (replacement, b):
                    state = (await _recv_type(ws, "match_state"))["state"]
                    assert state["map_id"] == "seafarers_gold_haven"
                    assert sum(t["terrain"] == "sea" for t in state["tiles"]) == 4
                    assert sum(t["terrain"] == "gold" for t in state["tiles"]) == 2
                    assert state["tiles"][state["pirate_tile"]]["terrain"] == "sea"
    asyncio.run(run())


def test_lobby_map_errors_do_not_advance_revision_and_new_room_resets(live_server):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            await _send(a, {"type": "create_room", "name": "Alice", "max_players": 2})
            first = await _recv_type(a, "room_state")
            await _recv_type(a, "reconnect_token")
            room = server.manager.rooms[first["room_code"]]
            await _send(b, {"type": "join_room", "room_code": room.room_code, "name": "Bob"})
            await _recv_type(b, "room_state")
            await _recv_type(b, "reconnect_token")
            await _recv_type(a, "room_state")
            await _send(a, {"type": "set_map", "map_id": "base_12vp"})
            assert (await _recv_type(a, "room_state"))["map_revision"] == 1
            await _recv_type(b, "room_state")
            before = net_protocol.room_state_message(room)
            for ws, payload, code in (
                (a, {"map_data": "invalid"}, "invalid"),
                (a, {"map_data": {"version": 1, "tiles": []}}, "invalid"),
                (a, {"map_id": "unknown"}, "invalid"),
                (b, {"map_id": "base_standard"}, "forbidden"),
            ):
                await _send(ws, {"type": "set_map", **payload})
                error = await _recv_error(ws, code)
                assert error["detail"]["request_type"] == "set_map"
                assert net_protocol.room_state_message(room) == before
            await _send(a, {"type": "create_room", "name": "Alice", "max_players": 2})
            new = await _recv_type(a, "room_state")
            assert new["room_code"] != room.room_code
            assert new["map_id"] == "base_standard" and new["map_revision"] == 0
            assert room.selected_map_id == "base_12vp" and room.map_revision == 1
    asyncio.run(run())


@pytest.mark.parametrize("extra", [
    {"roll": 12}, {"forced": 12}, {"dice": [6, 6]}, {"die1": 6, "die2": 6},
    {"roll": None}, {"forced": "bad"},
])
def test_ws_cannot_choose_dice_even_with_legacy_debug_enabled(live_server, monkeypatch, extra):
    monkeypatch.setenv("CATAN_DEBUG_ROLLS", "1")
    monkeypatch.setattr(server, "_roll_dice", lambda: 8)

    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            room, _, _, ms, _ = await start_pair(a, b)
            room.game.phase, room.game.rolled = "main", False
            before = deepcopy(room.game)
            cid = await _send_cmd(a, room.match_id, 1, {"type": "roll", **extra})
            await _recv_error(a, "invalid")
            ack = await _recv_cmd_ack(a, cid)
            assert ack["applied"] is False and room.game == before and room.tick == 0
            cid = await _send_cmd(a, room.match_id, 2, {"type": "roll"})
            ma, mb = await _recv_type(a, "match_state"), await _recv_type(b, "match_state")
            assert ma["state"]["last_roll"] == mb["state"]["last_roll"] == 8
            assert room.game.roll_history == [8]
            assert (await _recv_cmd_ack(a, cid))["applied"] is True
    asyncio.run(run())


def test_ws_grant_is_forbidden_and_full_state_unchanged(live_server):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            room, _, _, _, _ = await start_pair(a, b)
            before = deepcopy(room.game)
            cid = await _send_cmd(b, room.match_id, 1, {"type": "grant_resources", "res": {"wood": 19}})
            await _recv_error(b, "forbidden")
            assert (await _recv_cmd_ack(b, cid))["applied"] is False
            assert room.game == before and room.tick == 0
    asyncio.run(run())


def test_join_by_name_cannot_hijack_slot(live_server):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as attacker:
            await _send(a, {"type": "create_room", "name": "Alice", "max_players": 4})
            state = await _recv_type(a, "room_state")
            token = await _recv_type(a, "reconnect_token")
            room = server.manager.rooms[state["room_code"]]
            original_owner = room.players[0].active_ws
            await _send(attacker, {"type": "join_room", "name": "Alice", "room_code": room.room_code})
            await _recv_error(attacker, "not_found")
            assert room.players[0].active_ws is original_owner
            assert room.players[0].reconnect_token == token["reconnect_token"]
            await _send(attacker, {"type": "set_map", "map_id": "base_12vp"})
            await _recv_error(attacker, "not_found")
    asyncio.run(run())


def test_disconnected_same_name_requires_token():
    m = server.RoomManager()
    room = m.create_room("Alice", 4)
    room.players[0].connected = False
    before = deepcopy(room)
    assert m.join_room(room.room_code, "Alice") is None
    assert room == before
    assert m.join_room(room.room_code, "Bob") is room
    assert room.players[1].name == "Bob"


def test_private_snapshots_are_per_player_and_do_not_alias_engine(live_server):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            room, _, _, _, _ = await start_pair(a, b)
            g = room.game
            g.phase, g.rolled = "main", True
            rules.apply_cmd(g, 0, {"type": "grant_resources", "res": {"wood": 3}})
            rules.apply_cmd(g, 1, {"type": "grant_resources", "res": {"ore": 4}})
            g.players[0].dev_cards = [{"type": "monopoly", "new": False}]
            g.players[1].dev_cards = [{"type": "victory_point", "new": False}]
            g.players[1].vp = 3
            g.pending_gold, g.pending_gold_queue = {0: 1, 1: 2}, [0, 1]
            # noop requests a fresh update without changing gameplay data.
            cid = await _send_cmd(a, room.match_id, 1, {"type": "noop"})
            ma, mb = await _recv_type(a, "match_state"), await _recv_type(b, "match_state")
            await _recv_cmd_ack(a, cid)
            for msg, own, other in ((ma, 0, 1), (mb, 1, 0)):
                state = msg["state"]
                assert state["players"][own]["res"] == g.players[own].res
                assert state["players"][own]["dev_cards"] == g.players[own].dev_cards
                assert "res" not in state["players"][other]
                assert "dev_cards" not in state["players"][other]
                assert state["players"][other]["resource_count"] == sum(g.players[other].res.values())
                assert set(state["pending_gold"]) == {str(own)}
                assert "seed" not in msg and "bank" not in state and "dev_deck" not in state
            assert ma["state"]["players"][1]["vp"] == 2
            assert mb["state"]["players"][1]["vp"] == 3
            view = server._snapshot_state(g, room, 0)
            view["players"][0]["dev_cards"][0]["new"] = True
            assert not g.players[0].dev_cards[0]["new"]
    asyncio.run(run())


def test_match_has_only_present_players_and_setup_finishes(live_server):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            room, _, _, ma, mb = await start_pair(a, b, capacity=4)
            assert len(room.game.players) == 2
            assert ma["state"]["max_players"] == 2
            assert room.game.setup_order == [0, 1, 1, 0]
            clients, seq = {0: a, 1: b}, {0: 0, 1: 0}
            while room.game.phase == "setup":
                pid = room.game.turn
                state = (ma if pid == 0 else mb)["state"]
                other = (mb if pid == 0 else ma)["state"]["legal"]
                assert state["legal"]["pid"] == pid
                assert other["settlements"] == other["roads"] == []
                if state["setup_need"] == "settlement":
                    cmd = {"type": "place_settlement", "vid": state["legal"]["settlements"][0]}
                else:
                    cmd = {"type": "place_road", "eid": state["legal"]["roads"][0]}
                seq[pid] += 1
                cid = await _send_cmd(clients[pid], room.match_id, seq[pid], cmd)
                ma, mb = await _recv_type(a, "match_state"), await _recv_type(b, "match_state")
                assert ma["tick"] == mb["tick"]
                await _recv_cmd_ack(clients[pid], cid)
            assert room.game.turn == 0 and room.tick == 8
    asyncio.run(run())


def test_sparse_lobby_slots_are_remapped_with_tokens(monkeypatch):
    m = server.RoomManager()
    monkeypatch.setattr(server, "manager", m)
    room = m.create_room("Host", 4)
    m.join_room(room.room_code, "Absent")
    m.join_room(room.room_code, "Present")
    host = server.ClientConn(object())
    present = server.ClientConn(object())
    m.connections = {host.ws: host, present.ws: present}
    m.bind_player(host, room, 0)
    m.bind_player(present, room, 2)
    room.players[1].connected = False
    token = room.players[2].reconnect_token
    server._start_match(room)
    assert [p.name for p in room.game.players] == ["Host", "Present"]
    assert present.pid == 1 and room.players[1].reconnect_token == token
    assert room.game.setup_order == [0, 1, 1, 0]
    assert m.join_room(room.room_code, "LateJoin") is None


def test_not_enough_connected_players_does_not_start_match():
    m = server.RoomManager()
    room = m.create_room("Host", 4)
    m.join_room(room.room_code, "Absent")
    room.players[1].connected = False
    before = deepcopy(room)
    with pytest.raises(rules.RuleError):
        server._start_match(room)
    assert room == before


@pytest.mark.parametrize("revoke_second", [False, True])
def test_broadcast_freezes_views_and_checks_slot_owner_before_send(monkeypatch, revoke_second):
    m = server.RoomManager()
    monkeypatch.setattr(server, "manager", m)
    room = m.create_room("Host", 2)
    m.join_room(room.room_code, "Bob")

    class Socket:
        def __init__(self, hook=None):
            self.sent, self.hook = [], hook

        async def send_text(self, message):
            self.sent.append(json.loads(message))
            if self.hook:
                self.hook()

    replacement = server.ClientConn(Socket())

    def during_first_send():
        if revoke_second:
            m.bind_player(replacement, room, 1)
        else:
            room.game.players[1].res["ore"] = 3
            room.tick += 1

    first = server.ClientConn(Socket(during_first_send))
    second = server.ClientConn(Socket())
    m.connections = {c.ws: c for c in (first, second, replacement)}
    m.bind_player(first, room, 0)
    m.bind_player(second, room, 1)
    server._start_match(room)
    asyncio.run(server._send_match_state(room))
    if revoke_second:
        assert not second.ws.sent
    else:
        assert second.ws.sent[0]["tick"] == first.ws.sent[0]["tick"] == 0
        assert second.ws.sent[0]["state"]["players"][1]["res"]["ore"] == 0


def test_rejected_sequence_is_consumed_duplicate_safe_and_reconnectable(live_server):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            room, token, _, _, _ = await start_pair(a, b)
            before = deepcopy(room.game)
            cmd = {"type": "place_settlement", "vid": 99999}
            cid = await _send_cmd(a, room.match_id, 1, cmd)
            await _recv_error(a, "invalid")
            ack = await _recv_cmd_ack(a, cid)
            assert not ack["applied"] and ack["last_seq_applied"] == 1
            assert room.game == before and room.tick == 0
            await _send_cmd(a, room.match_id, 1, cmd, cid)
            assert (await _recv_cmd_ack(a, cid))["duplicate"]
            await _send_cmd(a, room.match_id, 3, {"type": "noop"})
            err = await _recv_error(a, "out_of_order")
            assert err["detail"]["expected_seq"] == 2
            # Token-based reconnect while the old socket is still alive revokes it.
            async with websockets.connect(live_server) as replacement:
                await _send(replacement, {"type": "reconnect", "room_code": room.room_code,
                                          "reconnect_token": token["reconnect_token"]})
                await _recv_type(replacement, "room_state")
                restored = await _recv_type(replacement, "reconnect_token")
                await _recv_type(replacement, "match_state")
                assert restored["last_seq_applied"] == 1
                await _send_cmd(a, room.match_id, 2, {"type": "noop"})
                await _recv_error(a, "not_found")
                cid = await _send_cmd(replacement, room.match_id, 2, {"type": "noop"})
                await _recv_type(replacement, "match_state")
                await _recv_type(b, "match_state")
                assert (await _recv_cmd_ack(replacement, cid))["applied"]
                assert room.tick == 1
                await a.close()
                assert room.players[0].connected
                await _send(replacement, {"type": "rematch"})
                await _recv_type(replacement, "room_state")
                new_token = await _recv_type(replacement, "reconnect_token")
                fresh = await _recv_type(replacement, "match_state")
                assert new_token["last_seq_applied"] == 0 and fresh["tick"] == 0
                cid = await _send_cmd(replacement, room.match_id, 1, {"type": "place_settlement",
                                     "vid": fresh["state"]["legal"]["settlements"][0]})
                await _recv_type(replacement, "match_state")
                assert (await _recv_cmd_ack(replacement, cid))["applied"]
    asyncio.run(run())


@pytest.mark.parametrize("field,value", [("seq", True), ("seq", 0), ("seq", -1),
                                         ("match_id", True), ("cmd_id", "")])
def test_protocol_rejects_invalid_sequence_shape(field, value):
    msg = {"type": "cmd", "match_id": 1, "seq": 1, "cmd_id": "valid", "cmd": {"type": "noop"}}
    msg[field] = value
    assert not net_protocol.validate_client_message(msg)["ok"]


def test_web_join_reconnect_against_live_server(live_server):
    node = shutil.which("node")
    web = Path(__file__).resolve().parents[1] / "web"
    if not node or not (web / "node_modules/typescript").is_dir():
        pytest.skip("Web integration requires Node and installed web dependencies")
    native_ws = subprocess.run([node, "-p", "typeof WebSocket"], capture_output=True, text=True, timeout=5)
    if native_ws.stdout.strip() != "function":
        pytest.skip("Web integration requires Node's native WebSocket")
    result = subprocess.run(
        [node, "--test", "tests/wsClient.test.mjs"], cwd=web,
        env={**os.environ, "CATAN_TEST_WS_URL": live_server},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_ws_pirate_action_and_replays_steal_only_once(live_server, pirate_game):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            room, _, _, _, _ = await start_pair(a, b)
            room.game = pirate_game
            g = room.game
            begin_movement(g, "knight")
            tile, other = pirate_targets(g)[:2]
            cmd = {"type": "move_pirate", "tile": tile, "victim": 1}
            before = deepcopy(g)
            cid = await _send_cmd(a, room.match_id, 1, cmd)
            ma, mb = await _recv_type(a, "match_state"), await _recv_type(b, "match_state")
            assert (await _recv_cmd_ack(a, cid))["applied"]
            assert ma["tick"] == mb["tick"] == room.tick == 1
            for msg in (ma, mb):
                assert msg["state"]["pirate_tile"] == tile
                assert msg["state"]["pending_action"] is None
                assert msg["state"]["pending_pid"] is None
            assert sum(g.players[0].res.values()) == sum(before.players[0].res.values()) + 1
            assert sum(g.players[1].res.values()) == sum(before.players[1].res.values()) - 1
            before = deepcopy(g)
            # A transport replay is acknowledged without invoking a second action.
            await _send_cmd(a, room.match_id, 1, cmd, cid)
            assert (await _recv_cmd_ack(a, cid))["duplicate"]
            assert g == before and room.tick == 1
            # A fresh command identity still cannot reuse the completed event.
            cid = await _send_cmd(a, room.match_id, 2,
                                  {"type": "move_pirate", "tile": other, "victim_pid": 1})
            await _recv_error(a, "illegal")
            ack = await _recv_cmd_ack(a, cid)
            assert not ack["applied"] and ack["last_seq_applied"] == 2
            assert g == before and room.tick == 1
    asyncio.run(run())


def test_ws_vp_stays_private_until_game_over_then_reveals_all_totals(live_server):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            room, _, _, _, _ = await start_pair(a, b)
            g = room.game
            finish_setup(g)
            g.rules_config.target_vp = 4
            # Arrange legal purchases of known cards without exposing a debug WS API.
            g.dev_deck = [c for c in g.dev_deck if c != "victory_point"] + ["victory_point"] * 5
            for pid, qty in ((0, 2), (1, 1)):
                rules.apply_cmd(g, pid, {"type": "grant_resources",
                                       "res": {"sheep": qty, "wheat": qty, "ore": qty}})
            for pid in (0, 1):
                rules.apply_cmd(g, pid, {"type": "roll", "roll": 2})
                rules.apply_cmd(g, pid, {"type": "buy_dev"})
                rules.apply_cmd(g, pid, {"type": "end_turn"})
            rules.apply_cmd(g, 0, {"type": "roll", "roll": 2})
            before = deepcopy(g)
            cid = await _send_cmd(a, room.match_id, 1, {"type": "noop"})
            active = [await _recv_type(client, "match_state") for client in (a, b)]
            assert (await _recv_cmd_ack(a, cid))["applied"] and g == before
            assert [p["vp"] for p in active[0]["state"]["players"]] == [3, 2]
            assert [p["vp"] for p in active[1]["state"]["players"]] == [2, 3]
            # The winning purchase uses the production command path and real game_over.
            cid = await _send_cmd(a, room.match_id, 2, {"type": "buy_dev"})
            final = [await _recv_type(client, "match_state") for client in (a, b)]
            assert (await _recv_cmd_ack(a, cid))["applied"]
            assert g.game_over and g.winner_pid == 0
            for own, (during, ended) in enumerate(zip(active, final)):
                assert not during["state"]["game_over"]
                assert ended["state"]["game_over"] and ended["state"]["winner_pid"] == 0
                assert [p["vp"] for p in ended["state"]["players"]] == [4, 3]
                assert ended["state"]["players"][own]["dev_cards"] == g.players[own].dev_cards
                for msg in (during, ended):
                    other = msg["state"]["players"][1 - own]
                    assert "dev_cards" not in other and "res" not in other
                    assert "bank" not in msg["state"] and "dev_deck" not in msg["state"]
                    assert "seed" not in msg
    asyncio.run(run())


def test_ws_rematch_drops_disconnected_player_and_preserves_retained_ownership(live_server):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b, \
                websockets.connect(live_server) as c:
            clients = (a, b, c)
            room, tokens = await start_trio(clients)
            old_match = room.match_id
            old_ids = []
            for client in clients:
                old_ids.append(await _send_cmd(client, old_match, 1, {"type": "noop"}))
                for recipient in clients:
                    await _recv_type(recipient, "match_state")
                assert (await _recv_cmd_ack(client, old_ids[-1]))["applied"]
            await b.close()
            for client in (a, c):
                assert not (await _recv_type(client, "room_state"))["players"][1]["connected"]
            # Before rematch, the disconnected participant can still restore the old slot.
            async with websockets.connect(live_server) as restored:
                await _send(restored, {"type": "reconnect", "room_code": room.room_code,
                                       "reconnect_token": tokens[1]["reconnect_token"]})
                await _recv_type(restored, "room_state")
                token = await _recv_type(restored, "reconnect_token")
                state = await _recv_type(restored, "match_state")
                assert token["pid"] == 1 and token["last_seq_applied"] == 1
                assert state["match_id"] == old_match and state["state"]["you_pid"] == 1
            for client in (a, c):
                assert not (await _recv_type(client, "room_state"))["players"][1]["connected"]
            before = deepcopy(room, {id(p.active_ws): p.active_ws for p in room.players if p.active_ws})
            await _send(c, {"type": "rematch"})
            await _recv_error(c, "forbidden")
            assert room == before
            await _send(a, {"type": "rematch"})
            for new_pid, client in enumerate((a, c)):
                lobby = await _recv_type(client, "room_state")
                token = await _recv_type(client, "reconnect_token")
                state = await _recv_type(client, "match_state")
                assert [p["name"] for p in lobby["players"]] == ["Alice", "Carol"]
                assert token["pid"] == state["state"]["you_pid"] == new_pid
                assert token["reconnect_token"] == tokens[0 if new_pid == 0 else 2]["reconnect_token"]
                assert token["last_seq_applied"] == 0 and token["match_id"] == old_match + 1
                assert state["match_id"] == old_match + 1 and state["tick"] == 0
                assert state["state"]["max_players"] == 2
                assert [p["pid"] for p in state["state"]["players"]] == [0, 1]
                assert [p["name"] for p in state["state"]["players"]] == ["Alice", "Carol"]
            assert room.game.setup_order == [0, 1, 1, 0] and room.max_players == 4
            before = deepcopy(room.game)
            await _send_cmd(a, old_match, 2, {"type": "noop"})
            await _recv_error(a, "invalid")
            assert room.game == before and room.tick == 0 and room.players[0].last_seq_applied == 0
            async with websockets.connect(live_server) as replacement:
                # Removed token cannot steal Carol's compacted pid=1 slot.
                await _send(replacement, {"type": "reconnect", "room_code": room.room_code,
                                          "reconnect_token": tokens[1]["reconnect_token"]})
                await _recv_error(replacement, "forbidden")
                assert room.game == before and room.tick == 0
                await _send(replacement, {"type": "join_room", "room_code": room.room_code, "name": "Carol"})
                await _recv_error(replacement, "not_found")
                await _send(replacement, {"type": "reconnect", "room_code": room.room_code,
                                          "reconnect_token": tokens[2]["reconnect_token"]})
                await _recv_type(replacement, "room_state")
                token = await _recv_type(replacement, "reconnect_token")
                state = await _recv_type(replacement, "match_state")
                assert token["pid"] == state["state"]["you_pid"] == 1
                assert token["last_seq_applied"] == 0 and state["match_id"] == old_match + 1
                await _send_cmd(c, room.match_id, 1, {"type": "noop"})
                await _recv_error(c, "not_found")
                await c.close()
                assert room.players[1].connected
                for client, old_id in ((a, old_ids[0]), (replacement, old_ids[2])):
                    cid = await _send_cmd(client, room.match_id, 1, {"type": "noop"}, old_id)
                    await _recv_type(a, "match_state")
                    await _recv_type(replacement, "match_state")
                    ack = await _recv_cmd_ack(client, cid)
                    assert ack["applied"] and not ack["duplicate"] and ack["last_seq_applied"] == 1
    asyncio.run(run())


def test_insufficient_rematch_preserves_old_game_identity_and_tokens(monkeypatch):
    m = server.RoomManager()
    monkeypatch.setattr(server, "manager", m)
    room = m.create_room("Host", 4)
    m.join_room(room.room_code, "Absent")
    server._start_match(room)
    room.players[1].connected = False
    old_game, before = room.game, deepcopy(room)
    with pytest.raises(rules.RuleError, match="at least 2 connected players"):
        server._start_match(room)
    assert room == before and room.game is old_game


def test_ws_disconnected_host_can_be_replaced_for_rematch(live_server):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b, \
                websockets.connect(live_server) as c:
            room, tokens = await start_trio((a, b, c))
            old_match = room.match_id
            await a.close()
            for client in (b, c):
                assert not (await _recv_type(client, "room_state"))["players"][0]["connected"]
            before = deepcopy(room, {id(p.active_ws): p.active_ws for p in room.players if p.active_ws})
            # Only the first connected participant may become the replacement host.
            await _send(c, {"type": "rematch"})
            await _recv_error(c, "forbidden")
            assert room == before
            await _send(b, {"type": "rematch"})
            for pid, client in enumerate((b, c)):
                state = await _recv_type(client, "room_state")
                token = await _recv_type(client, "reconnect_token")
                match = await _recv_type(client, "match_state")
                assert state["host_pid"] == 0 and match["state"]["you_pid"] == pid
                assert [p["name"] for p in match["state"]["players"]] == ["Bob", "Carol"]
                assert token["reconnect_token"] == tokens[pid + 1]["reconnect_token"]
                assert token["last_seq_applied"] == 0 and match["match_id"] == old_match + 1
            assert room.host_pid == 0 and len(room.game.players) == 2
    asyncio.run(run())
