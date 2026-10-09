"""S2B-1 actual server dispatch/COMMIT/recovery and real WebSocket refusals."""
import asyncio
from copy import deepcopy

import pytest
import websockets

from app import server_mp as server
from app.engine import rules
from app.engine.legal import board_legal_moves
from app.engine.scenario import vertex_islands
from app.engine.state import COST, ScenarioRules
from app.match_rulesets import CURRENT_RULESET, LEGACY_S1_RULESET, RulesetCompatibilityError, restricted
from app.persistence.coordinator import Coordinator
from app.persistence.errors import PersistenceUnavailable
from app.persistence.recovery import clone_room, restore_room
from app.persistence.snapshots import encode_snapshot
from app.persistence import models as m
from sqlalchemy import update
from tests.test_auth import connection
from tests.test_match_rulesets import legacy, unchanged_match
from tests.test_persistence_postgres import database_url, runtime, pair, command
from tests.test_seafarers_maps import fund, sea_path
from tests.test_seafarers_scenarios import scenario_map
from tests.test_server_authority import live_server, start_pair
from tests.test_seafarers_multiplayer import reject, accept


async def custom_pair(source):
    a, b = await connection(), await connection()
    await server._dispatch(a, {"type": "create_room", "name": "Alice", "max_players": 2})
    await server._dispatch(a, {"type": "set_map", "map_id": "explicit-custom", "map_data": source})
    await server._dispatch(a, {"type": "set_settings", "settings": {"starting_player": "host", "bank_visibility": "hidden"}})
    await server._dispatch(b, {"type": "join_room", "name": "Bob", "room_code": a.room_code})
    await server._dispatch(a, {"type": "start_match"})
    return server.manager.rooms[a.room_code], [a, b]


async def execute(room, clients, cmd):
    client = clients[room.game.pending_pid if room.game.pending_pid is not None else room.game.turn]
    request = command(room, client, cmd)
    await server._dispatch(client, request)
    assert client.ws.latest("cmd_ack")["applied"]
    return request


async def finish(room, clients, root):
    while room.game.phase == "setup" or room.game.pending_action == "choose_gold":
        g, legal = room.game, board_legal_moves(room.game, room.game.turn)
        if g.pending_action == "choose_gold":
            resource = next(r for r, n in g.bank.items() if n)
            await execute(room, clients, {"type": "choose_gold", "res": resource})
        elif g.setup_need == "settlement":
            vid = next(v for v in legal["settlements"] if vertex_islands(g.board, v) == {root}
                       and any(rules._edge_has_sea(g, e) and not rules._edge_blocked_by_pirate(g, e)
                               for e in g.edges if v in e))
            await execute(room, clients, {"type": "place_settlement", "vid": vid})
        else:
            ships = legal["ships"]
            await execute(room, clients, {"type": "build_ship" if ships else "place_road",
                                         "eid": (ships or legal["roads"])[0]})


async def reach(room, clients):
    # Explicit test-only funding and deterministic roll; commands after this
    # checkpoint still pass the unchanged authorization/sequence/commit path.
    candidate = clone_room(room)
    rules.apply_cmd(candidate.game, 0, {"type": "roll", "roll": 2})
    destination, path = sea_path(candidate.game, 0)
    for r, cost in {"wood": len(path) + 1, "sheep": len(path) + 1, "brick": 1, "wheat": 1}.items():
        fund(candidate.game, {r: cost})
    await server._commit(room, candidate, snapshot=True)
    for edge in path:
        if edge not in room.game.occupied_ships:
            await execute(room, clients, {"type": "build_ship", "eid": edge})
    return destination


@pytest.mark.parametrize("preset,restricted_start,bonus,target", [
    ("seafarers_gold_haven", True, 2, 12), ("seafarers_pirate_lanes", False, 3, 14)])
def test_custom_creation_atomic_award_receipt_restart_reconnect_privacy_and_rematch(
        database_url, monkeypatch, preset, restricted_start, bonus, target):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            source = scenario_map(preset, restricted=restricted_start, bonus=bonus, target=target)
            room, clients = await custom_pair(source)
            assert room.ruleset_id == CURRENT_RULESET and room.game.rules_config.target_vp == target
            root = 4 if preset == "seafarers_gold_haven" else 9
            await finish(room, clients, root)
            destination = await reach(room, clients)
            before = room.game.players[0].vp
            request = await execute(room, clients, {"type": "place_settlement", "vid": destination})
            assert room.game.players[0].vp == before + 1 + bonus
            assert room.game.scenario.awarded_islands == {0: {13}}
            bundle = await coord.repository.load(room.id)
            assert bundle["head"]["snapshot_version"] == 4 and bundle["head"]["engine_compatibility"] == 3
            assert bundle["match"]["ruleset_id"] == CURRENT_RULESET
            assert bundle["head"]["payload"]["engine"]["state"]["scenario"]["awarded_islands"] == {"0": [13]}
            proofs = [c.ws.latest("reconnect_token")["reconnect_token"] for c in clients]
            def forbidden(*args, **kwargs):
                pytest.fail("Restart must not execute rules or rebuild map")
            with monkeypatch.context() as guard:
                guard.setattr(rules, "apply_cmd", forbidden)
                guard.setattr(rules, "build_game", forbidden)
                server.manager = server.RoomManager()
                fresh = Coordinator(coord.database)
                await fresh.initialize(server.manager)
            monkeypatch.setattr(server, "persistence", fresh)
            restored = server.manager.rooms[room.room_code]
            assert restored.game == room.game and restored.selected_map_data == source
            clients = [await connection(), await connection()]
            for pid, c in enumerate(clients):
                await server._dispatch(c, {"type": "reconnect", "room_code": restored.room_code, "reconnect_token": proofs[pid]})
                view = c.ws.latest("match_state")["state"]
                assert view["players"][0]["special_vp"] == bonus
                assert view["scenario"]["awarded_islands"] == {"0": [13]}
                assert "res" not in view["players"][1-pid] and "dev_cards" not in view["players"][1-pid]
                assert {"seed", "dev_deck", "bank", "ships_built_this_turn"}.isdisjoint(view)
            before = encode_snapshot(restored.game)
            await server._dispatch(clients[0], request)
            assert clients[0].ws.latest("cmd_ack")["duplicate"]
            assert encode_snapshot(restored.game) == before
            # Fixture finish isolates rematch reset without claiming a full game.
            candidate = clone_room(restored)
            candidate.game.players[0].vp = target
            candidate.game.game_over, candidate.game.winner_pid = True, 0
            await server._commit(restored, candidate, snapshot=True)
            old_match = restored.match_uuid
            await server._dispatch(clients[0], {"type": "rematch"})
            assert restored.match_uuid != old_match and restored.match_id == 2 and restored.tick == 0
            assert restored.ruleset_id == CURRENT_RULESET
            assert restored.game.scenario.awarded_islands == {}
            assert restored.game.scenario.home_islands == {0: set(), 1: set()}
            assert all(p.last_seq_applied == 0 for p in restored.players)
            assert all(c.ws.latest("match_state")["state"]["phase"] == "setup" for c in clients)
    asyncio.run(run())


def test_rejected_opening_and_failed_award_commit_preserve_durable_state(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await custom_pair(scenario_map())
            foreign = next(v for v in room.game.vertices if vertex_islands(room.game.board, v) == {13})
            before = await coord.repository.load(room.id)
            state = encode_snapshot(room.game)
            await server._dispatch(clients[0], command(room, clients[0], {"type": "place_settlement", "vid": foreign}))
            assert not clients[0].ws.latest("cmd_ack")["applied"]
            after = await coord.repository.load(room.id)
            assert after["head"] == before["head"] and encode_snapshot(room.game) == state
            assert after["receipts"][-1]["outcome"] == "rejected"
            await finish(room, clients, 4)
            destination = await reach(room, clients)
            before = await coord.repository.load(room.id)
            state = encode_snapshot(room.game)
            counts = [len(c.ws.messages) for c in clients]
            def fail(point):
                if point == "before_commit": raise OSError("synthetic commit failure")
            coord.repository._test_fault = fail
            with pytest.raises(PersistenceUnavailable):
                await execute(room, clients, {"type": "place_settlement", "vid": destination})
            coord.repository._test_fault = None
            assert encode_snapshot(room.game) == state
            unchanged_match(before, await coord.repository.load(room.id))
            assert [len(c.ws.messages) for c in clients] == counts
    asyncio.run(run())


@pytest.mark.parametrize("version", [1, 2])
def test_verified_s1_recovers_without_new_rules_and_advances_codec_without_reclassification(database_url, monkeypatch, version):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair(map_id="seafarers_gold_haven")
            proof = clients[0].ws.latest("reconnect_token")["reconnect_token"]
            restored, original = await legacy(coord, room, version=version, marker=LEGACY_S1_RULESET)
            assert not restricted(restored) and restored.game.scenario.rules == ScenarioRules()
            c = await connection()
            await server._dispatch(c, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            assert c.ws.latest("room_state")["ruleset_compatibility"]["status"] == "compatible"
            assert (await coord.repository.load(room.id))["head"] == original["head"]
            candidate = clone_room(restored)
            candidate.game.scenario.rules = ScenarioRules((4,), 0)
            with pytest.raises(RulesetCompatibilityError):
                await server._commit(restored, candidate, snapshot=True)
            await server._dispatch(c, command(restored, c, {"type": "noop"}))
            latest = await coord.repository.load(restored.id)
            assert latest["match"]["ruleset_id"] == LEGACY_S1_RULESET
            assert latest["head"]["snapshot_version"] == 4
            assert restore_room(latest).ruleset_id == LEGACY_S1_RULESET
    asyncio.run(run())


def test_real_websocket_rejects_foreign_opening_then_accepts_allowed_setup(live_server):
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            room, *_ = await start_pair(a, b)
            room.game = rules.build_game(17, 2, map_data=scenario_map())  # Explicit map fixture; transport stays real.
            foreign = next(v for v in room.game.vertices if vertex_islands(room.game.board, v) == {13})
            clients = [a, b]
            await reject(room, clients, 0, {"type": "place_settlement", "vid": foreign, "setup": True})
            vertex = board_legal_moves(room.game, 0)["settlements"][0]
            views = await accept(room, clients, 0, {"type": "place_settlement", "vid": vertex, "setup": True})
            assert room.game.scenario.home_islands[0] == {4}
            for view in views:
                assert view["state"]["scenario"]["home_islands"]["0"] == [4]
                assert view["state"]["players"][0]["special_vp"] == 0
    asyncio.run(run())


def test_s1_marker_with_new_scenario_state_is_restricted_but_ownership_inspection_survives(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await custom_pair(scenario_map())
            proof = clients[0].ws.latest("reconnect_token")["reconnect_token"]
            # Synthetic provenance mismatch; no production data is modified.
            async with coord.database.sessions() as session, session.begin():
                await session.execute(update(m.matches).where(m.matches.c.id == room.match_uuid).values(ruleset_id=LEGACY_S1_RULESET))
            original = await coord.repository.load(room.id)
            restored = restore_room(original)
            server.manager.rooms[room.room_code] = restored
            assert restricted(restored)
            c = await connection()
            await server._dispatch(c, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            assert server._owns(c, restored)
            assert c.ws.latest("room_state")["ruleset_compatibility"]["status"] == "compatibility_required"
            assert not any(msg["type"] == "match_state" for msg in c.ws.messages)
            with pytest.raises(rules.RuleError) as error:
                await server._dispatch(c, command(restored, c, {"type": "noop"}))
            assert error.value.code == "compatibility_required"
            unchanged_match(original, await coord.repository.load(room.id))
    asyncio.run(run())
