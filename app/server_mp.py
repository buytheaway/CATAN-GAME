from __future__ import annotations

import asyncio
import json
import os
import random
import secrets
import string
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app import net_protocol
from app.engine import (
    DEFAULT_PRESET_ID,
    GameState,
    RuleError,
    can_place_road,
    can_place_settlement,
    can_place_ship,
    can_upgrade_city,
    apply_cmd,
    build_game,
    get_preset_meta,
    get_preset_map,
    list_presets,
    parse_rules_config,
)
from app.engine import maps as map_loader
from app.engine.serialize import to_player_dict


@dataclass
class PlayerSlot:
    pid: int
    name: str = ""
    connected: bool = False
    reconnect_token: Optional[str] = None
    last_seq_applied: int = 0
    seen_cmd_ids: Deque[str] = field(default_factory=deque)
    seen_cmd_set: Set[str] = field(default_factory=set)
    active_ws: Optional[WebSocket] = field(default=None, repr=False, compare=False)


@dataclass
class ClientConn:
    ws: WebSocket
    name: str = ""
    room_code: Optional[str] = None
    pid: Optional[int] = None


@dataclass
class Room:
    room_code: str
    max_players: int
    host_pid: int
    players: List[PlayerSlot]
    selected_map_id: str = DEFAULT_PRESET_ID
    selected_map_meta: Dict[str, Any] = field(default_factory=dict)
    map_presets: List[Dict[str, Any]] = field(default_factory=list)
    selected_rules_config: Dict[str, Any] = field(default_factory=dict)
    selected_map_data: Optional[Dict[str, Any]] = None
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
        room.map_presets = list_presets()
        room.selected_map_id = DEFAULT_PRESET_ID
        room.selected_map_meta = get_preset_meta(room.selected_map_id) or {"id": room.selected_map_id, "name": room.selected_map_id, "description": ""}
        rules_raw = get_preset_map(room.selected_map_id).get("rules", {})
        room.selected_rules_config = vars(parse_rules_config(rules_raw))
        room.selected_map_data = None
        self.rooms[code] = room
        self._assign_player(room, 0, name, connected=True)
        return room

    def _assign_player(self, room: Room, pid: int, name: str, connected: bool) -> None:
        slot = room.players[pid]
        slot.name = name
        slot.connected = connected
        if not slot.reconnect_token:
            slot.reconnect_token = uuid.uuid4().hex

    def join_room(self, room_code: str, name: str) -> Optional[Room]:
        if not isinstance(room_code, str):
            return None
        code = room_code.strip().upper()
        room = self.rooms.get(code)
        if not room or room.status != "lobby":
            return None
        name = name.strip()
        if not name or any(slot.name == name for slot in room.players):
            return None
        for slot in room.players:
            if not slot.name:
                slot.name = name
                slot.connected = True
                if not slot.reconnect_token:
                    slot.reconnect_token = uuid.uuid4().hex
                return room
        return None

    def bind_player(self, conn: ClientConn, room: Room, pid: int) -> None:
        """The reconnect token may transfer ownership, a display name may not."""
        self.leave_room(conn)
        slot = room.players[pid]
        previous = self.connections.get(slot.active_ws)
        if previous is not None and previous is not conn:
            previous.room_code = None
            previous.pid = None
        conn.room_code = room.room_code
        conn.pid = pid
        slot.active_ws = conn.ws
        slot.connected = True

    def leave_room(self, conn: ClientConn) -> None:
        if not conn.room_code:
            return
        room = self.rooms.get(conn.room_code)
        if not room or conn.pid is None:
            return
        slot = room.players[conn.pid]
        if slot.active_ws is not conn.ws:
            return
        slot.active_ws = None
        slot.connected = False
        room.last_activity_ts = time.time()


app = FastAPI()
manager = RoomManager()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


CMD_ID_LRU = 256
MULTIPLAYER_COMMANDS = frozenset({
    "place_settlement", "place_road", "upgrade_city", "build_ship", "move_ship",
    "roll", "discard", "choose_gold", "move_robber", "move_pirate",
    "trade_bank", "trade_offer_create", "trade_offer_accept", "trade_offer_decline",
    "trade_offer_cancel", "buy_dev", "play_dev", "end_turn", "noop",
})


def _snapshot_state(game: GameState, room: Room, pid: int) -> Dict:
    state = to_player_dict(game, pid)
    state["you_pid"] = pid
    state["legal"] = _legal_moves(game)
    return state


def _legal_moves(g: GameState) -> Dict[str, Any]:
    if g.game_over:
        return {}
    if g.pending_action is not None:
        return {"pid": g.turn, "settlements": [], "roads": [], "cities": [], "ships": []}
    pid = g.turn
    settlements: List[int] = []
    roads: List[List[int]] = []
    cities: List[int] = []
    ships: List[List[int]] = []
    if g.phase == "setup":
        if g.setup_order and pid != g.setup_order[g.setup_idx]:
            return {"pid": pid, "settlements": [], "roads": [], "cities": [], "ships": []}
        if g.setup_need == "settlement":
            for vid in g.vertices.keys():
                if can_place_settlement(g, pid, int(vid), require_road=False):
                    settlements.append(int(vid))
        else:
            anchor = g.setup_anchor_vid
            if anchor is not None:
                for a, b in g.edges:
                    if anchor in (a, b) and can_place_road(g, pid, (a, b), must_touch_vid=anchor):
                        roads.append([a, b])
        return {"pid": pid, "settlements": settlements, "roads": roads, "cities": [], "ships": []}
    if g.phase == "main":
        if not g.rolled:
            return {"pid": pid, "settlements": [], "roads": [], "cities": [], "ships": []}
        for vid in g.vertices.keys():
            if can_place_settlement(g, pid, int(vid), require_road=True):
                settlements.append(int(vid))
            if can_upgrade_city(g, pid, int(vid)):
                cities.append(int(vid))
        for a, b in g.edges:
            if can_place_road(g, pid, (a, b)):
                roads.append([a, b])
            if can_place_ship(g, pid, (a, b)):
                ships.append([a, b])
    return {"pid": pid, "settlements": settlements, "roads": roads, "cities": cities, "ships": ships}


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
    # Freeze all views before the first await so another command cannot make
    # recipients observe different ticks/states from this one update.
    messages = [
        (ws, conn.pid, net_protocol.match_state_message(room, _snapshot_state(room.game, room, conn.pid)))
        for ws, conn in list(manager.connections.items())
        if conn.room_code == room.room_code and conn.pid is not None
    ]
    for ws, pid, message in messages:
        conn = manager.connections.get(ws)
        if (not conn or conn.room_code != room.room_code or conn.pid != pid
                or room.match_id != message["match_id"] or room.players[pid].active_ws is not ws):
            continue
        try:
            await _send(ws, message)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass


async def _send_match_state_to(ws: WebSocket, room: Room) -> None:
    if not room.game:
        return
    conn = manager.connections.get(ws)
    if not conn or conn.room_code != room.room_code or conn.pid is None:
        return
    state = _snapshot_state(room.game, room, conn.pid)
    await _send(ws, net_protocol.match_state_message(room, state))


async def _send_reconnect_token(ws: WebSocket, room: Room, pid: int) -> None:
    slot = room.players[pid]
    await _send(ws, {
        "type": "reconnect_token",
        "room_code": room.room_code,
        "pid": pid,
        "reconnect_token": slot.reconnect_token,
        "last_seq_applied": slot.last_seq_applied,
        "match_id": room.match_id,
    })


async def _send_cmd_ack(ws: WebSocket, cmd_id: str, seq: int, last_seq_applied: int, applied: bool, duplicate: bool = False) -> None:
    await _send(ws, {
        "type": "cmd_ack",
        "cmd_id": cmd_id,
        "seq": int(seq),
        "last_seq_applied": int(last_seq_applied),
        "applied": bool(applied),
        "duplicate": bool(duplicate),
    })


def _get_conn(ws: WebSocket) -> ClientConn:
    return manager.connections[ws]


def _rematch_host_pid(room: Room) -> Optional[int]:
    if room.status != "in_match" or room.players[room.host_pid].connected:
        return room.host_pid
    return next((p.pid for p in room.players if p.name and p.connected), None)


def _start_match(room: Room) -> None:
    participants = [p for p in room.players if p.name and p.connected]
    host_pid = _rematch_host_pid(room)
    if len(participants) < 2 or host_pid not in [p.pid for p in participants]:
        raise RuleError("invalid", "Need the host and at least 2 connected players")
    seed = secrets.randbits(64)
    if room.selected_map_data is not None:
        game = build_game(
            seed=seed,
            max_players=len(participants),
            player_names=[p.name for p in participants],
            size=58.0,
            map_id=room.selected_map_id,
            map_data=room.selected_map_data,
        )
    else:
        game = build_game(seed=seed, max_players=len(participants), size=58.0,
                          player_names=[p.name for p in participants], map_id=room.selected_map_id)
    # Do not tie the secret development deck to the map's reproducible seed.
    random.SystemRandom().shuffle(game.dev_deck)
    mapping = {slot.pid: pid for pid, slot in enumerate(participants)}
    room.host_pid = mapping[host_pid]
    for conn in manager.connections.values():
        if conn.room_code == room.room_code:
            conn.pid = mapping.get(conn.pid)
            if conn.pid is None:
                conn.room_code = None
    room.players = participants
    room.game = game
    room.seed = seed
    room.match_id += 1
    room.tick = 0
    for pid, slot in enumerate(room.players):
        slot.pid = pid
        slot.last_seq_applied = 0
        slot.seen_cmd_ids.clear()
        slot.seen_cmd_set.clear()
    room.status = "in_match"


def _apply_cmd(room: Room, pid: int, cmd: Dict) -> Optional[Dict]:
    g = room.game
    if not g:
        return net_protocol.error_message("no_match", "Match not started")

    ctype = cmd.get("type")
    if not isinstance(ctype, str):
        return net_protocol.error_message("invalid", "cmd.type required")
    if ctype not in MULTIPLAYER_COMMANDS:
        return net_protocol.error_message("forbidden", "Command is not available in multiplayer")
    if ctype == "discard" and not isinstance(cmd.get("discards"), dict):
        return net_protocol.error_message("invalid", "discards must be object")

    if ctype == "roll":
        if set(cmd) != {"type"}:
            return net_protocol.error_message("invalid", "Send only the roll intention")
        cmd = {"type": "roll", "roll": _roll_dice()}

    try:
        apply_cmd(g, pid, cmd)
    except RuleError as exc:
        return net_protocol.error_message(exc.code, exc.message, exc.details)
    return None


def _roll_dice() -> int:
    """Tests may inject this function; no WebSocket debug fields enable it."""
    return secrets.randbelow(6) + secrets.randbelow(6) + 2


async def _start_and_notify(room: Room) -> None:
    _start_match(room)
    await _send_room_state(room)
    for ws, conn in list(manager.connections.items()):
        if conn.room_code == room.room_code and conn.pid is not None:
            await _send_reconnect_token(ws, room, conn.pid)
    await _send_match_state(room)


def _remember_cmd_id(slot: PlayerSlot, cmd_id: str) -> None:
    if cmd_id in slot.seen_cmd_set:
        return
    if len(slot.seen_cmd_ids) >= CMD_ID_LRU:
        old = slot.seen_cmd_ids.popleft()
        slot.seen_cmd_set.discard(old)
    slot.seen_cmd_ids.append(cmd_id)
    slot.seen_cmd_set.add(cmd_id)


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
                room = manager.create_room(data.get("name").strip(), data.get("max_players", 4))
                manager.bind_player(conn, room, 0)
                await _send(ws, net_protocol.room_state_message(room))
                await _send_reconnect_token(ws, room, 0)
                continue

            if mtype == "join_room":
                room_code = data.get("room_code")
                if isinstance(room_code, str):
                    room_code = room_code.strip().upper()
                name = data.get("name").strip()
                room = manager.join_room(room_code, name)
                if not room:
                    await _send(ws, net_protocol.error_message("not_found", "Room not found or full"))
                    continue
                # bind pid
                pid = None
                for slot in room.players:
                    if slot.name == name:
                        pid = slot.pid
                        break
                manager.bind_player(conn, room, pid)
                await _send(ws, net_protocol.room_state_message(room))
                if pid is not None:
                    await _send_reconnect_token(ws, room, pid)
                await _send_room_state(room)
                continue

            if mtype == "reconnect":
                room_code = data.get("room_code")
                if isinstance(room_code, str):
                    room_code = room_code.strip().upper()
                token = data.get("reconnect_token")
                room = manager.rooms.get(room_code)
                if not room:
                    await _send(ws, net_protocol.error_message("not_found", "Room not found"))
                    continue
                pid = None
                for slot in room.players:
                    if slot.reconnect_token and secrets.compare_digest(slot.reconnect_token.encode(), token.encode()):
                        pid = slot.pid
                        break
                if pid is None:
                    await _send(ws, net_protocol.error_message("forbidden", "Invalid reconnect token"))
                    continue
                manager.bind_player(conn, room, pid)
                await _send(ws, net_protocol.room_state_message(room))
                await _send_reconnect_token(ws, room, pid)
                if room.status == "in_match":
                    await _send_match_state_to(ws, room)
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
                if room.status != "lobby":
                    await _send(ws, net_protocol.error_message("invalid", "Match already started; use rematch"))
                    continue
                try:
                    await _start_and_notify(room)
                except RuleError as exc:
                    await _send(ws, net_protocol.error_message(exc.code, exc.message))
                continue

            if mtype == "set_map":
                room = manager.rooms.get(conn.room_code or "")
                if not room:
                    await _send(ws, net_protocol.error_message("not_found", "Room not found"))
                    continue
                if conn.pid != room.host_pid:
                    await _send(ws, net_protocol.error_message("forbidden", "Only host can set map"))
                    continue
                if room.status != "lobby":
                    await _send(ws, net_protocol.error_message("invalid", "Cannot change map after start"))
                    continue
                map_data = data.get("map_data")
                map_id = data.get("map_id") or data.get("id")
                if isinstance(map_data, dict):
                    try:
                        map_loader.validate_map_data(map_data)
                    except Exception as exc:
                        await _send(ws, net_protocol.error_message("invalid", f"Invalid map_data: {exc}"))
                        continue
                    room.selected_map_data = map_data
                    map_name = str(map_data.get("name", "custom"))
                    if not isinstance(map_id, str) or not map_id:
                        map_id = map_name
                    room.selected_map_id = str(map_id)
                    room.selected_map_meta = {
                        "id": str(map_id),
                        "name": map_name,
                        "description": str(map_data.get("description", "")),
                    }
                    rules_raw = map_data.get("rules", {})
                    room.selected_rules_config = vars(parse_rules_config(rules_raw if isinstance(rules_raw, dict) else {}))
                else:
                    if not isinstance(map_id, str):
                        await _send(ws, net_protocol.error_message("invalid", "map_id required"))
                        continue
                    meta = get_preset_meta(map_id)
                    if not meta:
                        await _send(ws, net_protocol.error_message("invalid", "Unknown map_id"))
                        continue
                    rules_raw = get_preset_map(map_id).get("rules", {})
                    room.selected_rules_config = vars(parse_rules_config(rules_raw))
                    room.selected_map_id = map_id
                    room.selected_map_meta = dict(meta)
                    room.selected_map_data = None
                await _send_room_state(room)
                continue

            if mtype == "rematch":
                room = manager.rooms.get(conn.room_code or "")
                if not room:
                    await _send(ws, net_protocol.error_message("not_found", "Room not found"))
                    continue
                if conn.pid != _rematch_host_pid(room):
                    await _send(ws, net_protocol.error_message("forbidden", "Only host can rematch"))
                    continue
                try:
                    await _start_and_notify(room)
                except RuleError as exc:
                    await _send(ws, net_protocol.error_message(exc.code, exc.message))
                continue

            if mtype == "cmd":
                room = manager.rooms.get(conn.room_code or "")
                if not room:
                    await _send(ws, net_protocol.error_message("not_found", "Room not found"))
                    continue
                if data.get("room_code") is not None and data.get("room_code") != room.room_code:
                    await _send(ws, net_protocol.error_message("invalid", "room_code mismatch"))
                    continue
                if data.get("match_id") != room.match_id:
                    await _send(ws, net_protocol.error_message("invalid", "match_id mismatch"))
                    continue
                if conn.pid is None:
                    await _send(ws, net_protocol.error_message("invalid", "No player slot assigned"))
                    continue
                cmd_id = data.get("cmd_id")
                seq = int(data.get("seq"))
                slot = room.players[conn.pid]
                expected_seq = slot.last_seq_applied + 1

                if cmd_id in slot.seen_cmd_set or seq <= slot.last_seq_applied:
                    await _send_cmd_ack(ws, cmd_id, seq, slot.last_seq_applied, applied=False, duplicate=True)
                    continue
                if seq > expected_seq:
                    await _send(ws, net_protocol.error_message("out_of_order", "Out of order seq", {"expected_seq": expected_seq}))
                    continue

                err = _apply_cmd(room, conn.pid, data.get("cmd", {}))
                # This is the last CONSUMED sequence, including rejected game commands.
                # Both outcomes are final; replay must not retry an old rejected intent.
                slot.last_seq_applied = seq
                _remember_cmd_id(slot, cmd_id)
                if err:
                    await _send(ws, err)
                    await _send_cmd_ack(ws, cmd_id, seq, slot.last_seq_applied, applied=False)
                else:
                    room.tick += 1
                    room.last_activity_ts = time.time()
                    await _send_match_state(room)
                    await _send_cmd_ack(ws, cmd_id, seq, slot.last_seq_applied, applied=True)
                continue

    except WebSocketDisconnect:
        manager.leave_room(conn)
        if conn.room_code:
            room = manager.rooms.get(conn.room_code)
            if room:
                await _send_room_state(room)
        manager.connections.pop(ws, None)
    except Exception:
        manager.leave_room(conn)
        manager.connections.pop(ws, None)


def main():
    import uvicorn

    host = os.getenv("CATAN_HOST", "0.0.0.0")
    port_raw = os.getenv("CATAN_PORT", "8000")
    try:
        port = int(port_raw)
    except ValueError:
        port = 8000
    uvicorn.run("app.server_mp:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
