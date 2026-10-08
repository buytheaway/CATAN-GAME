"""Strategy C: durable provenance and non-mutating legacy restriction on real PG."""
import asyncio
from copy import deepcopy

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import update

from app import server_mp as server
from app.engine import RuleError
from app.match_rulesets import CURRENT_RULESET, RulesetCompatibilityError, restricted
from app.persistence import models as m
from app.persistence.coordinator import Coordinator
from app.persistence.recovery import checksum, clone_room, restore_room, resume_timer
from app.persistence.snapshots import encode_snapshot
from tests.test_auth import account, connection, http, auth_config
from tests.test_persistence_postgres import database_url, runtime, pair, prepare, command
from tests.test_private_publication_postgres import account_game


async def legacy(coord, room, *, version=2, marker=None):
    """Only synthetic test matches; never touches actual development player data."""
    head = (await coord.repository.load(room.id))["head"]
    payload = deepcopy(head["payload"])
    if version == 1:
        payload["engine"]["snapshot_version"] = 1
        del payload["engine"]["state"]["ships_built_this_turn"]
        del payload["engine"]["state"]["ship_moved_this_turn"]
    async with coord.database.sessions() as session, session.begin():
        await session.execute(update(m.matches).where(m.matches.c.id == room.match_uuid).values(ruleset_id=marker))
        await session.execute(update(m.game_snapshots).where(m.game_snapshots.c.id == head["id"]).values(
            payload=payload, checksum=checksum(payload), snapshot_version=version))
    bundle = await coord.repository.load(room.id)
    restored = restore_room(bundle)
    server.manager.rooms[room.room_code] = restored
    return restored, bundle


def unchanged_match(before, after):
    assert after["head"] == before["head"]
    assert after["match"] == before["match"]
    assert after["participants"] == before["participants"]
    assert after["receipts"] == before["receipts"]


@pytest.mark.parametrize("map_id", ["base_standard", "seafarers_gold_haven"])
def test_new_ruleset_is_durable_and_native_recovery_is_playable(database_url, monkeypatch, map_id):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair(map_id=map_id)
            proof = clients[0].ws.latest("reconnect_token")["reconnect_token"]
            bundle = await coord.repository.load(room.id)
            assert bundle["match"]["ruleset_id"] == CURRENT_RULESET
            assert "ruleset_id" not in bundle["head"]["payload"]["engine"]
            server.manager = server.RoomManager()
            fresh = Coordinator(coord.database)
            await fresh.initialize(server.manager)
            restored = server.manager.rooms[room.room_code]
            assert restored.ruleset_id == CURRENT_RULESET and not restricted(restored)
            client = await connection()
            await server._dispatch(client, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            assert client.ws.latest("match_state")["state"]["you_pid"] == 0
            await server._dispatch(client, command(restored, client, {"type": "noop"}))
            assert client.ws.latest("cmd_ack")["applied"]
            assert (await coord.repository.load(room.id))["match"]["ruleset_id"] == CURRENT_RULESET
    asyncio.run(run())


@pytest.mark.parametrize("version,marker", [(1, None), (2, None), (2, "future-unrecognized")])
@pytest.mark.parametrize("map_id", ["base_standard", "seafarers_gold_haven"])
def test_valid_legacy_recovers_without_rules_and_cannot_execute(database_url, monkeypatch, version, marker, map_id):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair(map_id=map_id, settings={"turn_timer": 30})
            proof = clients[0].ws.latest("reconnect_token")["reconnect_token"]
            await prepare(room)
            def forbidden(*args, **kwargs):
                pytest.fail("Legacy recovery/publication must not execute rules or legal probes")
            for name in ("apply_cmd", "build_game", "_legal_moves"):
                monkeypatch.setattr(server, name, forbidden)
            restored, original = await legacy(coord, room, version=version, marker=marker)
            assert restricted(restored) and restored.status == "in_match" and not restored.persistence_blocked
            assert restored.ruleset_id == marker
            state = encode_snapshot(restored.game)
            client = await connection()
            await server._dispatch(client, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            assert server._owns(client, restored)
            assert restored.timer_paused and not resume_timer(restored)
            assert client.ws.latest("room_state")["ruleset_compatibility"]["status"] == "compatibility_required"
            assert not any(msg["type"] == "match_state" for msg in client.ws.messages)
            for action in ({"type": "roll"}, {"type": "noop"}, {"type": "place_road", "edge": [0, 1]},
                           {"type": "play_dev", "card": "road_building"}, {"type": "test_action", "action": "grant_resources"}):
                with pytest.raises(RuleError, match="older or unverified") as exc:
                    await server._dispatch(client, command(restored, client, action))
                assert exc.value.code == "compatibility_required"
                assert server._apply_cmd(restored, 0, action)["code"] == "compatibility_required"
            for kind in ("start_match", "rematch", "set_settings", "enable_test_mode"):
                with pytest.raises(RuleError) as exc:
                    await server._dispatch(client, {"type": kind})
                assert exc.value.code == "compatibility_required"
            with pytest.raises(RuleError):
                server._start_match(restored)
            with pytest.raises(RuleError):
                server._snapshot_state(restored.game, restored, 0)
            await server._send_match_state(restored)
            assert not any(msg["type"] == "match_state" for msg in client.ws.messages)
            await server._process_room_timer(restored)
            # Suppression is independent of the ordinary recovery pause flag.
            restored.timer_paused = False
            restored.timer.deadline = 0
            before_timer = deepcopy(restored.timer)
            await server._process_room_timer(restored)
            server._sync_timer(restored)
            assert restored.timer == before_timer and not resume_timer(restored)
            assert encode_snapshot(restored.game) == state
            unchanged_match(original, await coord.repository.load(room.id))
            assert restored.players[0].last_seq_applied == 0
    asyncio.run(run())


@pytest.mark.parametrize("change", ["snapshot", "receipt", "game", "marker", "rematch"])
def test_commit_gate_cannot_rewrite_legacy(database_url, monkeypatch, change):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, _ = await pair()
            restored, original = await legacy(coord, room)
            candidate, kwargs = clone_room(restored), {}
            if change == "snapshot": kwargs["snapshot"] = True
            elif change == "receipt": kwargs["receipt"] = {"outcome": "rejected"}
            elif change == "game": candidate.game.players[0].vp += 2
            elif change == "marker": candidate.ruleset_id = CURRENT_RULESET
            else: candidate.match_uuid = __import__("uuid").uuid4()
            with pytest.raises(RulesetCompatibilityError):
                await coord.commit(restored, candidate, **kwargs)
            unchanged_match(original, await coord.repository.load(room.id))
    asyncio.run(run())


def test_guest_takeover_inspection_and_new_room_preserve_legacy(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, old = await pair()
            proof = room.players[0].reconnect_token
            restored, original = await legacy(coord, room)
            first, second = await connection(), await connection()
            for c in (first, second):
                await server._dispatch(c, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            assert not server._owns(first, restored) and server._owns(second, restored)
            results = await coord.repository.inspect_credentials(server.manager, [(room.room_code, proof)])
            assert results[0]["game"]["ruleset_compatibility"]["status"] == "compatibility_required"
            assert results[0]["game"]["can_continue"]
            assert not {"res", "dev_cards", "seed"}.intersection(results[0]["game"])
            await server._dispatch(second, {"type": "leave_room"})
            await server._dispatch(second, {"type": "create_room", "name": "New Alice", "max_players": 2})
            other = await connection()
            await server._dispatch(other, {"type": "join_room", "name": "New Bob", "room_code": second.room_code})
            await server._dispatch(second, {"type": "start_match"})
            fresh = server.manager.rooms[second.room_code]
            assert fresh.room_code != restored.room_code and fresh.ruleset_id == CURRENT_RULESET
            assert second.ws.latest("match_state")["room_code"] == fresh.room_code
            unchanged_match(original, await coord.repository.load(room.id))
    asyncio.run(run())


def test_account_continue_and_guest_claim_remain_safe_for_legacy(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, (owner, guest), raw, who = await account_game(coord)
            proof = room.players[1].reconnect_token
            restored, original = await legacy(coord, room)
            a, b = await connection(who), await connection(who)
            for c in (a, b):
                await server._dispatch(c, {"type": "account_continue", "room_code": room.room_code})
            assert a.ws.closed == 4409 and server._owns(b, restored)
            assert not any(x["type"] == "match_state" for c in (a, b) for x in c.ws.messages)
            status, result, _ = await http("/api/games/active", cookie=raw)
            assert status == 200 and next(x for x in result["games"] if x["room_code"] == room.room_code)["ruleset_compatibility"]["status"] == "compatibility_required"
            new_raw, new_who = await account(coord, "Claimed")
            status, _, _ = await http("/api/games/claim", {"room_code": room.room_code, "reconnect_token": proof}, cookie=new_raw)
            assert status == 200
            claimed = await connection(new_who)
            await server._dispatch(claimed, {"type": "account_continue", "room_code": room.room_code})
            assert server._owns(claimed, restored) and claimed.pid == 1
            denied = await connection()
            with pytest.raises(RuleError) as exc:
                await server._dispatch(denied, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            assert exc.value.code == "forbidden"
            unchanged_match(original, await coord.repository.load(room.id))
    asyncio.run(run())


def test_finished_historical_results_and_snapshot_are_not_rewritten(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, _ = await pair()
            candidate = clone_room(room)
            candidate.game.game_over, candidate.game.winner_pid = True, 0
            candidate.game.players[0].vp = 10
            await server._commit(room, candidate, snapshot=True)
            proof = room.players[0].reconnect_token
            restored, original = await legacy(coord, room, version=1)
            client = await connection()
            await server._dispatch(client, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            with pytest.raises(RuleError) as exc:
                await server._dispatch(client, {"type": "rematch"})
            assert exc.value.code == "compatibility_required"
            summary = (await coord.repository.inspect_credentials(server.manager, [(room.room_code, proof)]))[0]["game"]
            assert summary["status"] == "game_over" and summary["winner"]["name"] == "Alice"
            assert restored.game.game_over and restored.game.players[0].vp == 10
            unchanged_match(original, await coord.repository.load(room.id))
    asyncio.run(run())


def test_additive_migration_preserves_heads_and_does_not_backfill(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, _ = await pair()
            original = await coord.repository.load(room.id)
            config = Config("alembic.ini")
            def old_schema(conn):
                config.attributes["connection"] = conn
                alembic_command.downgrade(config, "f1a001")
            async with coord.database.engine.begin() as conn:
                await conn.run_sync(old_schema)
            await coord.database.migrate()
            bundle = await coord.repository.load(room.id)
            assert bundle["match"]["ruleset_id"] is None
            expected = deepcopy(original)
            expected["match"]["ruleset_id"] = None
            assert bundle == expected
            assert restricted(restore_room(bundle))
            await coord.database.migrate()  # Idempotent; never marks existing v2 heads current.
            assert await coord.repository.load(room.id) == bundle
    asyncio.run(run())
