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
from app.rules_engine import (
    GameState,
    COST,
    build_game,
    can_pay,
    can_place_road,
    can_place_settlement,
    can_upgrade_city,
    check_win,
    distribute_for_roll,
    pay_to_bank,
    update_longest_road,
)


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
    return {
        "state_version": 1,
        "max_players": room.max_players,
        "size": game.size,
        "phase": game.phase,
        "turn": game.turn,
        "rolled": game.rolled,
        "setup_order": list(game.setup_order),
        "setup_idx": game.setup_idx,
        "setup_need": game.setup_need,
        "setup_anchor_vid": game.setup_anchor_vid,
        "last_roll": game.last_roll,
        "robber_tile": game.robber_tile,
        "pending_action": game.pending_action,
        "pending_pid": game.pending_pid,
        "pending_victims": list(game.pending_victims),
        "longest_road_owner": game.longest_road_owner,
        "longest_road_len": game.longest_road_len,
        "largest_army_owner": game.largest_army_owner,
        "largest_army_size": game.largest_army_size,
        "game_over": game.game_over,
        "winner_pid": game.winner_pid,
        "players": [
            {
                "pid": p.pid,
                "name": p.name,
                "vp": p.vp,
                "res": dict(p.res),
                "knights_played": p.knights_played,
            }
            for p in game.players
        ],
        "bank": dict(game.bank),
        "occupied_v": {str(k): [v[0], v[1]] for k, v in game.occupied_v.items()},
        "occupied_e": {f"{a},{b}": owner for (a, b), owner in game.occupied_e.items()},
        "tiles": [
            {
                "q": t.q,
                "r": t.r,
                "terrain": t.terrain,
                "number": t.number,
                "center": [t.center[0], t.center[1]],
            }
            for t in game.tiles
        ],
        "vertices": {str(k): [v[0], v[1]] for k, v in game.vertices.items()},
        "edges": [[a, b] for a, b in sorted(game.edges)],
        "vertex_adj_hexes": {str(k): v for k, v in game.vertex_adj_hexes.items()},
        "edge_adj_hexes": {f"{a},{b}": v for (a, b), v in game.edge_adj_hexes.items()},
        "ports": [[[a, b], kind] for (a, b), kind in game.ports],
    }


def _parse_edge_key(k: str) -> Optional[tuple]:
    try:
        a, b = k.split(",", 1)
        return int(a), int(b)
    except Exception:
        return None


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


def _hand_size(game: GameState, pid: int) -> int:
    return sum(game.players[pid].res.values())


def _victims_for_tile(game: GameState, tile: int, thief_pid: int) -> List[int]:
    victims = set()
    for vid, (owner, _level) in game.occupied_v.items():
        if owner == thief_pid:
            continue
        if tile in game.vertex_adj_hexes.get(vid, []):
            if _hand_size(game, owner) > 0:
                victims.add(owner)
    return sorted(victims)


def _steal_one(game: GameState, thief_pid: int, victim_pid: int) -> Optional[str]:
    res = game.players[victim_pid].res
    choices = [r for r, q in res.items() if q > 0]
    if not choices:
        return None
    r = random.choice(choices)
    game.players[victim_pid].res[r] -= 1
    game.players[thief_pid].res[r] += 1
    return r


def _apply_cmd(room: Room, pid: int, cmd: Dict) -> Optional[Dict]:
    g = room.game
    if not g:
        return net_protocol.error_message("no_match", "Match not started")

    ctype = cmd.get("type")
    if not isinstance(ctype, str):
        return net_protocol.error_message("invalid", "cmd.type required")

    if g.game_over:
        return net_protocol.error_message("game_over", "Game over")

    if g.pending_action is not None and ctype not in ("move_robber", "end_turn"):
        return net_protocol.error_message("pending_action", "Resolve pending action first")

    if ctype == "place_settlement":
        vid = int(cmd.get("vid"))
        setup = bool(cmd.get("setup", False)) or g.phase == "setup"
        if setup:
            if g.setup_need != "settlement":
                return net_protocol.error_message("illegal", "Not settlement step")
            if not can_place_settlement(g, pid, vid, require_road=False):
                return net_protocol.error_message("illegal", "Settlement not allowed")
            g.occupied_v[vid] = (pid, 1)
            g.players[pid].vp += 1
            update_longest_road(g)
            check_win(g)
            g.setup_need = "road"
            g.setup_anchor_vid = vid
            return None

        if g.turn != pid or g.phase != "main":
            return net_protocol.error_message("illegal", "Not your turn")
        if not can_place_settlement(g, pid, vid, require_road=True):
            return net_protocol.error_message("illegal", "Settlement not allowed")
        if not can_pay(g.players[pid], COST["settlement"]):
            return net_protocol.error_message("illegal", "Not enough resources")
        pay_to_bank(g, pid, COST["settlement"])
        g.occupied_v[vid] = (pid, 1)
        g.players[pid].vp += 1
        update_longest_road(g)
        check_win(g)
        return None

    if ctype == "place_road":
        eid = cmd.get("eid")
        if not isinstance(eid, (list, tuple)) or len(eid) != 2:
            return net_protocol.error_message("invalid", "eid required")
        a, b = int(eid[0]), int(eid[1])
        e = (a, b) if a < b else (b, a)
        setup = bool(cmd.get("setup", False)) or g.phase == "setup"
        if setup:
            if g.setup_need != "road":
                return net_protocol.error_message("illegal", "Not road step")
            if not can_place_road(g, pid, e, must_touch_vid=g.setup_anchor_vid):
                return net_protocol.error_message("illegal", "Road not allowed")
            g.occupied_e[e] = pid
            update_longest_road(g)
            check_win(g)
            g.setup_need = "settlement"
            g.setup_anchor_vid = None
            g.setup_idx += 1
            if g.setup_idx >= len(g.setup_order):
                g.phase = "main"
            return None

        if g.turn != pid or g.phase != "main":
            return net_protocol.error_message("illegal", "Not your turn")
        if not can_place_road(g, pid, e):
            return net_protocol.error_message("illegal", "Road not allowed")
        if not can_pay(g.players[pid], COST["road"]):
            return net_protocol.error_message("illegal", "Not enough resources")
        pay_to_bank(g, pid, COST["road"])
        g.occupied_e[e] = pid
        update_longest_road(g)
        check_win(g)
        return None

    if ctype == "upgrade_city":
        vid = int(cmd.get("vid"))
        if g.turn != pid or g.phase != "main":
            return net_protocol.error_message("illegal", "Not your turn")
        if not can_upgrade_city(g, pid, vid):
            return net_protocol.error_message("illegal", "City upgrade not allowed")
        if not can_pay(g.players[pid], COST["city"]):
            return net_protocol.error_message("illegal", "Not enough resources")
        pay_to_bank(g, pid, COST["city"])
        g.occupied_v[vid] = (pid, 2)
        g.players[pid].vp += 1
        update_longest_road(g)
        check_win(g)
        return None

    if ctype == "roll":
        if g.turn != pid or g.phase != "main":
            return net_protocol.error_message("illegal", "Not your turn")
        if g.rolled:
            return net_protocol.error_message("illegal", "Already rolled")
        forced = cmd.get("forced")
        if forced is not None and os.getenv("CATAN_DEBUG_ROLLS") != "1":
            return net_protocol.error_message("illegal", "Forced roll disabled")
        if forced is not None:
            roll = int(forced)
        else:
            roll = random.randint(1, 6) + random.randint(1, 6)
        g.last_roll = roll
        g.rolled = True
        if roll == 7:
            g.pending_action = "robber_move"
            g.pending_pid = pid
            g.pending_victims = []
            return None
        distribute_for_roll(g, roll)
        return None

    if ctype == "move_robber":
        tile = int(cmd.get("tile"))
        victim = cmd.get("victim_pid")
        if g.pending_action not in ("robber_move",):
            return net_protocol.error_message("illegal", "No robber move pending")
        if g.pending_pid is not None and pid != g.pending_pid:
            return net_protocol.error_message("illegal", "Not your robber move")
        if tile == g.robber_tile:
            return net_protocol.error_message("illegal", "Same robber tile")
        g.robber_tile = tile
        victims = _victims_for_tile(g, tile, pid)
        if victims:
            if isinstance(victim, int) and victim in victims:
                victim_pid = victim
            else:
                victim_pid = random.choice(victims)
            _steal_one(g, pid, victim_pid)
        g.pending_action = None
        g.pending_pid = None
        g.pending_victims = []
        return None

    if ctype == "end_turn":
        if g.turn != pid:
            return net_protocol.error_message("illegal", "Not your turn")
        if g.pending_action is not None:
            return net_protocol.error_message("illegal", "Resolve pending action first")
        g.turn = (g.turn + 1) % len(g.players)
        g.rolled = False
        g.last_roll = None
        return None

    return net_protocol.error_message("invalid", f"Unknown cmd: {ctype}")


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
