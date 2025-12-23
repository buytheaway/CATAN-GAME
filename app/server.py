from __future__ import annotations
import json
import uuid
from typing import Dict, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse

from .game import Game

app = FastAPI()

class Room:
    def __init__(self):
        self.game = Game()
        self.clients: Dict[str, WebSocket] = {}  # pid -> ws

rooms: Dict[str, Room] = {}

@app.get("/")
def root():
    return PlainTextResponse("CATAN server OK. Use WebSocket /ws/{room}")

def _room(room_id: str) -> Room:
    if room_id not in rooms:
        rooms[room_id] = Room()
    return rooms[room_id]

async def send_state(room: Room):
    # broadcast state to each connected player
    for pid, ws in list(room.clients.items()):
        try:
            pub, priv, hints = room.game.state_for(pid)
            await ws.send_text(json.dumps({
                "type": "state",
                "you": pid,
                "public": pub,
                "private": priv,
                "hints": hints
            }, ensure_ascii=False))
        except Exception:
            # ignore send errors
            pass

def _require(d: dict, k: str):
    if k not in d:
        raise ValueError(f"missing {k}")
    return d[k]

@app.websocket("/ws/{room_id}")
async def ws(room_id: str, ws: WebSocket):
    await ws.accept()
    room = _room(room_id)

    pid: Optional[str] = None
    try:
        # first message must be join
        raw = await ws.receive_text()
        msg = json.loads(raw)
        if msg.get("type") != "join":
            await ws.send_text(json.dumps({"type":"error","message":"First message must be join"}, ensure_ascii=False))
            return

        name = str(msg.get("name") or "Player")[:24]
        pid = uuid.uuid4().hex[:8]

        # register player
        room.clients[pid] = ws
        p = room.game.add_player(pid, name)
        p.online = True

        await send_state(room)

        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            t = msg.get("type")

            try:
                g = room.game

                if t == "start":
                    g.start(pid, msg.get("seed"))
                elif t == "place":
                    g.place_setup(pid, int(_require(msg,"node")), int(_require(msg,"edge")))
                elif t == "roll":
                    g.roll(pid)
                elif t == "build":
                    g.build(pid, str(_require(msg,"kind")), int(_require(msg,"id")))
                elif t == "trade_bank":
                    g.trade_bank(pid, str(_require(msg,"give_res")), int(_require(msg,"give_n")), str(_require(msg,"get_res")))
                elif t == "offer_trade":
                    g.offer_trade(pid, str(_require(msg,"to")), dict(_require(msg,"give")), dict(_require(msg,"get")))
                elif t == "accept_trade":
                    g.accept_trade(pid, str(_require(msg,"offer_id")))
                elif t == "cancel_trade":
                    g.cancel_trade(pid, str(_require(msg,"offer_id")))
                elif t == "end":
                    g.end_turn(pid)
                else:
                    raise ValueError("unknown message type")

            except Exception as e:
                try:
                    await ws.send_text(json.dumps({"type":"error","message":str(e)}, ensure_ascii=False))
                except Exception:
                    pass

            await send_state(room)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if pid and pid in room.clients:
            del room.clients[pid]
        # mark offline
        if pid:
            try:
                room.game.get_player(pid).online = False
            except Exception:
                pass
        await send_state(room)
