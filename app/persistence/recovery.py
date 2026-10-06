"""Room adapter around the released engine codec; sockets are never encoded."""
import hashlib
import json
import time
from collections import deque
from copy import copy, deepcopy
from dataclasses import asdict, fields
from datetime import datetime, timezone

from app.engine import get_preset_map, list_presets
from app.room_options import RoomSettings, TurnTimer, COLORS, BALANCED_ALGORITHM
from .errors import RecoveryError
from .snapshots import encode_snapshot, decode_snapshot


def checksum(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).digest()


def clone_room(room):
    """Copy mutable domain data, retaining real socket/lock references."""
    candidate = copy(room)
    for f in fields(room):
        if f.name not in {"lock", "players", "game"}:
            setattr(candidate, f.name, deepcopy(getattr(room, f.name)))
    candidate.game = deepcopy(room.game)
    candidate.players = []
    for slot in room.players:
        p = copy(slot)
        p.seen_cmd_ids, p.seen_cmd_set = deque(slot.seen_cmd_ids), set(slot.seen_cmd_set)
        p.chat_times = deque(slot.chat_times)
        candidate.players.append(p)
    return candidate


def room_config(room):
    return {"version": 1, "map_id": room.selected_map_id,
            "map_meta": deepcopy(room.selected_map_meta),
            "map_data": deepcopy(room.selected_map_data if room.selected_map_data is not None
                                 else get_preset_map(room.selected_map_id)),
            "rules": deepcopy(room.selected_rules_config), "settings": asdict(room.settings)}


def match_checkpoint(room):
    timer = None
    if room.timer:
        timer = {"pid": room.timer.pid, "stage": room.timer.stage,
                 "deadline_utc": datetime.fromtimestamp(room.timer.deadline_ms / 1000, timezone.utc).isoformat()}
    # JSON round-trip normalizes private audience keys BEFORE hashing/storage.
    payload = {"room_snapshot_version": 1, "room_id": str(room.id),
               "match_id": str(room.match_uuid), "match_no": room.match_id, "tick": room.tick,
               "engine": encode_snapshot(room.game),
               "runtime": {"seed": room.seed, "dice_algorithm": room.dice_algorithm,
                           "dice_bag": room.dice_bag, "dice": room.dice,
                           "roll_count": room.roll_count, "timer": timer,
                           "event_serial": room.event_serial, "events": room.game_events,
                           "next_test_dice": room.next_test_dice}}
    return json.loads(json.dumps(payload, allow_nan=False))


def _require(condition):
    if not condition:
        raise RecoveryError("Invalid durable room checkpoint")


def _number(n):
    return type(n) is int and n >= 0


def _pair(value):
    _require(isinstance(value, list) and len(value) == 2
             and all(type(v) is int and 1 <= v <= 6 for v in value))
    return tuple(value)


def restore_room(bundle):
    """Strict current-head recovery. Never regenerate or silently use history."""
    from app.server_mp import Room, PlayerSlot  # Domain construction, no ORM engine.
    row = bundle["room"]
    config = row["config"]
    _require(set(config) == {"version", "map_id", "map_meta", "map_data", "rules", "settings"}
             and config["version"] == 1 and type(config["version"]) is int)
    raw_settings = dict(config["settings"])
    _require(set(raw_settings) == {f.name for f in fields(RoomSettings)})
    target = raw_settings.pop("target_vp")
    settings = RoomSettings().updated(raw_settings)
    if target is not None:
        settings = settings.updated({"target_vp": target})
    named = sorted(bundle["members"], key=lambda p: p["current_pid"])
    pids = [p["current_pid"] for p in named]
    _require(len(pids) == len(set(pids)) and all(type(p) is int and 0 <= p < row["max_players"] for p in pids))
    capacity = row["max_players"] if row["status"] == "lobby" else len(named)
    _require(row["status"] in ("lobby", "in_match") and pids == list(range(len(named))))
    players = [PlayerSlot(pid=i) for i in range(capacity)]
    for member in named:
        token = bundle["tokens"].get(member["id"])
        _require(member["color"] in COLORS and token is not None)
        slot = players[member["current_pid"]]
        slot.id, slot.name, slot.color = member["id"], member["name"], member["color"]
        slot.token_hash, slot.token_expires_at = bytes(token["token_hash"]), token["expires_at"]
        slot.token_revoked_at = token["revoked_at"]
    host = next((p.pid for p in players if p.id == row["host_room_player_id"]), None)
    _require(host is not None)
    room = Room(room_code=row["room_code"], max_players=row["max_players"], host_pid=host, players=players)
    room.id, room.durable_revision = row["id"], row["durable_revision"]
    room.status, room.match_id, room.tick = row["status"], row["match_no"], row["tick"]
    room.created_at, room.last_activity_ts = row["created_at"], row["last_activity_at"].timestamp()
    room.closed_at, room.expires_at = row["closed_at"], row["expires_at"]
    room.selected_map_id, room.selected_map_meta = config["map_id"], deepcopy(config["map_meta"])
    room.selected_map_data, room.selected_rules_config = deepcopy(config["map_data"]), deepcopy(config["rules"])
    room.map_presets, room.settings = list_presets(), settings
    room.map_revision, room.config_revision = row["map_revision"], row["config_revision"]
    room.chat_revision, room.chat_history = row["chat_revision"], deepcopy(row["chat_history"])
    room.test_mode = row["is_test"]
    _require(isinstance(room.chat_history, list) and len(room.chat_history) <= 50)
    chat_ids = [c["id"] for c in room.chat_history]
    _require(chat_ids == sorted(set(chat_ids)) and (not chat_ids or chat_ids[-1] == room.chat_revision))
    for c in room.chat_history:
        _require(set(c) == {"id", "name", "color", "text", "sent_at_ms"}
                 and isinstance(c["text"], str) and 1 <= len(c["text"]) <= 500)
    if row["status"] == "lobby":
        _require(row["current_match_id"] is None and room.match_id == 0)
        return room
    match, head = bundle["match"], bundle["head"]
    _require(match is not None and head is not None
             and match["status"] in ("active", "finished")
             and match["id"] == row["current_match_id"] == head["match_id"]
             and match["match_no"] == room.match_id
             and head["revision"] <= room.durable_revision
             and match["tick"] == head["tick"] == room.tick)
    payload = head["payload"]
    _require(checksum(payload) == bytes(head["checksum"]))
    _require(set(payload) == {"room_snapshot_version", "room_id", "match_id", "match_no", "tick", "engine", "runtime"}
             and type(payload["room_snapshot_version"]) is int and payload["room_snapshot_version"] == 1
             and payload["room_id"] == str(room.id) and payload["match_id"] == str(match["id"])
             and payload["match_no"] == room.match_id and payload["tick"] == room.tick
             and head["snapshot_version"] == payload["engine"]["snapshot_version"]
             and head["engine_compatibility"] == payload["engine"]["engine_compatibility"])
    room.game = decode_snapshot(payload["engine"])
    _require(room.game.max_players == len(named) and room.game.map_id == match["map_id"]
             and room.game.game_over == (match["status"] == "finished"))
    room.match_uuid = match["id"]
    participants = bundle["participants"]
    _require(len(participants) == len(named))
    for mp in participants:
        _require(0 <= mp["pid"] < len(named) and room.players[mp["pid"]].id == mp["room_player_id"]
                 and room.game.players[mp["pid"]].name == room.players[mp["pid"]].name)
        slot = room.players[mp["pid"]]
        slot.match_player_id, slot.last_seq_applied = mp["id"], mp["consumed_seq"]
        receipts = sorted((r for r in bundle["receipts"] if r["match_player_id"] == mp["id"]), key=lambda r: r["seq"])
        _require(len(receipts) <= 256 and all(r["seq"] <= slot.last_seq_applied for r in receipts))
        slot.seen_cmd_ids = deque(r["cmd_id"] for r in receipts)
        slot.seen_cmd_set = set(slot.seen_cmd_ids)
    runtime = payload["runtime"]
    _require(set(runtime) == {"seed", "dice_algorithm", "dice_bag", "dice", "roll_count", "timer", "event_serial", "events", "next_test_dice"})
    _require(runtime["seed"] == room.game.seed and runtime["dice_algorithm"] == BALANCED_ALGORITHM
             and _number(runtime["roll_count"]) and _number(runtime["event_serial"]))
    room.seed, room.dice_algorithm = runtime["seed"], runtime["dice_algorithm"]
    _require(isinstance(runtime["dice_bag"], list) and len(runtime["dice_bag"]) <= 36)
    room.dice_bag = [_pair(p) for p in runtime["dice_bag"]]
    _require(len(room.dice_bag) == len(set(room.dice_bag)))
    room.dice = _pair(runtime["dice"]) if runtime["dice"] is not None else None
    room.roll_count, room.event_serial = runtime["roll_count"], runtime["event_serial"]
    room.next_test_dice = _pair(runtime["next_test_dice"]) if runtime["next_test_dice"] is not None else None
    _require(room.test_mode or room.next_test_dice is None)
    events = deepcopy(runtime["events"])
    _require(isinstance(events, list) and len(events) <= 80)
    ids = [e["id"] for e in events]
    _require(ids == sorted(set(ids)) and (not ids or ids[-1] == room.event_serial))
    for e in events:
        _require(0 <= e["actor_pid"] < len(named) and e["tick"] <= room.tick
                 and isinstance(e["_private"], dict))
        private = {}
        for key, value in e["_private"].items():
            _require(key in {str(i) for i in range(len(named))} and isinstance(value, dict))
            private[int(key)] = value
        e["_private"] = private
        if e["type"] == "theft":
            _require("resource" not in e and set(private) <= {e["actor_pid"], e["victim_pid"]})
    room.game_events = events
    timer = runtime["timer"]
    if timer is not None:
        _require(set(timer) == {"pid", "stage", "deadline_utc"} and timer["pid"] == room.game.turn
                 and timer["stage"] in ("turn", "grace", "blocked", "stopped")
                 and settings.turn_timer > 0 and room.game.phase == "main" and not room.game.game_over)
        deadline = datetime.fromisoformat(timer["deadline_utc"])
        _require(deadline.tzinfo is not None and deadline.utcoffset().total_seconds() == 0)
        room.timer = TurnTimer(timer["pid"], time.monotonic() + max(0, deadline.timestamp() - time.time()),
                               round(deadline.timestamp() * 1000), timer["stage"])
        room.timer_paused = True
    return room


def resume_timer(room):
    """Only a verified participant calls this; downtime never chains auto-turns."""
    if not room.timer_paused:
        return False
    room.timer_paused = False
    if room.timer and room.timer.stage in ("turn", "grace"):
        remaining = max(20, min(room.settings.turn_timer, room.timer.deadline_ms / 1000 - time.time()))
        room.timer = TurnTimer.start(room.timer.pid, remaining, time.monotonic(), time.time(), room.timer.stage)
    return True
