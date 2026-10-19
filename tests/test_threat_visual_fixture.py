"""Prepared visual acceptance has real legal triggers, victims and private projections."""
import asyncio
from copy import deepcopy

import pytest

from app.engine import rules
from app.persistence.snapshots import encode_snapshot
from tests.threat_visual_support import CASES, threat_game, threat_room, validate_prepared
from tests.test_persistence_postgres import database_url, runtime
from tests.test_resource_allocation import totals


@pytest.mark.parametrize("figure,trigger,mode", CASES)
def test_prepared_threat_uses_real_trigger_victims_conservation_and_no_pre_execution(figure, trigger, mode):
    game, spec = threat_game(figure, trigger, mode)
    before = encode_snapshot(game)
    accepted = validate_prepared(game, spec)
    assert encode_snapshot(game) == before and totals(game) == totals(accepted)
    assert accepted.pending_action is None and getattr(accepted, figure + "_tile") == spec["route"]["tile"]
    assert [p.vp for p in accepted.players] == [p.vp for p in game.players]
    expected = 0 if mode == "none" else 1
    assert accepted.players[0].res["ore"] == expected
    assert accepted.players[1].res["ore"] == 1 - expected
    assert accepted.players[2].res == game.players[2].res
    for pid in range(3):
        assert any(c["type"] == "victory_point" for c in game.players[pid].dev_cards)
    if mode == "fog":
        assert game.scenario.fog.revealed == frozenset() and accepted.scenario.fog == game.scenario.fog
    if mode == "offboard":
        assert game.map_id == "seafarers_gold_haven" and game.robber_tile == -1


@pytest.mark.parametrize("figure,trigger,mode", [CASES[0], CASES[-2], CASES[-1]])
def test_native_threat_fixture_pg_recovery_never_executes_gameplay(database_url, monkeypatch, figure, trigger, mode):
    async def run():
        from app import server_mp as server
        from app.persistence.coordinator import Coordinator
        async with runtime(database_url, monkeypatch) as coord:
            room, proofs, spec = await threat_room(coord, figure, trigger, mode)
            assert len(proofs) == 3 and room.game.pending_action is None
            before = encode_snapshot(room.game)
            def forbidden(*args, **kwargs):
                raise AssertionError("Native recovery must not execute gameplay")
            with monkeypatch.context() as guard:
                for name in ("build_game", "apply_cmd", "check_win", "distribute_for_roll", "_steal_one"):
                    guard.setattr(rules, name, forbidden)
                manager = server.RoomManager()
                fresh = Coordinator(coord.database)
                await fresh.initialize(manager)
            restored = manager.rooms[room.room_code]
            assert encode_snapshot(restored.game) == before and restored.match_uuid == room.match_uuid
            assert not getattr(server.app.state, "_fog_fixture_access", ())
    asyncio.run(run())
