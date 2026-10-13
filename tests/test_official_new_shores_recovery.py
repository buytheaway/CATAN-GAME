"""Official Scenario 1 through real dispatch, JSONB, ownership and recovery.

Funding/roll and the final result are explicit fixtures. Expansion commands,
award publication, receipts, reconnect and rematch use production paths.
"""
import asyncio
import json

import pytest
from sqlalchemy import select

from app import server_mp as server
from app.engine import maps, rules
from app.engine.scenario import vertex_islands
from app.match_rulesets import OFFICIAL_S3A_RULESET
from app.persistence import models as m
from app.persistence.coordinator import Coordinator
from app.persistence.errors import PersistenceUnavailable
from app.persistence.recovery import clone_room
from app.persistence.snapshots import encode_snapshot
from tests.test_auth import connection
from tests.test_match_rulesets import unchanged_match
from tests.test_persistence_postgres import database_url, runtime, pair, command
from tests.test_seafarers_scenario_recovery import execute, finish, reach


def preset(players):
    return f"seafarers_official_new_shores_{players}"


async def official_pair(players):
    return await pair(capacity=players, names=tuple(f"Participant {pid}" for pid in range(players)),
                      map_id=preset(players))


@pytest.mark.parametrize("players", [3, 4])
def test_official_award_commit_lost_ack_restart_privacy_and_rematch(database_url, monkeypatch, players):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await official_pair(players)
            assert room.ruleset_id == OFFICIAL_S3A_RULESET
            assert room.game.rules_config.target_vp == 14
            assert room.selected_map_meta["required_players"] == players
            root, = room.game.scenario.rules.starting_islands
            await finish(room, clients, root)
            assert room.game.scenario.home_islands == {pid: {root} for pid in range(players)}
            destination = await reach(room, clients)
            foreign, = vertex_islands(room.game.board, destination)

            # Nonempty secret cards make the subsequent multi-recipient privacy
            # check meaningful; no public endpoint accepts this fixture.
            candidate = clone_room(room)
            for player in candidate.game.players:
                candidate.game.dev_deck.remove("knight")
                player.dev_cards.append({"type": "knight", "new": False})
            await server._commit(room, candidate, snapshot=True)
            before_vp = room.game.players[0].vp
            request = command(room, clients[0], {"type": "place_settlement", "vid": destination})
            messages_before = len(clients[0].ws.messages)
            original_send = clients[0].ws.send_text
            dropped = []

            async def observe_and_lose_ack(raw):
                message = json.loads(raw)
                if message["type"] == "match_state":
                    bundle = await coord.repository.load(room.id)
                    receipt = await coord.repository.receipt(room.players[0].match_player_id,
                                                              request["seq"], request["cmd_id"])
                    assert receipt["outcome"] == "accepted"
                    assert bundle["head"]["tick"] == message["tick"]
                    assert bundle["head"]["payload"]["engine"]["state"]["scenario"]["awarded_islands"] == {"0": [foreign]}
                if message["type"] == "cmd_ack" and message["cmd_id"] == request["cmd_id"]:
                    dropped.append(message)
                    return
                await original_send(raw)

            monkeypatch.setattr(clients[0].ws, "send_text", observe_and_lose_ack)
            await server._dispatch(clients[0], request)
            assert dropped[0]["applied"] and not dropped[0]["duplicate"]
            assert not any(msg["type"] == "cmd_ack" and msg["cmd_id"] == request["cmd_id"]
                           for msg in clients[0].ws.messages[messages_before:])
            assert room.game.players[0].vp == before_vp + 3
            assert room.game.scenario.awarded_islands == {0: {foreign}}
            saved = await coord.repository.load(room.id)
            assert saved["head"]["snapshot_version"] == 4
            assert saved["head"]["engine_compatibility"] == 3
            assert saved["match"]["ruleset_id"] == OFFICIAL_S3A_RULESET
            proofs = [client.ws.latest("reconnect_token")["reconnect_token"] for client in clients]

            def forbidden(*args, **kwargs):
                pytest.fail("Recovery must preserve recorded state without rules/map regeneration")

            with monkeypatch.context() as guard:
                guard.setattr(rules, "apply_cmd", forbidden)
                guard.setattr(rules, "build_game", forbidden)
                guard.setattr(maps, "official_preset_meta", forbidden)
                server.manager = server.RoomManager()
                fresh = Coordinator(coord.database)
                await fresh.initialize(server.manager)
            monkeypatch.setattr(server, "persistence", fresh)
            restored = server.manager.rooms[room.room_code]
            assert restored.game == room.game
            assert restored.ruleset_id == room.ruleset_id
            assert restored.selected_map_meta == room.selected_map_meta
            clients = [await connection() for _ in range(players)]
            for pid, client in enumerate(clients):
                await server._dispatch(client, {"type": "reconnect", "room_code": room.room_code,
                                                "reconnect_token": proofs[pid]})
                view = client.ws.latest("match_state")["state"]
                assert server._owns(client, restored)
                assert view["scenario"]["awarded_islands"] == {"0": [foreign]}
                assert view["players"][0]["special_vp"] == 2
                assert {"seed", "dev_deck", "bank", "ships_built_this_turn", "ship_moved_this_turn"}.isdisjoint(view)
                for other, player in enumerate(view["players"]):
                    assert ("res" in player) is (other == pid)
                    assert ("dev_cards" in player) is (other == pid)
                    if other == pid:
                        assert player["dev_cards"] == [{"type": "knight", "new": False}]

            state = encode_snapshot(restored.game)
            await server._dispatch(clients[0], request)
            assert clients[0].ws.latest("cmd_ack")["duplicate"]
            assert not clients[0].ws.latest("cmd_ack")["applied"]
            assert encode_snapshot(restored.game) == state

            # Rematch checks reset, not a claim of a naturally played victory.
            candidate = clone_room(restored)
            candidate.game.players[0].vp = 14
            candidate.game.game_over, candidate.game.winner_pid = True, 0
            await server._commit(restored, candidate, snapshot=True)
            old_match = restored.match_uuid
            async with coord.database.sessions() as session:
                old_result = (await session.execute(select(m.matches).where(m.matches.c.id == old_match))).mappings().one()
                old_head = (await session.execute(select(m.game_snapshots).where(
                    m.game_snapshots.c.id == old_result["latest_snapshot_id"]))).mappings().one()
            await server._dispatch(clients[0], {"type": "rematch"})
            assert restored.match_uuid != old_match and restored.match_id == 2 and restored.tick == 0
            assert len(restored.game.players) == players
            assert restored.game.scenario.awarded_islands == {}
            assert restored.game.scenario.home_islands == {pid: set() for pid in range(players)}
            assert all(slot.last_seq_applied == 0 for slot in restored.players)
            assert all(client.ws.latest("match_state")["state"]["phase"] == "setup" for client in clients)
            async with coord.database.sessions() as session:
                assert (await session.execute(select(m.matches).where(m.matches.c.id == old_match))).mappings().one() == old_result
                assert (await session.execute(select(m.game_snapshots).where(
                    m.game_snapshots.c.id == old_head["id"]))).mappings().one() == old_head
            assert old_result["status"] == "finished"
    asyncio.run(run())


@pytest.mark.parametrize("players", [3, 4])
def test_official_foreign_setup_and_failed_award_commit_are_atomic(database_url, monkeypatch, players):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await official_pair(players)
            root, = room.game.scenario.rules.starting_islands
            foreign = next(vid for vid in room.game.vertices
                           if vertex_islands(room.game.board, vid) - {root})
            before = await coord.repository.load(room.id)
            state = encode_snapshot(room.game)
            await server._dispatch(clients[0], command(room, clients[0], {"type": "place_settlement", "vid": foreign}))
            assert not clients[0].ws.latest("cmd_ack")["applied"]
            after = await coord.repository.load(room.id)
            assert after["head"] == before["head"] and encode_snapshot(room.game) == state
            assert after["receipts"][-1]["outcome"] == "rejected"
            await finish(room, clients, root)
            destination = await reach(room, clients)
            before = await coord.repository.load(room.id)
            state = encode_snapshot(room.game)
            counts = [len(client.ws.messages) for client in clients]

            def fail(point):
                if point == "before_commit":
                    raise OSError("synthetic official award commit failure")

            coord.repository._test_fault = fail
            try:
                with pytest.raises(PersistenceUnavailable):
                    await execute(room, clients, {"type": "place_settlement", "vid": destination})
            finally:
                coord.repository._test_fault = None
            assert encode_snapshot(room.game) == state
            unchanged_match(before, await coord.repository.load(room.id))
            assert [len(client.ws.messages) for client in clients] == counts
    asyncio.run(run())


@pytest.mark.parametrize("required,online", [(3, 2), (3, 4), (4, 3), (4, 5)])
def test_official_start_and_rematch_require_actual_connected_count(database_url, monkeypatch, required, online):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            clients = [await connection() for _ in range(max(required, online))]
            await server._dispatch(clients[0], {"type": "create_room", "name": "Host", "max_players": 6})
            room = server.manager.rooms[clients[0].room_code]
            await server._dispatch(clients[0], {"type": "set_map", "map_id": preset(required)})
            for pid in range(1, online):
                await server._dispatch(clients[pid], {"type": "join_room", "room_code": room.room_code,
                                                     "name": f"Participant {pid}"})
            before = await coord.repository.load(room.id)
            with pytest.raises(rules.RuleError, match="exactly"):
                await server._dispatch(clients[0], {"type": "start_match"})
            assert await coord.repository.load(room.id) == before and room.game is None
            for pid in range(online, required):
                await server._dispatch(clients[pid], {"type": "join_room", "room_code": room.room_code,
                                                     "name": f"Participant {pid}"})
            for pid in range(required, online):
                await server._dispatch(clients[pid], {"type": "leave_room"})
            await server._dispatch(clients[0], {"type": "start_match"})
            assert len(room.game.players) == required
            candidate = clone_room(room)
            candidate.game.players[0].vp = 14
            candidate.game.game_over, candidate.game.winner_pid = True, 0
            await server._commit(room, candidate, snapshot=True)
            proof = clients[required - 1].ws.latest("reconnect_token")["reconnect_token"]
            await server._dispatch(clients[required - 1], {"type": "leave_room"})
            before = await coord.repository.load(room.id)
            state = encode_snapshot(room.game)
            with pytest.raises(rules.RuleError, match="exactly"):
                await server._dispatch(clients[0], {"type": "rematch"})
            assert await coord.repository.load(room.id) == before and encode_snapshot(room.game) == state
            assert room.game.max_players == required  # Disconnect never reinterprets the saved match.
            replacement = await connection()
            await server._dispatch(replacement, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            assert server._owns(replacement, room)
            await server._dispatch(clients[0], {"type": "rematch"})
            assert room.match_id == 2 and len(room.game.players) == required
            assert all(player.connected for player in room.players)
    asyncio.run(run())
