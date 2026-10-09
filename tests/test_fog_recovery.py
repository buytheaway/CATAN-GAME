"""Real PostgreSQL preserves trusted fog, but cannot activate incomplete gameplay."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import uuid

import pytest
from sqlalchemy import update

from app import server_mp as server
from app.engine import rules
from app.match_rulesets import (CURRENT_RULESET, LEGACY_S2B1_RULESET, RulesetCompatibilityError, restricted)
from app.persistence.coordinator import Coordinator
from app.persistence import models as m
from app.persistence.recovery import clone_room, resume_timer, restore_room
from tests.test_auth import account, auth_config, connection, http
from tests.test_fog_foundation import fog_recipe, recorded_fog
from tests.test_match_rulesets import legacy, unchanged_match
from tests.test_persistence_postgres import database_url, runtime, pair, command


async def trusted_room(*, pending=False, who=None):
    a, b = await connection(who), await connection()
    await server._dispatch(a, {"type": "create_room", "name": "Alice", "max_players": 2})
    await server._dispatch(b, {"type": "join_room", "name": "Bob", "room_code": a.room_code})
    room = server.manager.rooms[a.room_code]
    candidate = clone_room(room)
    candidate.game = recorded_fog(pending=pending)
    candidate.game.map_id = "trusted-fog-fixture"
    for p, slot in zip(candidate.game.players, candidate.players): p.name = slot.name
    candidate.selected_map_id = candidate.game.map_id
    candidate.selected_map_data = fog_recipe()
    candidate.selected_map_meta = {"id": candidate.game.map_id, "name": "Fog fixture", "description": ""}
    candidate.selected_rules_config = vars(candidate.game.rules_config).copy()
    candidate.seed = candidate.game.seed
    candidate.match_id, candidate.match_uuid = 1, uuid.uuid4()
    candidate.ruleset_id, candidate.status = CURRENT_RULESET, "in_match"
    for slot in candidate.players: slot.match_player_id = uuid.uuid4()
    await server._commit(room, candidate, snapshot=True)
    return room, (a, b)


@pytest.mark.parametrize("pending", [False, True])
def test_trusted_fog_restart_preserves_assignments_and_choices_but_stays_disabled(database_url, monkeypatch, pending):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await trusted_room(pending=pending)
            proof = clients[0].ws.latest("reconnect_token")["reconnect_token"]
            before = await coord.repository.load(room.id)
            assert (before["head"]["snapshot_version"], before["head"]["engine_compatibility"]) == (4, 3)
            def forbidden(*args, **kwargs): pytest.fail("Recovery must not execute gameplay or regenerate fog")
            with monkeypatch.context() as guard:
                for name in ("build_game", "apply_cmd", "check_win", "update_longest_road", "update_largest_army"):
                    guard.setattr(rules, name, forbidden)
                server.manager = server.RoomManager()
                fresh = Coordinator(coord.database)
                await fresh.initialize(server.manager)
            monkeypatch.setattr(server, "persistence", fresh)
            restored = server.manager.rooms[room.room_code]
            assert restored.game == room.game and restored.ruleset_id == CURRENT_RULESET
            assert restricted(restored) and not restored.persistence_blocked and not resume_timer(restored)
            unchanged_match(before, await fresh.repository.load(room.id))
            a, takeover = await connection(), await connection()
            for c in (a, takeover):
                await server._dispatch(c, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
                assert c.ws.latest("room_state")["ruleset_compatibility"]["status"] == "compatibility_required"
                assert not any(m["type"] == "match_state" for m in c.ws.messages)
            assert not server._owns(a, restored) and server._owns(takeover, restored)
            with pytest.raises(rules.RuleError) as error:
                await server._dispatch(takeover, command(restored, takeover, {"type": "noop"}))
            assert error.value.code == "feature_disabled"
            await server._process_room_timer(restored)
            for kwargs in ({"snapshot": True}, {"receipt": {"outcome": "rejected"}}):
                with pytest.raises(RulesetCompatibilityError):
                    await fresh.commit(restored, clone_room(restored), **kwargs)
            unchanged_match(before, await fresh.repository.load(room.id))
            assert restored.game == room.game and restored.players[0].last_seq_applied == 0
    asyncio.run(run())


def test_account_continue_inspection_and_new_match_do_not_expose_or_overwrite_fog(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            raw, who = await account(coord, "FogOwner")
            room, _ = await trusted_room(who=who)
            before = await coord.repository.load(room.id)
            owner, takeover = await connection(who), await connection(who)
            for c in (owner, takeover):
                await server._dispatch(c, {"type": "account_continue", "room_code": room.room_code})
                assert not any(m["type"] == "match_state" for m in c.ws.messages)
            assert owner.ws.closed == 4409 and server._owns(takeover, room)
            status, data, _ = await http("/api/games/active", cookie=raw)
            assert status == 200
            saved = next(g for g in data["games"] if g["room_code"] == room.room_code)
            assert saved["ruleset_compatibility"]["status"] == "compatibility_required"
            assert {"board", "tiles", "fog", "seed", "res", "dev_cards"}.isdisjoint(saved)
            await server._dispatch(takeover, {"type": "leave_room"})
            await server._dispatch(takeover, {"type": "create_room", "name": "New game", "max_players": 2})
            other = await connection()
            await server._dispatch(other, {"type": "join_room", "name": "New Bob", "room_code": takeover.room_code})
            await server._dispatch(takeover, {"type": "start_match"})
            new = server.manager.rooms[takeover.room_code]
            assert new.game.scenario.fog is None and new.ruleset_id == CURRENT_RULESET
            assert takeover.ws.latest("match_state")["room_code"] == new.room_code
            unchanged_match(before, await coord.repository.load(room.id))
    asyncio.run(run())


@pytest.mark.parametrize("map_id", ["base_standard", "seafarers_gold_haven"])
def test_verified_s2b1_v3_recovers_with_same_marker_and_advances_writer_without_conversion(database_url, monkeypatch, map_id):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair(map_id=map_id)
            proof = clients[0].ws.latest("reconnect_token")["reconnect_token"]
            restored, before = await legacy(coord, room, version=3, marker=LEGACY_S2B1_RULESET)
            assert restored.game.scenario.fog is None and not restricted(restored)
            client = await connection()
            await server._dispatch(client, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            assert client.ws.latest("match_state")["state"]["you_pid"] == 0
            assert (await coord.repository.load(room.id))["head"] == before["head"]
            await server._dispatch(client, command(restored, client, {"type": "noop"}))
            after = await coord.repository.load(room.id)
            assert after["match"]["ruleset_id"] == LEGACY_S2B1_RULESET and after["head"]["snapshot_version"] == 4
            assert restored.game.scenario.fog is None
            assert [p.vp for p in restored.game.players] == [p.vp for p in room.game.players]
    asyncio.run(run())


def test_wrong_marker_cannot_acquire_fog_or_rewrite_discovery_history(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, _ = await trusted_room()
            before = await coord.repository.load(room.id)
            candidate = clone_room(room)
            candidate.ruleset_id = LEGACY_S2B1_RULESET
            with pytest.raises(RulesetCompatibilityError): await coord.commit(room, candidate, snapshot=True)
            candidate = clone_room(room)
            candidate.game.scenario.fog = replace(candidate.game.scenario.fog, revealed=frozenset(), discoveries=())
            with pytest.raises(RulesetCompatibilityError): await coord.commit(room, candidate)
            unchanged_match(before, await coord.repository.load(room.id))
    asyncio.run(run())


@pytest.mark.parametrize("marker", [CURRENT_RULESET, LEGACY_S2B1_RULESET, None])
def test_valid_fog_storage_is_not_corruption_and_guest_claim_preserves_private_head(database_url, monkeypatch, marker):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await trusted_room()
            proof = clients[1].ws.latest("reconnect_token")["reconnect_token"]
            # Deliberate test-only provenance mismatch, never an automatic backfill.
            async with coord.database.sessions() as session, session.begin():
                await session.execute(update(m.matches).where(m.matches.c.id == room.match_uuid).values(ruleset_id=marker))
            before = await coord.repository.load(room.id)
            restored = restore_room(before)
            server.manager.rooms[room.room_code] = restored
            assert restricted(restored) and not restored.persistence_blocked and restored.game == room.game
            recent = await coord.repository.inspect_credentials(server.manager, [(room.room_code, proof)])
            assert recent[0]["game"]["ruleset_compatibility"]["status"] == "compatibility_required"
            assert {"tiles", "fog", "seed", "res", "dev_cards"}.isdisjoint(recent[0]["game"])
            raw, who = await account(coord, "Claim fog guest")
            status, _, _ = await http("/api/games/claim", {"room_code": room.room_code, "reconnect_token": proof}, cookie=raw)
            assert status == 200
            claimed = await connection(who)
            await server._dispatch(claimed, {"type": "account_continue", "room_code": room.room_code})
            assert claimed.pid == 1 and server._owns(claimed, restored)
            assert not any(msg["type"] == "match_state" for msg in claimed.ws.messages)
            invalid = await connection()
            with pytest.raises(rules.RuleError) as error:
                await server._dispatch(invalid, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            assert error.value.code == "forbidden"
            unchanged_match(before, await coord.repository.load(room.id))
    asyncio.run(run())
