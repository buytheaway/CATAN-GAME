"""Opt-in acceptance against an already-running disposable Compose project.

Set CATAN_PROXY_TEST_PROJECT to its *-test project name. This test never builds,
starts, stops or modifies the user's stack/database, and never prints cookies.
Start compose.yaml + tests/auth_proxy.compose.yaml under that explicit project;
the fixture forces a local disposable DB and enables IPv6 acceptance.
"""
import json
import os
import subprocess
import time
import uuid

import pytest


def docker(*args, source=None):
    result = subprocess.run(["docker", *args], input=source, text=True,
                            capture_output=True, timeout=90, check=False)
    assert result.returncode == 0, "Disposable Docker operation failed (private output omitted)"
    return result.stdout.strip()


@pytest.fixture
def stack():
    project = os.getenv("CATAN_PROXY_TEST_PROJECT")
    if not project:
        pytest.skip("Opt-in real Nginx acceptance: CATAN_PROXY_TEST_PROJECT=isolated *-test project")
    assert project.endswith("-test") and project != "catan-game"
    containers = json.loads(docker("inspect", f"{project}-backend-1", f"{project}-web-1", f"{project}-postgres-1"))
    assert all(c["Config"]["Labels"]["com.docker.compose.project"] == project for c in containers)
    backend, web, postgres = containers
    assert any(e.startswith("POSTGRES_DB=") and e.endswith("_test") for e in postgres["Config"]["Env"])
    assert not backend["HostConfig"]["PortBindings"]
    network = next(n for n in web["NetworkSettings"]["Networks"] if n.endswith("_proxy"))
    nginx = web["NetworkSettings"]["Networks"][network]
    assert f'FORWARDED_ALLOW_IPS={nginx["IPAddress"]}' in backend["Config"]["Env"]
    assert nginx["GlobalIPv6Address"], "Use an IPv6-enabled disposable proxy network"
    assert set(web["NetworkSettings"]["Networks"]) == {network}
    assert network not in postgres["NetworkSettings"]["Networks"]
    # Reset only this disposable backend's in-process budgets; retain DB data.
    docker("restart", backend["Id"])
    for _ in range(30):
        state = json.loads(docker("inspect", backend["Id"]))[0]["State"]
        if state.get("Health", {}).get("Status") == "healthy":
            break
        time.sleep(0.5)
    else:
        pytest.fail("Disposable backend did not become healthy")
    clients = []
    try:
        for suffix in ("a", "b", "c"):
            name = f"{project}-probe-{suffix}-{uuid.uuid4().hex[:6]}"
            docker("run", "-d", "--name", name, "--network", network,
                   "-e", f'SEC04_WEB_URL=http://{nginx["IPAddress"]}:8080',
                   backend["Config"]["Image"], "python", "-c", "import time; time.sleep(300)")
            clients.append(name)
        yield clients, nginx, backend
    finally:
        for name in clients:
            docker("rm", "-f", name)


REQUEST = '''
import json, os, urllib.request, urllib.error
def request(path="/api/auth/login", data=None, headers=None, url=None):
    url = url or os.environ.get("SEC04_WEB_URL", "http://web:8080")
    hdr = {"Content-Type": "application/json", "Origin": "http://sec04.test", **(headers or {})}
    req = urllib.request.Request(url + path, data=json.dumps(data or {}).encode(), headers=hdr)
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.code, json.load(response), response.headers
'''


def probe(name, source):
    return json.loads(docker("exec", "-i", name, "python", "-", source=REQUEST + source))


def test_real_nginx_independent_budgets_spoofing_ipv6_auth_and_reconnect(stack):
    (a, b, c), nginx, backend = stack
    forged = '{"X-Forwarded-For": "203.0.113.9, 127.0.0.1", "X-Real-IP": "203.0.113.9", "Forwarded": "for=203.0.113.9"}'
    assert probe(a, 'print(json.dumps([request()[0] for _ in range(16)]))') == [400] * 15 + [429]
    assert probe(b, 'print(json.dumps(request()[0]))') == 400
    assert probe(a, f'print(json.dumps(request(headers={forged})[:2]))') == [429, {"error": "rate_limited"}]
    # Direct backend peer is untrusted, even from the same Docker subnet.
    direct = next(v["IPAddress"] for k, v in backend["NetworkSettings"]["Networks"].items() if k.endswith("_proxy"))
    assert probe(a, f'print(json.dumps(request(headers={forged}, url="http://{direct}:8000")[:2]))') == [429, {"error": "rate_limited"}]

    registration = '''
import uuid
data = {"username": "sec04_" + uuid.uuid4().hex[:16], "display_name": "Disposable", "password": "public synthetic test password"}
print(json.dumps([request("/api/auth/register", data)[0] for _ in range(6)]))
'''
    assert probe(a, registration) == [201] + [409] * 4 + [429]
    assert probe(b, registration.replace('range(6)', 'range(1)')) == [201]
    assert probe(a, f'print(json.dumps(request("/api/auth/register", headers={forged})[:2]))') == [429, {"error": "rate_limited"}]

    # IPv6 is a real client -> Nginx connection, not a forged IPv6 header.
    ipv6_url = f'http://[{nginx["GlobalIPv6Address"]}]:8080'
    assert probe(a, f'print(json.dumps([request(url="{ipv6_url}")[0] for _ in range(16)]))') == [400] * 15 + [429]
    assert probe(b, f'print(json.dumps(request(url="{ipv6_url}")[0]))') == 400
    assert probe(a, f'print(json.dumps(request(headers={forged}, url="{ipv6_url}")[0]))') == 429

    # One synthetic account; cookie/session and seat ownership remain unchanged.
    account = '''
import asyncio, uuid, websockets
data = {"username": "sec04_" + uuid.uuid4().hex[:16], "display_name": "Disposable", "password": "public synthetic test password"}
status, result, hdr = request("/api/auth/register", data)
assert status == 201 and result["authenticated"]
cookie = hdr["Set-Cookie"].split(";", 1)[0]
assert "HttpOnly" in hdr["Set-Cookie"] and "SameSite=lax" in hdr["Set-Cookie"]
for origin in ("http://foreign.test", "null"):
    assert request(headers={"Origin": origin})[0] == 403
assert request(headers={"Origin": ""})[0] == 403
status, _, hdr = request("/api/auth/login", {k: data[k] for k in ("username", "password")})
assert status == 200
cookie = hdr["Set-Cookie"].split(";", 1)[0]
with urllib.request.urlopen(urllib.request.Request("http://web:8080/api/auth/me", headers={"Cookie": cookie})) as response:
    assert json.load(response)["authenticated"]
async def message(ws, kind):
    while True:
        value = json.loads(await asyncio.wait_for(ws.recv(), 10))
        assert value["type"] != "error", "Unexpected safe WS refusal"
        if value["type"] == kind:
            return value
async def run():
    async with websockets.connect("ws://web:8080/ws", origin="http://sec04.test", additional_headers={"Cookie": cookie}) as ws:
        await ws.send(json.dumps({"type": "create_room", "name": "Disposable", "max_players": 2}))
        room = await message(ws, "room_state")
    async with websockets.connect("ws://web:8080/ws", origin="http://sec04.test", additional_headers={"Cookie": cookie}) as ws:
        await ws.send(json.dumps({"type": "account_continue", "room_code": room["room_code"]}))
        assert (await message(ws, "room_state"))["room_code"] == room["room_code"]
    async with websockets.connect("ws://web:8080/ws", origin="http://sec04.test") as ws:
        await ws.send(json.dumps({"type": "create_room", "name": "Guest", "max_players": 2}))
        guest = await message(ws, "reconnect_token")
    async with websockets.connect("ws://web:8080/ws", origin="http://sec04.test") as ws:
        await ws.send(json.dumps({"type": "reconnect", "room_code": guest["room_code"], "reconnect_token": guest["reconnect_token"]}))
        assert (await message(ws, "room_state"))["room_code"] == guest["room_code"]
asyncio.run(run())
print(json.dumps({"account_login": True, "account_continue": True, "guest_reconnect": True, "origin": True}))
'''
    assert all(probe(c, account).values())
