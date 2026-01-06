from __future__ import annotations
# Пример заглушки: "Seafarers"
# Тут позже добавляются корабли, острова, вода, новые сценарии.
from dataclasses import dataclass

@dataclass
class Seafarers:
    id: str = "seafarers"
    title: str = "Seafarers (stub)"

    def on_game_start(self, ctx): ...
    def on_before_roll(self, ctx): ...
    def on_after_roll(self, ctx, roll: int): ...
    def on_turn_end(self, ctx): ...
