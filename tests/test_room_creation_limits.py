"""SEC-03: admission precedes allocation, and sockets are not IP identities."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app import server_mp as server
from app.engine import RuleError
from app.persistence.coordinator import Coordinator


class Socket:
    def __init__(self, peer="198.51.100.10", headers=None):
        self.client = SimpleNamespace(host=peer)
        self.headers = headers or {}
        self.messages = []

    async def send_text(self, raw):
        self.messages.append(json.loads(raw))

    async def close(self, code=1000):
        self.closed = code


def configure(monkeypatch, *, rate=2, lobbies=20, global_cap=100, window=600, tracking=4096):
    for key, value in {"LIMIT": rate, "WINDOW_SECONDS": window, "LOBBIES_PER_IP": lobbies,
                       "LOBBIES_GLOBAL": global_cap, "TRACKING_CAPACITY": tracking}.items():
        monkeypatch.setenv("CATAN_ROOM_CREATE_" + key, str(value))
    monkeypatch.setattr(server, "manager", server.RoomManager())
    monkeypatch.setattr(server, "persistence", Coordinator())


def client(peer="198.51.100.10", headers=None):
    conn = server.ClientConn(Socket(peer, headers))
    server.manager.connections[conn.ws] = conn
    return conn


async def create(conn):
    await server._dispatch(conn, {"type": "create_room", "name": "Guest", "max_players": 2})
    return server.manager.rooms[conn.room_code]


def test_new_socket_does_not_reset_creation_budget_or_allocate_on_refusal(monkeypatch):
    configure(monkeypatch)
    async def run():
        for _ in range(2):
            conn = client()
            await create(conn)
            server.manager.leave_room(conn)
        conn = client(headers={"x-forwarded-for": "203.0.113.8"})
        with patch.object(server.manager, "create_room", wraps=server.manager.create_room) as factory:
            with pytest.raises(RuleError) as error:
                await create(conn)
            assert error.value.code == "room_creation_rate_limited"
            factory.assert_not_called()
        assert len(server.manager.rooms) == 2
        assert conn.room_code is None and conn.ws.messages == []
        assert server.persistence.ready
    asyncio.run(run())


@pytest.mark.parametrize("peers", [("198.51.100.10", "198.51.100.11"),
                                    ("2001:db8::10", "2001:db8::11")])
def test_different_networks_have_separate_creation_budgets(monkeypatch, peers):
    configure(monkeypatch, rate=1)
    async def run():
        await create(client(peers[0]))
        with pytest.raises(RuleError, match="rate limit"):
            await create(client(peers[0]))
        await create(client(peers[1]))
        assert len(server.manager.rooms) == 2
    asyncio.run(run())


@pytest.mark.parametrize("peers", [("198.51.100.10", "::ffff:198.51.100.10"),
                                    ("2001:db8::10", "2001:0db8:0:0:0:0:0:10")])
def test_equivalent_ipv4_ipv6_addresses_share_budget(monkeypatch, peers):
    configure(monkeypatch, rate=1)
    async def run():
        await create(client(peers[0]))
        with pytest.raises(RuleError) as error:
            await create(client(peers[1]))
        assert error.value.code == "room_creation_rate_limited"
    asyncio.run(run())


def test_offline_lobby_still_counts_and_credential_stays_valid(monkeypatch):
    from app.persistence.credentials import valid_token
    configure(monkeypatch, rate=20, lobbies=1)
    async def run():
        host = client()
        room = await create(host)
        token = room.players[0].reconnect_token
        server.manager.leave_room(host)
        with pytest.raises(RuleError) as error:
            await create(client())
        assert error.value.code == "ip_lobby_limit_reached"
        assert valid_token(room.players[0], token)
        fresh = client()
        await server._dispatch(fresh, {"type": "reconnect", "room_code": room.room_code,
                                      "reconnect_token": token})
        assert fresh.room_code == room.room_code and room.players[0].active_ws is fresh.ws
    asyncio.run(run())


def test_global_lobby_limit_includes_all_origins_but_does_not_block_join_start(monkeypatch):
    configure(monkeypatch, global_cap=1)
    async def run():
        host = client()
        room = await create(host)
        with pytest.raises(RuleError) as error:
            await create(client("198.51.100.11"))
        assert error.value.code == "lobby_capacity_reached"
        guest = client("198.51.100.11")
        await server._dispatch(guest, {"type": "join_room", "name": "Other", "room_code": room.room_code})
        await server._dispatch(host, {"type": "start_match"})
        assert room.status == "in_match" and room.game is not None
        await create(client("198.51.100.11"))
        assert room.game is not None and len(server.manager.rooms) == 2
    asyncio.run(run())


def test_rejected_creation_preserves_existing_controller(monkeypatch):
    configure(monkeypatch, rate=1)
    async def run():
        host = client()
        room = await create(host)
        before = list(host.ws.messages)
        with pytest.raises(RuleError):
            await create(host)
        assert host.room_code == room.room_code and room.players[0].active_ws is host.ws
        assert host.ws.messages == before
    asyncio.run(run())


def test_concurrent_requests_respect_capacity(monkeypatch):
    configure(monkeypatch, rate=20, global_cap=2)
    async def run():
        results = await asyncio.gather(*(create(client(f"198.51.100.{i}")) for i in range(10, 16)),
                                       return_exceptions=True)
        assert sum(isinstance(result, RuleError) for result in results) == 4
        assert len(server.manager.rooms) == 2 and server.persistence.ready
    asyncio.run(run())


def test_memory_tracking_is_bounded_without_live_budget_eviction():
    from app.room_admission import MemoryRoomAdmission, RoomCreationLimits
    limiter = MemoryRoomAdmission(RoomCreationLimits(limit=1, tracking_capacity=2, window_seconds=60))
    for peer in (b"a", b"b"):
        limiter.check([], peer, 0)
        limiter.accepted(peer, 0)
    with pytest.raises(RuleError) as error:
        limiter.check([], b"c", 1)
    assert error.value.code == "room_creation_busy" and len(limiter.recent) == 2
    with pytest.raises(RuleError) as error:
        limiter.check([], b"a", 1)
    assert error.value.code == "room_creation_rate_limited"
    limiter.check([], b"a", 60)
    assert len(limiter.recent) == 0


@pytest.mark.parametrize("key,value", [("LIMIT", "0"), ("WINDOW_SECONDS", "-1"),
                                      ("LOBBIES_PER_IP", "bad"), ("LOBBIES_GLOBAL", "0"),
                                      ("TRACKING_CAPACITY", "-3")])
def test_invalid_operator_configuration_fails_closed(monkeypatch, key, value):
    from app.room_admission import RoomCreationLimits
    monkeypatch.setenv("CATAN_ROOM_CREATE_" + key, value)
    with pytest.raises(ValueError):
        RoomCreationLimits.configured()


def test_production_defaults(monkeypatch):
    from app.room_admission import RoomCreationLimits
    for key in ("LIMIT", "WINDOW_SECONDS", "LOBBIES_PER_IP", "LOBBIES_GLOBAL", "TRACKING_CAPACITY"):
        monkeypatch.delenv("CATAN_ROOM_CREATE_" + key, raising=False)
    assert RoomCreationLimits.configured() == RoomCreationLimits(20, 600, 20, 1000, 4096)


@pytest.mark.parametrize("trusted", [True, False])
def test_websocket_asgi_boundary_applies_exact_proxy_trust(monkeypatch, trusted):
    from starlette.websockets import WebSocket
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    configure(monkeypatch, rate=1)
    async def run():
        async def target(scope, receive, send):
            ws = WebSocket(scope, receive, send)
            conn = client(server.client_ip(ws))
            await create(conn)
        middleware = ProxyHeadersMiddleware(target, trusted_hosts="172.30.250.2")
        async def ignored(*args):
            return {"type": "websocket.disconnect"}
        for i in range(2):
            scope = {"type": "websocket", "client": ("172.30.250.2" if trusted else "198.51.100.10", 1000),
                     "scheme": "ws", "path": "/ws", "headers": [(b"x-forwarded-for", f"203.0.113.{i}".encode())]}
            if not trusted and i == 1:
                with pytest.raises(RuleError):
                    await middleware(scope, ignored, ignored)
            else:
                await middleware(scope, ignored, ignored)
        assert len(server.manager.rooms) == (2 if trusted else 1)
    asyncio.run(run())


def test_origin_budget_metadata_is_not_in_public_room_state(monkeypatch):
    configure(monkeypatch)
    async def run():
        conn = client()
        room = await create(conn)
        raw = json.dumps(conn.ws.messages)
        assert "198.51.100.10" not in raw and "creation_peer_hash" not in raw
        assert room.creation_peer_hash.hex() not in raw
    asyncio.run(run())
