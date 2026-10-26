"""Pinned owner capability against disposable PostgreSQL, never a name-based role."""
import asyncio
import time

import pytest
from sqlalchemy import insert, select, update

from app import server_mp as server
from app.auth import passwords
from app.auth.security import OWNER_ACCOUNT_ID, AuthError, authorization, owner_test_tools_required, authorize_transaction
from app.auth.service import AuthService
from app.persistence import models as m
from app.persistence.credentials import utcnow
from app.persistence.db import Database
from app.persistence.recovery import clone_room, restore_room
from app.persistence.snapshots import encode_snapshot
from tests.test_auth import SECRET, account, auth_config, connection, http
from tests.test_persistence_postgres import database_url, runtime, command, prepare


@pytest.fixture(autouse=True)
def no_global_tools(monkeypatch):
    monkeypatch.setattr(server, "TEST_TOOLS_ENABLED", False)


async def owner(coord):
    service = AuthService(coord.database)
    async with coord.database.sessions() as session, session.begin():
        exists = (await session.execute(select(m.users.c.id).where(m.users.c.id == OWNER_ACCOUNT_ID))).first()
        if not exists:
            now = utcnow()
            await session.execute(insert(m.users).values(id=OWNER_ACCOUNT_ID, username="buytheaway",
                username_normalized="buytheaway", display_name="Owner", password_hash=await passwords.hash_password(SECRET),
                created_at=now, updated_at=now))
        await session.execute(update(m.users).where(m.users.c.id == OWNER_ACCOUNT_ID)
                              .values(test_tools_enabled=False, disabled_at=None))
    raw, _ = await service.authenticate({"username": "buytheaway", "password": SECRET}, register=False)
    return raw, await service.resolve(raw)


async def lobby(who):
    host = await connection(who)
    await server._dispatch(host, {"type": "create_room", "name": "untrusted", "max_players": 2})
    room = server.manager.rooms[host.room_code]
    guest = await connection()
    await server._dispatch(guest, {"type": "join_room", "name": "Guest", "room_code": room.room_code})
    return room, host, guest


async def owner_match(coord, who):
    await AuthService(coord.database).set_owner_test_mode(who, True)
    room, host, guest = await lobby(who)
    await server._dispatch(host, {"type": "enable_test_mode"})
    await server._dispatch(host, {"type": "set_settings", "settings": {"starting_player": "host", "bank_visibility": "hidden"}})
    await server._dispatch(host, {"type": "start_match"})
    await prepare(room)
    return room, host, guest


def test_owner_preference_default_strict_http_and_login_restart_persistence(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, who = await owner(coord)
            assert (await http("/api/auth/me", cookie=raw))[1]["user"]["owner_test_mode"] == {"enabled": False}
            for value in (1, "true", [], None):
                assert (await http("/api/auth/test-mode", {"enabled": value}, cookie=raw))[0] == 400
            assert (await http("/api/auth/test-mode", {"enabled": True}, cookie=raw, origin="https://evil.example"))[0] == 403
            assert (await http("/api/auth/test-mode", {"enabled": True}))[0] == 401
            assert (await http("/api/auth/test-mode", {"enabled": True, "user_id": str(OWNER_ACCOUNT_ID)}, cookie=raw))[0] == 400
            assert (await http("/api/auth/test-mode", {"enabled": True}, cookie=raw))[0:2] == (200, {"enabled": True})
            # A new engine/service has no access to the original Python identity/cache.
            fresh = Database(database_url)
            try:
                assert await AuthService(fresh).owner_test_mode_enabled()
            finally:
                await fresh.close()
            assert (await http("/api/auth/logout", {}, cookie=raw))[0] == 200
            status, body, headers = await http("/api/auth/login", {"username": "BUYTHEAWAY", "password": SECRET})
            assert status == 200 and body["user"]["owner_test_mode"] == {"enabled": True}
            raw2 = headers[0].split(";", 1)[0].split("=", 1)[1]
            assert (await http("/api/auth/test-mode", {"enabled": False}, cookie=raw2))[0] == 200
            assert not await AuthService(coord.database).owner_test_mode_enabled()
    asyncio.run(run())


def test_other_accounts_and_guests_cannot_forge_owner_name_or_preference(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            _, who = await owner(coord)
            raw, other = await account(coord, "buytheaway")
            assert "owner_test_mode" not in (await http("/api/auth/me", cookie=raw))[1]["user"]
            assert (await http("/api/auth/test-mode", {"enabled": True}, cookie=raw))[0:2] == (403, {"error": "forbidden"})
            # Even a non-owner row with a true preference cannot acquire the capability.
            async with coord.database.sessions() as session, session.begin():
                await session.execute(update(m.users).where(m.users.c.id == other["user_id"]).values(test_tools_enabled=True))
            for identity in (None, other):
                conn = await connection(identity)
                await server._dispatch(conn, {"type": "hello", "name": "buytheaway", "version": 1})
                assert not conn.ws.latest("hello")["test_tools_available"]
                assert "owner_test_mode" not in conn.ws.latest("hello")
                await server._dispatch(conn, {"type": "create_room", "name": "buytheaway", "max_players": 2})
                room = server.manager.rooms[conn.room_code]
                before = await coord.repository.load(room.id)
                with pytest.raises(server.RuleError):
                    await server._dispatch(conn, {"type": "enable_test_mode"})
                assert await coord.repository.load(room.id) == before
            assert not await AuthService(coord.database).owner_test_mode_enabled()
    asyncio.run(run())


@pytest.mark.parametrize("developer_flag", [False, True])
def test_off_revokes_open_socket_and_normal_rooms_stay_protected(database_url, monkeypatch, developer_flag):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, who = await owner(coord)
            room, host, guest = await owner_match(coord, who)
            monkeypatch.setattr(server, "TEST_TOOLS_ENABLED", developer_flag)
            intent = command(room, host, {"type": "test_action", "action": "give_resources", "player": 0, "resource": "wood", "amount": 1})
            await server._dispatch(host, intent)
            assert host.ws.latest("cmd_ack")["applied"]
            count = room.game.players[0].res["wood"]
            await server._dispatch(host, intent)
            assert host.ws.latest("cmd_ack")["duplicate"] and room.game.players[0].res["wood"] == count
            assert (await http("/api/auth/test-mode", {"enabled": False}, cookie=raw))[0] == 200
            assert host.ws.latest("hello")["test_tools_available"] is False
            assert host.ws.latest("match_state")["state"]["test_tools"] is False
            before, tick = encode_snapshot(room.game), room.tick
            await server._dispatch(host, command(room, host, intent["cmd"]))
            assert not host.ws.latest("cmd_ack")["applied"]
            assert encode_snapshot(room.game) == before and room.tick == tick
            assert coord.ready and not room.persistence_blocked
            normal, normal_host, _ = await lobby(await AuthService(coord.database).resolve(raw))
            with pytest.raises(server.RuleError):
                await server._dispatch(normal_host, {"type": "enable_test_mode"})
            await AuthService(coord.database).set_owner_test_mode(who, True)
            await server._dispatch(normal_host, {"type": "start_match"})
            await prepare(normal)
            before = encode_snapshot(normal.game)
            await server._dispatch(normal_host, command(normal, normal_host, intent["cmd"]))
            assert not normal_host.ws.latest("cmd_ack")["applied"] and encode_snapshot(normal.game) == before
            with pytest.raises(server.RuleError):
                await server._dispatch(normal_host, {"type": "enable_test_mode"})
            assert not normal.test_mode
    asyncio.run(run())


def test_recovery_continue_takeover_and_opponent_privacy(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, who = await owner(coord)
            room, old, guest = await owner_match(coord, who)
            recovered = restore_room(await coord.repository.load(room.id))
            assert recovered.test_mode and recovered.players[0].user_id == OWNER_ACCOUNT_ID
            server.manager.rooms[room.room_code] = recovered
            fresh = await connection(await AuthService(coord.database).resolve(raw))
            await server._dispatch(fresh, {"type": "account_continue", "room_code": room.room_code})
            assert fresh.ws.latest("match_state")["state"]["test_tools"] is True
            other = await connection()
            token = guest.ws.latest("reconnect_token")["reconnect_token"]
            await server._dispatch(other, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": token})
            state = other.ws.latest("match_state")["state"]
            assert not state["test_tools"] and all("res" not in p and "dev_cards" not in p for p in state["players"] if p["pid"] != other.pid)
            await server._dispatch(other, command(recovered, other, {"type": "test_action", "action": "set_vp", "player": 0, "vp": 9}))
            assert not other.ws.latest("cmd_ack")["applied"]
            replacement = await connection(await AuthService(coord.database).resolve(raw))
            await server._dispatch(replacement, {"type": "account_continue", "room_code": room.room_code})
            with pytest.raises(server.RuleError):
                await server._dispatch(fresh, command(recovered, replacement, {"type": "test_action", "action": "set_vp", "player": 0, "vp": 9}))
            await AuthService(coord.database).set_owner_test_mode(who, False)
            await server._send_match_state(recovered)
            assert not replacement.ws.latest("match_state")["state"]["test_tools"]
    asyncio.run(run())


@pytest.mark.parametrize("developer_flag", [False, True])
def test_off_wins_candidate_commit_race_without_side_effect_and_with_rejected_receipt(database_url, monkeypatch, developer_flag):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            _, who = await owner(coord)
            room, host, _ = await owner_match(coord, who)
            monkeypatch.setattr(server, "TEST_TOOLS_ENABLED", developer_flag)
            before = encode_snapshot(room.game)
            original = coord.commit
            injected = False
            async def off_before_commit(prior, candidate, **kwargs):
                nonlocal injected
                if owner_test_tools_required.get() and not injected:
                    injected = True
                    await AuthService(coord.database).set_owner_test_mode(who, False)
                return await original(prior, candidate, **kwargs)
            monkeypatch.setattr(coord, "commit", off_before_commit)
            intent = command(room, host, {"type": "test_action", "action": "set_vp", "player": 0, "vp": 9})
            await server._dispatch(host, intent)
            assert injected and encode_snapshot(room.game) == before
            assert not host.ws.latest("cmd_ack")["applied"]
            receipt = await coord.repository.receipt(room.players[0].match_player_id, intent["seq"], intent["cmd_id"])
            assert receipt["outcome"] == "rejected" and receipt["error_code"] == "test_mode_disabled"
            assert coord.ready and not room.persistence_blocked
    asyncio.run(run())


def test_committing_authorized_action_orders_before_off(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            _, who = await owner(coord)
            await AuthService(coord.database).set_owner_test_mode(who, True)
            context = authorization.set(who)
            required = owner_test_tools_required.set(True)
            task = None
            try:
                async with coord.database.sessions() as session, session.begin():
                    await authorize_transaction(session)
                    # A separate request must wait for the command's SHARE locks.
                    async def off():
                        reset = owner_test_tools_required.set(False)
                        try: await AuthService(coord.database).set_owner_test_mode(who, False)
                        finally: owner_test_tools_required.reset(reset)
                    task = asyncio.create_task(off())
                    await asyncio.sleep(.05)
                    assert not task.done()
                await asyncio.wait_for(task, 3)
            finally:
                authorization.reset(context); owner_test_tools_required.reset(required)
            assert not await AuthService(coord.database).owner_test_mode_enabled()
    asyncio.run(run())


@pytest.mark.parametrize("developer_flag", [False, True])
def test_off_ignores_pending_forced_dice_but_does_not_change_normal_gameplay(database_url, monkeypatch, developer_flag):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            _, who = await owner(coord)
            room, host, _ = await owner_match(coord, who)
            monkeypatch.setattr(server, "TEST_TOOLS_ENABLED", developer_flag)
            await server._dispatch(host, command(room, host, {"type": "test_action", "action": "set_next_dice", "dice": [6, 6]}))
            await AuthService(coord.database).set_owner_test_mode(who, False)
            monkeypatch.setattr(server, "_roll_dice", lambda: (1, 2))
            await server._dispatch(host, command(room, host, {"type": "roll"}))
            assert host.ws.latest("cmd_ack")["applied"] and room.dice == (1, 2) and room.next_test_dice is None
    asyncio.run(run())


def test_development_tools_for_other_hosts_are_preserved(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            monkeypatch.setattr(server, "TEST_TOOLS_ENABLED", True)
            _, who = await account(coord)
            room, host, _ = await lobby(who)
            await server._dispatch(host, {"type": "enable_test_mode"})
            assert room.test_mode
            await server._dispatch(host, {"type": "start_match"})
            await prepare(room)
            await server._dispatch(host, command(room, host, {"type": "test_action", "action": "set_vp", "player": 0, "vp": 9}))
            assert host.ws.latest("cmd_ack")["applied"]
    asyncio.run(run())


@pytest.mark.parametrize("developer_flag", [False, True])
def test_off_racing_lobby_enable_cannot_create_test_room(database_url, monkeypatch, developer_flag):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            _, who = await owner(coord)
            await AuthService(coord.database).set_owner_test_mode(who, True)
            room, host, _ = await lobby(who)
            monkeypatch.setattr(server, "TEST_TOOLS_ENABLED", developer_flag)
            before = await coord.repository.load(room.id)
            original = coord.commit
            async def off_before_commit(prior, candidate, **kwargs):
                if owner_test_tools_required.get():
                    await AuthService(coord.database).set_owner_test_mode(who, False)
                return await original(prior, candidate, **kwargs)
            monkeypatch.setattr(coord, "commit", off_before_commit)
            with pytest.raises(AuthError) as exc:
                await server._dispatch(host, {"type": "enable_test_mode"})
            assert exc.value.code == "test_mode_disabled"
            assert not room.test_mode and await coord.repository.load(room.id) == before
            assert coord.ready and not room.persistence_blocked
    asyncio.run(run())


@pytest.mark.parametrize("enabled", [False, True])
def test_timer_dice_follow_current_owner_permission(database_url, monkeypatch, enabled):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            _, who = await owner(coord)
            room, host, _ = await owner_match(coord, who)
            await server._dispatch(host, command(room, host, {"type": "test_action", "action": "set_next_dice", "dice": [6, 6]}))
            await AuthService(coord.database).set_owner_test_mode(who, enabled)
            candidate = clone_room(room)
            candidate.settings = candidate.settings.updated({"turn_timer": 60})
            server._sync_timer(candidate)
            candidate.timer.deadline = time.monotonic() - 1
            await server._commit(room, candidate, snapshot=True)
            monkeypatch.setattr(server, "_roll_dice", lambda: (1, 2))
            await server._process_room_timer(room)
            assert room.dice == ((6, 6) if enabled else (1, 2)) and room.next_test_dice is None
    asyncio.run(run())
