from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

VERSION = 1


def _err(code: str, message: str, detail: Optional[Dict[str, Any]] = None):
    return {
        "ok": False,
        "error": {"code": code, "message": message, "detail": detail or {}},
    }


def validate_client_message(msg: Any) -> Dict[str, Any]:
    if not isinstance(msg, dict):
        return _err("invalid", "message must be object")
    mtype = msg.get("type")
    if not isinstance(mtype, str):
        return _err("invalid", "type must be string")

    if mtype == "hello":
        if msg.get("version") != VERSION:
            return _err("invalid", "unsupported version")
        if not isinstance(msg.get("name"), str):
            return _err("invalid", "name required")
        return {"ok": True}

    if mtype == "create_room":
        if not isinstance(msg.get("name"), str):
            return _err("invalid", "name required")
        max_players = msg.get("max_players", 4)
        if not isinstance(max_players, int) or not (2 <= max_players <= 6):
            return _err("invalid", "max_players must be 2..6")
        ruleset = msg.get("ruleset", {})
        if not isinstance(ruleset, dict):
            return _err("invalid", "ruleset must be object")
        return {"ok": True}

    if mtype == "join_room":
        if not isinstance(msg.get("room_code"), str):
            return _err("invalid", "room_code required")
        if not isinstance(msg.get("name"), str):
            return _err("invalid", "name required")
        return {"ok": True}

    if mtype == "reconnect":
        if not isinstance(msg.get("room_code"), str):
            return _err("invalid", "room_code required")
        if not isinstance(msg.get("reconnect_token"), str):
            return _err("invalid", "reconnect_token required")
        return {"ok": True}

    if mtype in ("leave_room", "start_match", "rematch"):
        return {"ok": True}

    if mtype == "cmd":
        if not isinstance(msg.get("match_id"), int):
            return _err("invalid", "match_id required")
        if not isinstance(msg.get("seq"), int):
            return _err("invalid", "seq required")
        if not isinstance(msg.get("cmd_id"), str):
            return _err("invalid", "cmd_id required")
        if "room_code" in msg and not isinstance(msg.get("room_code"), str):
            return _err("invalid", "room_code must be string")
        cmd = msg.get("cmd")
        if not isinstance(cmd, dict):
            return _err("invalid", "cmd must be object")
        if not isinstance(cmd.get("type"), str):
            return _err("invalid", "cmd.type required")
        return {"ok": True}

    return _err("unknown", f"unknown type: {mtype}")


def error_message(code: str, message: str, detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"type": "error", "code": code, "message": message, "detail": detail or {}}


def room_state_message(room) -> Dict[str, Any]:
    return {
        "type": "room_state",
        "room_code": room.room_code,
        "host_pid": room.host_pid,
        "players": [
            {"pid": p.pid, "name": p.name, "connected": p.connected}
            for p in room.players
        ],
        "max_players": room.max_players,
        "status": room.status,
    }


def match_state_message(room, state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "match_state",
        "room_code": room.room_code,
        "match_id": room.match_id,
        "tick": room.tick,
        "seed": room.seed,
        "state": state,
    }
