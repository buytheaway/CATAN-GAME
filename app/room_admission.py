"""Room admission policy. IP is an abuse budget, never a seat credential."""
import hashlib
import os
from collections import deque
from dataclasses import dataclass

from app.engine import RuleError


@dataclass(frozen=True)
class RoomCreationLimits:
    limit: int = 20
    window_seconds: int = 600
    lobbies_per_ip: int = 20
    lobbies_global: int = 1000
    tracking_capacity: int = 4096

    @classmethod
    def configured(cls):
        values = {key: int(os.getenv("CATAN_ROOM_CREATE_" + key.upper(), default))
                  for key, default in cls().__dict__.items()}
        if any(value <= 0 for value in values.values()):
            raise ValueError("Room creation limits must be positive integers")
        return cls(**values)

    def check(self, recent, peer_lobbies, global_lobbies):
        if global_lobbies >= self.lobbies_global:
            raise RuleError("lobby_capacity_reached", "Lobby capacity reached; join an existing room or retry later")
        if peer_lobbies >= self.lobbies_per_ip:
            raise RuleError("ip_lobby_limit_reached", "Too many open lobbies from this network; use an existing room")
        if recent >= self.limit:
            raise RuleError("room_creation_rate_limited", "Room creation rate limit reached; retry later",
                            {"retry_after_seconds": self.window_seconds})


def peer_hash(peer):
    # Internal metadata only; do not put raw IPs or this digest into public DTOs.
    return hashlib.sha256(peer.encode("utf-8")).digest()


class MemoryRoomAdmission:
    """Explicit memory mode only. Refuse when full; never evict live budgets."""
    def __init__(self, limits):
        self.limits = limits
        self.recent = deque()

    def check(self, rooms, peer, now):
        cutoff = now - self.limits.window_seconds
        while self.recent and self.recent[0][0] <= cutoff:
            self.recent.popleft()
        lobbies = [room for room in rooms if room.status == "lobby"]
        self.limits.check(sum(origin == peer for _, origin in self.recent),
                          sum(room.creation_peer_hash == peer for room in lobbies), len(lobbies))
        if len(self.recent) >= self.limits.tracking_capacity:
            raise RuleError("room_creation_busy", "Room creation temporarily busy; retry later")

    def accepted(self, peer, now):
        self.recent.append((now, peer))
