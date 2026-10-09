"""Historical board heads survive new preset definitions, through real PostgreSQL."""
import asyncio
from pathlib import Path

import pytest
from sqlalchemy import update

from app import server_mp as server
from app.engine import maps, rules
from app.engine.topology import land_components
from app.match_rulesets import CURRENT_RULESET, restricted
from app.persistence import models as m
from app.persistence.coordinator import Coordinator
from app.persistence.recovery import clone_room
from app.persistence.snapshots import loads_snapshot
from tests.test_auth import connection
from tests.test_persistence_postgres import database_url, runtime, pair, command


@pytest.mark.parametrize("known_rules", [True, False])
def test_saved_s1_board_recovery_retains_topology_ports_ownership_and_ruleset_gate(
        database_url, monkeypatch, known_rules):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair(map_id="seafarers_gold_haven")
            assert len(room.game.tiles) == 37 and len(land_components(room.game.board)) == 2
            proof = clients[0].ws.latest("reconnect_token")["reconnect_token"]
            old = loads_snapshot(Path(__file__).with_name("fixtures").joinpath("s1_gold_haven_v2.json").read_text())
            candidate = clone_room(room)
            candidate.game, candidate.seed = old, old.seed
            for p, slot in zip(old.players, candidate.players):
                p.name = slot.name
            # Persist a historical materialized board; its source data need not
            # pass today's new-map coastal validator and is never rebuilt.
            candidate.selected_map_data = {"version": 1, "name": old.map_name,
                "tiles": [{"q": t.q, "r": t.r, "terrain": t.terrain, "number": t.number} for t in old.tiles],
                "ports": [{"edge": list(e), "type": k} for e, k in old.ports], "rules": old.rules}
            await server._commit(room, candidate, snapshot=True)
            if not known_rules:
                async with coord.database.sessions() as session, session.begin():
                    await session.execute(update(m.matches).where(m.matches.c.id == room.match_uuid).values(ruleset_id=None))
            before = await coord.repository.load(room.id)
            def forbidden(*args, **kwargs):
                raise AssertionError("recovery must not execute rules or regenerate maps")
            with monkeypatch.context() as guard:
                guard.setattr(rules, "build_game", forbidden)
                guard.setattr(rules, "apply_cmd", forbidden)
                guard.setattr(maps, "build_board_from_map", forbidden)
                server.manager = server.RoomManager()
                fresh = Coordinator(coord.database)
                await fresh.initialize(server.manager)
            restored = server.manager.rooms[room.room_code]
            assert restored.game == old and len(restored.game.tiles) == 19
            assert restored.ruleset_id == (CURRENT_RULESET if known_rules else None)
            assert restricted(restored) == (not known_rules)
            client = await connection()
            await server._dispatch(client, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            assert client.pid == 0
            views = [v for v in client.ws.messages if v["type"] == "match_state"]
            if known_rules:
                assert len(views[-1]["state"]["tiles"]) == 19
                assert "res" not in views[-1]["state"]["players"][1]
            else:
                assert not views
                with pytest.raises(rules.RuleError, match="older or unverified ruleset"):
                    await server._dispatch(client, command(restored, client, {"type": "noop"}))
                assert not any(v["type"] == "cmd_ack" for v in client.ws.messages)
            after = await coord.repository.load(room.id)
            assert after["head"] == before["head"]
            assert after["match"]["ruleset_id"] == before["match"]["ruleset_id"]
            # New, separate matches use the updated definition without touching
            # the old head. Neither snapshot format nor provenance is inferred.
            new_room, _ = await pair(map_id="seafarers_gold_haven")
            assert len(new_room.game.tiles) == 37 and new_room.ruleset_id == CURRENT_RULESET
            assert (await coord.repository.load(restored.id))["head"] == before["head"]
    asyncio.run(run())
