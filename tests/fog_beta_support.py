"""Normal public Fog beta acceptance. Test RNG only; no admission bypasses.

The subprocess uses the production application's unmodified lifespan and public
WebSocket handlers. Unlike the older internal fixture launcher it never installs
FixtureAdmission, FogMatchAccess, a prepared match, or a private lifecycle gate.
"""
from contextvars import ContextVar
from copy import deepcopy
import json
import os
from pathlib import Path
import random
from unittest.mock import patch
from uuid import uuid4

from tests.full_match_support import Backend, Match, SETTINGS, install_test_rng, validate_database_url
from tests.fog_natural_support import FogMatch
from tests.fog_live_support import connect


class BetaBackend(Backend):
    def __init__(self, database_url, *, admission=True, stopped=False, port=None, assignment_seed=501):
        super().__init__(database_url, port, module="tests.fog_beta_support")
        self.admission, self.stopped, self.assignment_seed = admission, stopped, assignment_seed

    def start(self):
        # These are deployment switches supplied to the normal child process,
        # never client fields or privileged transport capabilities.
        with patch.dict(os.environ, {
            "CATAN_FOG_BETA_ADMISSION": str(int(self.admission)),
            "CATAN_FOG_BETA_EMERGENCY_STOP": str(int(self.stopped)),
            "CATAN_BETA_TEST_ASSIGNMENT_SEED": str(self.assignment_seed),
        }):
            super().start()


class BetaMatch(FogMatch):
    def __init__(self, backend, *, verify_toggles=False):
        super().__init__(backend)
        from app.fog_beta import BETA_MAP_ID
        self.map_id = BETA_MAP_ID
        self.verify_toggles = verify_toggles

    async def create(self):
        # Shared helper performs real create/join/settings/set_map/start_match;
        # no manifest, state edits, private fixture recipe or server bypass.
        await Match.create(self)
        from app.fog_beta import BETA_RULESET
        _, match, _ = await durable_state(self.backend.database_url, self.room_code)
        assert match["ruleset_id"] == BETA_RULESET
        assert self.state["rules_config"]["target_vp"] == 12
        assert self.state["turn_timer"] is None
        assert self.peers[0].room["ruleset_compatibility"]["status"] == "compatible"

    async def restart(self):
        if self.verify_toggles and self.state["pending_action"] == "choose_gold":
            self.backend.admission = False
            self.recovery_evidence.append({"kind": "admission_off_during_pending_gold"})
        await super().restart()

    async def rematch(self, result):
        if self.verify_toggles:
            # Turning off NEW admissions preserves the current finished match
            # and credentials, but refuses a new epoch without altering data.
            self.backend.admission = False
            await self.restart()
            before, _ = await self.committed_game()
            peer = self.peers[0]
            previous = len(peer.errors)
            await peer.send({"type": "rematch", "request_id": uuid4().hex,
                             "expected_match_id": peer.state["match_id"]})
            await peer.wait(lambda: len(peer.errors) > previous)
            assert peer.errors[-1]["code"] == "feature_disabled"
            after, _ = await self.committed_game()
            assert after == before
            assert await self.durable_result() == result
            self.recovery_evidence.append({"kind": "admission_off_preserves_finished_match_rejects_rematch"})
            self.backend.admission = True
            await self.restart()
        await super().rematch(result)


async def lobby(backend, *, count=2, capacity=None):
    peers = []
    uri, origin = f"ws://127.0.0.1:{backend.port}/ws", f"http://127.0.0.1:{backend.port}"
    code = None
    for pid in range(count):
        peer = await connect(uri, origin=origin)
        peers.append(peer)
        await peer.send({"type": "create_room", "name": f"Beta {pid}", "max_players": capacity or count}
                        if pid == 0 else {"type": "join_room", "room_code": code, "name": f"Beta {pid}"})
        await peer.wait(lambda: peer.room is not None and peer.token is not None)
        code = peer.room["room_code"]
    return peers


async def rejection(peer, payload, code=None):
    count = len(peer.errors)
    await peer.send(payload)
    await peer.wait(lambda: len(peer.errors) > count or peer.closed)
    assert not peer.closed
    if code: assert peer.errors[-1]["code"] == code, peer.errors[-1]
    return peer.errors[-1]


async def select_beta(peers):
    from app.fog_beta import BETA_MAP_ID
    host = peers[0]
    revision = host.room["map_revision"]
    await host.send({"type": "set_settings", "settings": SETTINGS})
    await host.wait(lambda: host.room["settings"]["starting_player"] == "host")
    await host.send({"type": "set_map", "map_id": BETA_MAP_ID})
    await host.wait(lambda: host.room["map_revision"] > revision)


async def start(peers):
    await select_beta(peers)
    await peers[0].send({"type": "start_match", "request_id": uuid4().hex, "expected_match_id": 0})
    for peer in peers:
        await peer.wait(lambda: peer.state is not None)


async def close_lobby(peers):
    if (peers and peers[0].room is not None and peers[0].room["status"] == "lobby"
            and peers[0].state is None and not peers[0].closed):
        peer = peers[0]
        before = len(peer.frames)
        errors = len(peer.errors)
        await peer.send({"type": "close_room", "room_code": peer.room["room_code"],
                         "request_id": uuid4().hex, "expected_match_id": 0})
        # A controller intentionally replaced during a test has a stale lobby
        # view. Its denied cleanup must not mask the assertion being tested or
        # weaken ownership; preserve that room for an owning reconnect.
        await peer.wait(lambda: len(peer.errors) > errors or
                        any(f["type"] == "room_closed" for f in peer.frames[before:]))
    for peer in peers:
        await peer.close()


async def durable_state(database_url, code):
    """Read-only complete room/match head evidence, not agent policy input."""
    from sqlalchemy import select
    from app.persistence.db import Database
    from app.persistence import models as m
    database = Database(database_url)
    try:
        async with database.sessions() as session:
            room = (await session.execute(select(m.rooms).where(m.rooms.c.room_code == code))).mappings().one()
            match = snapshot = None
            if room["current_match_id"]:
                match = (await session.execute(select(m.matches).where(m.matches.c.id == room["current_match_id"]))).mappings().one()
                snapshot = (await session.execute(select(m.game_snapshots.c.payload).where(m.game_snapshots.c.id == match["latest_snapshot_id"]))).scalar_one()
            return dict(room), dict(match) if match else None, deepcopy(snapshot)
    finally:
        await database.close()


def serve():
    validate_database_url(os.environ.get("DATABASE_URL", ""))
    if os.environ.get("CATAN_ENABLE_TEST_TOOLS", "0") != "0" or os.environ.get("CATAN_HOST", "127.0.0.1") != "127.0.0.1":
        raise ValueError("Isolated loopback with Test Tools disabled is required")
    os.environ["CATAN_AUTH_MODE"] = "development"
    install_test_rng()
    from app import server_mp as server
    # Controllable private assignment RNG only. The original _start_match and
    # build_game run with all production admission/ownership/persistence gates.
    epoch = ContextVar("beta_test_rng_epoch", default=0)
    original_start, original_build = server._start_match, server.build_game
    seed = int(os.environ.get("CATAN_BETA_TEST_ASSIGNMENT_SEED", "501"))
    def start_with_rng(room, **kwargs):
        token = epoch.set(room.match_id)
        try: return original_start(room, **kwargs)
        finally: epoch.reset(token)
    def build_with_rng(*args, **kwargs):
        return original_build(*args, **kwargs, fog_rng=random.Random(seed + epoch.get()))
    server._start_match, server.build_game = start_with_rng, build_with_rng
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException
    dist = Path(__file__).resolve().parents[1] / "web" / "dist"
    if (dist / "index.html").is_file():
        class ProductionFiles(StaticFiles):
            async def get_response(self, path, scope):
                try: return await super().get_response(path, scope)
                except HTTPException as error:
                    if error.status_code != 404 or path.startswith(("assets/", "api/")): raise
                    return await super().get_response("index.html", scope)
        server.app.mount("/", ProductionFiles(directory=dist, html=True))
    import uvicorn
    uvicorn.run(server.app, host="127.0.0.1", port=int(os.environ["CATAN_PORT"]),
                loop="app.persistence.db:selector_event_loop" if os.name == "nt" else "auto",
                proxy_headers=False, log_level="error", access_log=False)


if __name__ == "__main__":
    serve()
