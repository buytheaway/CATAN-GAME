"""Explicit lobby closure is distinct from disconnect and match abandonment."""
import asyncio
import uuid
from datetime import timedelta

import pytest

from app import net_protocol, server_mp as server
from app.engine import RuleError
from app.persistence.credentials import utcnow, valid_token
from tests.test_room_creation_limits import configure, client, create


def close_request(room):
    return {"type": "close_room", "room_code": room.room_code,
            "request_id": str(uuid.uuid4()), "expected_match_id": 0}


async def lobby(peer="198.51.100.30"):
    host, guest = client(peer), client("198.51.100.31")
    room = await create(host)
    await server._dispatch(guest, {"type": "join_room", "room_code": room.room_code, "name": "Participant"})
    return room, host, guest


def test_close_protocol_requires_a_bound_room_and_request_not_client_identity():
    payload = {"type": "close_room", "room_code": "ABC123", "request_id": "close-1", "expected_match_id": 0}
    assert net_protocol.validate_client_message(payload)["ok"]
    invalid = [dict(payload, pid=0), dict(payload, reconnect_token="proof"),
               dict(payload, expected_match_id=True), dict(payload, expected_match_id=1),
               dict(payload, room_code=""), dict(payload, request_id=""),
               {k: v for k, v in payload.items() if k != "request_id"}]
    assert all(not net_protocol.validate_client_message(message)["ok"] for message in invalid)


def test_host_close_notifies_participants_and_fences_room_without_touching_other_lobby(monkeypatch):
    configure(monkeypatch, rate=20, lobbies=1)
    async def run():
        room, host, guest = await lobby()
        other = await create(client("198.51.100.32"))
        request = close_request(room)
        await server._dispatch(host, request)
        assert room.status == "closed" and room.closed_at is not None and room.game is None
        assert room.room_code not in server.manager.rooms and other.room_code in server.manager.rooms
        for conn in (host, guest):
            closed = conn.ws.messages[-1]
            assert closed == {"type": "room_closed", "room_code": room.room_code, "request_id": request["request_id"]}
            assert conn.room_code is None and conn.pid is None
        assert all(not p.connected and p.active_ws is None for p in room.players)
        assert not valid_token(room.players[0], host.ws.messages[1]["reconnect_token"])
        with pytest.raises(RuleError):
            await server._dispatch(host, request)  # Safe repeat, no room recreation.
        assert room.game is None and other.status == "lobby"
        await create(client("198.51.100.30"))  # Explicit closure releases origin capacity.
    asyncio.run(run())


@pytest.mark.parametrize("intruder", ["participant", "unbound", "stale", "expired", "revoked"])
def test_unauthorized_closure_does_not_mutate_lobby(monkeypatch, intruder):
    configure(monkeypatch, rate=20)
    async def run():
        room, host, guest = await lobby()
        conn = guest if intruder == "participant" else host
        if intruder == "unbound":
            conn = client()
        if intruder == "stale":
            fresh = client()
            await server._dispatch(fresh, {"type": "reconnect", "room_code": room.room_code,
                                          "reconnect_token": room.players[0].reconnect_token})
        elif intruder == "expired":
            room.players[0].token_expires_at = utcnow() - timedelta(seconds=1)
        elif intruder == "revoked":
            room.players[0].token_revoked_at = utcnow()
        revision = room.durable_revision
        with pytest.raises(RuleError):
            await server._dispatch(conn, close_request(room))
        assert room.status == "lobby" and room.closed_at is None and room.durable_revision == revision
        assert not any(msg["type"] == "room_closed" for c in (host, guest) for msg in c.ws.messages)
    asyncio.run(run())


@pytest.mark.parametrize("finished", [False, True])
def test_close_cannot_abandon_active_or_finished_match(monkeypatch, finished):
    from app.persistence.snapshots import encode_snapshot
    configure(monkeypatch, rate=20)
    async def run():
        room, host, _ = await lobby()
        await server._dispatch(host, {"type": "start_match"})
        room.game.game_over = finished
        before = encode_snapshot(room.game)
        revision = room.durable_revision
        with pytest.raises(RuleError):
            await server._dispatch(host, close_request(room))
        assert room.status == "in_match" and room.durable_revision == revision
        assert encode_snapshot(room.game) == before
    asyncio.run(run())


def test_disconnect_keeps_lobby_and_reconnect_but_wrong_room_close_is_rejected(monkeypatch):
    configure(monkeypatch, rate=20)
    async def run():
        room, host, _ = await lobby()
        token = room.players[0].reconnect_token
        await server._dispatch(host, {"type": "leave_room"})
        assert room.status == "lobby" and valid_token(room.players[0], token)
        fresh = client()
        await server._dispatch(fresh, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": token})
        request = close_request(room)
        request["room_code"] = "OTHER"
        with pytest.raises(RuleError):
            await server._dispatch(fresh, request)
        assert room.status == "lobby" and server._owns(fresh, room)
    asyncio.run(run())


def test_queued_join_cannot_resurrect_room_after_close(monkeypatch):
    configure(monkeypatch, rate=20)
    async def run():
        room = await create(client())
        host = server.manager.connections[room.players[0].active_ws]
        waiting = client("198.51.100.33")
        await room.lock.acquire()
        closing = asyncio.create_task(server._dispatch(host, close_request(room)))
        joining = asyncio.create_task(server._dispatch(waiting, {"type": "join_room", "room_code": room.room_code, "name": "Late"}))
        await asyncio.sleep(0)
        room.lock.release()
        results = await asyncio.gather(closing, joining, return_exceptions=True)
        assert results[0] is None and isinstance(results[1], RuleError)
        assert room.room_code not in server.manager.rooms and waiting.room_code is None
    asyncio.run(run())
