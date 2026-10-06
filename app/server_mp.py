from __future__ import annotations

import asyncio
import json
import os
import random
import secrets
import string
import time
import uuid
import logging
from contextlib import asynccontextmanager, suppress
from collections import deque
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional, Set

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from app.persistence.coordinator import Coordinator
from app.persistence.db import configured_database
from app.persistence.credentials import utcnow, issue_token, token_hash, valid_token, renewed_expiry
from app.persistence.errors import PersistenceUnavailable, RecoveryError
from app.persistence.recovery import clone_room, resume_timer, checksum
from app.persistence.inspection import MAX_CREDENTIALS, MAX_BODY_BYTES, InspectionLimiter, inspect_memory

from app import net_protocol
from app import game_events, test_tools
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
    reconnect_token: Optional[str] = field(default=None, repr=False)
    last_seq_applied: int = 0
    seen_cmd_ids: Deque[str] = field(default_factory=deque)
    seen_cmd_set: Set[str] = field(default_factory=set)
    active_ws: Optional[WebSocket] = field(default=None, repr=False, compare=False)
    chat_times: Deque[float] = field(default_factory=deque, repr=False)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    match_player_id: Optional[uuid.UUID] = None
    token_hash: Optional[bytes] = field(default=None, repr=False)
    token_expires_at: Optional[datetime] = None
    token_revoked_at: Optional[datetime] = None


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
    test_mode: bool = False
    next_test_dice: Optional[tuple[int, int]] = field(default=None, repr=False)
    game_events: List[Dict[str, Any]] = field(default_factory=list, repr=False)
    event_serial: int = 0
    game: Optional[GameState] = None
    last_activity_ts: float = field(default_factory=lambda: time.time())
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    match_uuid: Optional[uuid.UUID] = None
    durable_revision: int = 0
    created_at: datetime = field(default_factory=utcnow)
    closed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False, compare=False)
    persistence_blocked: bool = False
    timer_paused: bool = False


class RoomManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.connections: Dict[WebSocket, ClientConn] = {}
        self.create_lock = asyncio.Lock()

    def _gen_code(self) -> str:
        while True:
            code = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
            if code not in self.rooms and code not in persistence.reserved_codes:
                return code

    def create_room(self, name: str, max_players: int, *, register: bool = True) -> Room:
        code = self._gen_code()
        players = [PlayerSlot(pid=i) for i in range(max_players)]
        room = Room(room_code=code, max_players=max_players, host_pid=0, players=players)
        room.map_presets = list_presets()
        room.selected_map_id = DEFAULT_PRESET_ID
        room.selected_map_meta = get_preset_meta(room.selected_map_id) or {"id": room.selected_map_id, "name": room.selected_map_id, "description": ""}
        rules_raw = get_preset_map(room.selected_map_id).get("rules", {})
        room.selected_rules_config = vars(parse_rules_config(rules_raw))
        room.selected_map_data = None
        if register:
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
            slot.reconnect_token = issue_token()
            slot.token_hash = token_hash(slot.reconnect_token)
            slot.token_expires_at = renewed_expiry()

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
    global persistence
    persistence = Coordinator(configured_database())
    try:
        await persistence.initialize(manager)
    except Exception:
        persistence.ready = False
        logging.getLogger(__name__).error("Database/schema/recovery unavailable; readiness disabled")
    # One bounded scheduler for the process; no dormant task per room.
    task = asyncio.create_task(_timer_loop(), name="room-turn-timers")
    recovery_task = asyncio.create_task(_persistence_monitor(), name="persistence-readiness")
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        recovery_task.cancel()
        with suppress(asyncio.CancelledError):
            await recovery_task
        for room in manager.rooms.values():
            room.timer = None
        await persistence.close()


app = FastAPI(lifespan=lifespan)
manager = RoomManager()
persistence = Coordinator()
inspection_limiter = InspectionLimiter()


@app.get("/health")
def health():
    return JSONResponse({"status": "ok" if persistence.ready else "unavailable",
                         "ready": persistence.ready,
                         "persistence": "postgresql" if persistence.database else "memory"},
                        status_code=200 if persistence.ready else 503)


@app.post("/api/reconnect/inspect-many")
async def inspect_recent_games(request: Request):
    # Parse manually: FastAPI's default validation response can echo a secret input.
    headers = {"Cache-Control": "no-store"}
    def failure(code):
        return JSONResponse({"status": "temporarily_unavailable" if code in (429, 503) else "invalid_request"},
                            status_code=code, headers=headers)
    peer = request.client.host if request.client else "unknown"
    if not inspection_limiter.allow(peer):
        return failure(429)
    if not persistence.ready:
        return failure(503)
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            return failure(413)
        body.extend(chunk)
    try:
        data = json.loads(body)
        entries = data["credentials"]
        if set(data) != {"credentials"} or not isinstance(entries, list) or not 1 <= len(entries) <= MAX_CREDENTIALS:
            return failure(400)
        credentials = []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"room_code", "reconnect_token"}:
                return failure(400)
            code, token = entry["room_code"], entry["reconnect_token"]
            if (not isinstance(code, str) or not 1 <= len(code) <= 32
                    or not isinstance(token, str) or not 1 <= len(token) <= 512):
                return failure(400)
            code.encode("utf-8"), token.encode("utf-8")
            credentials.append((code.strip().upper(), token))
    except (ValueError, KeyError, TypeError, UnicodeError):
        return failure(400)
    try:
        results = (await persistence.repository.inspect_credentials(manager, credentials) if persistence.repository
                   else await inspect_memory(manager, credentials))
    except Exception:
        # No row, query parameters, request body or underlying exception in logs/responses.
        logging.getLogger(__name__).warning("Recent-game inspection temporarily unavailable")
        return failure(503)
    return JSONResponse({"results": results}, headers=headers)


CMD_ID_LRU = 256
TEST_TOOLS_ENABLED = os.getenv("CATAN_ENABLE_TEST_TOOLS", "0") == "1"
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
    if state["turn_timer"] and room.timer_paused:
        state["turn_timer"].update(stage="stopped", remaining_ms=0, paused=True)
    state["game_events"] = game_events.project(room, pid)
    state["test_mode"] = room.test_mode
    state["test_tools"] = TEST_TOOLS_ENABLED and room.test_mode and pid == room.host_pid
    for player in state["players"]:
        player["color"] = room.players[player["pid"]].color
    if room.settings.bank_visibility == "visible":
        state["bank"] = dict(game.bank)
    return state


def _legal_moves(g: GameState, pid: int) -> Dict[str, Any]:
    return board_legal_moves(g, pid)


async def _send(ws: WebSocket, obj: Dict) -> None:
    await asyncio.wait_for(ws.send_text(json.dumps(obj)), timeout=2)


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


def _start_match(room: Room, *, rebind: bool = True) -> None:
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
    game.rules_config.discard_threshold = room.settings.discard_threshold
    game.rules["discard_threshold"] = room.settings.discard_threshold
    # Do not tie the secret development deck to the map's reproducible seed.
    random.SystemRandom().shuffle(game.dev_deck)
    room.host_pid = mapping[host_pid]
    if rebind:
        for conn in manager.connections.values():
            if conn.room_code == room.room_code:
                conn.pid = mapping.get(conn.pid)
                if conn.pid is None:
                    conn.room_code = None
    room.players = participants
    room.game = game
    room.seed = seed
    room.match_id += 1
    room.match_uuid = uuid.uuid4()
    room.tick = 0
    room.dice = None
    room.roll_count = 0
    room.game_events = []
    room.event_serial = 0
    room.next_test_dice = None
    room.dice_bag = []
    room.timer = None
    room.timer_paused = False
    room.config_revision += 1
    for pid, slot in enumerate(room.players):
        slot.pid = pid
        slot.match_player_id = uuid.uuid4()
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
    if ctype == "test_action":
        if not TEST_TOOLS_ENABLED or not room.test_mode or pid != room.host_pid:
            return net_protocol.error_message("forbidden", "Test tools are unavailable for this room/player")
        before = game_events.resources_before(g)
        try:
            action, target, events = test_tools.execute(room, cmd)
        except RuleError as exc:
            return net_protocol.error_message(exc.code, exc.message, exc.details)
        game_events.record(room, "debug", pid, action=action, player_pid=target)
        if action == "trigger_seven":
            game_events.committed(room, g.turn, {"type": "roll"}, events, before, g.robber_tile, g.pirate_tile)
        return None
    if ctype not in MULTIPLAYER_COMMANDS:
        return net_protocol.error_message("forbidden", "Command is not available in multiplayer")
    if ctype == "discard" and not isinstance(cmd.get("discards"), dict):
        return net_protocol.error_message("invalid", "discards must be object")

    dice = None
    next_bag = None
    if ctype == "roll":
        if set(cmd) != {"type"}:
            return net_protocol.error_message("invalid", "Send only the roll intention")
        if TEST_TOOLS_ENABLED and room.test_mode and room.next_test_dice is not None:
            dice = room.next_test_dice
        elif room.settings.dice_mode == "balanced":
            next_bag = room.dice_bag if len(room.dice_bag) > 12 else shuffled_bag()
            dice = next_bag[-1]
        else:
            dice = _roll_dice()
        cmd = {"type": "roll", "roll": sum(dice)}

    before = game_events.resources_before(g)
    old_robber, old_pirate = g.robber_tile, g.pirate_tile
    try:
        _, events = apply_cmd(g, pid, cmd)
    except RuleError as exc:
        return net_protocol.error_message(exc.code, exc.message, exc.details)
    if dice is not None:
        # Public presentation metadata is committed only with an accepted roll.
        room.dice = dice
        room.roll_count += 1
        room.next_test_dice = None
        if next_bag is not None:
            room.dice_bag = next_bag[:-1]
    game_events.committed(room, pid, cmd, events, before, old_robber, old_pirate)
    return None


def _roll_dice() -> tuple[int, int]:
    """Tests may inject this function; no WebSocket debug fields enable it."""
    return secrets.randbelow(6) + 1, secrets.randbelow(6) + 1


async def _start_and_notify(room: Room) -> None:
    async with room.lock:
        candidate = clone_room(room)
        _start_match(candidate, rebind=False)
        _sync_timer(candidate)
        await _commit(room, candidate, snapshot=True)
        await _notify_start(room)


async def _notify_start(room: Room) -> None:
    await _send_room_state(room)
    for ws, conn in list(manager.connections.items()):
        if conn.room_code == room.room_code and conn.pid is not None:
            await _send_reconnect_token(ws, room, conn.pid)
    await _send_match_state(room)


def _sync_timer(room: Room) -> None:
    if room.timer_paused:
        return
    g = room.game
    if not g or g.game_over or g.phase != "main" or not room.settings.turn_timer:
        room.timer = None
    elif room.timer is None or room.timer.pid != g.turn:
        room.timer = TurnTimer.start(g.turn, room.settings.turn_timer, time.monotonic(), time.time())


async def _process_room_timer(room: Room) -> None:
    async with room.lock:
        await _process_room_timer_locked(room)


async def _process_room_timer_locked(room: Room) -> None:
    if manager.rooms.get(room.room_code) is not room:
        return
    if not persistence.ready or room.persistence_blocked or room.timer_paused:
        return
    if room.timer is None and (not room.game or not room.settings.turn_timer
                              or room.game.game_over or room.game.phase != "main"):
        return
    candidate = clone_room(room)
    _sync_timer(candidate)
    timer, g = candidate.timer, candidate.game
    if not timer or not g or time.monotonic() < timer.deadline:
        if candidate.timer != room.timer:
            await _commit(room, candidate, snapshot=bool(candidate.game))
        return
    if timer.stage == "stopped":
        return
    mandatory = g.pending_action is not None or int(g.free_roads.get(g.turn, 0)) > 0
    if mandatory:
        if timer.stage == "blocked":
            return
        timer.stage = "blocked"
    else:
        error = _apply_cmd(candidate, g.turn, {"type": "end_turn" if g.rolled else "roll"})
        if error:
            # Stop retrying an unsafe/unknown state until a real command resolves it.
            timer.stage = "stopped"
            await _commit(room, candidate, snapshot=True)
            return
        if candidate.game.turn == timer.pid:
            candidate.timer = TurnTimer.start(g.turn, 20, time.monotonic(), time.time(), "grace")
        _sync_timer(candidate)
    candidate.tick += 1
    candidate.last_activity_ts = time.time()
    await _commit(room, candidate, snapshot=True)
    await _send_match_state(room)


async def _timer_loop() -> None:
    import logging
    while True:
        await asyncio.sleep(.25)
        for room in list(manager.rooms.values()):
            try:
                # Never cancel an in-flight COMMIT merely because publication is slow.
                await _process_room_timer(room)
            except PersistenceUnavailable:
                pass
            except Exception:
                logging.getLogger(__name__).error("Turn timer update failed: room_id=%s", room.id)


def _promote(room: Room, candidate: Room) -> None:
    if room.game is not None and candidate.game is not None and room.match_uuid == candidate.match_uuid:
        # Preserve domain references held by local tools/tests, but only AFTER commit.
        for f in fields(GameState):
            setattr(room.game, f.name, getattr(candidate.game, f.name))
        candidate.game = room.game
    old = {p.id: p for p in room.players}
    conn_ids = {ws: room.players[c.pid].id for ws, c in manager.connections.items()
                if c.room_code == room.room_code and c.pid is not None and 0 <= c.pid < len(room.players)}
    retained = []
    for new in candidate.players:
        slot = old.get(new.id, new)
        if new.reconnect_token is None and slot.token_hash == new.token_hash:
            new.reconnect_token = slot.reconnect_token
        for f in fields(PlayerSlot):
            if f.name not in {"active_ws", "connected"}:
                setattr(slot, f.name, getattr(new, f.name))
        retained.append(slot)
    for f in fields(Room):
        if f.name not in {"lock", "players"}:
            setattr(room, f.name, getattr(candidate, f.name))
    room.players = retained
    mapping = {p.id: p.pid for p in retained}
    for ws, member_id in conn_ids.items():
        conn = manager.connections[ws]
        conn.pid = mapping.get(member_id)
        if conn.pid is None or room.status == "closed":
            conn.room_code = None
            conn.pid = None


async def _commit(room: Room, candidate: Room, **kwargs) -> None:
    await persistence.commit(room, candidate, **kwargs)
    _promote(room, candidate)


async def _persistence_monitor() -> None:
    initialized = persistence.ready
    while True:
        await asyncio.sleep(1)
        if not persistence.database:
            continue
        try:
            if not initialized:
                await persistence.initialize(manager)
                initialized = True
            await persistence.database.ping()
            for room in list(manager.rooms.values()):
                if room.persistence_blocked:
                    async with room.lock:
                        try:
                            recovered = await persistence.resolve(room)
                            _promote(room, recovered)
                            # Revalidate credentials and deliver the resolved head through ordinary reconnect.
                            # This also resumes a paused timer after a same-process DB outage.
                            for slot in room.players:
                                if slot.active_ws is not None:
                                    with suppress(Exception):
                                        await asyncio.wait_for(slot.active_ws.close(code=1013), timeout=2)
                        except RecoveryError:
                            await _broadcast(room, net_protocol.error_message("recovery_error", "Room checkpoint quarantined"))
                            manager.destroy_room(room.room_code)
            persistence.ready = True
        except Exception:
            persistence.ready = False
            for room in manager.rooms.values():
                room.persistence_blocked = True


async def close_room(code: str) -> None:
    """Internal lifecycle API; close/revoke atomically, no new client/UI route."""
    room = manager.rooms.get(code)
    if not room:
        return
    async with room.lock:
        candidate = clone_room(room)
        candidate.status, candidate.closed_at, candidate.timer = "closed", utcnow(), None
        await _commit(room, candidate)
        manager.destroy_room(code)


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
    room.selected_rules_config = {**room.selected_rules_config, "discard_threshold": updated.discard_threshold}
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


def _set_map(room: Room, pid: int, data: Dict) -> None:
    if pid != room.host_pid:
        raise RuleError("forbidden", "Only host can set map")
    if room.status != "lobby":
        raise RuleError("invalid", "Cannot change map after start")
    source, map_id = data.get("map_data"), data.get("map_id") or data.get("id")
    if isinstance(source, dict):
        try:
            map_loader.validate_map_data(source)
        except Exception as exc:
            raise RuleError("invalid", f"Invalid map_data: {exc}") from exc
        name = str(source.get("name", "custom"))
        map_id = map_id if isinstance(map_id, str) and map_id else name
        meta = {"id": map_id, "name": name, "description": str(source.get("description", ""))}
        room.selected_map_data = source
    else:
        meta = get_preset_meta(map_id) if isinstance(map_id, str) else None
        if not meta:
            raise RuleError("invalid", "Unknown map_id")
        source = get_preset_map(map_id)
        room.selected_map_data = None
    rules_raw = source.get("rules", {})
    room.selected_rules_config = vars(parse_rules_config(rules_raw if isinstance(rules_raw, dict) else {}))
    room.selected_map_id, room.selected_map_meta = map_id, dict(meta)
    if room.settings.target_vp is not None:
        room.selected_rules_config["target_vp"] = room.settings.target_vp
    room.selected_rules_config["discard_threshold"] = room.settings.discard_threshold
    room.map_revision += 1
    room.config_revision += 1


def _owns(conn: ClientConn, room: Room) -> bool:
    return (conn.room_code == room.room_code and conn.pid is not None
            and 0 <= conn.pid < len(room.players)
            and room.players[conn.pid].active_ws is conn.ws
            and room.players[conn.pid].token_expires_at is not None
            and room.players[conn.pid].token_revoked_at is None
            and room.players[conn.pid].token_expires_at > utcnow())


async def _dispatch(conn: ClientConn, data: Dict) -> None:
    ws, kind = conn.ws, data["type"]
    if kind == "hello":
        conn.name = data["name"]
        await _send(ws, {"type": "hello", "version": net_protocol.VERSION,
                         "test_tools_available": TEST_TOOLS_ENABLED})
        return
    if not persistence.ready:
        raise PersistenceUnavailable("Database/recovery temporarily unavailable")
    if kind == "create_room":
        async with manager.create_lock:
            room = manager.create_room(data["name"].strip(), data.get("max_players", 4), register=False)
            await persistence.commit(None, room)
            manager.rooms[room.room_code] = room
            manager.bind_player(conn, room, 0)
            await _send(ws, net_protocol.room_state_message(room))
            await _send_reconnect_token(ws, room, 0)
        return
    code = data.get("room_code", "").strip().upper() if kind in ("join_room", "reconnect") else conn.room_code
    room = manager.rooms.get(code or "")
    if not room:
        if code in persistence.quarantined_codes:
            raise PersistenceUnavailable("Room recovery quarantined; server attention required")
        if kind in ("set_settings", "set_color", "chat", "enable_test_mode"):
            raise RuleError("forbidden", "Room membership required")
        raise RuleError("not_found", "Room not found")
    async with room.lock:
        if room.persistence_blocked:
            raise PersistenceUnavailable("Room persistence temporarily blocked")
        if kind == "join_room":
            name = data["name"].strip()
            if room.status != "lobby" or any(p.name == name for p in room.players):
                raise RuleError("not_found", "Room not found or full")
            pid = next((p.pid for p in room.players if not p.name), None)
            if pid is None:
                raise RuleError("not_found", "Room not found or full")
            candidate = clone_room(room)
            manager._assign_player(candidate, pid, name, connected=True)
            candidate.config_revision += 1
            candidate.last_activity_ts = time.time()
            await _commit(room, candidate)
            manager.bind_player(conn, room, pid)
            await _send(ws, net_protocol.room_state_message(room))
            await _send_reconnect_token(ws, room, pid)
            await _send_room_state(room)
            return
        if kind == "reconnect":
            raw = data["reconnect_token"]
            pid = next((p.pid for p in room.players if p.name and valid_token(p, raw)), None)
            if pid is None:
                raise RuleError("forbidden", "Invalid reconnect token")
            candidate = clone_room(room)
            candidate.players[pid].reconnect_token = raw  # Presented proof, never a DB field.
            candidate.players[pid].token_expires_at = renewed_expiry()
            candidate.last_activity_ts = time.time()
            resumed = resume_timer(candidate)
            await _commit(room, candidate, snapshot=resumed)
            manager.bind_player(conn, room, pid)
            await _send(ws, net_protocol.room_state_message(room))
            await _send_reconnect_token(ws, room, pid)
            await _send_match_state_to(ws, room)
            return
        if not _owns(conn, room):
            raise RuleError("forbidden", "Room membership required")
        if kind == "leave_room":
            candidate = clone_room(room)
            candidate.last_activity_ts = time.time()
            await _commit(room, candidate)
            manager.leave_room(conn)
            await _send_room_state(room)
            conn.room_code, conn.pid = None, None
            return
        if kind == "cmd":
            await _process_room_timer_locked(room)
            if not _owns(conn, room):
                raise RuleError("forbidden", "Room membership required")
            if data.get("room_code") is not None and data["room_code"] != room.room_code:
                raise RuleError("invalid", "room_code mismatch")
            if data["match_id"] != room.match_id:
                raise RuleError("invalid", "match_id mismatch")
            if room.game is None:
                raise RuleError("no_match", "Match not started")
            slot, seq, cmd_id = room.players[conn.pid], data["seq"], data["cmd_id"]
            digest = checksum(data["cmd"])
            if cmd_id in slot.seen_cmd_set or seq <= slot.last_seq_applied:
                if persistence.repository:
                    known = await persistence.repository.receipt(slot.match_player_id, seq, cmd_id)
                    if known and known["cmd_id"] == cmd_id and bytes(known["payload_hash"]) != digest:
                        raise RuleError("invalid", "cmd_id payload conflict")
                await _send_match_state_to(ws, room)
                await _send_cmd_ack(ws, cmd_id, seq, slot.last_seq_applied, applied=False, duplicate=True)
                return
            if seq > slot.last_seq_applied + 1:
                raise RuleError("out_of_order", "Out of order seq", {"expected_seq": slot.last_seq_applied + 1})
            candidate = clone_room(room)
            error = _apply_cmd(candidate, conn.pid, data["cmd"])
            if error:
                candidate = clone_room(room)  # Reject discards all domain effects; only transport outcome commits.
            player = candidate.players[conn.pid]
            player.last_seq_applied = seq
            player.token_expires_at = renewed_expiry()
            _remember_cmd_id(player, cmd_id)
            candidate.last_activity_ts = time.time()
            if not error:
                _sync_timer(candidate)
                candidate.tick += 1
            receipt = {"match_player_id": player.match_player_id, "seq": seq, "cmd_id": cmd_id,
                       "payload_hash": digest, "outcome": "rejected" if error else "accepted",
                       "error_code": error["code"] if error else None}
            await _commit(room, candidate, snapshot=not error, receipt=receipt)
            if error:
                await _send(ws, error)
            else:
                await _send_match_state(room)
            await _send_cmd_ack(ws, cmd_id, seq, room.players[conn.pid].last_seq_applied, applied=not error)
            return
        operation = None
        request_id = data.get("request_id")
        if kind in ("start_match", "rematch", "set_settings", "set_color") and request_id:
            digest = checksum(data)
            known = await persistence.repository.operation(room.id, request_id) if persistence.repository else None
            if known:
                if known["room_player_id"] != room.players[conn.pid].id or bytes(known["payload_hash"]) != digest:
                    raise RuleError("invalid", "request_id conflict")
                await _send_room_state(room, request_id)
                if kind in ("start_match", "rematch"):
                    await _send_reconnect_token(ws, room, conn.pid)
                    await _send_match_state_to(ws, room)
                return
            operation = {"request_id": request_id, "room_player_id": room.players[conn.pid].id,
                         "kind": kind, "payload_hash": digest, "expected_epoch": room.match_id}
        candidate = clone_room(room)
        if kind in ("start_match", "rematch"):
            if data.get("expected_match_id", room.match_id) != room.match_id:
                raise RuleError("invalid", "Stale match operation")
            if conn.pid != (room.host_pid if kind == "start_match" else _rematch_host_pid(room)):
                raise RuleError("forbidden", "Only host can start/rematch")
            if kind == "start_match" and room.status != "lobby":
                raise RuleError("invalid", "Match already started; use rematch")
            _start_match(candidate, rebind=False)
            _sync_timer(candidate)
        elif kind == "set_map":
            _set_map(candidate, conn.pid, data)
        elif kind == "set_settings":
            _set_room_settings(candidate, conn.pid, data["settings"])
        elif kind == "set_color":
            _set_player_color(candidate, conn.pid, data["color"])
        elif kind == "chat":
            _append_chat(candidate, conn.pid, data["text"])
        elif kind == "enable_test_mode":
            if not TEST_TOOLS_ENABLED or conn.pid != room.host_pid or room.status != "lobby":
                raise RuleError("forbidden", "Only host on a test-enabled server may enable a lobby test room")
            candidate.test_mode = True
            candidate.config_revision += 1
        else:
            raise RuleError("unknown", "Unknown operation")
        candidate.last_activity_ts = time.time()
        actor_id = room.players[conn.pid].id
        next(p for p in candidate.players if p.id == actor_id).token_expires_at = renewed_expiry()
        await _commit(room, candidate, snapshot=kind in ("start_match", "rematch"), operation=operation)
        if kind in ("start_match", "rematch"):
            await _notify_start(room)
        elif kind == "chat":
            await _broadcast(room, {"type": "chat_state", "room_code": room.room_code,
                                   "chat_revision": room.chat_revision, "chat_history": list(room.chat_history)})
        else:
            await _send_room_state(room, request_id)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    conn = ClientConn(ws=ws)
    manager.connections[ws] = conn
    try:
        while True:
            raw = await ws.receive_text()
            data = None
            try:
                data = json.loads(raw)
                json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
            except (ValueError, TypeError):
                await _send(ws, net_protocol.error_message("invalid", "Invalid JSON"))
                continue
            validation = net_protocol.validate_client_message(data)
            detail = {"request_type": data.get("type"), "request_id": data.get("request_id")} if isinstance(data, dict) else {}
            if not validation.get("ok"):
                error = validation["error"]
                await _send(ws, net_protocol.error_message(error["code"], error["message"], {**error.get("detail", {}), **detail}))
                continue
            try:
                await _dispatch(conn, data)
            except RuleError as exc:
                await _send(ws, net_protocol.error_message(exc.code, exc.message, {**(exc.details or {}), **detail}))
            except PersistenceUnavailable:
                await _send(ws, net_protocol.error_message("persistence_unavailable", "Durable state temporarily unavailable; reconnect to retry",
                                                          {**detail, "retryable": True}))
                await ws.close(code=1013)
                return
            except Exception:
                # Database driver errors in receipt/recovery reads are also temporary;
                # logs deliberately omit SQL values, credential, URL and private state.
                if persistence.database:
                    persistence.ready = False
                    room = manager.rooms.get(conn.room_code or "")
                    if room:
                        room.persistence_blocked = True
                    logging.getLogger(__name__).error("Room operation failed (private details omitted)")
                    await _send(ws, net_protocol.error_message("persistence_unavailable", "Durable operation unavailable", {**detail, "retryable": True}))
                    await ws.close(code=1013)
                    return
                raise
    except (WebSocketDisconnect, RuntimeError, OSError, asyncio.TimeoutError):
        pass
    finally:
        room = manager.rooms.get(conn.room_code or "")
        if room:
            async with room.lock:
                manager.leave_room(conn)
                await _send_room_state(room)
        manager.connections.pop(ws, None)


def main():
    import uvicorn

    host = os.getenv("CATAN_HOST", "0.0.0.0")
    port_raw = os.getenv("CATAN_PORT", "8000")
    try:
        port = int(port_raw)
    except ValueError:
        port = 8000
    loop = "app.persistence.db:selector_event_loop" if os.name == "nt" else "auto"
    uvicorn.run("app.server_mp:app", host=host, port=port, reload=False, workers=1, loop=loop)


if __name__ == "__main__":
    main()
