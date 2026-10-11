"""Bounded room presentation history. Never broadcast raw engine events.

Private resource details are projected for each recipient, independently of bank
visibility. This feed describes committed effects; it cannot drive gameplay.
"""
from __future__ import annotations

import time
from typing import Any

from app.engine.state import RESOURCES, TERRAIN_TO_RES
from app.engine.exploration import has_fog, tile_is_known

EVENT_LIMIT = 80
PUBLIC_FIELDS = {
    "roll": ("dice", "total"), "production": ("player_pid", "quantity"),
    "move_robber": ("from_tile", "tile"), "move_pirate": ("from_tile", "tile"),
    "theft": ("victim_pid", "quantity"), "discard": ("quantity",),
    "trade_bank": ("quantity",), "buy_dev": ("quantity",), "choose_gold": ("quantity",),
    "play_dev": ("card",), "debug": ("action", "player_pid"),
    "discover_tile": ("tile", "terrain", "number", "reward"),
    **{kind: () for kind in ("place_settlement", "place_road", "build_ship", "upgrade_city",
                            "move_ship", "end_turn", "trade_offer_create", "trade_offer_accept",
                            "trade_offer_decline", "trade_offer_cancel")},
}
PRIVATE_FIELDS = {"production": ("resources",), "theft": ("resource",),
                  **{kind: ("paid", "gained") for kind in ("discard", "trade_bank", "buy_dev", "choose_gold")}}


def _field(key, value):
    if key in ("resources", "paid", "gained"):
        return {r: value[r] for r in RESOURCES if type(value.get(r)) is int and value[r] >= 0} if type(value) is dict else None
    if key == "resource":
        return value if type(value) is str and value in RESOURCES else None
    if key == "dice":
        return list(value) if type(value) is list and len(value) == 2 and all(type(x) is int and 1 <= x <= 6 for x in value) else None
    if key == "reward":
        if type(value) is not dict or type(value.get("quantity")) is not int or value["quantity"] not in (0, 1):
            return None
        kind = value.get("kind")
        if kind not in ("none", "resource", "gold_choice"):
            return None
        result = {"kind": kind, "quantity": value["quantity"]}
        if kind == "resource":
            resource = _field("resource", value.get("resource"))
            if resource is None:
                return None
            result["resource"] = resource
        return result
    if key in ("card", "action", "terrain"):
        return value if type(value) is str and (key != "terrain" or value in TERRAIN_TO_RES) else None
    return value if type(value) is int else None


def record(room, kind: str, actor: int, *, private=None, **public) -> None:
    room.event_serial += 1
    room.game_events.append({"id": room.event_serial, "tick": room.tick + 1,
                             "at_ms": round(time.time() * 1000), "type": kind,
                             "actor_pid": actor, **public, "_private": private or {}})
    room.game_events = room.game_events[-EVENT_LIMIT:]


def project(room, pid: int) -> list[dict[str, Any]]:
    result = []
    fog = has_fog(room.game)
    for event in room.game_events:
        if type(event) is not dict:
            continue
        kind = event.get("type")
        if type(kind) is not str or kind not in PUBLIC_FIELDS or fog and kind == "debug":
            continue
        if fog and any(type(event[key]) is int and event[key] >= 0 and
                       (event[key] >= len(room.game.tiles) or not tile_is_known(room.game, event[key]))
                       for key in ("tile", "from_tile") if key in event):
            continue
        if kind == "discover_tile" and (not fog or type(event.get("tile")) is not int
                                       or event["tile"] not in room.game.scenario.fog.revealed):
            continue
        view = {"type": kind}
        for key in ("id", "tick", "at_ms", "actor_pid", *PUBLIC_FIELDS[kind]):
            if key not in event:
                continue
            value = _field(key, event[key])
            if value is not None or key in ("number", "from_tile") and event[key] is None:
                view[key] = value
        audiences = event.get("_private")
        private = audiences.get(pid, {}) if type(audiences) is dict else {}
        if type(private) is not dict:
            private = {}
        for key in PRIVATE_FIELDS.get(kind, ()):
            value = _field(key, private.get(key))
            if value is not None:
                view[key] = value
        result.append(view)
    return result


def resources_before(game) -> dict[int, dict[str, int]]:
    return {p.pid: dict(p.res) for p in game.players}


def committed(room, actor: int, cmd: dict, events: list[dict], before: dict,
              old_robber: int, old_pirate: int | None) -> None:
    """Closed projection: do not accidentally expose future engine event fields."""
    kind, g = cmd["type"], room.game
    if kind == "roll":
        record(room, "roll", actor, dice=list(room.dice), total=g.last_roll)
        for player in g.players:
            gained = {r: player.res[r] - before[player.pid][r] for r in RESOURCES
                      if player.res[r] > before[player.pid][r]}
            if gained:
                record(room, "production", actor, player_pid=player.pid, quantity=sum(gained.values()),
                       private={player.pid: {"resources": gained}})
    elif kind in ("move_robber", "move_pirate"):
        event = next(e for e in events if e["type"] == kind)
        record(room, kind, actor, from_tile=old_robber if kind == "move_robber" else old_pirate,
               tile=event["tile"])
        if event.get("stolen") and event.get("victim") is not None:
            victim = event["victim"]
            detail = {"resource": event["stolen"]}
            record(room, "theft", actor, victim_pid=victim, quantity=1,
                   private={actor: detail, victim: detail})
    elif kind in ("discard", "trade_bank", "buy_dev", "choose_gold"):
        paid = {r: before[actor][r] - g.players[actor].res[r] for r in RESOURCES
                if before[actor][r] > g.players[actor].res[r]}
        gained = {r: g.players[actor].res[r] - before[actor][r] for r in RESOURCES
                  if g.players[actor].res[r] > before[actor][r]}
        record(room, kind, actor, quantity=sum(paid.values()) or sum(gained.values()),
               private={actor: {"paid": paid, "gained": gained}})
    elif kind == "play_dev":
        # Played cards are public; unplayed draws and effect result internals are not.
        record(room, kind, actor, card=cmd["card"])
    elif kind != "noop":
        record(room, kind, actor)
    # Canonical facts are appended to the detached candidate only after engine
    # success. COMMIT/promotion precede any projection/publication by the server.
    if has_fog(g):
        ledger = {entry.tile_index: entry for entry in g.scenario.fog.discoveries}
        for event in events:
            tile = event.get("tile")
            if event.get("type") != "discover_tile" or tile not in ledger or ledger[tile].pid != actor:
                continue
            terrain = g.tiles[tile].terrain
            resource = TERRAIN_TO_RES[terrain]
            if terrain == "gold":
                reward = {"kind": "gold_choice", "quantity": int(ledger[tile].reward_status != "unavailable")}
            elif resource is not None:
                reward = {"kind": "resource", "resource": resource,
                          "quantity": int(ledger[tile].reward_status == "awarded")}
            else:
                reward = {"kind": "none", "quantity": 0}
            record(room, "discover_tile", actor, tile=tile, terrain=terrain, number=g.tiles[tile].number,
                   reward=reward)
