"""Only the prepared browser fixture is new; production rules/projection stay untouched."""
import asyncio
from copy import deepcopy

from app.engine import rules
from app.engine.legal import board_legal_moves
from app.persistence.snapshots import encode_snapshot
from tests.fog_live_support import ship_movement_room
from tests.test_persistence_postgres import database_url, runtime


def test_visual_movement_fixture_is_legal_and_preload_does_not_move_ship(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, proofs, command = await ship_movement_room(coord)
            source, target = tuple(command["from_eid"]), tuple(command["to_eid"])
            before = encode_snapshot(room.game)
            legal = board_legal_moves(room.game, 0, trusted_fog=True)
            assert list(source) in legal["move_ship"]["sources"]
            assert list(target) in legal["move_ship"]["targets"][",".join(map(str, source))]
            assert len(proofs) == 2 and source in room.game.occupied_ships and target not in room.game.occupied_ships
            candidate = deepcopy(room.game)
            rules.apply_cmd(candidate, 0, command, trusted_fog=True)
            assert encode_snapshot(room.game) == before
            assert candidate.pending_action == "choose_gold"
    asyncio.run(run())
