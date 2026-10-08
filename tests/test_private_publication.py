"""Private publications require current seat ownership, including open sockets."""
import asyncio
import json
from datetime import timedelta

import pytest

from app import server_mp as server
from app.persistence.coordinator import Coordinator
from app.persistence.credentials import utcnow
from app.persistence.snapshots import encode_snapshot
from tests.test_server_authority import live_server, start_pair
from tests.test_multiplayer_basic import _send_cmd, _recv_type, _recv_cmd_ack
import websockets


class Socket:
    def __init__(self):
        self.messages = []
        self.closed = None

    async def send_text(self, raw):
        self.messages.append(json.loads(raw))

    async def close(self, code=1000):
        self.closed = code

    def states(self):
        return [m for m in self.messages if m["type"] == "match_state"]


@pytest.fixture
def guest_game(monkeypatch):
    manager = server.RoomManager()
    monkeypatch.setattr(server, "manager", manager)
    monkeypatch.setattr(server, "persistence", Coordinator())
    room = manager.create_room("Alice", 2)
    manager.join_room(room.room_code, "Bob")
    server._set_room_settings(room, 0, {"bank_visibility": "hidden", "starting_player": "host"})
    clients = [server.ClientConn(Socket()) for _ in range(2)]
    for pid, conn in enumerate(clients):
        manager.connections[conn.ws] = conn
        manager.bind_player(conn, room, pid)
    server._start_match(room)
    room.game.players[0].res["wood"] = 3
    room.game.players[0].dev_cards = [{"type": "knight", "new": False}]
    room.game.players[1].res["ore"] = 5
    room.game.players[1].dev_cards = [{"type": "year_of_plenty", "new": False}] * 2
    return room, clients


@pytest.mark.parametrize("credential", ["expired", "revoked"])
@pytest.mark.parametrize("publication", ["broadcast", "direct"])
def test_invalid_guest_on_open_socket_receives_no_private_state(guest_game, credential, publication):
    room, (guest, peer) = guest_game
    if credential == "expired":
        room.players[0].token_expires_at = utcnow() - timedelta(seconds=1)
    else:
        room.players[0].token_revoked_at = utcnow()
    before = encode_snapshot(room.game)

    async def run():
        assert not server._owns(guest, room)
        with pytest.raises(server.RuleError) as exc:
            await server._dispatch(guest, {"type": "cmd", "match_id": room.match_id,
                                          "seq": 1, "cmd_id": "denied", "cmd": {"type": "roll"}})
        assert exc.value.code == "forbidden"
        if publication == "broadcast":
            await server._send_match_state(room)
            assert len(peer.ws.states()) == 1
        else:
            await server._send_match_state_to(guest.ws, room)
        assert not guest.ws.states()
        assert guest.ws.closed == 4401
        assert room.players[0].active_ws is None and not room.players[0].connected
        assert encode_snapshot(room.game) == before
        assert room.tick == room.players[0].last_seq_applied == 0

    asyncio.run(run())


def assert_personal(state, room, pid):
    assert state["you_pid"] == pid
    own = state["players"][pid]
    assert own["res"] == room.game.players[pid].res
    assert own["dev_cards"] == room.game.players[pid].dev_cards
    for player in state["players"]:
        if player["pid"] != pid:
            assert "res" not in player and "dev_cards" not in player
    assert "seed" not in state and "dev_deck" not in state


def test_valid_personal_broadcast_and_direct_send_preserve_privacy(guest_game):
    room, clients = guest_game

    async def run():
        await server._send_match_state(room)
        for pid, client in enumerate(clients):
            assert len(client.ws.states()) == 1 and client.ws.closed is None
            assert_personal(client.ws.states()[0]["state"], room, pid)
            await server._send_match_state_to(client.ws, room)
            assert len(client.ws.states()) == 2
            assert_personal(client.ws.states()[1]["state"], room, pid)
        assert clients[0].ws.states()[0]["tick"] == clients[1].ws.states()[0]["tick"]

    asyncio.run(run())


def test_valid_guest_reconnect_transfers_private_publication(guest_game):
    room, (old, peer) = guest_game
    proof = room.players[0].reconnect_token
    fresh = server.ClientConn(Socket())
    server.manager.connections[fresh.ws] = fresh

    async def run():
        await server._dispatch(fresh, {"type": "reconnect", "room_code": room.room_code,
                                       "reconnect_token": proof})
        assert_personal(fresh.ws.states()[0]["state"], room, 0)
        assert old.pid is None and not server._owns(old, room)
        assert server._owns(fresh, room) and room.players[0].active_ws is fresh.ws
        await server._send_match_state(room)
        await server._send_match_state_to(old.ws, room)
        assert not old.ws.states() and len(fresh.ws.states()) == 2
        assert_personal(peer.ws.states()[0]["state"], room, 1)

    asyncio.run(run())


@pytest.mark.parametrize("credential", ["expired", "revoked"])
def test_credential_changes_between_broadcast_recipients(guest_game, monkeypatch, credential):
    room, (first, second) = guest_game
    send = first.ws.send_text

    async def revoke_after_first_frame(raw):
        await send(raw)
        if credential == "expired":
            room.players[1].token_expires_at = utcnow() - timedelta(seconds=1)
        else:
            room.players[1].token_revoked_at = utcnow()

    monkeypatch.setattr(first.ws, "send_text", revoke_after_first_frame)
    asyncio.run(server._send_match_state(room))
    assert len(first.ws.states()) == 1 and not second.ws.states()
    assert second.ws.closed == 4401 and room.players[1].active_ws is None


@pytest.mark.parametrize("publication", ["broadcast", "direct"])
@pytest.mark.parametrize("change", ["expired", "revoked", "takeover", "different_seat", "new_match"])
def test_recipient_is_rechecked_after_await(guest_game, monkeypatch, publication, change):
    room, (guest, peer) = guest_game

    async def run():
        checked, release = asyncio.Event(), asyncio.Event()

        async def delayed_validation(conn):
            if conn is guest:
                checked.set()
                await release.wait()
            return True

        monkeypatch.setattr(server, "account_socket_valid", delayed_validation)
        task = asyncio.create_task(server._send_match_state(room) if publication == "broadcast"
                                   else server._send_match_state_to(guest.ws, room))
        await asyncio.wait_for(checked.wait(), 1)
        fresh = server.ClientConn(Socket())
        server.manager.connections[fresh.ws] = fresh
        if change == "expired":
            room.players[0].token_expires_at = utcnow() - timedelta(seconds=1)
        elif change == "revoked":
            room.players[0].token_revoked_at = utcnow()
        elif change == "takeover":
            server.manager.bind_player(fresh, room, 0)
        elif change == "different_seat":
            server.manager.bind_player(guest, room, 1)
        else:
            server._start_match(room)
        release.set()
        await task
        assert not guest.ws.states()
        if change in ("expired", "revoked"):
            assert guest.ws.closed == 4401 and room.players[0].active_ws is None
        else:
            assert guest.ws.closed is None and fresh.ws.closed is None
            if change == "takeover":
                assert server._owns(fresh, room)
            else:
                assert server._owns(guest, room)

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["error_frame", "close"])
def test_invalid_connection_is_fenced_even_if_transport_fails(guest_game, monkeypatch, failure):
    room, (guest, peer) = guest_game
    room.players[0].token_revoked_at = utcnow()

    async def fail(*args, **kwargs):
        raise OSError("closed transport")

    monkeypatch.setattr(guest.ws, "send_text" if failure == "error_frame" else "close", fail)
    asyncio.run(server._send_match_state(room))
    assert not guest.ws.states() and len(peer.ws.states()) == 1
    assert not server._owns(guest, room) and room.players[0].active_ws is None


def test_unavailable_persistence_does_not_publish_cached_private_state(guest_game):
    room, clients = guest_game
    proof = room.players[0].reconnect_token
    server.persistence.ready = False
    asyncio.run(server._send_match_state(room))
    assert all(not client.ws.states() and client.ws.closed == 1013 for client in clients)
    assert room.players[0].reconnect_token == proof and room.players[0].token_revoked_at is None


@pytest.mark.parametrize("credential", ["expired", "revoked"])
def test_open_websocket_is_closed_without_private_broadcast(live_server, credential):
    async def run():
        async with websockets.connect(live_server) as guest, websockets.connect(live_server) as peer:
            room, _, _, _, _ = await start_pair(guest, peer)
            if credential == "expired":
                room.players[0].token_expires_at = utcnow() - timedelta(seconds=1)
            else:
                room.players[0].token_revoked_at = utcnow()
            before = encode_snapshot(room.game)
            cid = await _send_cmd(peer, room.match_id, 1, {"type": "noop"})
            message = await _recv_type(peer, "match_state")
            assert message["state"]["you_pid"] == 1 and message["tick"] == 1
            assert (await _recv_cmd_ack(peer, cid))["applied"]
            received = []
            with pytest.raises(websockets.exceptions.ConnectionClosedError):
                while True:
                    received.append(json.loads(await asyncio.wait_for(guest.recv(), 2)))
            assert not any(m["type"] == "match_state" for m in received)
            assert guest.close_code == 4401 and any(m.get("code") == "forbidden" for m in received)
            assert encode_snapshot(room.game) == before
            assert room.players[0].active_ws is None and room.players[0].last_seq_applied == 0

    asyncio.run(run())
