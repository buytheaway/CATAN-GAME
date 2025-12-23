from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Optional

@dataclass
class ExpansionContext:
    name: str

class Expansion(Protocol):
    """
    Скелет для расширений (Seafarers / Cities&Knights / etc).
    Реализация: добавить новые действия, фазы, ресурсы, правила выдачи.
    """
    id: str
    title: str

    def on_game_start(self, ctx: ExpansionContext) -> None: ...
    def on_before_roll(self, ctx: ExpansionContext) -> None: ...
    def on_after_roll(self, ctx: ExpansionContext, roll: int) -> None: ...
    def on_turn_end(self, ctx: ExpansionContext) -> None: ...
