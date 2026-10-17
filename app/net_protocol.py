from __future__ import annotations

import math
import unicodedata
from typing import Any, Dict, Optional, Tuple
from app.engine.public_projection import public_map_metadata, public_rules_config
from app.engine.rules import RuleError, dev_card_options

VERSION = 1


def _err(code: str, message: str, detail: Optional[Dict[str, Any]] = None):
    return {
        "ok": False,
        "error": {"code": code, "message": message, "detail": detail or {}},
    }


def _storage_safe(value: Any) -> bool:
    """JSONB/Text cannot store NUL or unpaired surrogates, including in keys."""
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if "\x00" in item:
                return False
            try:
                item.encode("utf-8")
            except UnicodeError:
                return False
        elif isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                return False
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
        elif isinstance(item, float):
            if not math.isfinite(item):
                return False
        elif item is not None and type(item) not in (int, bool):
            return False
    return True


def _display_name(value: Any) -> bool:
    return (isinstance(value, str) and 1 <= len(value.strip()) <= 32
            and not any(unicodedata.category(c).startswith("C") for c in value))


def _validate_command(cmd: Dict) -> None:
    # Syntactic types only. Turn/cost/targets/authority remain engine checks.
    kind = cmd["type"]
    fields = {
        "place_settlement": {"vid": int, "setup": bool},
        "place_road": {"eid": list, "setup": bool, "free": bool},
        "upgrade_city": {"vid": int}, "build_ship": {"eid": list, "setup": bool, "free": bool},
        "move_ship": {"from_eid": list, "to_eid": list},
        "move_robber": {"tile": int, "victim": int, "victim_pid": int},
        "move_pirate": {"tile": int, "victim": int, "victim_pid": int},
        "discard": {"discards": dict}, "choose_gold": {"res": str, "qty": int},
        "trade_bank": {"give": str, "get": str, "get_qty": int},
        "trade_offer_create": {"give": dict, "get": dict, "to": int, "to_pid": int},
        "trade_offer_accept": {"offer_id": int, "id": int},
        "trade_offer_decline": {"offer_id": int, "id": int},
        "trade_offer_cancel": {"offer_id": int, "id": int},
    }
    nullable = {"victim", "victim_pid", "to", "to_pid"}
    for key, expected in fields.get(kind, {}).items():
        if key not in cmd or (key in nullable and cmd[key] is None):
            continue
        value = cmd[key]
        if type(value) is not expected:
            raise RuleError("invalid", f"cmd.{key} must be {expected.__name__}")
        if key in ("eid", "from_eid", "to_eid"):
            if len(value) != 2 or any(type(v) is not int for v in value):
                raise RuleError("invalid", f"cmd.{key} must contain two integers")
        if key in ("give", "get", "discards") and isinstance(value, dict):
            if any(type(qty) is not int for qty in value.values()):
                raise RuleError("invalid", f"cmd.{key} quantities must be integers")
    if kind == "play_dev":
        dev_card_options(cmd)


def validate_client_message(msg: Any) -> Dict[str, Any]:
    if not isinstance(msg, dict):
        return _err("invalid", "message must be object")
    if not _storage_safe(msg):
        return _err("invalid", "Payload contains invalid JSON/storage values")
    if "request_id" in msg and (not isinstance(msg["request_id"], str) or not 1 <= len(msg["request_id"]) <= 128):
        return _err("invalid", "Invalid request_id")
    if "room_code" in msg and not isinstance(msg["room_code"], str):
        return _err("invalid", "room_code must be string")
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
        if not _display_name(msg.get("name")):
            return _err("invalid", "name must be 1..32 characters without controls")
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
        if not _display_name(msg.get("name")):
            return _err("invalid", "name must be 1..32 characters without controls")
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

    if mtype == "close_room":
        if (set(msg) != {"type", "room_code", "request_id", "expected_match_id"}
                or not isinstance(msg["room_code"], str) or not 1 <= len(msg["room_code"]) <= 32
                or not isinstance(msg["request_id"], str) or not 1 <= len(msg["request_id"]) <= 128
                or type(msg["expected_match_id"]) is not int or msg["expected_match_id"] != 0):
            return _err("invalid", "Close requires room_code, request_id and unstarted match epoch")
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
        if map_id is not None and not isinstance(map_id, str):
            return _err("invalid", "map_id must be string")
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
        try:
            _validate_command(cmd)
        except RuleError as exc:
            return _err(exc.code, exc.message)
        return {"ok": True}

    return _err("unknown", f"unknown type: {mtype}")


def error_message(code: str, message: str, detail: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"type": "error", "code": code, "message": message, "detail": detail or {}}


def room_state_message(room, *, fog_access=None) -> Dict[str, Any]:
    from app.match_rulesets import compatibility
    map_rules = public_rules_config(room.selected_rules_config)
    preset_target = map_rules.get("target_vp", room.game.rules_config.target_vp if room.game else 10)
    msg = {
        "type": "room_state",
        "room_code": room.room_code,
        "map_revision": room.map_revision,
        "config_revision": room.config_revision,
        "settings": room.settings.public(preset_target),
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
        msg["map_meta"] = public_map_metadata(room.selected_map_meta)
    if hasattr(room, "map_presets"):
        msg["map_presets"] = [public_map_metadata(meta) for meta in room.map_presets]
    if hasattr(room, "selected_rules_config"):
        msg["map_rules"] = map_rules
    if room.game is not None:
        msg["ruleset_compatibility"] = compatibility(room.ruleset_id, room.game)
        from app.fog_transport import FogMatchAccess
        if type(fog_access) is FogMatchAccess and fog_access.permits(room):
            msg["ruleset_compatibility"]["status"] = "compatible"
    return msg


def match_state_message(room, state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "match_state",
        "room_code": room.room_code,
        "match_id": room.match_id,
        "tick": room.tick,
        "state": state,
    }
