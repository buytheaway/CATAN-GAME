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
        if not isinstance(msg.get("name"), str) or not msg["name"].strip():
            return _err("invalid", "name required")
        max_players = msg.get("max_players", 4)
        if type(max_players) is not int or not (2 <= max_players <= 6):
            return _err("invalid", "max_players must be 2..6")
        ruleset = msg.get("ruleset", {})
        if not isinstance(ruleset, dict):
            return _err("invalid", "ruleset must be object")
        return {"ok": True}

    if mtype == "join_room":
        if not isinstance(msg.get("room_code"), str):
            return _err("invalid", "room_code required")
        if not isinstance(msg.get("name"), str) or not msg["name"].strip():
            return _err("invalid", "name required")
        return {"ok": True}

    if mtype == "reconnect":
        if not isinstance(msg.get("room_code"), str):
            return _err("invalid", "room_code required")
        if not isinstance(msg.get("reconnect_token"), str) or not msg["reconnect_token"]:
            return _err("invalid", "reconnect_token required")
        return {"ok": True}

    if mtype == "account_continue":
        if (not isinstance(msg.get("room_code"), str) or not 1 <= len(msg["room_code"]) <= 32
                or set(msg) != {"type", "room_code"}):
            return _err("invalid", "room_code required; identity comes from session")
        return {"ok": True}

    if mtype in ("leave_room", "start_match", "rematch", "enable_test_mode"):
        if "request_id" in msg and (not isinstance(msg["request_id"], str) or not 1 <= len(msg["request_id"]) <= 128):
            return _err("invalid", "Invalid request_id")
        if "expected_match_id" in msg and (type(msg["expected_match_id"]) is not int or msg["expected_match_id"] < 0):
            return _err("invalid", "Invalid expected_match_id")
        return {"ok": True}

    if mtype == "set_map":
        map_id = msg.get("map_id")
        map_data = msg.get("map_data")
        if map_data is None and not isinstance(map_id, str):
            return _err("invalid", "map_id or map_data required")
        if map_data is not None and not isinstance(map_data, dict):
            return _err("invalid", "map_data must be object")
        return {"ok": True}

    if mtype in ("set_settings", "set_color"):
        if "request_id" in msg and (not isinstance(msg["request_id"], str) or not 1 <= len(msg["request_id"]) <= 128):
            return _err("invalid", "Invalid request_id")
        if mtype == "set_settings" and not isinstance(msg.get("settings"), dict):
            return _err("invalid", "settings must be object")
        if mtype == "set_color" and not isinstance(msg.get("color"), str):
            return _err("invalid", "color required")
        return {"ok": True}

    if mtype == "chat":
        if not isinstance(msg.get("text"), str):
            return _err("invalid", "Chat text required")
        return {"ok": True}

    if mtype == "cmd":
        if type(msg.get("match_id")) is not int or msg["match_id"] <= 0:
            return _err("invalid", "match_id required")
        if type(msg.get("seq")) is not int or msg["seq"] <= 0:
            return _err("invalid", "seq required")
        if not isinstance(msg.get("cmd_id"), str) or not 1 <= len(msg["cmd_id"]) <= 128:
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
    from app.match_rulesets import compatibility
    msg = {
        "type": "room_state",
        "room_code": room.room_code,
        "map_revision": room.map_revision,
        "config_revision": room.config_revision,
        "settings": room.settings.public(room.selected_rules_config.get("target_vp", 10)),
        "chat_history": list(room.chat_history),
        "chat_revision": room.chat_revision,
        "host_pid": room.host_pid,
        "players": [
            {"pid": p.pid, "name": p.name, "connected": p.connected, "color": p.color}
            for p in room.players
        ],
        "max_players": room.max_players,
        "status": room.status,
        "test_mode": room.test_mode,
    }
    if hasattr(room, "selected_map_id"):
        msg["map_id"] = getattr(room, "selected_map_id")
    if hasattr(room, "selected_map_meta"):
        msg["map_meta"] = getattr(room, "selected_map_meta")
    if hasattr(room, "map_presets"):
        msg["map_presets"] = getattr(room, "map_presets")
    if hasattr(room, "selected_rules_config"):
        msg["map_rules"] = getattr(room, "selected_rules_config")
    if room.game is not None:
        msg["ruleset_compatibility"] = compatibility(room.ruleset_id, room.game)
    return msg


def match_state_message(room, state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "match_state",
        "room_code": room.room_code,
        "match_id": room.match_id,
        "tick": room.tick,
        "state": state,
    }
