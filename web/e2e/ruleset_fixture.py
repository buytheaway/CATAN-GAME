"""Isolated synthetic legacy data + real production app/static build for F2 E2E.

DATABASE_URL must identify a disposable *_test database. No browser test routes
or gameplay mocks are added. Seed before starting the normal recovery lifespan.
"""
import asyncio
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

from sqlalchemy import update
from sqlalchemy.engine import make_url
from fastapi.staticfiles import StaticFiles

from app import server_mp as server
from app.auth.service import AuthService
from app.persistence import models as m
from app.persistence.coordinator import Coordinator
from app.persistence.db import Database
from app.persistence.recovery import checksum

ROOT = Path(__file__).resolve().parents[2]
url = os.environ.get("DATABASE_URL", "")
if not url or not make_url(url).database.endswith("_test"):
    raise RuntimeError("F2 browser fixture requires an isolated *_test database")

app = server.app
app.mount("/", StaticFiles(directory=ROOT / "web" / "dist", html=True), name="browser-production-build")


class Socket:
    def __init__(self): self.messages = []
    async def send_text(self, raw): self.messages.append(json.loads(raw))


async def seed(destination):
    db = Database(url)
    await db.migrate()
    server.manager = server.RoomManager()
    server.persistence = Coordinator(db)
    server.persistence.ready = True
    fixtures = {"guests": []}
    try:
        for version in (1, 2, "account"):
            clients = [server.ClientConn(Socket()), server.ClientConn(Socket())]
            for c in clients: server.manager.connections[c.ws] = c
            name = f"Legacy V{version} Alice"
            if version == "account":
                service = AuthService(db)
                login = {"username": "f2_browser_owner", "display_name": "Legacy Account Alice", "password": "synthetic browser password"}
                raw, _ = await service.authenticate(login, register=True)
                server.set_account_context(clients[0], await service.resolve(raw))
                fixtures["account"] = login
            await server._dispatch(clients[0], {"type": "create_room", "name": name, "max_players": 2})
            room = server.manager.rooms[clients[0].room_code]
            await server._dispatch(clients[0], {"type": "set_map", "map_id": "seafarers_gold_haven"})
            await server._dispatch(clients[1], {"type": "join_room", "name": "Synthetic Bob", "room_code": room.room_code})
            await server._dispatch(clients[0], {"type": "start_match"})
            bundle = await server.persistence.repository.load(room.id)
            head, payload = bundle["head"], deepcopy(bundle["head"]["payload"])
            codec = 1 if version == 1 else 2
            if codec == 1:
                payload["engine"]["snapshot_version"] = 1
                del payload["engine"]["state"]["ships_built_this_turn"]
                del payload["engine"]["state"]["ship_moved_this_turn"]
            async with db.sessions() as session, session.begin():
                await session.execute(update(m.matches).where(m.matches.c.id == room.match_uuid).values(ruleset_id=None))
                await session.execute(update(m.game_snapshots).where(m.game_snapshots.c.id == head["id"]).values(
                    payload=payload, checksum=checksum(payload), snapshot_version=codec))
            if version == "account":
                fixtures["account"]["room_code"] = room.room_code
            else:
                fixtures["guests"].append({"room_code": room.room_code, "reconnect_token": room.players[0].reconnect_token,
                    "last_known_name": name, "last_seen_at": 1})
        Path(destination).write_text(json.dumps(fixtures), encoding="utf-8")
        print("Synthetic v1/v2 guest and account fixtures created; proofs stay in the temporary E2E input file.")
    finally:
        await db.close()


if __name__ == "__main__":
    if sys.argv[1] == "--serve":
        import uvicorn
        uvicorn.run(app, host="127.0.0.1", port=18082, workers=1,
                    loop="app.persistence.db:selector_event_loop" if os.name == "nt" else "auto")
    else:
        asyncio.run(seed(sys.argv[1]))
