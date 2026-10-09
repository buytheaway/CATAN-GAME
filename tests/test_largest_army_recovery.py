"""Largest Army survives actual PostgreSQL commits/restarts without rescoring."""
import asyncio
from copy import deepcopy

import pytest

from app import server_mp as server
from app.engine import rules
from app.match_rulesets import CURRENT_RULESET, LEGACY_S1_RULESET, restricted
from app.persistence.snapshots import encode_snapshot
from tests.test_match_rulesets import legacy, unchanged_match
from tests.test_persistence_postgres import database_url, runtime, prepare
from tests.test_persistence_snapshots import main_game, give_card, assert_equivalent
from tests.test_seafarers_recovery import create_room, hydrate, continue_room, dispatch


@pytest.mark.parametrize("map_id", ["base_standard", "seafarers_pirate_lanes"])
@pytest.mark.parametrize("historical", [False, True])
def test_committed_tie_or_historical_unawarded_tie_recovers_without_rescoring(
        database_url, monkeypatch, map_id, historical):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients, proofs = await create_room(coord, "guest", map_id)
            g = main_game(map_id)
            g.players[0].knights_played = 3
            g.players[1].knights_played = 3 if historical else 2
            g.largest_army_owner, g.largest_army_size = (None if historical else 0), 3
            if not historical:
                g.players[0].vp += 2
                give_card(g, "knight", pid=1)
            give_card(g, "victory_point", pid=0)
            g.turn = 1
            await prepare(room, g)
            request = None
            if historical:
                room, _ = await legacy(coord, room, version=2, marker=LEGACY_S1_RULESET)
            else:
                request = await dispatch(room, clients[1], {"type": "play_dev", "card": "knight"})
                assert room.game.largest_army_owner == 0
                assert room.game.players[0].vp == g.players[0].vp
                assert room.game.players[1].knights_played == 3
            before, bundle = deepcopy(room.game), await coord.repository.load(room.id)
            def forbidden(*args, **kwargs):
                pytest.fail("Normal PostgreSQL recovery must not execute gameplay or repair scores")
            with monkeypatch.context() as guard:
                for name in ("apply_cmd", "build_game", "update_largest_army", "update_longest_road", "check_win"):
                    guard.setattr(rules, name, forbidden)
                fresh, restored = await hydrate(coord, room, monkeypatch)
            assert_equivalent(before, restored.game)
            unchanged_match(bundle, await fresh.repository.load(restored.id))
            marker = LEGACY_S1_RULESET if historical else CURRENT_RULESET
            assert restored.ruleset_id == marker and not restricted(restored)
            assert restored.game.largest_army_owner == (None if historical else 0)
            clients = await continue_room(fresh, restored, proofs)
            for pid, client in enumerate(clients):
                view = client.ws.latest("match_state")["state"]
                assert view["largest_army_owner"] == before.largest_army_owner
                assert view["largest_army_size"] == 3
                assert view["players"][0]["vp"] == before.players[0].vp - (pid != 0)
                assert "res" not in view["players"][1 - pid]
                assert "dev_cards" not in view["players"][1 - pid]
            continued = await fresh.repository.load(restored.id)
            # Compatible Continue updates metadata timestamps, never the head,
            # scores or consumed command receipts; recovery itself writes none.
            assert continued["head"] == bundle["head"]
            for key, columns in (("participants", ("id",)), ("receipts", ("match_player_id", "seq"))):
                identity = lambda row: tuple(row[column] for column in columns)
                assert sorted(continued[key], key=identity) == sorted(bundle[key], key=identity)
            assert {k: v for k, v in continued["match"].items() if k != "updated_at"} == {
                k: v for k, v in bundle["match"].items() if k != "updated_at"}
            if request:
                state = encode_snapshot(restored.game)
                await server._dispatch(clients[1], request)
                assert clients[1].ws.latest("cmd_ack")["duplicate"]
                assert encode_snapshot(restored.game) == state
                unchanged_match(continued, await fresh.repository.load(restored.id))
    asyncio.run(run())
