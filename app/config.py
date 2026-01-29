from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

GameMode = Literal["singleplayer", "multiplayer"]
Expansion = Literal["base", "seafarers"]
MapPreset = str
ThemeName = Literal["dark", "light", "midnight"]


@dataclass
class GameConfig:
    mode: GameMode = "singleplayer"
    expansion: Expansion = "base"
    map_preset: MapPreset = "base_standard"
    bot_enabled: bool = True
    bot_difficulty: int = 1
    theme: ThemeName = "midnight"
    ui_scale: float = 1.0
    fullscreen: bool = False
