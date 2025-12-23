from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from app.catan_core import Game

app = FastAPI()

@dataclass
class Room:
    id: str
    game: Game = field(default_factory=Game)
    conns: Dict[str, WebSocket] = field(default_factory=dict)  # pid -> ws
    names: Dict[str, str] = field(default_factory=dict)        # pid -> name
    host_id: Optional[str] = None

ROOMS: Dict[str, Room] = {}

def get_room(room_id: str) -> Room:
    if room_id not in ROOMS:
        ROOMS[room_id] = Room(id=room_id)
    return ROOMS[room_id]

async def send(ws: WebSocket, obj: dict):
    await ws.send_text(json.dumps(obj, ensure_ascii=False))

def build_hints(game: Game, pid: str) -> dict:
    hints: dict = {}
    if game.board is None:
        return hints

    if game.current_player == pid:
        if game.phase == "setup":
            nodes = game.valid_initial_nodes()[:25]
            hints["setup_nodes"] = nodes
            if nodes:
                hints["setup_edges_for_node"] = {str(nodes[0]): game.valid_initial_edges(nodes[0])[:25]}
        elif game.phase == "main":
            hints["ports"] = game.ports_for_player(pid)
            if game.rolled:
                hints["build_edges"] = game.valid_build_edges(pid)[:30]
                hints["build_nodes"] = game.valid_build_nodes(pid)[:25]
        elif game.phase == "discard":
            hints["discard_required"] = game.discard_required.get(pid, 0)
        elif game.phase == "robber":
            all_hex = list(game.board.hexes.keys())
            hints["robber_hexes"] = [h for h in all_hex if h != game.board.robber_hex][:30]

    return hints

async def broadcast(room: Room):
    for pid, ws in list(room.conns.items()):
        try:
            await send(ws, {
                "type": "state",
                "public": room.game.public_state(),
                "private": room.game.private_state(pid),
                "you": pid,
                "host": room.host_id,
                "hints": build_hints(room.game, pid),
            })
        except Exception:
            pass

@app.get("/")
def root():
    return PlainTextResponse(
        "CATAN-GAME server running.\n"
        "WS: ws://HOST:8000/ws/<room>\n"
    )

@app.websocket("/ws/{room_id}")
async def ws_room(ws: WebSocket, room_id: str):
    await ws.accept()
    room = get_room(room_id)

    pid = secrets.token_hex(4)

    try:
        raw = await ws.receive_text()
        msg = json.loads(raw)
        if msg.get("type") != "join":
            await send(ws, {"type":"error","message":"first message must be join"})
            await ws.close()
            return

        name = str(msg.get("name") or "Player")[:24]
        room.conns[pid] = ws
        room.names[pid] = name
        if room.host_id is None:
            room.host_id = pid

        room.game.add_player(pid, name)
        await broadcast(room)

        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            t = msg.get("type")

            try:
                if t == "start":
                    if pid != room.host_id:
                        raise ValueError("only host can start")
                    room.game.start(seed=msg.get("seed"))

                elif t == "place":
                    room.game.place_initial(pid, int(msg["node"]), int(msg["edge"]))

                elif t == "roll":
                    room.game.roll_dice(pid)

                elif t == "discard":
                    room.game.discard(pid, msg.get("give") or {})

                elif t == "robber":
                    room.game.move_robber(pid, int(msg["hex"]), victim=msg.get("victim"))

                elif t == "build":
                    kind = msg.get("kind")
                    if kind == "road":
                        room.game.build_road(pid, int(msg["id"]), free=bool(msg.get("free", False)))
                    elif kind == "settlement":
                        room.game.build_settlement(pid, int(msg["id"]))
                    elif kind == "city":
                        room.game.build_city(pid, int(msg["id"]))
                    else:
                        raise ValueError("unknown build kind")

                elif t == "trade_bank":
                    room.game.trade_bank(pid, str(msg["give_res"]), int(msg["give_n"]), str(msg["get_res"]))

                elif t == "buy_dev":
                    room.game.buy_dev(pid)

                elif t == "play_dev":
                    kind = msg.get("kind")
                    if kind == "knight":
                        room.game.play_knight(pid, int(msg["hex"]), victim=msg.get("victim"))
                    elif kind == "road":
                        room.game.play_road_building(pid, int(msg["edge1"]), int(msg["edge2"]))
                    elif kind == "monopoly":
                        room.game.play_monopoly(pid, str(msg["res"]))
                    elif kind == "plenty":
                        room.game.play_year_of_plenty(pid, str(msg["res1"]), str(msg["res2"]))
                    else:
                        raise ValueError("unknown dev kind")

                elif t == "end":
                    room.game.end_turn(pid)

                else:
                    raise ValueError("unknown message type")

            except Exception as e:
                await send(ws, {"type":"error","message":str(e)})
                continue

            await broadcast(room)

    except WebSocketDisconnect:
        pass
    finally:
        if pid in room.conns:
            del room.conns[pid]
        await broadcast(room)
