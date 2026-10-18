"""Opt-in normal production image + real Nginx/WS/disposable PostgreSQL."""
import asyncio
import json
import os
from uuid import uuid4

import pytest

from app.fog_beta import BETA_MAP_ID
from tests.test_auth_proxy_docker import docker
from tests.fog_live_support import connect, http_json
from tests.fog_beta_support import rejection


def test_production_docker_beta_admission_and_real_setup():
    project = os.environ.get("CATAN_FOG_BETA_TEST_PROJECT")
    if not project:
        pytest.skip("CATAN_FOG_BETA_TEST_PROJECT requires an isolated *-test Compose stack")
    assert project.endswith("-test") and project != "catan-game"
    backend, web, postgres = json.loads(docker("inspect", f"{project}-backend-1",
                                                f"{project}-web-1", f"{project}-postgres-1"))
    assert all(c["Config"]["Labels"]["com.docker.compose.project"] == project for c in (backend, web, postgres))
    assert any(e.startswith("POSTGRES_DB=") and e.endswith("_test") for e in postgres["Config"]["Env"])
    assert not backend["HostConfig"]["PortBindings"]
    bindings = web["HostConfig"]["PortBindings"]["8080/tcp"]
    assert len(bindings) == 1 and bindings[0]["HostIp"] == "127.0.0.1"
    origin = f'http://127.0.0.1:{bindings[0]["HostPort"]}'
    uri = origin.replace("http", "ws", 1) + "/ws"
    enabled = "CATAN_FOG_BETA_ADMISSION=1" in backend["Config"]["Env"]
    assert "CATAN_FOG_BETA_EMERGENCY_STOP=1" not in backend["Config"]["Env"]
    assert docker("exec", backend["Id"], "python", "-c",
                  "from app.server_mp import app; print(hasattr(app.state,'_fog_fixture_access'))") == "False"

    async def run():
        peers = []
        try:
            status, health = await http_json(uri, "/health")
            assert status == 200 and health["ready"]
            host = await connect(uri, origin=origin)
            peers.append(host)
            await host.send({"type": "create_room", "name": "Docker beta host", "max_players": 2})
            await host.wait(lambda: host.room is not None and host.token is not None)
            assert (BETA_MAP_ID in {p["id"] for p in host.room["map_presets"]}) is enabled
            if not enabled:
                await rejection(host, {"type": "set_map", "map_id": BETA_MAP_ID}, "feature_disabled")
                assert host.state is None
                count = len(host.frames)
                await host.send({"type": "close_room", "room_code": host.room["room_code"],
                                 "request_id": uuid4().hex, "expected_match_id": 0})
                await host.wait(lambda: any(f["type"] == "room_closed" for f in host.frames[count:]))
                return
            guest = await connect(uri, origin=origin)
            peers.append(guest)
            await guest.send({"type": "join_room", "room_code": host.room["room_code"], "name": "Docker beta guest"})
            await guest.wait(lambda: guest.room is not None)
            revision = host.room["map_revision"]
            await host.send({"type": "set_map", "map_id": BETA_MAP_ID})
            await host.wait(lambda: host.room["map_revision"] > revision)
            await host.send({"type": "start_match", "request_id": uuid4().hex, "expected_match_id": 0})
            await asyncio.gather(*(p.wait(lambda p=p: p.state is not None) for p in peers))
            assert host.room["ruleset_compatibility"]["ruleset_id"] == "catan-fog-beta-1"
            assert sum(t["visibility"] == "hidden" for t in host.state["state"]["tiles"]) == 8
            for _ in range(32):
                state = host.state["state"]
                for pid, peer in enumerate(peers):
                    personal = peer.state["state"]
                    assert personal["you_pid"] == pid and "seed" not in personal
                    assert all(("res" in p) is (p["pid"] == pid) for p in personal["players"])
                    assert all(t["terrain"] == "fog" and t["number"] is None for t in personal["tiles"] if t["visibility"] == "hidden")
                if state["phase"] == "main" and not state["pending_action"]:
                    assert state["rules_config"]["target_vp"] == 12 and state["turn_timer"] is None
                    return
                actor = state["pending_pid"] if state["pending_pid"] is not None else state["turn"]
                own = peers[actor].state["state"]
                legal = own["legal"]
                if state["pending_action"] == "choose_gold":
                    cmd = {"type": "choose_gold", "res": "wood", "qty": 1}
                elif legal["settlements"]:
                    cmd = {"type": "place_settlement", "vid": legal["settlements"][0]}
                elif legal["ships"]:
                    cmd = {"type": "build_ship", "eid": legal["ships"][0]}
                else:
                    assert legal["roads"]
                    cmd = {"type": "place_road", "eid": legal["roads"][0]}
                tick = host.state["tick"]
                await peers[actor].execute(cmd)
                await asyncio.gather(*(p.wait(lambda p=p: p.state["tick"] > tick) for p in peers))
            pytest.fail("Normal Docker setup did not complete")
        finally:
            await asyncio.gather(*(p.close() for p in peers), return_exceptions=True)
    asyncio.run(run())
