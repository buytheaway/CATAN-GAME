"""Internal engine/real PG acceptance; public WS fog stays disabled throughout.

The thin in-process driver supplies explicit trusted opt-ins, never patches the
public gate, and uses real ownership/lock/candidate/Coordinator/Repository paths.
It is not a playable network fog transport or a claim of frontend acceptance.
"""
import asyncio
from copy import deepcopy
from datetime import timedelta
import uuid

import pytest
from sqlalchemy import select

from app import server_mp as server, game_events
from app.engine import rules, maps
from app.engine import exploration
from app.match_rulesets import CURRENT_RULESET, RulesetCompatibilityError, restricted
from app.persistence import models as m
from app.persistence.coordinator import Coordinator
from app.persistence.credentials import utcnow
from app.persistence.errors import PersistenceUnavailable
from app.persistence.recovery import checksum, clone_room, restore_room, resume_timer
from tests.test_auth import connection
from tests.test_fog_foundation import fog_recipe
from tests.test_fog_exploration import exploration_game, anchor_and_fund, route_edge
from tests.test_match_rulesets import unchanged_match
from tests.test_persistence_postgres import database_url, runtime, command


async def internal_room(coord, *, setup=False, kind="place_road", free=False, game=None):
    clients = [await connection(), await connection()]
    await server._dispatch(clients[0], {"type": "create_room", "name": "Alice", "max_players": 2})
    await server._dispatch(clients[1], {"type": "join_room", "name": "Bob", "room_code": clients[0].room_code})
    room = server.manager.rooms[clients[0].room_code]
    candidate = clone_room(room)
    candidate.game = deepcopy(game) if game is not None else exploration_game("gold", setup=setup)
    if setup:
        candidate.game.setup_idx, candidate.game.turn = 3, 0
    edge = route_edge(candidate.game, kind)
    anchor_and_fund(candidate.game, edge, kind=kind, setup=setup)
    if free:
        candidate.game.rolled = False
        candidate.game.players[0].dev_cards = [{"type": "road_building", "new": False}]
        rules.apply_cmd(candidate.game, 0, {"type": "play_dev", "card": "road_building"}, trusted_fog=True)
    candidate.game.map_id = "internal-exploration-fixture"
    for p, slot in zip(candidate.game.players, candidate.players):
        p.name = slot.name
        slot.match_player_id = uuid.uuid4()
    candidate.selected_map_id = candidate.game.map_id
    candidate.selected_map_data = fog_recipe()
    hidden = candidate.game.scenario.rules.fog.initially_hidden
    candidate.selected_map_data["fog_pool"] = {
        "terrain": [candidate.game.tiles[i].terrain for i in hidden],
        "numbers": [candidate.game.tiles[i].number for i in hidden if candidate.game.tiles[i].number is not None]}
    candidate.selected_map_data["rules"]["target_vp"] = candidate.game.rules_config.target_vp
    candidate.selected_map_meta = {"id": candidate.game.map_id, "name": candidate.game.map_name, "description": ""}
    candidate.selected_rules_config = vars(candidate.game.rules_config).copy()
    candidate.seed = candidate.game.seed
    candidate.match_id, candidate.match_uuid = 1, uuid.uuid4()
    candidate.ruleset_id, candidate.status = CURRENT_RULESET, "in_match"
    # Existing foundation permits trusted fixture creation from a lobby. Actual
    # public selection/start remains closed and is never used for fog here.
    await server._commit(room, candidate, snapshot=True)
    return room, clients, {"type": kind, "eid": edge, **({"free": True} if free else {})}


async def internal_command(coord, room, client, request):
    async with room.lock:
        if not server._owns(client, room):
            raise rules.RuleError("forbidden", "Current ownership required")
        assert request["room_code"] == room.room_code and request["match_id"] == room.match_id
        slot, seq, cmd_id = room.players[client.pid], request["seq"], request["cmd_id"]
        digest = checksum(request["cmd"])
        known = await coord.repository.receipt(slot.match_player_id, seq, cmd_id)
        if seq <= slot.last_seq_applied or cmd_id in slot.seen_cmd_set:
            assert known is not None and bytes(known["payload_hash"]) == digest
            return {"duplicate": True, "outcome": known["outcome"]}
        assert seq == slot.last_seq_applied + 1
        candidate = clone_room(room)
        before = game_events.resources_before(candidate.game)
        error = None
        try:
            _, events = rules.apply_cmd(candidate.game, client.pid, request["cmd"], trusted_fog=True)
        except rules.RuleError as exc:
            error, candidate = exc.code, clone_room(room)
        else:
            game_events.committed(candidate, client.pid, request["cmd"], events, before,
                                  room.game.robber_tile, room.game.pirate_tile)
            candidate.tick += 1
        player = candidate.players[client.pid]
        player.last_seq_applied = seq
        server._remember_cmd_id(player, cmd_id)
        receipt = {"match_player_id": player.match_player_id, "seq": seq, "cmd_id": cmd_id,
                   "payload_hash": digest, "outcome": "rejected" if error else "accepted", "error_code": error}
        await coord.commit(room, candidate, snapshot=not error, receipt=receipt, trusted_fog=True)
        server._promote(room, candidate)
        return {"duplicate": False, "outcome": receipt["outcome"]}


async def restart_and_reconnect(coord, room, client, monkeypatch):
    proof = client.ws.latest("reconnect_token")["reconnect_token"]
    recorded = deepcopy(room.game)
    def forbidden(*args, **kwargs):
        pytest.fail("Normal recovery must not execute exploration, reward, rules or RNG")
    with monkeypatch.context() as guard:
        for name in ("build_game", "apply_cmd", "check_win", "update_longest_road", "update_largest_army"):
            guard.setattr(rules, name, forbidden)
        guard.setattr(exploration, "discover_route", forbidden)
        guard.setattr(exploration, "record_gold_reward", forbidden)
        guard.setattr(maps.random, "SystemRandom", forbidden)
        server.manager = server.RoomManager()
        fresh = Coordinator(coord.database)
        await fresh.initialize(server.manager)
    monkeypatch.setattr(server, "persistence", fresh)
    restored = server.manager.rooms[room.room_code]
    # For unresolved COMMIT, recorded may be the previous RAM state. The DB is
    # authoritative; callers compare to the independently loaded durable head.
    owner = await connection()
    await server._dispatch(owner, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
    assert server._owns(owner, restored) and restricted(restored) and not resume_timer(restored)
    assert not any(msg["type"] == "match_state" for msg in owner.ws.messages)
    return fresh, restored, owner, recorded


@pytest.mark.parametrize("setup,kind,free", [
    (True, "place_road", False), (True, "build_ship", False),
    (False, "place_road", False), (False, "build_ship", False), (False, "place_road", True)])
def test_real_pending_gold_commit_restart_reconnect_and_continuation(database_url, monkeypatch, setup, kind, free):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients, route = await internal_room(coord, setup=setup, kind=kind, free=free)
            request = command(room, clients[0], route)
            await internal_command(coord, room, clients[0], request)
            bundle = await coord.repository.load(room.id)
            assert bundle["head"]["snapshot_version"] == 4 and bundle["head"]["engine_compatibility"] == 3
            assert bundle["receipts"][0]["outcome"] == "accepted" and room.game.pending_gold
            expected = deepcopy(room.game)
            assert restore_room(bundle).game == expected
            # Another connection can lock the durable row while Gold awaits user
            # input: there is no transaction kept open for the continuation.
            async with coord.database.sessions() as session, session.begin():
                assert (await session.execute(select(m.rooms.c.id).where(m.rooms.c.id == room.id)
                                               .with_for_update(nowait=True))).scalar_one() == room.id
            coord, restored, owner, _ = await restart_and_reconnect(coord, room, clients[0], monkeypatch)
            assert restored.game == expected
            await internal_command(coord, restored, owner, request)
            assert restored.game == expected  # Lost ACK/replayed route gives no second reward.
            count = restored.game.pending_gold[0]
            for remaining in range(count, 0, -1):
                choice = command(restored, owner, {"type": "choose_gold", "res": "ore"})
                await internal_command(coord, restored, owner, choice)
                assert restore_room(await coord.repository.load(room.id)).game == restored.game
                if remaining > 1:
                    coord, restored, owner, _ = await restart_and_reconnect(coord, restored, owner, monkeypatch)
            assert restored.game.pending_action is None and restored.game.scenario.fog.continuation is None
            assert restored.game.players[0].res["ore"] == count
            assert all(d.reward_status == "awarded" for d in restored.game.scenario.fog.discoveries)
            if setup:
                assert restored.game.phase == "main" and restored.game.setup_idx == 4
            if free:
                assert restored.game.free_roads[0] == 1 and not restored.game.rolled
            if kind == "build_ship" and not setup:
                assert tuple(route["eid"]) in restored.game.ships_built_this_turn
            before = await coord.repository.load(restored.id)
            for public in (route, {"type": "choose_gold", "res": "ore", "trusted_fog": True}, {"type": "noop"}):
                with pytest.raises(rules.RuleError) as error:
                    await server._dispatch(owner, command(restored, owner, public))
                assert error.value.code == "feature_disabled"
            await server._send_match_state(restored)
            assert not any(msg["type"] == "match_state" for msg in owner.ws.messages)
            unchanged_match(before, await coord.repository.load(restored.id))
    asyncio.run(run())


@pytest.mark.parametrize("stage", ["before_write", "before_commit", "after_commit", "unresolved_commit"])
def test_commit_failure_or_uncertainty_and_same_command_retry_never_duplicate_discovery(database_url, monkeypatch, stage):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients, route = await internal_room(coord)
            request = command(room, clients[0], route)
            before, domain = await coord.repository.load(room.id), deepcopy(room.game)
            messages = [len(c.ws.messages) for c in clients]
            def fault(point):
                if point == ("after_commit" if stage == "unresolved_commit" else stage):
                    raise OSError("synthetic isolated transaction failure")
            coord.repository._test_fault = fault
            with monkeypatch.context() as guard:
                if stage == "unresolved_commit":
                    async def unavailable(*args, **kwargs): raise OSError("synthetic resolution outage")
                    guard.setattr(coord.repository, "load", unavailable)
                if stage == "after_commit":
                    await internal_command(coord, room, clients[0], request)
                else:
                    with pytest.raises(PersistenceUnavailable):
                        await internal_command(coord, room, clients[0], request)
                    assert room.game == domain and room.persistence_blocked and not coord.ready
            coord.repository._test_fault = None
            assert [len(c.ws.messages) for c in clients] == messages  # No pre-COMMIT ACK or state publication.
            after = await coord.repository.load(room.id)
            committed = stage in ("after_commit", "unresolved_commit")
            if committed:
                assert after["head"] != before["head"] and len(after["receipts"]) == 1
            else:
                unchanged_match(before, after)
            coord, restored, owner, _ = await restart_and_reconnect(coord, room, clients[0], monkeypatch)
            expected = restore_room(after).game
            assert restored.game == expected
            result = await internal_command(coord, restored, owner, request)
            assert result["duplicate"] == committed
            gold = restored.game.pending_gold[0]
            choice = command(restored, owner, {"type": "choose_gold", "res": "ore", "qty": gold})
            await internal_command(coord, restored, owner, choice)
            done = deepcopy(restored.game)
            coord, restored, owner, _ = await restart_and_reconnect(coord, restored, owner, monkeypatch)
            assert (await internal_command(coord, restored, owner, choice))["duplicate"]
            assert restored.game == done and restored.game.players[0].res["ore"] == gold
            assert len((await coord.repository.load(restored.id))["receipts"]) == 2
    asyncio.run(run())


def test_concurrent_duplicate_and_final_rejection_use_real_durable_receipts(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients, route = await internal_room(coord)
            initial = deepcopy(room.game)
            bad = command(room, clients[0], {"type": "place_road", "eid": [9998, 9999]})
            assert (await internal_command(coord, room, clients[0], bad))["outcome"] == "rejected"
            assert room.game == initial and not room.game_events
            assert (await internal_command(coord, room, clients[0], bad))["duplicate"]
            request = command(room, clients[0], route)
            results = await asyncio.gather(*(internal_command(coord, room, clients[0], request) for _ in range(2)))
            assert sum(not r["duplicate"] for r in results) == 1
            assert len(room.game.scenario.fog.discoveries) == room.game.pending_gold[0]
            accepted_events = deepcopy(room.game_events)
            assert [e["type"] for e in accepted_events] == ["place_road"] + ["discover_tile"] * len(room.game.scenario.fog.discoveries)
            assert room.tick == 1
            bundle = await coord.repository.load(room.id)
            assert [r["outcome"] for r in sorted(bundle["receipts"], key=lambda r: r["seq"])] == ["rejected", "accepted"]
            before = deepcopy(room.game)
            invalid = command(room, clients[0], {"type": "choose_gold", "res": "gold"})
            assert (await internal_command(coord, room, clients[0], invalid))["outcome"] == "rejected"
            assert room.game == before and room.game_events == accepted_events
            assert restore_room(await coord.repository.load(room.id)).game == before
    asyncio.run(run())


@pytest.mark.parametrize("marker", [None, "unknown", "catan-seafarers-s1", "catan-seafarers-s2b-1"])
def test_trusted_opt_in_cannot_weaken_unknown_ruleset_or_change_provenance(marker):
    # Test the public commit fence without a database write or a backfill.
    from app.match_rulesets import validate_transition
    g = exploration_game()
    before = server.Room("FOGPROVENANCE", 2, 0, [server.PlayerSlot(i, f"P{i}") for i in range(2)],
                         game=g, ruleset_id=marker, match_uuid=uuid.uuid4(), match_id=1)
    candidate = clone_room(before)
    candidate.tick += 1
    with pytest.raises(RulesetCompatibilityError):
        validate_transition(before, candidate, snapshot=True, trusted_fog=True)
    candidate.ruleset_id = CURRENT_RULESET
    with pytest.raises(RulesetCompatibilityError):
        validate_transition(before, candidate, snapshot=True, trusted_fog=True)


@pytest.mark.parametrize("change", ["assignment", "new_epoch", "rematch", "finished_result", "status", "timer"])
def test_trusted_commit_preserves_assignment_epoch_and_historical_result_fences(change):
    from app.match_rulesets import validate_transition
    g = exploration_game()
    before = server.Room("FOGTRANSITION", 2, 0, [server.PlayerSlot(i, f"P{i}") for i in range(2)],
                         game=g, ruleset_id=CURRENT_RULESET, match_uuid=uuid.uuid4(), match_id=1)
    candidate = clone_room(before)
    operation = None
    if change == "assignment":
        tile = candidate.game.tiles[candidate.game.scenario.rules.fog.initially_hidden[0]]
        tile.number = 8
        from dataclasses import replace
        candidate.game.scenario.fog = replace(candidate.game.scenario.fog,
            assignment_digest=exploration.assignment_digest(candidate.game.board))
    elif change == "new_epoch": candidate.match_uuid = uuid.uuid4()
    elif change == "rematch": operation = {"kind": "rematch"}
    elif change == "status": candidate.status = "closed"
    elif change == "timer": candidate.timer_paused = not before.timer_paused
    else:
        before.game.game_over, before.game.winner_pid = True, 0
        candidate = clone_room(before)
        candidate.game.players[0].vp += 2
    with pytest.raises(RulesetCompatibilityError):
        validate_transition(before, candidate, snapshot=True, operation=operation, trusted_fog=True)


@pytest.mark.parametrize("credential", ["expired", "revoked", "takeover"])
def test_invalid_or_replaced_socket_cannot_drive_internal_fixture_or_get_private_state(database_url, monkeypatch, credential):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients, route = await internal_room(coord)
            before = await coord.repository.load(room.id)
            request = command(room, clients[0], route)
            other = None
            if credential == "expired":
                room.players[0].token_expires_at = utcnow() - timedelta(seconds=1)
            elif credential == "revoked":
                room.players[0].token_revoked_at = utcnow()
            else:
                proof = clients[0].ws.latest("reconnect_token")["reconnect_token"]
                other = await connection()
                await server._dispatch(other, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
                assert not server._owns(clients[0], room) and server._owns(other, room)
            with pytest.raises(rules.RuleError) as error:
                await internal_command(coord, room, clients[0], request)
            assert error.value.code == "forbidden"
            await server._send_match_state(room)
            assert not any(m["type"] == "match_state" for c in clients for m in c.ws.messages)
            if other:
                assert not any(m["type"] == "match_state" for m in other.ws.messages)
            unchanged_match(before, await coord.repository.load(room.id))
    asyncio.run(run())
