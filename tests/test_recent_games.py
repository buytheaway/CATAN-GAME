"""Guest discovery contract, including HTTP failures without secret-input echo."""
import asyncio
import json
from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import event, update

from app import server_mp as server
from app.persistence import models as m
from app.persistence.coordinator import Coordinator
from app.persistence.credentials import utcnow
from app.persistence.inspection import InspectionLimiter
from app.persistence.recovery import clone_room
from app.persistence.snapshots import encode_snapshot
from tests.test_persistence_postgres import database_url, runtime, pair, Socket, recovered


async def post(credentials=None, *, body=None):
    if body is None:
        body = json.dumps({"credentials": credentials}).encode()
    messages = []
    received = False
    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}
    async def send(message):
        messages.append(message)
    await server.app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                      "method": "POST", "scheme": "http", "path": "/api/reconnect/inspect-many",
                      "raw_path": b"/api/reconnect/inspect-many", "query_string": b"",
                      "headers": [(b"content-type", b"application/json")],
                      "client": ("127.0.0.1", 1234), "server": ("test", 80)}, receive, send)
    start = next(message for message in messages if message["type"] == "http.response.start")
    text = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    assert (b"cache-control", b"no-store") in start["headers"]
    return start["status"], json.loads(text)


def credential(room, pid=0, token=None):
    return {"room_code": room.room_code, "reconnect_token": token or room.players[pid].reconnect_token}


@pytest.fixture
def memory(monkeypatch):
    monkeypatch.setattr(server, "manager", server.RoomManager())
    monkeypatch.setattr(server, "persistence", Coordinator())
    monkeypatch.setattr(server, "inspection_limiter", InspectionLimiter())


def assert_private_summary(result, token, status, *, winner=False):
    assert result["status"] == "available"
    game = result["game"]
    assert set(game) == {"room_code", "map_name", "own_name", "own_color", "player_count", "max_players",
                         "connected_count", "status", "target_vp", "updated_at", "can_continue"} | ({"winner"} if winner else set()) | ({"ruleset_compatibility"} if status != "lobby" else set())
    if status != "lobby":
        assert game["ruleset_compatibility"] == {"status": "compatible", "ruleset_id": server.CURRENT_RULESET,
                                                "current_ruleset_id": server.CURRENT_RULESET}
    assert token not in json.dumps(result)
    assert game["status"] == status
    assert game["own_name"] == "Alice"
    assert game["can_continue"] is True
    if winner:
        assert set(game["winner"]) == {"name", "color"}
    return game


@pytest.mark.parametrize("stage", ["lobby", "active", "game_over"])
def test_memory_safe_summary_and_inspection_has_no_effect(memory, stage):
    async def run():
        room = server.manager.create_room("Alice", 4)
        server.manager.join_room(room.room_code, "Bob")
        if stage != "lobby":
            server._start_match(room)
        if stage == "game_over":
            room.game.game_over, room.game.winner_pid = True, 0
        slot = room.players[0]
        # Paused recovery must not resume, renew or take over merely on inspection.
        room.timer_paused = True
        before = (deepcopy(encode_snapshot(room.game)) if room.game else None,
                  slot.token_expires_at, slot.active_ws, slot.connected, room.durable_revision, room.timer_paused)
        code, response = await post([credential(room)])
        assert code == 200
        game = assert_private_summary(response["results"][0], slot.reconnect_token, stage, winner=stage == "game_over")
        assert (game["player_count"], game["max_players"]) == (2, 4)
        assert before == (encode_snapshot(room.game) if room.game else None,
                          slot.token_expires_at, slot.active_ws, slot.connected, room.durable_revision, room.timer_paused)
    asyncio.run(run())


@pytest.mark.parametrize("reason", ["wrong", "missing", "revoked", "expired", "closed", "room_expired"])
def test_permanent_failure_is_generic_and_only_one_entry_invalid(memory, reason):
    async def run():
        good = server.manager.create_room("Alice", 2)
        bad = server.manager.create_room("Other", 2)
        proof = credential(bad)
        if reason == "wrong": proof["reconnect_token"] = "wrong-secret"
        if reason == "missing": proof["room_code"] = "ABSENT"
        if reason == "revoked": bad.players[0].token_revoked_at = utcnow()
        if reason == "expired": bad.players[0].token_expires_at = utcnow() - timedelta(seconds=1)
        if reason == "closed": bad.status = "closed"
        if reason == "room_expired": bad.expires_at = utcnow() - timedelta(seconds=1)
        code, response = await post([proof, credential(good)])
        assert code == 200
        assert response["results"][0] == {"status": "invalid"}
        assert_private_summary(response["results"][1], good.players[0].reconnect_token, "lobby")
    asyncio.run(run())


@pytest.mark.parametrize("body", [b"null", b"[]", b"broken-secret", b'{"credentials":[]}',
    b'{"credentials":[{"room_code":"ABCDEF","reconnect_token":123,"secret":"never-echo"}]}',
    json.dumps({"credentials": [{"room_code": "ABCDEF", "reconnect_token": "secret"}] * 11}).encode(),
    b'{"credentials":[{"room_code":"ABCDEF","reconnect_token":"\\ud800"}]}'])
def test_malformed_request_never_echoes_credential(memory, body):
    code, response = asyncio.run(post(body=body))
    assert code == 400
    assert response == {"status": "invalid_request"}


def test_bounded_body_rate_limit_and_readiness_are_temporary(memory, monkeypatch):
    async def run():
        code, _ = await post(body=b"sensitive-secret" * 2000)
        assert code == 413
        monkeypatch.setattr(server, "inspection_limiter", InspectionLimiter(limit=1))
        code, _ = await post([{ "room_code": "ABCDEF", "reconnect_token": "secret" }])
        assert code == 200
        code, response = await post([])
        assert (code, response) == (429, {"status": "temporarily_unavailable"})
        monkeypatch.setattr(server, "inspection_limiter", InspectionLimiter())
        server.persistence.ready = False
        assert await post([]) == (503, {"status": "temporarily_unavailable"})
    asyncio.run(run())


@pytest.mark.parametrize("stage", ["lobby", "active", "game_over"])
def test_postgres_metadata_only_query_and_unchanged_recovery(database_url, monkeypatch, stage):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            monkeypatch.setattr(server, "inspection_limiter", InspectionLimiter())
            room, clients = await pair()
            if stage == "lobby":
                other = server.ClientConn(Socket())
                server.manager.connections[other.ws] = other
                await server._dispatch(other, {"type": "create_room", "name": "Alice", "max_players": 4})
                room = server.manager.rooms[other.room_code]
            if stage == "game_over":
                candidate = clone_room(room)
                candidate.game.game_over, candidate.game.winner_pid = True, 0
                await server._commit(room, candidate, snapshot=True)
            before = await coord.repository.load(room.id)
            statements = []
            def capture(_, __, statement, ___, ____, _____): statements.append(statement)
            event.listen(coord.database.engine.sync_engine, "before_cursor_execute", capture)
            try:
                code, response = await post([credential(room), credential(room, token="wrong")])
            finally:
                event.remove(coord.database.engine.sync_engine, "before_cursor_execute", capture)
            assert code == 200
            game = assert_private_summary(response["results"][0], room.players[0].reconnect_token, stage, winner=stage == "game_over")
            assert game["map_name"] == room.selected_map_meta["name"]
            assert response["results"][1] == {"status": "invalid"}
            assert len(statements) == 1
            assert "game_snapshots" not in statements[0] and "chat_history" not in statements[0]
            assert before == await coord.repository.load(room.id)
    asyncio.run(run())


@pytest.mark.parametrize("reason", ["revoked", "expired", "closed", "retired", "room_expired", "quarantined"])
def test_postgres_lifecycle_results(database_url, monkeypatch, reason):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            monkeypatch.setattr(server, "inspection_limiter", InspectionLimiter())
            room, clients = await pair()
            proof = credential(room)
            async with coord.database.sessions() as session, session.begin():
                if reason == "revoked": await session.execute(update(m.seat_tokens).where(m.seat_tokens.c.room_player_id == room.players[0].id).values(revoked_at=utcnow()))
                if reason == "expired": await session.execute(update(m.seat_tokens).where(m.seat_tokens.c.room_player_id == room.players[0].id).values(expires_at=utcnow() - timedelta(seconds=1)))
                if reason == "retired": await session.execute(update(m.room_players).where(m.room_players.c.id == room.players[0].id).values(status="retired", current_pid=None))
                if reason in ("closed", "quarantined"): await session.execute(update(m.rooms).where(m.rooms.c.id == room.id).values(status=reason))
                if reason == "room_expired": await session.execute(update(m.rooms).where(m.rooms.c.id == room.id).values(expires_at=utcnow() - timedelta(seconds=1)))
            code, response = await post([proof])
            assert code == 200
            assert response == {"results": [{"status": "temporarily_unavailable" if reason == "quarantined" else "invalid"}]}
    asyncio.run(run())


def test_postgres_rematch_name_truth_compact_pid_and_read_failure(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            monkeypatch.setattr(server, "inspection_limiter", InspectionLimiter())
            room, clients = await pair(names=("Alice", "Gone", "Carol"))
            proof = credential(room, 2)
            removed = credential(room, 1)
            candidate = clone_room(room)
            candidate.players[2].name = "Server Carol"
            await server._commit(room, candidate)
            server.manager.leave_room(clients[1])
            await server._dispatch(clients[0], {"type": "rematch", "expected_match_id": 1, "request_id": "inspect-rematch"})
            code, response = await post([proof, removed])
            assert code == 200
            summary = response["results"][0]["game"]
            assert summary["own_name"] == "Server Carol" and summary["player_count"] == 2
            assert response["results"][1] == {"status": "invalid"}
            assert clients[2].pid == 1
            restored = await recovered(coord, room)
            server.manager.rooms[room.room_code] = restored
            code, response = await post([proof])
            assert response["results"][0]["game"]["connected_count"] == 0
            assert restored.timer_paused == (restored.timer is not None)
            async def failed(*_): raise RuntimeError("secret must not be emitted")
            monkeypatch.setattr(coord.repository, "inspect_credentials", failed)
            assert await post([proof]) == (503, {"status": "temporarily_unavailable"})
    asyncio.run(run())
