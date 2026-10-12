"""SEC-03 PostgreSQL admission/recovery; strictly disposable *_test database."""
import asyncio
import ipaddress
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, update

from app import server_mp as server
from app.engine import RuleError
from app.persistence import models as m
from app.persistence.coordinator import Coordinator
from app.persistence.credentials import utcnow, valid_token
from app.persistence.errors import PersistenceUnavailable
from app.persistence.recovery import checksum, clone_room, restore_room
from app.room_admission import peer_hash
from tests.test_persistence_postgres import database_url, runtime
from tests.test_room_creation_limits import configure, client, create


def origin():
    # Distinct ASGI peer per test, not a client-selected protocol identity.
    return str(ipaddress.ip_address("2001:db8:" + ":".join(uuid.uuid4().hex[i:i+4] for i in range(0, 24, 4))))


async def counts(coord):
    tables = (m.rooms, m.room_players, m.seat_tokens, m.matches, m.game_snapshots, m.room_operations)
    async with coord.database.sessions() as session:
        return tuple([(await session.execute(select(func.count()).select_from(table))).scalar_one() for table in tables])


async def lobby_count(coord):
    async with coord.database.sessions() as session:
        return (await session.execute(select(func.count()).select_from(m.rooms).where(m.rooms.c.status == "lobby"))).scalar_one()


def test_rate_refusal_has_no_records_tokens_or_publication_and_survives_restart(database_url, monkeypatch):
    configure(monkeypatch, rate=2, lobbies=20)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            peer = origin()
            first = await create(client(peer))
            await create(client(peer))
            before = await counts(coord)
            manager = server.RoomManager()
            restarted = Coordinator(coord.database)
            await restarted.initialize(manager)
            monkeypatch.setattr(server, "manager", manager)
            monkeypatch.setattr(server, "persistence", restarted)
            refused = client(peer)
            with patch.object(manager, "create_room", wraps=manager.create_room) as factory:
                with pytest.raises(RuleError) as error:
                    await create(refused)
                factory.assert_not_called()
            assert error.value.code == "room_creation_rate_limited"
            assert await counts(coord) == before and restarted.ready
            assert refused.room_code is None and refused.ws.messages == []
            restored = manager.rooms[first.room_code]
            assert restored.creation_peer_hash == peer_hash(peer)
            assert valid_token(restored.players[0], first.players[0].reconnect_token)
            await server._dispatch(refused, {"type": "reconnect", "room_code": first.room_code,
                                            "reconnect_token": first.players[0].reconnect_token})
            assert restored.players[0].active_ws is refused.ws
    asyncio.run(run())


def test_offline_and_unloaded_lobbies_count_towards_persistent_ip_cap(database_url, monkeypatch):
    configure(monkeypatch, rate=20, lobbies=1)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            peer = origin()
            host = client(peer)
            room = await create(host)
            server.manager.leave_room(host)
            # A room absent from RAM must still consume durable capacity.
            server.manager.rooms.pop(room.room_code)
            before = await counts(coord)
            with pytest.raises(RuleError) as error:
                await create(client(peer))
            assert error.value.code == "ip_lobby_limit_reached" and await counts(coord) == before
            bundle = await coord.repository.load(room.id)
            assert valid_token(restore_room(bundle).players[0], room.players[0].reconnect_token)
            assert bundle["room"]["status"] == "lobby" and bundle["room"]["closed_at"] is None
            await create(client(origin()))
    asyncio.run(run())


def test_global_boundary_counts_legacy_unknown_origins_without_backfill(database_url, monkeypatch):
    configure(monkeypatch, rate=20)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room = await create(client(origin()))
            async with coord.database.sessions() as session:
                await session.execute(update(m.rooms).where(m.rooms.c.id == room.id).values(creation_peer_hash=None))
                await session.commit()
            from dataclasses import replace
            server.manager.creation_limits = replace(server.manager.creation_limits, lobbies_global=await lobby_count(coord))
            before = await counts(coord)
            with pytest.raises(RuleError) as error:
                await create(client(origin()))
            assert error.value.code == "lobby_capacity_reached" and await counts(coord) == before
            assert (await coord.repository.load(room.id))["room"]["creation_peer_hash"] is None
    asyncio.run(run())


@pytest.mark.parametrize("budget", ["rate", "ip", "global"])
def test_database_transaction_serializes_independent_creation_gates(database_url, monkeypatch, budget):
    configure(monkeypatch, rate=2 if budget == "rate" else 20, lobbies=2 if budget == "ip" else 20)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            from dataclasses import replace
            limits = server.manager.creation_limits
            if budget == "global":
                limits = replace(limits, lobbies_global=await lobby_count(coord) + 2)
            peer = origin()
            before = await counts(coord)
            allocated = []
            async def independent(i):
                # Bypass the in-process mutex to exercise the actual PostgreSQL gate.
                fingerprint = peer_hash(origin() if budget == "global" else peer)
                async with coord.repository.room_creation(limits, fingerprint) as session:
                    room = server.manager.create_room("Guest", 2, register=False)
                    room.creation_peer_hash = fingerprint
                    allocated.append(room)
                    await coord.commit(None, room, _session=session)
                    return room
            results = await asyncio.gather(*(independent(i) for i in range(6)), return_exceptions=True)
            assert len(allocated) == 2
            expected = {"rate": "room_creation_rate_limited", "ip": "ip_lobby_limit_reached", "global": "lobby_capacity_reached"}[budget]
            errors = [result for result in results if isinstance(result, RuleError)]
            assert len(errors) == 4 and all(error.code == expected for error in errors)
            after = await counts(coord)
            assert after == tuple(value + (2 if i < 3 else 0) for i, value in enumerate(before))
            assert coord.ready
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["before_write", "before_commit"])
def test_failed_transaction_does_not_spend_creation_budget(database_url, monkeypatch, fault):
    configure(monkeypatch, rate=1)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            peer = origin()
            before = await counts(coord)
            def fail(point):
                if point == fault:
                    raise RuntimeError("Synthetic rollback")
            coord.repository._test_fault = fail
            with pytest.raises(PersistenceUnavailable):
                await create(client(peer))
            assert await counts(coord) == before and not coord.ready
            coord.repository._test_fault = None
            coord.ready = True
            await create(client(peer))
    asyncio.run(run())


def test_committed_creation_lost_response_still_consumes_budget(database_url, monkeypatch):
    configure(monkeypatch, rate=1)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            peer = origin()
            def ambiguous(point):
                if point == "after_commit":
                    raise RuntimeError("Synthetic lost COMMIT response")
            coord.repository._test_fault = ambiguous
            room = await create(client(peer))
            assert room.durable_revision == 1 and coord.ready
            before = await counts(coord)
            with pytest.raises(RuleError):
                await create(client(peer))
            assert await counts(coord) == before
    asyncio.run(run())


def test_window_expiry_only_reopens_rate_budget_not_offline_lobby(database_url, monkeypatch):
    configure(monkeypatch, rate=1, lobbies=2)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            peer = origin()
            room = await create(client(peer))
            async with coord.database.sessions() as session:
                await session.execute(update(m.rooms).where(m.rooms.c.id == room.id).values(
                    created_at=utcnow() - timedelta(seconds=601)))
                await session.commit()
            second = await create(client(peer))
            assert second.id != room.id
            with pytest.raises(RuleError) as error:
                await create(client(peer))
            assert error.value.code == "ip_lobby_limit_reached"
            assert (await coord.repository.load(room.id))["room"]["status"] == "lobby"
    asyncio.run(run())


@pytest.mark.parametrize("budget", ["ip", "global"])
def test_explicit_close_of_never_started_lobby_releases_capacity_without_deletion(database_url, monkeypatch, budget):
    from dataclasses import replace
    configure(monkeypatch, rate=20, lobbies=1 if budget == "ip" else 20)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            peer = origin()
            if budget == "global":
                server.manager.creation_limits = replace(
                    server.manager.creation_limits, lobbies_global=await lobby_count(coord) + 1)
            room = await create(client(peer))
            before = await counts(coord)
            with pytest.raises(RuleError) as error:
                await create(client(peer))
            assert error.value.code == ("ip_lobby_limit_reached" if budget == "ip" else "lobby_capacity_reached")
            assert room.game is None and room.match_id == 0 and room.match_uuid is None
            await server.close_room(room.room_code)
            closed = await coord.repository.load(room.id)
            assert closed["room"]["status"] == "closed" and closed["room"]["closed_at"] is not None
            assert closed["match"] is None and closed["head"] is None
            assert all(token["revoked_at"] is not None for token in closed["tokens"].values())
            assert await counts(coord) == before  # Closure retains every durable row.
            manager = server.RoomManager()
            restarted = Coordinator(coord.database)
            await restarted.initialize(manager)
            monkeypatch.setattr(server, "manager", manager)
            monkeypatch.setattr(server, "persistence", restarted)
            assert room.room_code not in manager.rooms
            fresh = await create(client(peer))
            assert fresh.id != room.id and fresh.status == "lobby"
            assert (await coord.repository.load(room.id))["room"] == closed["room"]
    asyncio.run(run())


@pytest.mark.parametrize("expiry", ["guest_credential", "room_timestamp"])
def test_expiration_without_lifecycle_transition_does_not_reclaim_lobby_capacity(database_url, monkeypatch, expiry):
    configure(monkeypatch, rate=20, lobbies=1)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            peer = origin()
            host = client(peer)
            room = await create(host)
            token = room.players[0].reconnect_token
            await server._dispatch(host, {"type": "leave_room"})
            past = utcnow() - timedelta(days=31)
            async with coord.database.sessions() as session:
                await session.execute(update(m.rooms).where(m.rooms.c.id == room.id).values(created_at=past))
                if expiry == "guest_credential":
                    await session.execute(update(m.seat_tokens).where(
                        m.seat_tokens.c.room_player_id == room.players[0].id).values(expires_at=past))
                else:
                    await session.execute(update(m.rooms).where(m.rooms.c.id == room.id).values(expires_at=past))
                await session.commit()
            bundle = await coord.repository.load(room.id)
            assert bundle["room"]["status"] == "lobby" and bundle["room"]["closed_at"] is None
            if expiry == "guest_credential":
                assert not valid_token(restore_room(bundle).players[0], token)
            else:
                assert room.id not in await coord.repository.recoverable_ids()
            manager = server.RoomManager()
            restarted = Coordinator(coord.database)
            await restarted.initialize(manager)
            monkeypatch.setattr(server, "manager", manager)
            monkeypatch.setattr(server, "persistence", restarted)
            assert (room.room_code in manager.rooms) == (expiry == "guest_credential")
            before = await counts(coord)
            with pytest.raises(RuleError) as error:
                await create(client(peer))
            assert error.value.code == "ip_lobby_limit_reached"
            assert await counts(coord) == before and restarted.ready
            assert (await coord.repository.load(room.id))["room"] == bundle["room"]
    asyncio.run(run())


def test_guest_account_nat_coexist_join_continue_rematch_and_history_protected(database_url, monkeypatch):
    from tests.test_auth import account, http
    configure(monkeypatch, rate=20, lobbies=2)
    monkeypatch.setenv("CATAN_AUTH_MODE", "development")
    monkeypatch.setenv("CATAN_AUTH_ORIGINS", "http://test")
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            peer = origin()
            raw, who = await account(coord)
            owner = client(peer)
            server.set_account_context(owner, who)
            room = await create(owner)
            guest_host = client(peer)
            other = await create(guest_host)
            with pytest.raises(RuleError):
                await create(client(peer))
            guest = client(peer)
            await server._dispatch(guest, {"type": "join_room", "name": "Guest2", "room_code": room.room_code})
            await server._dispatch(owner, {"type": "start_match"})
            live_head = await coord.repository.load(room.id)
            digest = checksum(live_head["head"]["payload"])
            await create(client(peer))  # Starting the match releases only its lobby capacity.
            assert checksum((await coord.repository.load(room.id))["head"]["payload"]) == digest
            status, body, _ = await http("/api/games/active", cookie=raw)
            assert status == 200 and any(entry["room_code"] == room.room_code for entry in body["games"])
            continued = client(peer)
            server.set_account_context(continued, who)
            await server._dispatch(continued, {"type": "account_continue", "room_code": room.room_code})
            assert continued.pid == 0 and owner.room_code is None
            candidate = clone_room(room)
            candidate.game.game_over = True
            candidate.game.winner_pid = 0
            await server._commit(room, candidate, snapshot=True)
            historical = await coord.repository.load(room.id)
            match_id = room.match_uuid
            await server._dispatch(continued, {"type": "rematch", "request_id": str(uuid.uuid4()), "expected_match_id": 1})
            assert room.match_id == 2 and room.match_uuid != match_id
            async with coord.database.sessions() as session:
                history = (await session.execute(select(m.matches).where(m.matches.c.id == match_id))).mappings().one()
                assert history["status"] == "finished"
                snapshots = (await session.execute(select(func.count()).select_from(m.game_snapshots).where(
                    m.game_snapshots.c.match_id == match_id))).scalar_one()
                assert snapshots > 0
            assert other.room_code in server.manager.rooms
            assert historical["head"]["payload"]["engine"]["state"]["game_over"]
    asyncio.run(run())


def test_additive_origin_migration_keeps_historical_match_and_credentials_exact(database_url, monkeypatch):
    from copy import deepcopy
    from alembic import command
    from alembic.config import Config
    from tests.test_persistence_postgres import pair
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, _ = await pair()
            original = await coord.repository.load(room.id)
            config = Config("alembic.ini")
            def previous_schema(connection):
                config.attributes["connection"] = connection
                command.downgrade(config, "f2a001")
            async with coord.database.engine.begin() as connection:
                await connection.run_sync(previous_schema)
            await coord.database.migrate()
            restored = await coord.repository.load(room.id)
            expected = deepcopy(original)
            expected["room"]["creation_peer_hash"] = None
            assert restored == expected
            await coord.database.migrate()
            assert await coord.repository.load(room.id) == restored
            assert restore_room(restored).ruleset_id == room.ruleset_id
    asyncio.run(run())


def test_cancelled_admission_releases_lock_without_partial_records(database_url, monkeypatch):
    configure(monkeypatch, rate=1)
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            peer = origin()
            before = await counts(coord)
            with pytest.raises(asyncio.CancelledError):
                async with coord.repository.room_creation(server.manager.creation_limits, peer_hash(peer)):
                    raise asyncio.CancelledError()
            assert await counts(coord) == before
            await asyncio.wait_for(create(client(peer)), timeout=3)
            assert coord.ready
    asyncio.run(run())
