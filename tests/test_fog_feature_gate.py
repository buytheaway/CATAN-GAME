"""Disabled means no public fog creation, execution, hints or private publication."""
import asyncio
from copy import deepcopy
import json

import pytest
import websockets

from app import server_mp as server, test_tools
from app.engine import rules
from app.engine.exploration import FOG_DISABLED_MESSAGE, FogUnavailableError
from app.engine.legal import board_legal_moves
from app.match_rulesets import CURRENT_RULESET
from tests.test_fog_foundation import fog_game, fog_recipe
from tests.test_multiplayer_basic import _send, _send_cmd, _recv_type, _recv_error
from tests.test_server_authority import live_server


@pytest.mark.parametrize("finished", [False, True])
def test_internal_state_cannot_reach_gameplay_legal_debug_or_rematch(finished):
    g = fog_game()
    g.game_over, g.winner_pid = finished, 0 if finished else None
    room = server.Room("FOGGATE", 2, 0, [server.PlayerSlot(pid=i, name=f"P{i}") for i in range(2)],
                       game=g, status="in_match", ruleset_id=CURRENT_RULESET)
    before = deepcopy(g)
    with pytest.raises(FogUnavailableError): board_legal_moves(g, 0)
    with pytest.raises(FogUnavailableError): server._snapshot_state(g, room, 0)
    with pytest.raises(rules.RuleError) as error: server._start_match(room)
    assert error.value.code == "feature_disabled"
    for action in ({"type": "noop"}, {"type": "roll"},
                   {"type": "test_action", "action": "set_vp", "player": 0, "vp": 12}):
        assert server._apply_cmd(room, 0, action)["code"] == "feature_disabled"
    with pytest.raises(rules.RuleError) as error:
        test_tools.execute(room, {"type": "test_action", "action": "set_vp", "player": 0, "vp": 12})
    assert error.value.code == "feature_disabled" and g == before


def test_direct_start_gate_precedes_seed_generation_and_state_mutation(monkeypatch):
    room = server.Room("FOGSTART", 2, 0,
                       [server.PlayerSlot(pid=i, name=f"P{i}", connected=True) for i in range(2)],
                       selected_map_data=fog_recipe())
    before = deepcopy((room.game, room.players, room.seed, room.match_id, room.match_uuid, room.ruleset_id))
    def forbidden(*args, **kwargs): pytest.fail("Public start must not assign fog or create a new epoch")
    monkeypatch.setattr(server.secrets, "randbits", forbidden)
    with pytest.raises(rules.RuleError) as error: server._start_match(room)
    assert error.value.code == "feature_disabled"
    assert (room.game, room.players, room.seed, room.match_id, room.match_uuid, room.ruleset_id) == before


def test_named_preset_and_custom_json_cannot_bypass_selection_gate(monkeypatch):
    room = server.Room("FOGPRESET", 2, 0, [server.PlayerSlot(pid=i) for i in range(2)])
    initial = deepcopy((room.selected_map_id, room.selected_map_data, room.map_revision))
    monkeypatch.setattr(server, "get_preset_map", lambda _: fog_recipe())
    for request in ({"map_id": "base_standard"}, {"map_data": fog_recipe()}):
        with pytest.raises(rules.RuleError) as error: server._set_map(room, 0, request)
        assert error.value.code == "feature_disabled"
        assert (room.selected_map_id, room.selected_map_data, room.map_revision) == initial


def test_real_websocket_rejections_never_echo_recipe_or_publish_trusted_tiles(live_server):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            await _send(a, {"type": "create_room", "name": "Alice", "max_players": 2})
            created = await _recv_type(a, "room_state")
            await _recv_type(a, "reconnect_token")
            source = fog_recipe()
            source["name"] = "DO_NOT_ECHO_PRIVATE_LAYOUT"
            await _send(a, {"type": "set_map", "map_data": source})
            error = await _recv_error(a, "feature_disabled")
            assert error["code"] == "feature_disabled" and error["message"] == FOG_DISABLED_MESSAGE
            assert "DO_NOT_ECHO_PRIVATE_LAYOUT" not in json.dumps(error)
            assert error["detail"] == {"request_type": "set_map", "request_id": None}
            room = server.manager.rooms[created["room_code"]]
            assert room.game is None and room.selected_map_id == "base_standard" and room.map_revision == 0
            await _send(b, {"type": "join_room", "name": "Bob", "room_code": room.room_code})
            await _recv_type(b, "room_state")
            await _recv_type(b, "reconnect_token")
            await _recv_type(a, "room_state")
            await _send(a, {"type": "start_match"})
            await _recv_type(a, "match_state")
            await _recv_type(b, "match_state")
            assert room.game.scenario.fog is None and room.ruleset_id == CURRENT_RULESET
            # Inject only a trusted server fixture. Public map/start handlers stay real.
            room.game = fog_game()
            before = deepcopy(room.game)
            for action in ({"type": "roll"}, {"type": "test_action", "action": "set_vp", "player": 0, "vp": 12}):
                await _send_cmd(a, room.match_id, 1, action)
                error = await _recv_error(a, "feature_disabled")
                assert error["code"] == "feature_disabled"
                assert error["detail"] == {"request_type": "cmd", "request_id": None}
            for kind in ("rematch", "start_match"):
                await _send(a, {"type": kind})
                assert (await _recv_error(a, "feature_disabled"))["code"] == "feature_disabled"
            assert room.game == before and room.players[0].last_seq_applied == 0
            async with room.lock:
                await server._send_match_state(room)
            for client in (a, b):
                message = await _recv_type(client, "room_state")
                assert message["ruleset_compatibility"]["status"] == "compatibility_required"
                assert {"tiles", "board", "fog", "fog_pool", "state", "seed"}.isdisjoint(message)
    asyncio.run(run())
