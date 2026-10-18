"""Real loopback Fog transport fixtures. Never imported by production startup.

The optional subprocess entry mounts the normal web/dist and reinstalls only
manifest-bound in-process access after normal PostgreSQL recovery. No endpoint
creates Fog or reads the manifest. The file contains synthetic seat proofs/IDs,
not trusted boards, assignments, pools or RNG; keep it outside tracked files.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

import uvicorn
import websockets
from websockets.exceptions import ConnectionClosed

from tests.full_match_support import Peer, free_port, validate_database_url


class WirePeer(Peer):
    def __init__(self, socket):
        self.frames = []
        self.last_seq = 0
        self.nonce = None
        super().__init__(socket)

    async def _read(self):
        try:
            async for raw in self.socket:
                message = json.loads(raw)
                self.frames.append(message)
                kind = message["type"]
                if kind == "cmd_ack" and message["cmd_id"] in self.drop_ack_ids:
                    continue  # Deliberate client-side ACK loss, never server rollback.
                if kind == "match_state": self.state = message
                elif kind == "room_state": self.room = message
                elif kind == "reconnect_token": self.token = message["reconnect_token"]
                elif kind == "hello": self.nonce = message["connection_nonce"]
                elif kind == "cmd_ack": self.acks[message["cmd_id"]] = message
                elif kind == "error": self.errors.append(message)
                if "last_seq_applied" in message: self.last_seq = message["last_seq_applied"]
                self.changed.set()
        except ConnectionClosed:
            pass
        finally:
            self.closed = True
            self.changed.set()

    def command(self, cmd, *, seq=None, cmd_id=None):
        return {"type":"cmd", "room_code":self.room["room_code"], "match_id":self.state["match_id"],
                "seq":self.last_seq+1 if seq is None else seq, "cmd_id":cmd_id or uuid4().hex, "cmd":cmd}

    async def execute(self, cmd, *, applied=True, request=None):
        request = request or self.command(cmd)
        self.acks.pop(request["cmd_id"],None)
        await self.send(request)
        await self.wait(lambda: request["cmd_id"] in self.acks or self.closed)
        assert not self.closed, "Owning fixture socket unexpectedly closed"
        ack = self.acks[request["cmd_id"]]
        assert ack["applied"] is applied, "Unexpected durable command outcome"
        return request, ack


async def connect(uri, *, cookie=None, origin="http://test"):
    from app.auth.security import COOKIE
    headers = {"Cookie":f"{COOKIE}={cookie}"} if cookie else None
    peer = WirePeer(await websockets.connect(uri, origin=origin, additional_headers=headers, max_size=2**22))
    await peer.send({"type":"hello", "version":1, "name":"Fog fixture participant"})
    await peer.wait(lambda: peer.nonce is not None)
    return peer


async def reconnect(uri, code, proof, **kwargs):
    peer = await connect(uri, **kwargs)
    await peer.send({"type":"reconnect", "room_code":code, "reconnect_token":proof})
    await peer.wait(lambda: peer.state is not None)
    return peer


@asynccontextmanager
async def tcp_server():
    from app import server_mp as server
    port = free_port()
    instance = uvicorn.Server(uvicorn.Config(server.app, host="127.0.0.1", port=port,
        lifespan="off", log_level="error", access_log=False, proxy_headers=False))
    task = asyncio.create_task(instance.serve())
    try:
        async def ready():
            while not instance.started:
                if task.done(): await task
                await asyncio.sleep(.01)
        await asyncio.wait_for(ready(),5)
        yield f"ws://127.0.0.1:{port}/ws"
    finally:
        instance.should_exit = True
        await asyncio.wait_for(task,10)


async def fixture_room(coord, **kwargs):
    from app import server_mp as server
    from app.persistence.recovery import clone_room
    from tests.test_fog_exploration_recovery import internal_room
    room, clients, route = await internal_room(coord, **kwargs)
    # Explicit privacy fixture: real deck cards, conserved resources, hidden bank.
    # This is NOT a naturally played opening or a production fixture endpoint.
    candidate=clone_room(room)
    candidate.settings=replace(candidate.settings,bank_visibility="hidden")
    for player in candidate.game.players:
        for card in ("knight","victory_point"):
            candidate.game.dev_deck.remove(card)
            player.dev_cards.append({"type":card,"new":False})
        player.vp+=1
    await server._commit(room,candidate,snapshot=True,trusted_fog=True)
    proofs = [c.ws.latest("reconnect_token")["reconnect_token"] for c in clients]
    for c in clients:
        server.manager.leave_room(c)
        server.manager.connections.pop(c.ws)
    return room, proofs, route


async def ship_movement_room(coord):
    """Prepared visual acceptance fixture; the original executor validates the move."""
    from copy import deepcopy
    from app.engine import rules
    from tests.test_fog_exploration import movement_fixture
    game, source, target = movement_fixture("gold")
    room, proofs, _ = await fixture_room(coord, game=game, kind="build_ship")
    command = {"type": "move_ship", "from_eid": list(source), "to_eid": list(target)}
    # Validate on a detached copy; never execute a move as recovery or preload.
    candidate = deepcopy(room.game)
    rules.apply_cmd(candidate, 0, command, trusted_fog=True)
    assert source in room.game.occupied_ships and target not in room.game.occupied_ships
    assert source not in candidate.occupied_ships and candidate.occupied_ships[target] == 0
    return room, proofs, command


async def http_json(uri, path, data=None, *, cookie=None, origin="http://test"):
    from app.auth.security import COOKIE
    def request():
        headers = {"Origin":origin, "Content-Type":"application/json"}
        if cookie: headers["Cookie"] = f"{COOKIE}={cookie}"
        query = Request(uri.replace("ws://","http://").removesuffix("/ws")+path,
            data=None if data is None else json.dumps(data).encode(), headers=headers)
        try: response = urlopen(query,timeout=5)
        except HTTPError as error: response = error
        with response:
            return response.status, json.loads(response.read())
    return await asyncio.to_thread(request)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",type=int,default=18769)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--ship-motion",action="store_true",help="Include a validated prepared ship-movement visual fixture")
    args=parser.parse_args()
    validate_database_url(os.environ.get("DATABASE_URL",""))
    if args.port<1024 or os.environ.get("CATAN_ENABLE_TEST_TOOLS","0")!="0":
        raise SystemExit("Unprivileged loopback port and disabled Test Tools required")
    origin=f"http://127.0.0.1:{args.port}"
    os.environ.update(CATAN_AUTH_MODE="development", CATAN_AUTH_ORIGINS=origin,
                     CATAN_PERSISTENCE_MODE="durable", CATAN_ENABLE_TEST_TOOLS="0")
    from app import server_mp as server
    from app.fog_transport import FogMatchAccess
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException
    original=server.app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            if args.manifest.is_file():
                manifest=json.loads(args.manifest.read_text(encoding="utf-8"))
            else:
                manifest=[]
                for setup,kind in ((True,"place_road"),(False,"build_ship")):
                    room,proofs,route=await fixture_room(server.persistence,setup=setup,kind=kind)
                    manifest.append({"room_code":room.room_code,"room_id":str(room.id),
                        "match_uuid":str(room.match_uuid),"proofs":proofs,"route":route,"setup":setup})
                if args.ship_motion:
                    room,proofs,route=await ship_movement_room(server.persistence)
                    manifest.append({"room_code":room.room_code,"room_id":str(room.id),
                        "match_uuid":str(room.match_uuid),"proofs":proofs,"route":route,"setup":False})
                args.manifest.parent.mkdir(parents=True,exist_ok=True)
                args.manifest.write_text(json.dumps(manifest),encoding="utf-8")
            access=[]
            for entry in manifest:
                scope=FogMatchAccess(UUID(entry["room_id"]),UUID(entry["match_uuid"]))
                room=server.manager.rooms.get(entry["room_code"])
                if not scope.permits(room): raise RuntimeError("Fixture manifest does not match recovered native state")
                access.append(scope)
            app.state._fog_fixture_access=tuple(access)
            try: yield
            finally: del app.state._fog_fixture_access

    server.app.router.lifespan_context=lifespan
    dist=Path(__file__).resolve().parents[1]/"web"/"dist"
    if not (dist/"index.html").is_file(): raise SystemExit("Build production web/dist first")
    class ProductionFiles(StaticFiles):
        async def get_response(self,path,scope):
            try: return await super().get_response(path,scope)
            except HTTPException as error:
                if error.status_code!=404 or path.startswith(("assets/","api/")): raise
                return await super().get_response("index.html",scope)
    server.app.mount("/",ProductionFiles(directory=dist,html=True))
    uvicorn.run(server.app,host="127.0.0.1",port=args.port,proxy_headers=False,
        loop="app.persistence.db:selector_event_loop" if os.name=="nt" else "auto",log_level="error",access_log=False)


if __name__=="__main__": main()
