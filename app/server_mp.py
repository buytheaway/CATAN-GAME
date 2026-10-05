from __future__ import annotations

import asyncio
import json
import os
import random
import secrets
import string
import time
import uuid
from contextlib import asynccontextmanager, suppress
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from app import net_protocol
from app.engine import (
    DEFAULT_PRESET_ID,
    GameState,
    RuleError,
    apply_cmd,
    build_game,
    get_preset_meta,
    get_preset_map,
    list_presets,
    parse_rules_config,
)
from app.engine import maps as map_loader
from app.engine.legal import board_legal_moves
from app.engine.serialize import to_player_dict
from app.room_options import (BALANCED_ALGORITHM, CHAT_LIMIT, CHAT_MAX_LENGTH,
                             CHAT_RATE_COUNT, CHAT_RATE_SECONDS, COLORS,
                             RoomSettings, TurnTimer, shuffled_bag)


@dataclass
class PlayerSlot:
    pid: int
    name: str = ""
    color: Optional[str] = None
    connected: bool = False
    reconnect_token: Optional[str] = None
    last_seq_applied: int = 0
    seen_cmd_ids: Deque[str] = field(default_factory=deque)
    seen_cmd_set: Set[str] = field(default_factory=set)
    active_ws: Optional[WebSocket] = field(default=None, repr=False, compare=False)
    chat_times: Deque[float] = field(default_factory=deque, repr=False)


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
    map_revision: int = 0
    config_revision: int = 0
    settings: RoomSettings = field(default_factory=RoomSettings)
    dice_algorithm: str = BALANCED_ALGORITHM
    dice_bag: List[tuple[int, int]] = field(default_factory=list, repr=False)
    timer: Optional[TurnTimer] = None
    chat_history: List[Dict[str, Any]] = field(default_factory=list)
    chat_revision: int = 0
    status: str = "lobby"
    match_id: int = 0
    tick: int = 0
    seed: int = 0
    dice: Optional[tuple[int, int]] = None
    roll_count: int = 0
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
        if slot.color is None:
            used = {p.color for p in room.players if p.name and p is not slot}
            slot.color = next(color for color in COLORS if color not in used)
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
                self._assign_player(room, slot.pid, name, connected=True)
                room.config_revision += 1
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

    def destroy_room(self, code: str) -> None:
        room = self.rooms.pop(code, None)
        if room is None:
            return
        room.timer = None
        for conn in self.connections.values():
            if conn.room_code == code:
                conn.room_code = None
                conn.pid = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # One bounded scheduler for the process; no dormant task per room.
    task = asyncio.create_task(_timer_loop(), name="room-turn-timers")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        for room in manager.rooms.values():
            room.timer = None


app = FastAPI(lifespan=lifespan)
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
    state["legal"] = _legal_moves(game, pid)
    state["dice"] = list(room.dice) if room.dice is not None else None
    state["roll_count"] = room.roll_count
    state["room_settings"] = room.settings.public(game.rules_config.target_vp)
    state["turn_timer"] = room.timer.public(time.monotonic(), time.time()) if room.timer else None
    for player in state["players"]:
        player["color"] = room.players[player["pid"]].color
    if room.settings.bank_visibility == "visible":
        state["bank"] = dict(game.bank)
    return state


def _legal_moves(g: GameState, pid: int) -> Dict[str, Any]:
    return board_legal_moves(g, pid)


async def _send(ws: WebSocket, obj: Dict) -> None:
    await ws.send_text(json.dumps(obj))


async def _broadcast(room: Room, obj: Dict) -> None:
    for ws, conn in list(manager.connections.items()):
        if conn.room_code == room.room_code:
            try:
                await _send(ws, obj)
            except Exception:
                pass


async def _send_room_state(room: Room, request_id: Optional[str] = None) -> None:
    message = net_protocol.room_state_message(room)
    if request_id is not None:
        message["request_id"] = request_id
    await _broadcast(room, message)


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
    mapping = {slot.pid: pid for pid, slot in enumerate(participants)}
    starter = mapping[host_pid] if room.settings.starting_player == "host" else secrets.randbelow(len(participants))
    if room.selected_map_data is not None:
        game = build_game(
            seed=seed,
            max_players=len(participants),
            player_names=[p.name for p in participants],
            size=58.0,
            map_id=room.selected_map_id,
            map_data=room.selected_map_data,
            starting_pid=starter,
        )
    else:
        game = build_game(seed=seed, max_players=len(participants), size=58.0,
                          player_names=[p.name for p in participants], map_id=room.selected_map_id,
                          starting_pid=starter)
    if room.settings.target_vp is not None:
        game.rules_config.target_vp = room.settings.target_vp
        game.rules["target_vp"] = room.settings.target_vp
    # Do not tie the secret development deck to the map's reproducible seed.
    random.SystemRandom().shuffle(game.dev_deck)
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
    room.dice = None
    room.roll_count = 0
    room.dice_bag = []
    room.timer = None
    room.config_revision += 1
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

    dice = None
    next_bag = None
    if ctype == "roll":
        if set(cmd) != {"type"}:
            return net_protocol.error_message("invalid", "Send only the roll intention")
        if room.settings.dice_mode == "balanced":
            next_bag = room.dice_bag if len(room.dice_bag) > 12 else shuffled_bag()
            dice = next_bag[-1]
        else:
            dice = _roll_dice()
        cmd = {"type": "roll", "roll": sum(dice)}

    try:
        apply_cmd(g, pid, cmd)
    except RuleError as exc:
        return net_protocol.error_message(exc.code, exc.message, exc.details)
    if dice is not None:
        # Public presentation metadata is committed only with an accepted roll.
        room.dice = dice
        room.roll_count += 1
        if next_bag is not None:
            room.dice_bag = next_bag[:-1]
    return None


def _roll_dice() -> tuple[int, int]:
    """Tests may inject this function; no WebSocket debug fields enable it."""
    return secrets.randbelow(6) + 1, secrets.randbelow(6) + 1


async def _start_and_notify(room: Room) -> None:
    _start_match(room)
    _sync_timer(room)
    await _send_room_state(room)
    for ws, conn in list(manager.connections.items()):
        if conn.room_code == room.room_code and conn.pid is not None:
            await _send_reconnect_token(ws, room, conn.pid)
    await _send_match_state(room)


def _sync_timer(room: Room) -> None:
    g = room.game
    if not g or g.game_over or g.phase != "main" or not room.settings.turn_timer:
        room.timer = None
    elif room.timer is None or room.timer.pid != g.turn:
        room.timer = TurnTimer.start(g.turn, room.settings.turn_timer, time.monotonic(), time.time())


async def _process_room_timer(room: Room) -> None:
    if manager.rooms.get(room.room_code) is not room:
        return
    _sync_timer(room)
    timer, g = room.timer, room.game
    if not timer or not g or time.monotonic() < timer.deadline:
        return
    if timer.stage == "stopped":
        return
    mandatory = g.pending_action is not None or int(g.free_roads.get(g.turn, 0)) > 0
    if mandatory:
        if timer.stage == "blocked":
            return
        timer.stage = "blocked"
    else:
        error = _apply_cmd(room, g.turn, {"type": "end_turn" if g.rolled else "roll"})
        if error:
            # Stop retrying an unsafe/unknown state until a real command resolves it.
            timer.stage = "stopped"
            return
        if room.game.turn == timer.pid:
            room.timer = TurnTimer.start(g.turn, 20, time.monotonic(), time.time(), "grace")
        _sync_timer(room)
    room.tick += 1
    room.last_activity_ts = time.time()
    await _send_match_state(room)


async def _timer_loop() -> None:
    import logging
    while True:
        await asyncio.sleep(.25)
        for room in list(manager.rooms.values()):
            try:
                await asyncio.wait_for(_process_room_timer(room), timeout=2)
            except Exception:
                logging.getLogger(__name__).exception("Turn timer update failed for %s", room.room_code)


def _set_room_settings(room: Room, pid: int, patch: Dict[str, Any]) -> None:
    if pid != room.host_pid:
        raise RuleError("forbidden", "Only host can set room settings")
    if room.status != "lobby":
        raise RuleError("invalid", "Room settings are locked after start")
    try:
        updated = room.settings.updated(patch)
    except ValueError as exc:
        raise RuleError("invalid", str(exc)) from exc
    room.settings = updated
    if updated.target_vp is not None:
        room.selected_rules_config = {**room.selected_rules_config, "target_vp": updated.target_vp}
    room.config_revision += 1


def _set_player_color(room: Room, pid: int, color: str) -> None:
    if room.status != "lobby":
        raise RuleError("invalid", "Colors are locked after start")
    if color not in COLORS:
        raise RuleError("invalid", "Unknown player color")
    if any(p.name and p.pid != pid and p.color == color for p in room.players):
        raise RuleError("invalid", "Color already occupied")
    room.players[pid].color = color
    room.config_revision += 1


def _append_chat(room: Room, pid: int, text: str) -> None:
    if len(text) > CHAT_MAX_LENGTH or not text.strip():
        raise RuleError("invalid", f"Chat must contain 1..{CHAT_MAX_LENGTH} characters")
    slot, now = room.players[pid], time.monotonic()
    recent = [t for t in slot.chat_times if now - t < CHAT_RATE_SECONDS]
    if len(recent) >= CHAT_RATE_COUNT:
        raise RuleError("rate_limited", "Wait before sending more chat messages")
    slot.chat_times = deque([*recent, now])
    room.chat_revision += 1
    room.chat_history.append({"id": room.chat_revision, "name": slot.name, "color": slot.color,
                              "text": text.strip(), "sent_at_ms": round(time.time() * 1000)})
    room.chat_history = room.chat_history[-CHAT_LIMIT:]


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
                detail = err.get("detail", {})
                if isinstance(data, dict) and data.get("type") in ("set_map", "set_settings", "set_color", "chat"):
                    detail = {**detail, "request_type": data["type"], "request_id": data.get("request_id")}
                await _send(ws, net_protocol.error_message(err.get("code", "invalid"), err.get("message", "invalid"), detail))
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
                    await _send(ws, net_protocol.error_message("not_found", "Room not found", {"request_type": "set_map"}))
                    continue
                if conn.pid != room.host_pid:
                    await _send(ws, net_protocol.error_message("forbidden", "Only host can set map", {"request_type": "set_map"}))
                    continue
                if room.status != "lobby":
                    await _send(ws, net_protocol.error_message("invalid", "Cannot change map after start", {"request_type": "set_map"}))
                    continue
                map_data = data.get("map_data")
                map_id = data.get("map_id") or data.get("id")
                if isinstance(map_data, dict):
                    try:
                        map_loader.validate_map_data(map_data)
                    except Exception as exc:
                        await _send(ws, net_protocol.error_message("invalid", f"Invalid map_data: {exc}", {"request_type": "set_map"}))
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
                        await _send(ws, net_protocol.error_message("invalid", "map_id required", {"request_type": "set_map"}))
                        continue
                    meta = get_preset_meta(map_id)
                    if not meta:
                        await _send(ws, net_protocol.error_message("invalid", "Unknown map_id", {"request_type": "set_map"}))
                        continue
                    rules_raw = get_preset_map(map_id).get("rules", {})
                    room.selected_rules_config = vars(parse_rules_config(rules_raw))
                    room.selected_map_id = map_id
                    room.selected_map_meta = dict(meta)
                    room.selected_map_data = None
                room.map_revision += 1
                if room.settings.target_vp is not None:
                    room.selected_rules_config["target_vp"] = room.settings.target_vp
                room.config_revision += 1
                await _send_room_state(room)
                continue

            if mtype in ("set_settings", "set_color", "chat"):
                room = manager.rooms.get(conn.room_code or "")
                detail = {"request_type": mtype, "request_id": data.get("request_id")}
                if not room or conn.pid is None or room.players[conn.pid].active_ws is not ws:
                    await _send(ws, net_protocol.error_message("forbidden", "Room membership required", detail))
                    continue
                try:
                    if mtype == "set_settings":
                        _set_room_settings(room, conn.pid, data["settings"])
                    elif mtype == "set_color":
                        _set_player_color(room, conn.pid, data["color"])
                    else:
                        _append_chat(room, conn.pid, data["text"])
                except RuleError as exc:
                    await _send(ws, net_protocol.error_message(exc.code, exc.message, detail))
                    continue
                if mtype == "chat":
                    await _broadcast(room, {"type": "chat_state", "room_code": room.room_code,
                                           "chat_revision": room.chat_revision, "chat_history": list(room.chat_history)})
                else:
                    await _send_room_state(room, data.get("request_id"))
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
                await _process_room_timer(room)
                if conn.room_code != room.room_code or conn.pid is None or room.players[conn.pid].active_ws is not ws:
                    await _send(ws, net_protocol.error_message("forbidden", "Room membership required"))
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
                    _sync_timer(room)
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
