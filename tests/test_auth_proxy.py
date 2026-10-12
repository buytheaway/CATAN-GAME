"""Auth budgets use the ASGI peer authenticated by Uvicorn, never raw headers."""
import asyncio
import json

import pytest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app import server_mp as server
from app.auth import routes
from app.persistence.inspection import InspectionLimiter

PROXY = "172.30.250.2"


async def request(app, peer, forwarded, path="login"):
    sent = []
    headers = [(b"content-type", b"application/json"), (b"origin", b"http://test")]
    if forwarded is not None:
        headers.extend([(b"x-forwarded-for", forwarded.encode()),
                        (b"x-forwarded-proto", b"https")])
    scope = dict(type="http", asgi={"version": "3.0"}, http_version="1.1",
                 method="POST", scheme="http", path=f"/api/auth/{path}",
                 query_string=b"", headers=headers, client=(peer, 1234), server=("test", 80))
    async def receive():
        return {"type": "http.request", "body": b"{}", "more_body": False}
    async def send(message):
        sent.append(message)
    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = json.loads(b"".join(m.get("body", b"") for m in sent))
    return status, body


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("CATAN_AUTH_MODE", "development")
    monkeypatch.setenv("CATAN_AUTH_ORIGINS", "http://test")
    monkeypatch.setattr(routes, "login_limit", InspectionLimiter(limit=15))
    monkeypatch.setattr(routes, "register_limit", InspectionLimiter(limit=5))
    return ProxyHeadersMiddleware(server.app, trusted_hosts=PROXY)


@pytest.mark.parametrize("path,limit", [("login", 15), ("register", 5)])
@pytest.mark.parametrize("clients", [("198.51.100.10", "198.51.100.11"),
                                    ("2001:db8::10", "2001:db8::11")])
def test_trusted_proxy_separates_real_clients_and_preserves_limits(app, path, limit, clients):
    async def run():
        for _ in range(limit):
            assert await request(app, PROXY, clients[0], path) == (400, {"error": "invalid_request"})
        assert await request(app, PROXY, clients[0], path) == (429, {"error": "rate_limited"})
        assert await request(app, PROXY, clients[1], path) == (400, {"error": "invalid_request"})
    asyncio.run(run())


@pytest.mark.parametrize("peer", ["198.51.100.10", "172.30.250.3", "2001:db8::10", "127.0.0.1", "::1"])
def test_untrusted_direct_peer_cannot_rotate_forwarded_headers(app, peer):
    async def run():
        for i in range(15):
            assert (await request(app, peer, f"198.51.100.{i + 20}"))[0] == 400
        assert await request(app, peer, "203.0.113.99") == (429, {"error": "rate_limited"})
        assert set(routes.login_limit.peers) == {peer}
    asyncio.run(run())


@pytest.mark.parametrize("aliases", [("2001:db8::10", "2001:0db8:0:0:0:0:0:0010"),
                                    ("198.51.100.10", "::ffff:198.51.100.10")])
def test_equivalent_ip_spellings_share_one_budget(app, aliases):
    async def run():
        for _ in range(15):
            assert (await request(app, PROXY, aliases[0]))[0] == 400
        assert (await request(app, PROXY, aliases[1]))[0] == 429
    asyncio.run(run())


@pytest.mark.parametrize("peer,forwarded,expected,scheme", [
    (PROXY, "2001:db8::42", "2001:db8::42", "wss"),
    ("198.51.100.5", "203.0.113.8", "198.51.100.5", "ws"),
    ("2001:db8::5", "203.0.113.8", "2001:db8::5", "ws"),
])
def test_proxy_trust_is_identical_for_websocket_scope(peer, forwarded, expected, scheme):
    observed = []
    async def endpoint(scope, receive, send):
        observed.append((scope["client"][0], scope["scheme"]))
    app = ProxyHeadersMiddleware(endpoint, trusted_hosts=PROXY)
    scope = dict(type="websocket", client=(peer, 10), scheme="ws",
                 headers=[(b"x-forwarded-for", forwarded.encode()), (b"x-forwarded-proto", b"https")])
    asyncio.run(app(scope, None, None))
    assert observed == [(expected, scheme)]


def test_local_startup_disables_forwarded_trust_even_if_environment_is_broad(monkeypatch):
    import uvicorn
    options = {}
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: options.update(kwargs))
    server.main()
    assert options["forwarded_allow_ips"] == ""


def test_no_proxy_configuration_ignores_forged_headers(app):
    local = ProxyHeadersMiddleware(server.app, trusted_hosts="")
    async def run():
        for i in range(15):
            assert (await request(local, "127.0.0.1", f"198.51.100.{i}"))[0] == 400
        assert (await request(local, "127.0.0.1", "2001:db8::1"))[0] == 429
    asyncio.run(run())
