"""Bounded room presentation history. Never broadcast raw engine events.

Private resource details are projected for each recipient, independently of bank
visibility. This feed describes committed effects; it cannot drive gameplay.
"""
from __future__ import annotations

import time
from copy import deepcopy
from typing import Any

from app.engine.state import RESOURCES

EVENT_LIMIT = 80


def record(room, kind: str, actor: int, *, private=None, **public) -> None:
    room.event_serial += 1
    room.game_events.append({"id": room.event_serial, "tick": room.tick + 1,
                             "at_ms": round(time.time() * 1000), "type": kind,
                             "actor_pid": actor, **public, "_private": private or {}})
    room.game_events = room.game_events[-EVENT_LIMIT:]


def project(room, pid: int) -> list[dict[str, Any]]:
    return [deepcopy({**{k: v for k, v in e.items() if k != "_private"},
                      **e["_private"].get(pid, {})}) for e in room.game_events]


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
