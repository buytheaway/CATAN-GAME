"""Real PostgreSQL lifecycle, authorization, quota and failure boundaries."""
import asyncio
import json
from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import update

from app import server_mp as server
from app.engine import RuleError
from app.auth.security import AuthError
from app.persistence import models as m
from app.persistence.coordinator import Coordinator
from app.persistence.credentials import utcnow, valid_token
from app.persistence.errors import PersistenceUnavailable
from app.persistence.recovery import clone_room
from tests.test_auth import account, http
from tests.test_lobby_lifecycle import close_request
from tests.test_persistence_postgres import database_url, runtime, pair
from tests.test_room_creation_limits import configure, client, create
from tests.test_room_creation_postgres import counts, lobby_count, origin


def test_guest_closure_commit_before_notice_durable_quota_release_and_restart(database_url, monkeypatch):
    configure(monkeypatch, rate=20, lobbies=1)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            peer = origin()
            server.manager.creation_limits = replace(server.manager.creation_limits, lobbies_global=await lobby_count(coord) + 1)
            host, guest = client(peer), client(origin())
            room = await create(host)
            await server._dispatch(guest, {"type": "join_room", "room_code": room.room_code, "name": "Participant"})
            proofs = [(room.room_code, p.reconnect_token) for p in room.players]
            request = close_request(room)
            before = await counts(coord)
            original_send = host.ws.send_text
            async def observe(raw):
                if json.loads(raw)["type"] == "room_closed":
                    bundle = await coord.repository.load(room.id)
                    receipt = await coord.repository.operation(room.id, request["request_id"])
                    assert bundle["room"]["status"] == "closed" and receipt["kind"] == "close_room"
                    assert all(t["revoked_at"] == bundle["room"]["closed_at"] for t in bundle["tokens"].values())
                await original_send(raw)
            monkeypatch.setattr(host.ws, "send_text", observe)
            await server._dispatch(host, request)
            closed = await coord.repository.load(room.id)
            assert closed["match"] is None and closed["head"] is None
            assert await counts(coord) == (*before[:-1], before[-1] + 1)
            assert guest.ws.messages[-1]["type"] == "room_closed"
            with pytest.raises(RuleError):
                await server._dispatch(host, request)
            assert await coord.repository.load(room.id) == closed
            results = await coord.repository.inspect_credentials(server.manager, proofs)
            assert results == [{"status": "invalid"}, {"status": "invalid"}]
            manager, fresh = server.RoomManager(), Coordinator(coord.database)
            await fresh.initialize(manager)
            monkeypatch.setattr(server, "manager", manager)
            monkeypatch.setattr(server, "persistence", fresh)
            assert room.room_code not in manager.rooms and room.room_code in fresh.reserved_codes
            for request_type in ("join_room", "reconnect", "start_match"):
                outsider = client(peer)
                payload = {"type": request_type, "room_code": room.room_code, "name": "Guest",
                           "reconnect_token": proofs[0][1]}
                with pytest.raises(RuleError):
                    await server._dispatch(outsider, payload)
            assert await coord.repository.load(room.id) == closed
            new = await create(client(peer))
            assert new.id != room.id and new.status == "lobby" and fresh.ready
    asyncio.run(run())


@pytest.mark.parametrize("ownership", ["native", "claimed"])
def test_account_host_closes_with_current_session_and_disappears_from_active_games(database_url, monkeypatch, ownership):
    configure(monkeypatch, rate=20)
    monkeypatch.setenv("CATAN_AUTH_MODE", "development")
    monkeypatch.setenv("CATAN_AUTH_ORIGINS", "http://test")
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, who = await account(coord)
            host = client(origin())
            if ownership == "native":
                server.set_account_context(host, who)
            room = await create(host)
            if ownership == "claimed":
                proof = room.players[0].reconnect_token
                status, _, _ = await http("/api/games/claim", {"room_code": room.room_code,
                    "reconnect_token": proof, "connection_nonce": host.connection_nonce}, cookie=raw)
                assert status == 200 and host.user_id == who["user_id"]
                assert not valid_token(room.players[0], proof)
            status, body, _ = await http("/api/games/active", cookie=raw)
            assert status == 200 and any(g["room_code"] == room.room_code for g in body["games"])
            await server._dispatch(host, close_request(room))
            status, body, _ = await http("/api/games/active", cookie=raw)
            assert status == 200 and not any(g["room_code"] == room.room_code for g in body["games"])
            reconnect = client(origin())
            server.set_account_context(reconnect, who)
            with pytest.raises(RuleError) as rejected:
                await server._dispatch(reconnect, {"type": "account_continue", "room_code": room.room_code})
            assert rejected.value.code == "seat_not_owned"
            status, me, _ = await http("/api/auth/me", cookie=raw)
            assert status == 200 and me["authenticated"]
            await create(reconnect)  # Account/session kept; no surrender or account deletion.
    asyncio.run(run())


@pytest.mark.parametrize("credential", ["expired", "revoked"])
def test_guest_closure_revalidates_durable_credential_even_if_socket_cache_is_valid(database_url, monkeypatch, credential):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            host = client(origin())
            room = await create(host)
            async with coord.database.sessions() as session:
                values = {"expires_at": utcnow() - timedelta(seconds=1)} if credential == "expired" else {"revoked_at": utcnow()}
                await session.execute(update(m.seat_tokens).where(m.seat_tokens.c.room_player_id == room.players[0].id).values(**values))
                await session.commit()
            assert server._owns(host, room)  # Deliberately stale cache cannot authorize closure.
            before = await coord.repository.load(room.id)
            with pytest.raises(RuleError) as error:
                await server._dispatch(host, close_request(room))
            assert error.value.code == "forbidden" and coord.ready
            assert await coord.repository.load(room.id) == before
            assert room.status == "lobby" and not any(x["type"] == "room_closed" for x in host.ws.messages)
    asyncio.run(run())


@pytest.mark.parametrize("session_state", ["expired", "revoked", "other_account"])
def test_account_closure_rejects_expired_revoked_and_other_session_owners(database_url, monkeypatch, session_state):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            _, who = await account(coord)
            host = client(origin())
            server.set_account_context(host, who)
            room = await create(host)
            if session_state == "other_account":
                _, wrong = await account(coord)
                server.set_account_context(host, wrong)
            else:
                values = {"expires_at": utcnow() - timedelta(seconds=1)} if session_state == "expired" else {"revoked_at": utcnow()}
                async with coord.database.sessions() as session:
                    await session.execute(update(m.user_sessions).where(m.user_sessions.c.id == who["session_id"]).values(**values))
                    await session.commit()
            before = await coord.repository.load(room.id)
            with pytest.raises((AuthError, RuleError)):
                await server._dispatch(host, close_request(room))
            assert await coord.repository.load(room.id) == before and coord.ready
            assert room.status == "lobby"
    asyncio.run(run())


@pytest.mark.parametrize("finished", [False, True])
def test_close_rejects_active_and_completed_matches_with_exact_heads_and_history_preserved(database_url, monkeypatch, finished):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, (host, _) = await pair()
            if finished:
                candidate = clone_room(room)
                candidate.game.game_over, candidate.game.winner_pid = True, 0
                await server._commit(room, candidate, snapshot=True)
            before = await coord.repository.load(room.id)
            with pytest.raises(RuleError):
                await server._dispatch(host, close_request(room))
            assert await coord.repository.load(room.id) == before and coord.ready
            assert room.status == "in_match"
    asyncio.run(run())


def test_durable_history_guard_refuses_false_lobby_cache(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, (host, _) = await pair()
            before = await coord.repository.load(room.id)
            room.status, room.game, room.match_id, room.match_uuid = "lobby", None, 0, None
            with pytest.raises(RuleError):
                await server._dispatch(host, close_request(room))
            assert await coord.repository.load(room.id) == before and coord.ready
    asyncio.run(run())


@pytest.mark.parametrize("stage", ["before_write", "before_commit", "after_commit"])
def test_closure_rollback_or_ambiguous_commit_never_publishes_an_uncommitted_close(database_url, monkeypatch, stage):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            host = client(origin())
            room = await create(host)
            before = await coord.repository.load(room.id)
            request = close_request(room)
            def fail(point):
                if point == stage:
                    raise OSError("Synthetic lifecycle fault")
            coord.repository._test_fault = fail
            if stage == "after_commit":
                await server._dispatch(host, request)
                assert room.status == "closed" and coord.ready
                assert host.ws.messages[-1]["type"] == "room_closed"
                assert (await coord.repository.operation(room.id, request["request_id"]))["kind"] == "close_room"
            else:
                with pytest.raises(PersistenceUnavailable):
                    await server._dispatch(host, request)
                assert await coord.repository.load(room.id) == before
                assert room.status == "lobby" and server._owns(host, room)
                assert not any(x["type"] == "room_closed" for x in host.ws.messages)
                coord.repository._test_fault = None
                manager, recovered = server.RoomManager(), Coordinator(coord.database)
                await recovered.initialize(manager)
                monkeypatch.setattr(server, "manager", manager)
                monkeypatch.setattr(server, "persistence", recovered)
                fresh = client(origin())
                await server._dispatch(fresh, {"type": "reconnect", "room_code": room.room_code,
                                              "reconnect_token": room.players[0].reconnect_token})
                await server._dispatch(fresh, request)
                assert (await coord.repository.load(room.id))["room"]["status"] == "closed"
    asyncio.run(run())


def test_close_create_use_one_admission_order_without_partial_room_records(database_url, monkeypatch):
    configure(monkeypatch, rate=20, lobbies=1)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            peer = origin()
            server.manager.creation_limits = replace(server.manager.creation_limits, lobbies_global=await lobby_count(coord) + 1)
            host = client(peer)
            room = await create(host)
            before = await counts(coord)
            with pytest.raises(RuleError):
                await create(client(peer))  # A still-open lobby is not an available slot.
            assert await counts(coord) == before
            entered, release = asyncio.Event(), asyncio.Event()
            original = coord.commit
            async def pause_close(previous, candidate, **kwargs):
                if candidate.status == "closed":
                    entered.set()
                    await release.wait()
                await original(previous, candidate, **kwargs)
            monkeypatch.setattr(coord, "commit", pause_close)
            closing = asyncio.create_task(server._dispatch(host, close_request(room)))
            await entered.wait()
            creating = asyncio.create_task(create(client(peer)))
            await asyncio.sleep(.05)
            assert not creating.done()  # Admission waits for the same PostgreSQL lock.
            release.set()
            await closing
            fresh = await creating
            with pytest.raises(RuleError):
                await create(client(peer))
            after = await counts(coord)
            assert after == (before[0] + 1, before[1] + 1, before[2] + 1, before[3], before[4], before[5] + 1)
            assert fresh.id != room.id and (await coord.repository.load(room.id))["room"]["status"] == "closed"
    asyncio.run(run())


def test_request_id_conflict_is_a_controlled_refusal_not_a_persistence_outage(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            host = client(origin())
            room = await create(host)
            request = close_request(room)
            await server._dispatch(host, {"type": "set_settings", "settings": {"starting_player": "host"}, "request_id": request["request_id"]})
            before = await coord.repository.load(room.id)
            with pytest.raises(RuleError) as error:
                await server._dispatch(host, request)
            assert error.value.code == "invalid" and coord.ready
            assert await coord.repository.load(room.id) == before
    asyncio.run(run())


def test_unresolved_closed_commit_is_recovered_as_closed_not_quarantined_or_resurrected(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            host = client(origin())
            room = await create(host)
            original_load = coord.repository.load
            async def unavailable(*args):
                raise OSError("Synthetic read outage")
            def lost_response(stage):
                if stage == "after_commit":
                    raise OSError("Synthetic lost COMMIT response")
            monkeypatch.setattr(coord.repository, "load", unavailable)
            coord.repository._test_fault = lost_response
            with pytest.raises(PersistenceUnavailable):
                await server._dispatch(host, close_request(room))
            assert room.status == "lobby" and room.persistence_blocked and not coord.ready
            monkeypatch.setattr(coord.repository, "load", original_load)
            coord.repository._test_fault = None
            monitor = asyncio.create_task(server._persistence_monitor())
            try:
                async def wait_closed():
                    while room.room_code in server.manager.rooms:
                        await asyncio.sleep(.05)
                await asyncio.wait_for(wait_closed(), timeout=4)
            finally:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)
            assert (await original_load(room.id))["room"]["status"] == "closed"
            assert room.room_code not in coord.quarantined_codes and coord.ready
            assert host.ws.messages[-1] == {"type": "room_closed", "room_code": room.room_code}
    asyncio.run(run())
