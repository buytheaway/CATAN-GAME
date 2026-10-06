"""Room policy, separate from the shared engine's gameplay state."""
from __future__ import annotations

import secrets
from dataclasses import asdict, dataclass, replace
from typing import Any

COLORS = ("red", "blue", "orange", "white", "green", "purple")
BALANCED_ALGORITHM = "balanced_v1"
CHAT_LIMIT = 50
CHAT_MAX_LENGTH = 500
CHAT_RATE_COUNT = 5
CHAT_RATE_SECONDS = 10


@dataclass(frozen=True)
class RoomSettings:
    dice_mode: str = "random"
    starting_player: str = "random"
    turn_timer: int = 0
    bank_visibility: str = "visible"
    target_vp: int | None = None  # None follows the selected preset.
    discard_threshold: int = 7

    def updated(self, patch: dict[str, Any]) -> RoomSettings:
        validators = {
            "dice_mode": lambda v: v in ("random", "balanced"),
            "starting_player": lambda v: v in ("random", "host"),
            "turn_timer": lambda v: type(v) is int and v in (0, 30, 60, 90, 120),
            "bank_visibility": lambda v: v in ("visible", "hidden"),
            "target_vp": lambda v: type(v) is int and 3 <= v <= 30,
            "discard_threshold": lambda v: type(v) is int and 1 <= v <= 50,
        }
        if not patch or any(k not in validators or not validators[k](v) for k, v in patch.items()):
            raise ValueError("Invalid room settings")
        return replace(self, **patch)

    def public(self, preset_target: int) -> dict[str, Any]:
        return {**asdict(self), "target_vp": self.target_vp if self.target_vp is not None else preset_target}


def shuffled_bag() -> list[tuple[int, int]]:
    """balanced_v1: 36 ordered outcomes; replace, never merge, at 12 left."""
    bag = [(a, b) for a in range(1, 7) for b in range(1, 7)]
    secrets.SystemRandom().shuffle(bag)
    return bag


@dataclass
class TurnTimer:
    pid: int
    deadline: float  # Monotonic: wall-clock adjustments cannot change authority.
    deadline_ms: int
    stage: str = "turn"

    @classmethod
    def start(cls, pid: int, seconds: int, now: float, wall: float, stage: str = "turn") -> TurnTimer:
        return cls(pid, now + seconds, round((wall + seconds) * 1000), stage)

    def public(self, now: float, wall: float) -> dict[str, Any]:
        return {"pid": self.pid, "deadline_ms": self.deadline_ms,
                "server_time_ms": round(wall * 1000),
                "remaining_ms": max(0, round((self.deadline - now) * 1000)), "stage": self.stage}
