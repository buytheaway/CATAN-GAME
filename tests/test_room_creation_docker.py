"""Bounded raw WebSocket acceptance through real trusted Nginx, disposable PG."""
import json
import ipaddress
import os
import secrets

import pytest

from tests.test_auth_proxy_docker import docker, probe as proxy_probe, stack as proxy_stack


@pytest.fixture
def stack(monkeypatch, request):
    project = os.getenv("CATAN_ROOM_LIMIT_TEST_PROJECT")
    if not project:
        pytest.skip("Opt-in room-limit acceptance: CATAN_ROOM_LIMIT_TEST_PROJECT=isolated *-test project")
    monkeypatch.setenv("CATAN_PROXY_TEST_PROJECT", project)
    clients, nginx, backend = request.getfixturevalue("proxy_stack")
    # Persistent quotas deliberately survive restart. Give disposable probes fresh
    # real IPv6 addresses on each run rather than clearing DB data or bypassing limits.
    first = json.loads(docker("inspect", clients[0]))[0]
    network = next(name for name in first["NetworkSettings"]["Networks"] if name.endswith("_proxy"))
    prefix = int(ipaddress.IPv6Network(nginx["GlobalIPv6Address"] + "/64", strict=False).network_address)
    for name in clients:
        address = str(ipaddress.IPv6Address(prefix | secrets.randbits(64)))
        docker("network", "disconnect", network, name)
        docker("network", "connect", "--ip6", address, network, name)
        docker("exec", "-i", name, "python", "-c",
               "import sys; from pathlib import Path; Path('/tmp/sec03-public-url.txt').write_text(sys.stdin.read())",
               source=f'http://[{nginx["GlobalIPv6Address"]}]:8080')
    return clients, nginx, backend


def probe(name, source):
    return proxy_probe(name, "from pathlib import Path\nos.environ['SEC04_WEB_URL']=Path('/tmp/sec03-public-url.txt').read_text()\n" + source)


def metadata_counts(backend):
    return json.loads(docker("exec", "-i", backend["Id"], "python", "-", source='''
import asyncio, json
from sqlalchemy import select, func
from app.persistence import models as m
from app.persistence.db import configured_database
async def run():
    db = configured_database()
    async with db.sessions() as session:
        values = [(await session.execute(select(func.count()).select_from(t))).scalar_one()
                  for t in (m.rooms, m.room_players, m.seat_tokens)]
    await db.close()
    print(json.dumps(values))
asyncio.run(run())
'''))


WS = '''
import asyncio, websockets
async def receive(ws, *types):
    while True:
        value = json.loads(await asyncio.wait_for(ws.recv(), 10))
        if value['type'] in types: return value
async def create(headers=None, uri=None):
    uri = uri or os.environ['SEC04_WEB_URL'].replace('http://', 'ws://')+'/ws'
    async with websockets.connect(uri, origin='http://sec04.test', additional_headers=headers or {}) as ws:
        await ws.send(json.dumps({'type':'create_room','name':'Bounded SEC03 guest','max_players':2}))
        value = await receive(ws, 'room_state', 'error')
        if value['type'] == 'error': return {'error': value['code']}
        token = await receive(ws, 'reconnect_token')
        return {'code':value['room_code'], 'token':token['reconnect_token']}
'''


def test_real_proxy_same_ip_new_sockets_spoofing_other_clients_recovery_and_join(stack):
    (a, b, c), nginx, backend = stack
    assert "CATAN_ROOM_CREATE_LIMIT=3" in backend["Config"]["Env"], "Use room_limits.compose.yaml"
    # Reuse one client process to reconnect; the in-process secret never appears in tool output.
    before = metadata_counts(backend)
    result = probe(a, WS + '''
from pathlib import Path
async def run():
    successful = [await create() for _ in range(3)]
    assert all('code' in item for item in successful)
    Path('/tmp/sec03-proof.json').write_text(json.dumps(successful[0]))
    failures = [await create({'X-Forwarded-For':str(i)+'.1.1.1', 'X-Real-IP':'203.0.113.9',
                             'Forwarded':'for=203.0.113.8'}) for i in range(2)]
    assert all(item == {'error':'room_creation_rate_limited'} for item in failures)
    print(json.dumps({'accepted':3,'rejected':2,'code':successful[0]['code']}))
asyncio.run(run())
''')
    assert result["accepted"] == 3 and result["rejected"] == 2
    assert metadata_counts(backend) == [value + 3 for value in before]
    direct = next(v["IPAddress"] for k, v in backend["NetworkSettings"]["Networks"].items() if k.endswith("_proxy"))
    direct_result = probe(a, WS + f'''
async def run():
    # Backend listens on IPv4. This is the actual IPv4 peer's separate budget,
    # not the IPv6 budget exhausted above. No arbitrary forwarding is trusted.
    results = [await create({{'X-Forwarded-For':f'198.51.100.{{i}}'}}, 'ws://{direct}:8000/ws') for i in range(5)]
    accepted = sum('code' in result for result in results)
    assert accepted <= 3
    assert results[-1]['error'] in ('room_creation_rate_limited', 'ip_lobby_limit_reached')
    print(json.dumps({{'accepted':accepted,'rejected':5-accepted}}))
asyncio.run(run())
''')
    assert direct_result["rejected"] >= 2
    assert metadata_counts(backend) == [value + 3 + direct_result["accepted"] for value in before]
    # Different physical client gets its own quota despite forged incoming headers.
    other = probe(b, WS + '''
async def run():
    result = await create({'X-Forwarded-For':'203.0.113.9'})
    assert 'code' in result
    print(json.dumps({'accepted':True}))
asyncio.run(run())
''')
    assert other == {"accepted": True}
    # A quota refusal must not fence unrelated rooms or readiness.
    joined = probe(c, WS + f'''
async def run():
    async with websockets.connect(os.environ['SEC04_WEB_URL'].replace('http://','ws://')+'/ws', origin='http://sec04.test') as ws:
        await ws.send(json.dumps({{'type':'join_room','name':'Other guest','room_code':{result['code']!r}}}))
        value = await receive(ws, 'room_state', 'error')
        assert value['type'] == 'room_state'
        print(json.dumps({{'joined':True}}))
asyncio.run(run())
''')
    assert joined == {"joined": True}
    docker("restart", backend["Id"])
    # Wait for real health without reading credentials or private snapshots.
    assert probe(a, '''
import time
for _ in range(40):
    try:
        with urllib.request.urlopen(os.environ['SEC04_WEB_URL']+'/health',timeout=2) as r:
            assert r.status == 200
        print(json.dumps(True)); break
    except (urllib.error.URLError, AssertionError): time.sleep(.25)
else: raise AssertionError('Disposable restart failed')
''')
    counts = metadata_counts(backend)
    assert probe(a, WS + '''
from pathlib import Path
async def run():
    assert await create({'X-Forwarded-For':'198.51.100.99'}) == {'error':'room_creation_rate_limited'}
    proof = json.loads(Path('/tmp/sec03-proof.json').read_text())
    async with websockets.connect(os.environ['SEC04_WEB_URL'].replace('http://','ws://')+'/ws', origin='http://sec04.test') as ws:
        await ws.send(json.dumps({'type':'reconnect','room_code':proof['code'],'reconnect_token':proof['token']}))
        value = await receive(ws,'room_state','error')
        assert value['type'] == 'room_state'
        print(json.dumps({'reconnected':True,'rate_survived_restart':True}))
asyncio.run(run())
''') == {"reconnected": True, "rate_survived_restart": True}
    assert metadata_counts(backend) == counts
