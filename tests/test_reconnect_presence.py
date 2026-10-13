"""Reconnect publishes presence to existing peers without changing gameplay.

Dispatch cases use real PostgreSQL ownership checks. The TCP case reproduces
the browser refresh that left the other client's Rematch presence stale. These
are notification regressions, not substitutes for natural full-match tests.
"""
import asyncio
from copy import deepcopy

import pytest

from app import server_mp as server
from app.persistence.snapshots import encode_snapshot
from tests.full_match_support import Backend, Match, validate_database_url
from tests.test_auth import account, auth_config, connection
from tests.test_persistence_postgres import database_url, runtime


async def make_pair(coordinator, ownership, started):
    identity = (await account(coordinator, "Presence owner"))[1] if ownership == "account" else None
    owner, observer = await connection(identity), await connection()
    await server._dispatch(owner, {"type": "create_room", "name": "Presence host", "max_players": 2})
    room = server.manager.rooms[owner.room_code]
    await server._dispatch(observer, {"type": "join_room", "name": "Presence peer", "room_code": room.room_code})
    if started:
        await server._dispatch(owner, {"type": "start_match"})
    return room, owner, observer, identity


def reconnect_intent(room, ownership):
    if ownership == "account":
        return {"type": "account_continue", "room_code": room.room_code}
    return {"type": "reconnect", "room_code": room.room_code,
            "reconnect_token": room.players[0].reconnect_token}


def assert_both_present(connection_, room):
    frames = [message for message in connection_.ws.messages if message["type"] == "room_state"]
    assert frames, "The reconnect must publish current room presence to existing clients"
    state = frames[-1]
    assert state["room_code"] == room.room_code
    assert [player["connected"] for player in state["players"]] == [True, True]


@pytest.mark.parametrize("ownership", ["guest", "account"])
@pytest.mark.parametrize("started", [False, True], ids=["lobby", "match"])
def test_durable_reconnect_refreshes_other_clients_presence(database_url, monkeypatch, ownership, started):
    validate_database_url(database_url)

    async def run():
        async with runtime(database_url, monkeypatch) as coordinator:
            room, old, observer, identity = await make_pair(coordinator, ownership, started)
            intent = reconnect_intent(room, ownership)
            game = encode_snapshot(room.game) if started else None
            head = (await coordinator.repository.load(room.id))["head"] if started else None
            # This is the endpoint's normal disconnect cleanup, not a lobby close.
            async with room.lock:
                server.manager.leave_room(old)
                await server._send_room_state(room)
            server.manager.connections.pop(old.ws)
            assert observer.ws.latest("room_state")["players"][0]["connected"] is False
            observer.ws.messages.clear()

            fresh = await connection(identity)
            await server._dispatch(fresh, intent)

            assert_both_present(observer, room)
            assert_both_present(fresh, room)
            assert server._owns(fresh, room) and not server._owns(old, room)
            assert room.players[0].active_ws is fresh.ws
            if started:
                assert encode_snapshot(room.game) == game
                assert (await coordinator.repository.load(room.id))["head"] == head
                snapshot = fresh.ws.latest("match_state")["state"]
                assert snapshot["you_pid"] == 0
                assert "res" not in snapshot["players"][1] and "dev_cards" not in snapshot["players"][1]
                assert not any(message["type"] == "match_state" for message in observer.ws.messages)
            else:
                assert not any(message["type"] == "match_state" for message in fresh.ws.messages)

    asyncio.run(run())


@pytest.mark.parametrize("ownership", ["guest", "account"])
def test_takeover_publishes_presence_and_old_disconnect_cannot_clear_new_controller(
        database_url, monkeypatch, ownership):
    validate_database_url(database_url)

    async def run():
        async with runtime(database_url, monkeypatch) as coordinator:
            room, old, observer, identity = await make_pair(coordinator, ownership, True)
            intent = reconnect_intent(room, ownership)
            game = encode_snapshot(room.game)
            observer.ws.messages.clear()
            old.ws.messages.clear()
            fresh = await connection(identity)
            await server._dispatch(fresh, intent)

            assert_both_present(observer, room)
            assert old.pid is None and old.room_code is None
            assert server._owns(fresh, room) and not server._owns(old, room)
            assert not any(message["type"] == "match_state" for message in old.ws.messages)
            if ownership == "account":
                assert old.ws.closed == 4409

            # A delayed finally block from the displaced socket must not mark
            # the new controlling socket offline or send it the wrong hand.
            async with room.lock:
                server.manager.leave_room(old)
                await server._send_room_state(room)
                await server._send_match_state(room)
            assert_both_present(observer, room)
            assert room.players[0].connected and room.players[0].active_ws is fresh.ws
            assert fresh.ws.latest("match_state")["state"]["you_pid"] == 0
            assert not any(message["type"] == "match_state" for message in old.ws.messages)
            assert encode_snapshot(room.game) == game

    asyncio.run(run())


def test_real_tcp_guest_refresh_updates_other_connected_player(database_url):
    backend = Backend(database_url)

    async def run():
        match = Match(backend, 2, "base_standard")
        try:
            await match.create()
            observer, old = match.peers
            before, token = deepcopy(old.state), old.token
            await old.close()
            await observer.wait(lambda: observer.room["players"][1]["connected"] is False)
            fresh = await match.connect()
            match.peers[1] = fresh
            await fresh.send({"type": "reconnect", "room_code": match.room_code, "reconnect_token": token})
            await fresh.wait(lambda: fresh.state is not None and fresh.token is not None)
            # The original implementation notified only the reconnecting client;
            # this wait therefore fails against that implementation.
            await observer.wait(lambda: observer.room["players"][1]["connected"] is True, timeout=3)
            assert fresh.state == before and fresh.token == token
            assert all(player["connected"] for player in observer.room["players"])
            match.assert_views()
        finally:
            await match.close()

    try:
        backend.start()
        asyncio.run(run())
    finally:
        backend.close()
