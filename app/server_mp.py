from __future__ import annotations

import asyncio
import json
import os
import random
import string
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app import net_protocol
from app.engine import GameState, RuleError, apply_cmd, build_game, to_dict


@dataclass
class PlayerSlot:
    pid: int
    name: str = ""
    connected: bool = False


@dataclass
class ClientConn:
    ws: WebSocket
    name: str = ""
    room_code: Optional[str] = None
    pid: Optional[int] = None
    last_seq: int = -1


@dataclass
class Room:
    room_code: str
    max_players: int
    host_pid: int
    players: List[PlayerSlot]
    status: str = "lobby"
    match_id: int = 0
    tick: int = 0
    seed: int = 0
    game: Optional[GameState] = None
    last_activity_ts: float = field(default_factory=lambda: time.time())


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.connections: Dict[WebSocket, ClientConn] = {}

    def _gen_code(self) -> str:
        while True:
            code = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
            if code not in self.rooms:
                return code

    def create_room(self, name: str, max_players: int) -> Room:
        code = self._gen_code()
        players = [PlayerSlot(pid=i) for i in range(max_players)]
        room = Room(room_code=code, max_players=max_players, host_pid=0, players=players)
        self.rooms[code] = room
        self._assign_player(room, 0, name, connected=True)
        return room

    def _assign_player(self, room: Room, pid: int, name: str, connected: bool) -> None:
        slot = room.players[pid]
        slot.name = name
        slot.connected = connected

    def join_room(self, room_code: str, name: str) -> Optional[Room]:
        room = self.rooms.get(room_code)
        if not room:
            return None
        # reconnect by name
        for slot in room.players:
            if slot.name == name:
                slot.connected = True
                return room
        for slot in room.players:
            if not slot.name:
                slot.name = name
                slot.connected = True
                return room
        return None

    def leave_room(self, conn: ClientConn) -> None:
        if not conn.room_code:
            return
        room = self.rooms.get(conn.room_code)
        if not room or conn.pid is None:
            return
        room.players[conn.pid].connected = False
        room.last_activity_ts = time.time()


app = FastAPI()
manager = RoomManager()


def _snapshot_state(game: GameState, room: Room) -> Dict:
    state = to_dict(game)
    state["max_players"] = room.max_players
    return state


async def _send(ws: WebSocket, obj: Dict) -> None:
    await ws.send_text(json.dumps(obj))


async def _broadcast(room: Room, obj: Dict) -> None:
    for ws, conn in list(manager.connections.items()):
        if conn.room_code == room.room_code:
            try:
                await _send(ws, obj)
            except Exception:
                pass


async def _send_room_state(room: Room) -> None:
    await _broadcast(room, net_protocol.room_state_message(room))


async def _send_match_state(room: Room) -> None:
    if not room.game:
        return
    state = _snapshot_state(room.game, room)
    await _broadcast(room, net_protocol.match_state_message(room, state))


def _get_conn(ws: WebSocket) -> ClientConn:
    return manager.connections[ws]


def _start_match(room: Room) -> None:
    room.match_id += 1
    room.tick = 0
    room.seed = random.randint(1, 999999)
    room.game = build_game(seed=room.seed, max_players=room.max_players, size=58.0)
    for slot in room.players:
        if slot.name:
            room.game.players[slot.pid].name = slot.name
    room.status = "in_match"


def _apply_cmd(room: Room, pid: int, cmd: Dict) -> Optional[Dict]:
    g = room.game
    if not g:
        return net_protocol.error_message("no_match", "Match not started")

    ctype = cmd.get("type")
    if not isinstance(ctype, str):
        return net_protocol.error_message("invalid", "cmd.type required")

    if ctype == "roll":
        forced = cmd.get("forced")
        if forced is not None and os.getenv("CATAN_DEBUG_ROLLS") != "1":
            return net_protocol.error_message("illegal", "Forced roll disabled")
        if forced is not None:
            cmd = dict(cmd)
            cmd["roll"] = int(forced)
        elif cmd.get("roll") is None:
            cmd = dict(cmd)
            cmd["roll"] = random.randint(1, 6) + random.randint(1, 6)

    try:
        apply_cmd(g, pid, cmd)
    except RuleError as exc:
        return net_protocol.error_message(exc.code, exc.message, exc.details)
    return None


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    conn = ClientConn(ws=ws)
    manager.connections[ws] = conn
    try:
        while True:
            msg = await ws.receive_text()
            try:
                data = json.loads(msg)
            except Exception:
                await _send(ws, net_protocol.error_message("invalid", "Invalid JSON"))
                continue

            val = net_protocol.validate_client_message(data)
            if not val.get("ok"):
                err = val.get("error", {})
                await _send(ws, net_protocol.error_message(err.get("code", "invalid"), err.get("message", "invalid"), err.get("detail")))
                continue

            mtype = data.get("type")
            if mtype == "hello":
                conn.name = data.get("name")
                await _send(ws, {"type": "hello", "version": net_protocol.VERSION})
                continue

            if mtype == "create_room":
                room = manager.create_room(data.get("name"), data.get("max_players", 4))
                conn.room_code = room.room_code
                conn.pid = 0
                await _send(ws, net_protocol.room_state_message(room))
                continue

            if mtype == "join_room":
                room_code = data.get("room_code")
                room = manager.join_room(room_code, data.get("name"))
                if not room:
                    await _send(ws, net_protocol.error_message("not_found", "Room not found or full"))
                    continue
                # bind pid
                pid = None
                for slot in room.players:
                    if slot.name == data.get("name"):
                        pid = slot.pid
                        break
                conn.room_code = room.room_code
                conn.pid = pid
                await _send(ws, net_protocol.room_state_message(room))
                await _send_room_state(room)
                continue

            if mtype == "leave_room":
                manager.leave_room(conn)
                if conn.room_code:
                    room = manager.rooms.get(conn.room_code)
                    if room:
                        await _send_room_state(room)
                conn.room_code = None
                conn.pid = None
                continue

            if mtype == "start_match":
                room = manager.rooms.get(conn.room_code or "")
                if not room:
                    await _send(ws, net_protocol.error_message("not_found", "Room not found"))
                    continue
                if conn.pid != room.host_pid:
                    await _send(ws, net_protocol.error_message("forbidden", "Only host can start"))
                    continue
                if sum(1 for p in room.players if p.name) < 2:
                    await _send(ws, net_protocol.error_message("invalid", "Need at least 2 players"))
                    continue
                _start_match(room)
                await _send_room_state(room)
                await _send_match_state(room)
                continue

            if mtype == "rematch":
                room = manager.rooms.get(conn.room_code or "")
                if not room:
                    await _send(ws, net_protocol.error_message("not_found", "Room not found"))
                    continue
                if conn.pid != room.host_pid:
                    await _send(ws, net_protocol.error_message("forbidden", "Only host can rematch"))
                    continue
                _start_match(room)
                await _send_match_state(room)
                continue

            if mtype == "cmd":
                room = manager.rooms.get(conn.room_code or "")
                if not room:
                    await _send(ws, net_protocol.error_message("not_found", "Room not found"))
                    continue
                if data.get("match_id") != room.match_id:
                    await _send(ws, net_protocol.error_message("invalid", "match_id mismatch"))
                    continue
                seq = int(data.get("seq"))
                if seq <= conn.last_seq:
                    continue
                conn.last_seq = seq

                err = _apply_cmd(room, conn.pid, data.get("cmd", {}))
                if err:
                    await _send(ws, err)
                    continue

                room.tick += 1
                room.last_activity_ts = time.time()
                await _send_match_state(room)
                continue

    except WebSocketDisconnect:
        manager.leave_room(conn)
        if conn.room_code:
            room = manager.rooms.get(conn.room_code)
            if room:
                await _send_room_state(room)
        manager.connections.pop(ws, None)
    except Exception:
        manager.connections.pop(ws, None)


def main():
    import uvicorn

    uvicorn.run("app.server_mp:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
