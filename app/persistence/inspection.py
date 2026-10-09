"""Read-only guest discovery. This DTO deliberately has no GameState projection."""
import time
from collections import OrderedDict
from datetime import datetime, timezone

from .credentials import utcnow, valid_token
from app.match_rulesets import compatibility

MAX_CREDENTIALS = 10
MAX_BODY_BYTES = 16_384


class InspectionLimiter:
    """Bounded, process-local peer limit for the existing single-worker deployment."""
    def __init__(self, limit=120, window=60, max_peers=1024):
        self.limit, self.window, self.max_peers = limit, window, max_peers
        self.peers = OrderedDict()
        self.total = (0.0, 0)

    def allow(self, peer):
        now = time.monotonic()
        start, count = self.peers.pop(peer, (now, 0))
        if now - start >= self.window:
            start, count = now, 0
        total_start, total_count = self.total
        if now - total_start >= self.window:
            total_start, total_count = now, 0
        allowed = count < self.limit and total_count < self.limit * 5
        self.peers[peer] = (start, count + int(allowed))
        self.total = (total_start, total_count + int(allowed))
        while len(self.peers) > self.max_peers:
            self.peers.popitem(last=False)
        return allowed


def safe_game(*, room_code, map_name, name, color, player_count, max_players,
              connected_count, status, target_vp, updated_at, winner=None, ruleset=None):
    # Closed allowlist; never pass a Room, database row or private checkpoint through.
    game = dict(room_code=room_code, map_name=map_name, own_name=name, own_color=color,
                player_count=player_count, max_players=max_players,
                connected_count=connected_count, status=status, target_vp=target_vp,
                updated_at=updated_at.isoformat(), can_continue=True)
    if winner is not None:
        game["winner"] = {"name": winner["name"], "color": winner["color"]}
    if ruleset is not None:
        game["ruleset_compatibility"] = ruleset
    return {"status": "available", "game": game}


async def inspect_memory(manager, credentials):
    results = []
    for code, raw in credentials:
        room = manager.rooms.get(code)
        if room is None:
            results.append({"status": "invalid"})
            continue
        async with room.lock:
            slot = next((p for p in room.players if p.name and valid_token(p, raw)), None)
            if (slot is None or room.status not in ("lobby", "in_match", "quarantined")
                    or room.closed_at or (room.expires_at and room.expires_at <= utcnow())):
                results.append({"status": "invalid"})
            elif room.persistence_blocked or room.status == "quarantined":
                results.append({"status": "temporarily_unavailable"})
            else:
                finished = room.game is not None and room.game.game_over
                winner = None
                if finished and room.game.winner_pid is not None:
                    p = room.players[room.game.winner_pid]
                    winner = {"name": p.name, "color": p.color}
                results.append(safe_game(
                    room_code=code, map_name=room.selected_map_meta.get("name", room.selected_map_id),
                    name=slot.name, color=slot.color,
                    player_count=sum(bool(p.name) for p in room.players), max_players=room.max_players,
                    connected_count=sum(bool(p.name and p.connected) for p in room.players),
                    status="game_over" if finished else "active" if room.game else "lobby",
                    target_vp=room.selected_rules_config.get("target_vp", 10),
                    updated_at=datetime.fromtimestamp(room.last_activity_ts, timezone.utc), winner=winner,
                    ruleset=compatibility(room.ruleset_id, room.game) if room.game else None))
    return results
