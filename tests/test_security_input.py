"""SEC-01 regressions: real localhost WebSockets and isolated PostgreSQL.

The shared database_url fixture rejects non-test database names.
"""
import asyncio
import json
import socket
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from copy import deepcopy

import pytest
import uvicorn
import websockets
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app import net_protocol, server_mp as server
from app.engine import get_preset_map, maps, rules
from app.persistence import models as m
from app.persistence.db import Database
from app.persistence.recovery import room_config
from tests.test_multiplayer_basic import _find_free_port, _recv_type, _send
from tests.test_persistence_postgres import database_url, runtime
from tests.test_server_authority import start_pair


@asynccontextmanager
async def live_postgres(url, monkeypatch):
    monkeypatch.setenv("CATAN_AUTH_MODE", "development")
    monkeypatch.setenv("CATAN_AUTH_ORIGINS", "http://test")
    async with runtime(url, monkeypatch) as coordinator:
        port = _find_free_port()
        instance = uvicorn.Server(uvicorn.Config(
            server.app, host="127.0.0.1", port=port, lifespan="off", log_level="critical"))
        task = asyncio.create_task(instance.serve())
        try:
            for _ in range(100):
                if instance.started:
                    break
                if task.done():
                    await task
                    raise AssertionError("Local test server did not start")
                await asyncio.sleep(.02)
            assert instance.started
            yield f"ws://127.0.0.1:{port}/ws", f"http://127.0.0.1:{port}", coordinator
        finally:
            instance.should_exit = True
            await asyncio.wait_for(task, 5)


async def receive(ws, *kinds):
    async with asyncio.timeout(5):
        while True:
            message = json.loads(await ws.recv())
            if message.get("type") in kinds:
                return message


async def health(base):
    def get():
        try:
            with urllib.request.urlopen(base + "/health", timeout=3) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code
    return await asyncio.to_thread(get)


def envelope(room, cmd, seq=1, cmd_id="security-input"):
    return {"type": "cmd", "room_code": room.room_code, "match_id": room.match_id,
            "seq": seq, "cmd_id": cmd_id, "cmd": cmd}


@pytest.mark.parametrize("case", ["guest_nul", "dev_g", "map_limit"])
def test_original_inputs_do_not_disable_persistence_or_other_rooms(database_url, monkeypatch, case):
    async def run():
        async with live_postgres(database_url, monkeypatch) as (url, base, coord):
            async with (websockets.connect(url) as control, websockets.connect(url) as control_peer,
                        websockets.connect(url) as attacker, websockets.connect(url) as attack_peer):
                other, *_ = await start_pair(control, control_peer)
                room = None
                if case == "dev_g":
                    room, *_ = await start_pair(attack_peer, attacker)
                    payload = envelope(room, {"type": "play_dev", "card": "knight", "g": {}})
                elif case == "map_limit":
                    await _send(attacker, {"type": "create_room", "name": "Map host", "max_players": 2})
                    state = await _recv_type(attacker, "room_state")
                    await _recv_type(attacker, "reconnect_token")
                    room = server.manager.rooms[state["room_code"]]
                    source = deepcopy(get_preset_map("base_standard"))
                    source.setdefault("rules", {})["max_roads"] = []
                    payload = {"type": "set_map", "map_id": "invalid-limit", "map_data": source}
                else:
                    payload = {"type": "create_room", "name": "bad\x00name", "max_players": 2}
                async with coord.database.sessions() as session:
                    count_before = await session.scalar(select(func.count()).select_from(m.rooms))
                before = await coord.repository.load(room.id) if room else None
                domain_before = deepcopy(room.game) if room else None
                config_before = deepcopy(room_config(room)) if room else None
                # Send the exact original payload over TCP, without client-side validation.
                await attacker.send(json.dumps(payload))
                error = await receive(attacker, "error")
                health_after = await health(base)
                await _send(control, envelope(other, {"type": "noop"}, cmd_id="control-after-rejection"))
                control_result = await receive(control, "cmd_ack", "error")
                print({"case": case, "error": error["code"], "health": health_after,
                       "other_room": control_result.get("applied", control_result.get("code"))})
                assert error["code"] == "invalid"
                assert health_after == 200 and coord.ready and not other.persistence_blocked
                assert control_result["type"] == "cmd_ack" and control_result["applied"]
                if room:
                    assert not room.persistence_blocked and room.game == domain_before
                    assert room_config(room) == config_before
                    assert await coord.repository.load(room.id) == before
                async with coord.database.sessions() as session:
                    assert await session.scalar(select(func.count()).select_from(m.rooms)) == count_before
                # A malformed intent consumes no sequence and leaves the socket usable.
                if case == "dev_g":
                    await _send(attacker, envelope(room, {"type": "noop"}, cmd_id="valid-after-malformed"))
                    assert (await receive(attacker, "cmd_ack"))["applied"]
                elif case == "map_limit":
                    await _send(attacker, {"type": "set_map", "map_id": "base_12vp"})
                    assert (await _recv_type(attacker, "room_state"))["map_id"] == "base_12vp"
                else:
                    await _send(attacker, {"type": "create_room", "name": "Valid guest", "max_players": 2})
                    assert (await _recv_type(attacker, "room_state"))["status"] == "lobby"
    asyncio.run(run())


@pytest.mark.parametrize("payload", [
    {"type": "create_room", "name": "x\x00y"},
    {"type": "join_room", "room_code": "ROOM", "name": "x\ny"},
    {"type": "create_room", "name": "\ud800"},
    {"type": "create_room", "name": "x" * 33},
    {"type": "chat", "text": "x\x00y"},
    {"type": "set_map", "map_data": {"nested": {"x\x00key": "y"}}},
    {"type": "set_map", "map_data": {"nested": ["\udfff"]}},
    {"type": "set_map", "map_id": "base_standard", "request_id": []},
    {"type": "set_map", "map_id": {}},
    {"type": "set_settings", "settings": {"value": float("nan")}},
])
def test_storage_incompatible_protocol_values_are_controlled_errors(payload):
    assert net_protocol.validate_client_message(payload)["error"]["code"] == "invalid"


@pytest.mark.parametrize("name", ["Alice", "  Alice  ", "Player 2", "\u0410\u043b\u0438\u0441\u0430", "Player \U0001f431"])
def test_valid_guest_names_remain_supported(name):
    assert net_protocol.validate_client_message({"type": "create_room", "name": name})["ok"]


@pytest.mark.parametrize("cmd", [
    {"type": "play_dev", "card": "knight", "g": {}},
    {"type": "play_dev", "card": "knight", "card_type": "knight"},
    {"type": "play_dev", "card": []},
    {"type": "play_dev", "card": "year_of_plenty", "a": [], "qa": 1},
    {"type": "play_dev", "card": "year_of_plenty", "qa": True},
    {"type": "play_dev", "card": "monopoly", "r": {}},
    {"type": "place_settlement", "vid": [], "setup": True},
    {"type": "place_road", "eid": [0, True]},
    {"type": "build_ship", "eid": [0, 1], "free": []},
    {"type": "move_ship", "from_eid": [0], "to_eid": [1, 2]},
    {"type": "move_robber", "tile": [], "victim": 1},
    {"type": "move_pirate", "tile": 0, "victim": {}},
    {"type": "discard", "discards": {"wood": []}},
    {"type": "choose_gold", "res": "wood", "qty": True},
    {"type": "trade_bank", "give": [], "get": "ore"},
    {"type": "trade_offer_create", "give": {"wood": True}, "get": {"ore": 1}},
    {"type": "trade_offer_accept", "offer_id": {}},
])
def test_nested_command_types_rejected_before_execution(cmd):
    message = {"type": "cmd", "match_id": 1, "seq": 1, "cmd_id": "input", "cmd": cmd}
    assert net_protocol.validate_client_message(message)["error"]["code"] == "invalid"


@pytest.mark.parametrize("key", ["max_roads", "max_settlements", "max_cities", "max_ships"])
@pytest.mark.parametrize("location", ["top", "limits", "limits_alias"])
def test_map_limit_aliases_validate_before_conversion(key, location):
    config = {key: []} if location == "top" else {"limits": {
        key if location == "limits_alias" else key.removeprefix("max_"): []}}
    source = deepcopy(get_preset_map("base_standard"))
    source["rules"] = config
    before = deepcopy(source)
    with pytest.raises(maps.MapValidationError):
        maps.validate_map_data(source)
    with pytest.raises(rules.RuleError) as exc:
        rules.parse_rules_config(config)
    assert exc.value.code == "invalid" and source == before


@pytest.mark.parametrize("config", [
    {"target_vp": True}, {"robber_count": "1"}, {"limits": []},
    {"discard_threshold": []}, {"enable_seafarers": 1},
    {"enable_pirate": "true"}, {"enable_gold": None}, {"enable_move_ship": {}},
])
def test_map_rule_types_are_strict(config):
    with pytest.raises(rules.RuleError) as exc:
        rules.parse_rules_config(config)
    assert exc.value.code == "invalid"


def test_engine_dev_dispatch_rejects_injected_kwargs_without_mutation():
    game = rules.build_game(1, 2)
    game.phase, game.turn = "main", 0
    game.players[0].dev_cards = [{"type": "knight", "new": False}]
    before = deepcopy(game)
    with pytest.raises(rules.RuleError) as exc:
        rules.apply_cmd(game, 0, {"type": "play_dev", "card": "knight", "g": {}})
    assert exc.value.code == "invalid" and game == before


@pytest.mark.parametrize("raw", [
    "{", "NaN", '{"type":"chat","text":"\\ud800"}',
    "[" * 1100 + "0" + "]" * 1100,
    '{"type":"chat","text":"bad\\u0000text"}',
])
def test_raw_invalid_json_and_storage_values_leave_socket_healthy(database_url, monkeypatch, raw):
    async def run():
        async with live_postgres(database_url, monkeypatch) as (url, base, coord):
            async with websockets.connect(url) as ws:
                await ws.send(raw)
                assert (await receive(ws, "error"))["code"] == "invalid"
                assert coord.ready and await health(base) == 200
                await _send(ws, {"type": "create_room", "name": "Healthy", "max_players": 2})
                assert (await _recv_type(ws, "room_state"))["status"] == "lobby"
    asyncio.run(run())


@pytest.mark.parametrize("stage", ["write", "receipt_read"])
def test_real_postgres_connection_failure_still_fences_unsafe_operations(database_url, monkeypatch, stage):
    def canonical_bundle(bundle):
        # Repository.load's relational SELECTs have no ORDER BY. Compare full
        # rows by their primary keys, keeping every field and payload array.
        return {**bundle,
                "members": sorted(bundle["members"], key=lambda row: row["id"]),
                "participants": sorted(bundle["participants"], key=lambda row: row["id"]),
                "receipts": sorted(bundle["receipts"], key=lambda row: (row["match_player_id"], row["seq"]))}

    async def run():
        async with live_postgres(database_url, monkeypatch) as (url, base, coord):
            async with websockets.connect(url) as ws, websockets.connect(url) as peer:
                room, *_ = await start_pair(ws, peer)
                request = envelope(room, {"type": "noop"})
                if stage == "receipt_read":
                    await _send(ws, request)
                    assert (await receive(ws, "cmd_ack"))["applied"]
                before = canonical_bundle(await coord.repository.load(room.id))
                domain_before, tick = deepcopy(room.game), room.tick
                # Reserve an unreachable local port; this is an actual TCP failure,
                # not a mocked DB exception and not an outage of the user's DB.
                with socket.socket() as reserved:
                    reserved.bind(("127.0.0.1", 0))
                    unavailable = Database(make_url(database_url).set(port=reserved.getsockname()[1]))
                    coord.repository.db = unavailable
                    try:
                        await _send(ws, request)
                        error = await receive(ws, "error")
                        assert error["code"] == "persistence_unavailable"
                        assert not coord.ready and room.persistence_blocked and await health(base) == 503
                        assert room.game == domain_before and room.tick == tick
                        await _send(peer, envelope(room, {"type": "noop"}, cmd_id="no-unsafe-fallback"))
                        assert (await receive(peer, "error"))["code"] == "persistence_unavailable"
                    finally:
                        coord.repository.db = coord.database
                        await unavailable.close()
                assert canonical_bundle(await coord.repository.load(room.id)) == before
    asyncio.run(run())


def test_domain_rejection_remains_durable_and_reconnect_keeps_consumed_sequence(database_url, monkeypatch):
    async def run():
        async with live_postgres(database_url, monkeypatch) as (url, base, coord):
            async with websockets.connect(url) as ws, websockets.connect(url) as peer:
                room, token, *_ = await start_pair(ws, peer)
                before = deepcopy(room.game), room.tick
                request = envelope(room, {"type": "place_settlement", "vid": -1, "setup": True})
                send_ack = server._send_cmd_ack
                async def committed_ack(socket, *args, **kwargs):
                    bundle = await coord.repository.load(room.id)
                    assert bundle["receipts"][-1]["outcome"] == "rejected"
                    assert bundle["receipts"][-1]["cmd_id"] == request["cmd_id"]
                    await send_ack(socket, *args, **kwargs)
                monkeypatch.setattr(server, "_send_cmd_ack", committed_ack)
                await _send(ws, request)
                assert (await receive(ws, "error"))["code"] == "invalid"
                ack = await receive(ws, "cmd_ack")
                assert not ack["applied"] and ack["last_seq_applied"] == 1
                assert (room.game, room.tick) == before and coord.ready and await health(base) == 200
                async with websockets.connect(url) as replacement:
                    await _send(replacement, {"type": "reconnect", "room_code": room.room_code,
                                              "reconnect_token": token["reconnect_token"]})
                    restored = await receive(replacement, "reconnect_token")
                    assert restored["last_seq_applied"] == 1
                    await _send(replacement, request)
                    duplicate = await receive(replacement, "cmd_ack")
                    assert duplicate["duplicate"] and not duplicate["applied"]
                    assert (room.game, room.tick) == before
    asyncio.run(run())


def test_unexpected_server_bug_is_not_relabelled_as_persistence_outage(database_url, monkeypatch):
    class EndpointSocket:
        headers, cookies = {}, {}
        async def accept(self):
            pass
        async def receive_text(self):
            return json.dumps({"type": "hello", "version": 1, "name": "Valid"})

    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            async def unexpected(*args):
                raise TypeError("synthetic programming error")
            monkeypatch.setattr(server, "_dispatch", unexpected)
            with pytest.raises(TypeError, match="synthetic programming error"):
                await server.websocket_endpoint(EndpointSocket())
            assert coord.ready and not server.manager.connections
    asyncio.run(run())
