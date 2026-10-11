"""Real PG receipts/recovery/ownership, without opening any public Fog gate."""
import asyncio
from copy import deepcopy
from datetime import timedelta
import json

import pytest

from app import server_mp as server, net_protocol
from app.engine import rules
from app.persistence.credentials import utcnow
from app.persistence.recovery import clone_room
from app.match_rulesets import restricted
from tests.test_auth import account, auth_config, connection, http
from tests.test_persistence_postgres import database_url, runtime, command
from tests.test_fog_exploration_recovery import internal_room, internal_command, restart_and_reconnect
from tests.test_match_rulesets import unchanged_match
from tests.test_fog_projection import observable


@pytest.mark.parametrize("setup,kind,free", [(True, "place_road", False), (True, "build_ship", False),
    (False, "place_road", False), (False, "build_ship", False), (False, "place_road", True)])
def test_committed_projection_and_discovery_events_survive_gold_restart_and_lost_ack(database_url, monkeypatch, setup, kind, free):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients, route = await internal_room(coord, setup=setup, kind=kind, free=free)
            request = command(room, clients[0], route)
            await internal_command(coord, room, clients[0], request)
            expected = [server._project_fog_snapshot(room, pid) for pid in (0, 1)]
            assert any(e["type"] == "discover_tile" for e in expected[0]["game_events"])
            assert "assignment_digest" not in json.dumps(expected)
            assert expected[1]["pending_gold"] == {} and expected[1]["pending_gold_queue"] == []
            coord, restored, owner, _ = await restart_and_reconnect(coord, room, clients[0], monkeypatch)
            assert [server._project_fog_snapshot(restored, pid) for pid in (0, 1)] == expected
            assert (await internal_command(coord, restored, owner, request))["duplicate"]
            assert [server._project_fog_snapshot(restored, pid) for pid in (0, 1)] == expected
            before = deepcopy(restored.game_events)
            invalid = command(restored, owner, {"type": "choose_gold", "res": "gold"})
            assert (await internal_command(coord, restored, owner, invalid))["outcome"] == "rejected"
            assert restored.game_events == before
            count = restored.game.pending_gold[0]
            choice = command(restored, owner, {"type": "choose_gold", "res": "ore", "qty": count})
            await internal_command(coord, restored, owner, choice)
            expected = [server._project_fog_snapshot(restored, pid) for pid in (0, 1)]
            assert expected[0]["game_events"][-1]["gained"] == {"ore": count}
            assert "gained" not in expected[1]["game_events"][-1]
            coord, restored, owner, _ = await restart_and_reconnect(coord, restored, owner, monkeypatch)
            assert (await internal_command(coord, restored, owner, choice))["duplicate"]
            assert [server._project_fog_snapshot(restored, pid) for pid in (0, 1)] == expected
            assert not any(m["type"] == "match_state" for m in owner.ws.messages)
    asyncio.run(run())


@pytest.mark.parametrize("stage", ["before_commit", "after_commit"])
def test_discovery_events_and_safe_projection_follow_commit_outcome(database_url, monkeypatch, stage):
    from app.persistence.errors import PersistenceUnavailable
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients, route = await internal_room(coord)
            expected = observable(room, 0)
            request = command(room, clients[0], route)
            def fault(point):
                if point == stage:
                    raise OSError("synthetic projection commit failure")
            coord.repository._test_fault = fault
            if stage == "before_commit":
                with pytest.raises(PersistenceUnavailable):
                    await internal_command(coord, room, clients[0], request)
                assert observable(room, 0) == expected and not room.game_events
            else:
                await internal_command(coord, room, clients[0], request)
                assert any(e["type"] == "discover_tile" for e in room.game_events)
            coord.repository._test_fault = None
            coord, restored, owner, _ = await restart_and_reconnect(coord, room, clients[0], monkeypatch)
            result = await internal_command(coord, restored, owner, request)
            assert result["duplicate"] == (stage == "after_commit")
            assert len(restored.game_events) == 1 + len(restored.game.scenario.fog.discoveries)
            assert not any(m["type"] == "match_state" for c in (*clients, owner) for m in c.ws.messages)
    asyncio.run(run())


@pytest.mark.parametrize("credential", ["expired", "revoked", "takeover"])
def test_open_guest_socket_cannot_get_fog_state_or_enable_trusted_projection(database_url, monkeypatch, credential):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients, route = await internal_room(coord)
            old = clients[0]
            if credential == "takeover":
                replacement = await connection()
                await server._dispatch(replacement, {"type": "reconnect", "room_code": room.room_code,
                                       "reconnect_token": old.ws.latest("reconnect_token")["reconnect_token"]})
            else:
                candidate = clone_room(room)
                if credential == "expired":
                    candidate.players[0].token_expires_at = utcnow() - timedelta(seconds=1)
                else:
                    candidate.players[0].token_revoked_at = utcnow()
                await server._commit(room, candidate)
            assert not server._owns(old, room)
            before = await coord.repository.load(room.id)
            payload = {"type": "cmd", "room_code": room.room_code, "match_id": room.match_id, "seq": 1,
                       "cmd_id": "untrusted-projection", "trusted_fog": True,
                       "cmd": {**route, "trusted_fog": True}}
            with pytest.raises(rules.RuleError) as error:
                await server._dispatch(old, payload)
            assert error.value.code == ("not_found" if credential == "takeover" else "forbidden")
            message = net_protocol.match_state_message(room, server._project_fog_snapshot(room, 0))
            await server._publish_match_state(old, room, 0, room.players[0].id, message)
            await server._send_match_state(room)
            assert not any(m["type"] == "match_state" for c in clients for m in c.ws.messages)
            unchanged_match(before, await coord.repository.load(room.id))
    asyncio.run(run())


def test_claim_account_continue_active_recent_and_nested_map_name_stay_private(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, who = await account(coord, "FogAccount")
            room, clients, _ = await internal_room(coord)
            proof = clients[0].ws.latest("reconnect_token")["reconnect_token"]
            candidate = clone_room(room)
            candidate.selected_map_meta.update(name={"SECRET_ASSIGNMENT": [vars(t) for t in room.game.tiles]},
                                               private_pool="SECRET_ASSIGNMENT")
            await server._commit(room, candidate)
            before = await coord.repository.load(room.id)
            status, recent, _ = await http("/api/reconnect/inspect-many", {"credentials": [
                {"room_code": room.room_code, "reconnect_token": proof}]})
            assert status == 200 and recent["results"][0]["game"]["map_name"] == "Unknown map"
            assert "SECRET_ASSIGNMENT" not in json.dumps(recent)
            status, data, _ = await http("/api/games/claim", {"room_code": room.room_code,
                "reconnect_token": proof, "connection_nonce": clients[0].connection_nonce}, cookie=raw)
            assert status == 200 and data["claimed"] and server._owns(clients[0], room)
            assert not any(m["type"] == "match_state" for m in clients[0].ws.messages)
            status, active, _ = await http("/api/games/active", cookie=raw)
            assert status == 200 and "SECRET_ASSIGNMENT" not in json.dumps(active)
            assert next(g for g in active["games"] if g["room_code"] == room.room_code)["map_name"] == "Unknown map"
            owner = await connection(who)
            await server._dispatch(owner, {"type": "account_continue", "room_code": room.room_code})
            assert server._owns(owner, room) and not server._owns(clients[0], room)
            assert restricted(room) and not any(m["type"] == "match_state" for m in owner.ws.messages)
            assert "SECRET_ASSIGNMENT" not in json.dumps(owner.ws.latest("room_state"))
            # Ownership-only mutations neither rewrite the head nor prune history.
            unchanged_match(before, await coord.repository.load(room.id))
    asyncio.run(run())
