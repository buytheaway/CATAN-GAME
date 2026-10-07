"""Account behavior against real PostgreSQL; no SQLite or auth mocks."""
import asyncio
import json
import uuid
from datetime import timedelta
from copy import deepcopy

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from argon2 import PasswordHasher, Type
from sqlalchemy import select, update, func

from app import server_mp as server
from app.auth import passwords, routes
from app.auth.security import AuthError, COOKIE, authorization, authorize_transaction, allowed_origin
from app.auth.service import AuthService
from app.persistence import models as m
from app.persistence.credentials import token_hash, utcnow, valid_token
from app.persistence.inspection import InspectionLimiter
from app.persistence.recovery import clone_room, restore_room
from app.persistence.snapshots import encode_snapshot
from tests.test_persistence_postgres import database_url, runtime, pair, Socket, command, recovered

SECRET = "correct horse battery staple"


@pytest.fixture(autouse=True)
def auth_config(monkeypatch):
    monkeypatch.setenv("CATAN_AUTH_MODE", "development")
    monkeypatch.setenv("CATAN_AUTH_ORIGINS", "http://test")
    monkeypatch.setattr(routes, "login_limit", InspectionLimiter(limit=15))
    monkeypatch.setattr(routes, "register_limit", InspectionLimiter(limit=5))
    monkeypatch.setattr(Socket, "close", AuthSocket.close, raising=False)


class AuthSocket(Socket):
    closed = None
    async def close(self, code=1000):
        self.closed = code


async def http(path, data=None, *, cookie=None, origin="http://test", raw=None):
    payload = raw if raw is not None else json.dumps(data).encode() if data is not None else b""
    sent = []; done = False
    async def receive():
        nonlocal done
        if done: return {"type": "http.disconnect"}
        done = True
        return {"type": "http.request", "body": payload, "more_body": False}
    async def send(message): sent.append(message)
    headers = [(b"content-type", b"application/json")]
    if origin is not None: headers.append((b"origin", origin.encode()))
    if cookie: headers.append((b"cookie", f"{COOKIE}={cookie}".encode()))
    await server.app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST" if data is not None or raw is not None else "GET", "scheme": "http",
        "path": path, "raw_path": path.encode(), "query_string": b"", "headers": headers,
        "client": ("127.0.0.1", 10), "server": ("test", 80)}, receive, send)
    start = next(x for x in sent if x["type"] == "http.response.start")
    assert (b"cache-control", b"no-store") in start["headers"]
    result = json.loads(b"".join(x.get("body", b"") for x in sent if x["type"] == "http.response.body"))
    cookies = [value.decode() for key, value in start["headers"] if key == b"set-cookie"]
    return start["status"], result, cookies


async def account(coord, name="Account"):
    service = AuthService(coord.database)
    raw, user = await service.authenticate({"username": "u_" + uuid.uuid4().hex[:16], "display_name": name, "password": SECRET}, register=True)
    return raw, await service.resolve(raw)


async def connection(who=None):
    c = server.ClientConn(AuthSocket())
    if who: server.set_account_context(c, who)
    server.manager.connections[c.ws] = c
    return c


def test_upgrade_previous_schema_preserves_guest_room_match_head_and_token(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair()
            before = await coord.repository.load(room.id)
            raw = clients[0].ws.latest("reconnect_token")["reconnect_token"]
            config = Config("alembic.ini"); config.set_main_option("script_location", "migrations")
            def downgrade(conn):
                config.attributes["connection"] = conn
                alembic_command.downgrade(config, "ab68cc7c6ebb")
            async with coord.database.engine.begin() as conn:
                await conn.run_sync(downgrade)
            await coord.database.migrate()
            after = await coord.repository.load(room.id)
            assert after["head"] == before["head"] and after["match"] == before["match"] and after["tokens"] == before["tokens"]
            restored = restore_room(after)
            assert all(p.user_id is None for p in restored.players)
            assert valid_token(restored.players[0], raw)
    asyncio.run(run())


@pytest.mark.parametrize("value", ["ab", "a b c", "аbc", "abc\u200b", "a" * 33])
def test_username_policy_rejects_ambiguous_values(value):
    with pytest.raises(AuthError): passwords.username(value)


def test_argon2_verification_salts_and_parameter_upgrade():
    async def run():
        value = passwords.password("пароль с пробелами 😀")
        encoded = await passwords.hash_password(value)
        assert encoded.startswith("$argon2id$") and value not in encoded
        assert await passwords.verify_password(encoded, value)
        assert not await passwords.verify_password(encoded, value + "!")
        assert not await passwords.verify_password("malformed", value)
        assert encoded != await passwords.hash_password(value)
        older = PasswordHasher(time_cost=1, memory_cost=19456, parallelism=1, type=Type.ID).hash(value)
        assert passwords.hasher.check_needs_rehash(older)
        assert await passwords.verify_password(older, value)
        with pytest.raises(AuthError): passwords.password("x" * 129)
        with pytest.raises(AuthError): passwords.display_name("Alice\u200b")
        assert passwords.username("  Alice_1  ") == "alice_1"
    asyncio.run(run())


def test_register_login_me_rotation_logout_and_safe_dto(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            name = "Test_" + uuid.uuid4().hex[:12]
            data = {"username": name, "display_name": "Дони", "password": SECRET}
            status, body, headers = await http("/api/auth/register", data)
            assert status == 201 and body == {"authenticated": True, "user": {"username": name.lower(), "display_name": "Дони"}}
            cookie = headers[0].split(";", 1)[0].split("=", 1)[1]
            assert "HttpOnly" in headers[0] and "SameSite=lax" in headers[0] and "Path=/" in headers[0] and "Secure" not in headers[0]
            assert (await http("/api/auth/register", {**data, "username": name.upper()}))[0:2] == (409, {"error": "username_taken"})
            assert (await http("/api/auth/me", cookie=cookie))[1] == body
            for username, password in ((name, "wrong password"), ("no_such_user", SECRET)):
                assert (await http("/api/auth/login", {"username": username, "password": password}))[0:2] == (401, {"error": "invalid_credentials"})
            status, _, headers2 = await http("/api/auth/login", {"username": name.upper(), "password": SECRET}, cookie=cookie)
            current = headers2[0].split(";", 1)[0].split("=", 1)[1]
            assert status == 200 and current != cookie
            assert (await http("/api/auth/me", cookie=cookie))[1] == {"authenticated": False}
            assert (await http("/api/auth/logout", {}, cookie=current))[1] == {"authenticated": False}
            assert (await http("/api/auth/me", cookie=current))[1] == {"authenticated": False}
            async with coord.database.sessions() as s:
                row = (await s.execute(select(m.users).where(m.users.c.username_normalized == name.lower()))).mappings().one()
                assert row["password_hash"].startswith("$argon2id$")
                sessions = (await s.execute(select(m.user_sessions).where(m.user_sessions.c.user_id == row["id"]))).mappings().all()
                assert all(x["revoked_at"] and x["token_hash"] not in (cookie.encode(), current.encode()) for x in sessions)
    asyncio.run(run())


@pytest.mark.parametrize("origin", [None, "null", "https://evil.example", "http://test.evil", "http://test/"])
def test_csrf_rejects_missing_or_foreign_origin(origin):
    async def run():
        for path in ("/api/auth/register", "/api/auth/login", "/api/auth/logout", "/api/games/claim"):
            assert (await http(path, {}, origin=origin))[0:2] == (403, {"error": "origin_forbidden"})
    asyncio.run(run())


def test_secure_production_cookie_and_origin_no_wildcard(database_url, monkeypatch):
    monkeypatch.setenv("CATAN_AUTH_MODE", "production"); monkeypatch.setenv("CATAN_AUTH_ORIGINS", "https://game.example")
    async def run():
        async with runtime(database_url, monkeypatch):
            status, _, headers = await http("/api/auth/register", {"username": uuid.uuid4().hex, "display_name": "Player", "password": SECRET}, origin="https://game.example")
            assert status == 201 and all(value in headers[0] for value in ("Secure", "HttpOnly", "SameSite=lax", "Path=/", "Max-Age=2592000"))
            assert not allowed_origin("http://game.example") and not allowed_origin("https://game.example.evil")
    asyncio.run(run())


def test_rate_limits_and_secret_input_errors(monkeypatch):
    monkeypatch.setattr(routes, "login_limit", InspectionLimiter(limit=1))
    async def run():
        # Invalid JSON fails before persistence access, without echoing its secret.
        status, body, _ = await http("/api/auth/login", raw=b'{"password":"super-secret"')
        assert status == 400 and "super-secret" not in json.dumps(body)
        assert (await http("/api/auth/login", raw=b"{}"))[0:2] == (429, {"error": "rate_limited"})
        status, body, _ = await http("/api/auth/register", raw=b"sensitive" * 600)
        assert status == 413 and "sensitive" not in json.dumps(body)
    asyncio.run(run())


@pytest.mark.parametrize("condition", ["expired", "revoked", "disabled"])
def test_session_invalidates_account_continue_and_private_publication(database_url, monkeypatch, condition):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, who = await account(coord)
            c = await connection(who)
            await server._dispatch(c, {"type": "create_room", "name": "ignored", "max_players": 2})
            room = server.manager.rooms[c.room_code]
            before = await coord.repository.load(room.id)
            async with coord.database.sessions() as s, s.begin():
                if condition == "disabled":
                    await s.execute(update(m.users).where(m.users.c.id == who["user_id"]).values(disabled_at=utcnow()))
                else:
                    patch = {"expires_at": utcnow() - timedelta(seconds=1)} if condition == "expired" else {"revoked_at": utcnow()}
                    await s.execute(update(m.user_sessions).where(m.user_sessions.c.id == who["session_id"]).values(**patch))
            assert (await http("/api/auth/me", cookie=raw))[1] == {"authenticated": False}
            with pytest.raises(AuthError): await server._dispatch(c, {"type": "account_continue", "room_code": room.room_code})
            assert await coord.repository.load(room.id) == before
            assert not await server.account_socket_valid(c) and c.ws.closed == 4401
    asyncio.run(run())


def test_account_create_join_metadata_continue_takeover_and_foreign_denial(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, who = await account(coord, "Account One")
            _, foreign = await account(coord, "Other")
            a = await connection(who)
            await server._dispatch(a, {"type": "create_room", "name": "private-login-name", "max_players": 3})
            room = server.manager.rooms[a.room_code]
            assert room.players[0].user_id == who["user_id"] and room.players[0].name == "Account One"
            assert room.players[0].token_hash is None and a.ws.latest("seat_identity")["pid"] == 0
            guest = await connection()
            await server._dispatch(guest, {"type": "join_room", "name": "Guest", "room_code": room.room_code})
            await server._dispatch(a, {"type": "start_match"})
            before = encode_snapshot(room.game)
            fresh = await connection(who)
            await server._dispatch(fresh, {"type": "account_continue", "room_code": room.room_code})
            assert fresh.pid == 0 and a.pid is None and a.ws.closed == 4409 and not server._owns(a, room)
            assert encode_snapshot(room.game) == before and fresh.ws.latest("match_state")["state"]["you_pid"] == 0
            foreign_socket = await connection(foreign)
            with pytest.raises(server.RuleError) as exc:
                await server._dispatch(foreign_socket, {"type": "account_continue", "room_code": room.room_code})
            assert exc.value.code == "seat_not_owned" and foreign_socket.pid is None
            status, body, _ = await http("/api/games/active", cookie=raw)
            assert status == 200 and body["games"][0]["own_name"] == "Account One"
            text = json.dumps(body)
            assert all(secret not in text for secret in (raw, "seed", "dev_cards", "token_hash", "user_id", "res\"", "dice_bag"))
            foreign_raw = await AuthService(coord.database).authenticate({"username": foreign["username"], "password": SECRET}, register=False)
            assert (await http("/api/games/active", cookie=foreign_raw[0]))[1] == {"games": []}
            projected = fresh.ws.latest("match_state")["state"]
            assert "res" not in projected["players"][1] and "dev_cards" not in projected["players"][1]
            restored = await recovered(coord, room)
            assert restored.players[0].user_id == who["user_id"] and valid_token(restored.players[1], room.players[1].reconnect_token)
    asyncio.run(run())


def test_duplicate_account_join_and_claim_cannot_create_second_seat(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, who = await account(coord)
            a = await connection(who)
            await server._dispatch(a, {"type": "create_room", "name": "Account", "max_players": 3})
            room = server.manager.rooms[a.room_code]
            duplicate = await connection(who)
            with pytest.raises(server.RuleError) as exc:
                await server._dispatch(duplicate, {"type": "join_room", "name": "Different", "room_code": room.room_code})
            assert exc.value.code == "duplicate_room_membership"
            guest = await connection()
            await server._dispatch(guest, {"type": "join_room", "name": "Guest", "room_code": room.room_code})
            proof = room.players[guest.pid].reconnect_token
            assert (await http("/api/games/claim", {"room_code": room.room_code, "reconnect_token": proof}, cookie=raw))[0:2] == (409, {"error": "duplicate_room_membership"})
            assert valid_token(room.players[guest.pid], proof)
    asyncio.run(run())


def test_guest_claim_preserves_requesting_socket_state_and_revokes_only_its_proof(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair()
            a = clients[0]
            raw, who = await account(coord)
            proof = room.players[0].reconnect_token
            other = room.players[1].reconnect_token
            before = encode_snapshot(room.game)
            status, _, _ = await http("/api/games/claim", {"room_code": room.room_code, "reconnect_token": proof, "connection_nonce": a.connection_nonce}, cookie=raw)
            assert status == 200 and room.players[0].user_id == who["user_id"]
            assert a.pid == 0 and server._owns(a, room) and a.ws.latest("seat_identity")["pid"] == 0
            assert encode_snapshot(room.game) == before and not valid_token(room.players[0], proof) and valid_token(room.players[1], other)
            bundle = await coord.repository.load(room.id)
            assert bundle["tokens"][room.players[0].id]["revoked_at"] is not None
            restored = restore_room(bundle)
            assert restored.players[0].user_id == who["user_id"] and not valid_token(restored.players[0], proof)
            foreign = await connection()
            with pytest.raises(server.RuleError):
                await server._dispatch(foreign, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
    asyncio.run(run())


def test_claim_without_current_socket_nonce_fences_the_previous_controller(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            guest = await connection()
            await server._dispatch(guest, {"type": "create_room", "name": "Guest", "max_players": 2})
            room = server.manager.rooms[guest.room_code]
            raw, who = await account(coord)
            assert (await http("/api/games/claim", {"room_code": room.room_code, "reconnect_token": room.players[0].reconnect_token}, cookie=raw))[0] == 200
            assert guest.ws.closed == 4409 and not server._owns(guest, room)
            new = await connection(who)
            await server._dispatch(new, {"type": "account_continue", "room_code": room.room_code})
            assert new.pid == 0
    asyncio.run(run())


def test_invalid_claim_and_failed_commit_leave_guest_ownership_intact(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, _ = await pair()
            raw, _ = await account(coord)
            before = await coord.repository.load(room.id)
            assert (await http("/api/games/claim", {"room_code": room.room_code, "reconnect_token": "wrong"}, cookie=raw))[0] == 403
            assert await coord.repository.load(room.id) == before
            def fail(stage):
                if stage == "before_write": raise RuntimeError("secret details")
            coord.repository._test_fault = fail
            status, body, _ = await http("/api/games/claim", {"room_code": room.room_code, "reconnect_token": room.players[0].reconnect_token}, cookie=raw)
            assert status == 503 and body == {"error": "persistence_unavailable"}
            assert room.players[0].user_id is None and await coord.repository.load(room.id) == before
    asyncio.run(run())


def test_logout_orders_after_inflight_authorized_transaction_and_invalidates_following_writes(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, who = await account(coord)
            locked = asyncio.Event(); release = asyncio.Event()
            async def mutation():
                context = authorization.set(who)
                try:
                    async with coord.database.sessions() as s, s.begin():
                        await authorize_transaction(s); locked.set(); await release.wait()
                finally: authorization.reset(context)
            task = asyncio.create_task(mutation()); await locked.wait()
            logout = asyncio.create_task(AuthService(coord.database).revoke(who))
            await asyncio.sleep(.05); assert not logout.done()
            release.set(); await task; await logout
            context = authorization.set(who)
            try:
                async with coord.database.sessions() as s:
                    with pytest.raises(AuthError): await authorize_transaction(s)
            finally: authorization.reset(context)
            assert await AuthService(coord.database).resolve(raw) is None
    asyncio.run(run())


def test_auth_outage_does_not_revoke_session_or_guest_proof(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, _ = await account(coord)
            room, _ = await pair()
            before = await coord.repository.load(room.id)
            coord.ready = False
            c = await connection(who=await AuthService(coord.database).resolve(raw))
            assert not await server.account_socket_valid(c) and c.ws.closed == 1013
            assert c.user_id is not None
            for path in ("/api/auth/me", "/api/games/active"):
                assert (await http(path, cookie=raw))[0:2] == (503, {"error": "persistence_unavailable"})
            coord.ready = True
            assert await AuthService(coord.database).resolve(raw)
            assert await coord.repository.load(room.id) == before
    asyncio.run(run())


def test_account_join_and_claim_retry_are_owned_without_guest_fallback(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            guest = await connection()
            await server._dispatch(guest, {"type": "create_room", "name": "Guest", "max_players": 3})
            room = server.manager.rooms[guest.room_code]
            raw, who = await account(coord)
            joined = await connection(who)
            await server._dispatch(joined, {"type": "join_room", "room_code": room.room_code, "name": "ignored"})
            assert room.players[joined.pid].user_id == who["user_id"] and room.players[joined.pid].token_hash is None
            raw2, _ = await account(coord, "Claim owner")
            proof = room.players[0].reconnect_token
            data = {"room_code": room.room_code, "reconnect_token": proof, "connection_nonce": guest.connection_nonce}
            assert (await http("/api/games/claim", data, cookie=raw2))[0] == 200
            assert (await http("/api/games/claim", data, cookie=raw2))[0] == 200  # Lost HTTP success can safely retry.
            assert (await http("/api/games/claim", data, cookie=raw))[0:2] == (409, {"error": "already_claimed"})
            assert (await http("/api/games/claim", data))[0] == 401
            assert room.players[0].name == "Guest"  # Claim does not rewrite the seat nickname.
    asyncio.run(run())


def test_retained_account_ownership_follows_rematch_compact_pid_and_epoch(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair(names=("Alice", "Bob", "Cara"))
            identities = []
            for index in (0, 2):
                raw, who = await account(coord, f"Owner {index}")
                identities.append(who)
                assert (await http("/api/games/claim", {"room_code": room.room_code, "reconnect_token": room.players[index].reconnect_token,
                    "connection_nonce": clients[index].connection_nonce}, cookie=raw))[0] == 200
            server.manager.leave_room(clients[1])
            candidate = clone_room(room); candidate.game.game_over = True; candidate.game.winner_pid = 0
            await server._commit(room, candidate, snapshot=True)
            await server._dispatch(clients[0], {"type": "rematch"})
            assert room.match_id == 2 and len(room.players) == 2
            assert room.players[1].user_id == identities[1]["user_id"] and room.players[1].name == "Cara"
            fresh = await connection(identities[1])
            await server._dispatch(fresh, {"type": "account_continue", "room_code": room.room_code})
            assert fresh.pid == 1 and fresh.ws.latest("seat_identity")["last_seq_applied"] == 0
            restored = await recovered(coord, room)
            assert restored.players[1].user_id == identities[1]["user_id"] and restored.match_id == 2
    asyncio.run(run())


def test_session_last_seen_is_throttled_and_login_rehashes_old_parameters(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, who = await account(coord)
            service = AuthService(coord.database)
            async with coord.database.sessions() as s:
                before = (await s.execute(select(m.user_sessions).where(m.user_sessions.c.id == who["session_id"]))).mappings().one()
            for _ in range(3): assert await service.resolve(raw)
            async with coord.database.sessions() as s:
                after = (await s.execute(select(m.user_sessions).where(m.user_sessions.c.id == who["session_id"]))).mappings().one()
            assert after == before
            async with coord.database.sessions() as s, s.begin():
                await s.execute(update(m.user_sessions).where(m.user_sessions.c.id == who["session_id"]).values(last_seen_at=utcnow()-timedelta(minutes=6)))
                old = PasswordHasher(time_cost=1, memory_cost=19456, parallelism=1).hash(SECRET)
                await s.execute(update(m.users).where(m.users.c.id == who["user_id"]).values(password_hash=old))
            assert await service.resolve(raw)
            await service.authenticate({"username": who["username"], "password": SECRET}, register=False)
            async with coord.database.sessions() as s:
                row = (await s.execute(select(m.users.c.password_hash).where(m.users.c.id == who["user_id"]))).scalar_one()
                session = (await s.execute(select(m.user_sessions).where(m.user_sessions.c.id == who["session_id"]))).mappings().one()
            assert not passwords.hasher.check_needs_rehash(row) and session["expires_at"] == before["expires_at"]
            assert session["last_seen_at"] > before["last_seen_at"]
    asyncio.run(run())


def test_websocket_origin_and_cookie_handshake_policy(database_url, monkeypatch):
    async def websocket(origin, cookie=None):
        messages=[]; connected=False
        async def receive():
            nonlocal connected
            if not connected: connected=True; return {"type":"websocket.connect"}
            return {"type":"websocket.disconnect", "code":1000}
        async def send(message): messages.append(message)
        headers=[(b"host",b"test")]
        if origin is not None: headers.append((b"origin",origin.encode()))
        if cookie: headers.append((b"cookie",f"{COOKIE}={cookie}".encode()))
        await server.app({"type":"websocket","asgi":{"version":"3.0"},"scheme":"ws","path":"/ws","raw_path":b"/ws",
            "query_string":b"","headers":headers,"client":("127.0.0.1",10),"server":("test",80),"subprotocols":[]},receive,send)
        return messages
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            raw,_=await account(coord)
            for origin in ("https://evil.example", "null", None):
                messages=await websocket(origin,raw)
                assert not any(x["type"]=="websocket.accept" for x in messages)
            assert any(x["type"]=="websocket.accept" for x in await websocket("http://test",raw))
            assert any(x["type"]=="websocket.accept" for x in await websocket(None))  # Desktop guest.
            messages=await websocket("http://test","invalid-cookie")
            assert messages[-1]=={"type":"websocket.close","code":4401,"reason":""}
    asyncio.run(run())
