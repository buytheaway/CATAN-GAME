"""The browser fixture uses real legal commands and preserves its pre-action state."""
import asyncio
from copy import deepcopy

import pytest

from app.engine import rules
from app.engine.legal import board_legal_moves
from app.persistence.snapshots import encode_snapshot
from tests.building_visual_support import building_room
from tests.test_persistence_postgres import database_url, runtime


@pytest.mark.parametrize("kind,field", [("place_road", "roads"),
    ("place_settlement", "settlements"), ("upgrade_city", "cities")])
def test_prepared_building_command_is_legal_and_unapplied(database_url, monkeypatch, kind, field):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, proofs, command = await building_room(coord, kind)
            before = encode_snapshot(room.game)
            legal = board_legal_moves(room.game, 0, trusted_fog=True)
            assert command.get("eid", command.get("vid")) in legal[field]
            assert len(proofs) == 2 and room.game.occupied_ships
            assert room.game.pending_action is None and not room.game.game_over
            for resource, quantity in room.game.bank.items():
                assert quantity + sum(p.res[resource] for p in room.game.players) == 19
            candidate = deepcopy(room.game)
            rules.apply_cmd(candidate, 0, command, trusted_fog=True)
            assert encode_snapshot(room.game) == before
            if kind == "place_road":
                assert candidate.occupied_e[tuple(command["eid"])] == 0
                assert candidate.pending_action == "choose_gold"
            else:
                assert candidate.occupied_v[command["vid"]] == (0, 2 if kind == "upgrade_city" else 1)
                assert candidate.pending_action is None
    asyncio.run(run())
