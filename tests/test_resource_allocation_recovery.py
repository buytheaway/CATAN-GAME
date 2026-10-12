"""B1/B2 through real PostgreSQL commits, receipts and fresh hydration.

The shared database_url fixture only accepts an isolated *_test database.
No production database, snapshot or credential is inspected or rewritten.
"""
import asyncio
from copy import deepcopy

import pytest
from sqlalchemy import update

from app import server_mp as server
from app.engine import rules
from app.match_rulesets import CURRENT_RULESET, LEGACY_S1_RULESET, restricted
from app.persistence import models as m
from app.persistence.errors import PersistenceUnavailable
from app.persistence.recovery import restore_room
from app.persistence.snapshots import decode_snapshot, encode_snapshot
from tests.test_persistence_postgres import database_url, runtime, pair, prepare, command
from tests.test_persistence_snapshots import give_card
from tests.test_seafarers_recovery import hydrate, continue_room
from tests.test_seafarers_multiplayer import private_view, presentation
from tests.test_resource_allocation import FixedDraw, theft_game, sea_ring_shortage, totals


@pytest.fixture(autouse=True)
def local_options(monkeypatch):
    monkeypatch.setenv("CATAN_AUTH_MODE", "development")
    monkeypatch.setenv("CATAN_AUTH_ORIGINS", "http://test")
    monkeypatch.setattr(server, "_roll_dice", lambda: (1, 1))


def proofs(room):
    return [("guest", slot.reconnect_token) for slot in room.players]


def no_draw(stop):
    pytest.fail("Restoration/replay must not draw the accepted theft again")


@pytest.mark.parametrize("figure", ["robber", "pirate"])
def test_client_cannot_supply_theft_resource_result_or_seed(database_url, monkeypatch, figure):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            game, move = theft_game(figure)
            room, clients = await pair(names=("Alice", "Bob", "Carol"), map_id=game.map_id)
            await prepare(room, game)
            rng = FixedDraw(3)
            monkeypatch.setattr(rules, "_THEFT_RNG", rng)
            before, meta = deepcopy(room.game), presentation(room)
            for field, value in (("resource", "wood"), ("stolen", "wood"), ("seed", 17),
                                 ("random_result", 0), ("rng", 0), ("theft_rng", 0)):
                await server._dispatch(clients[0], command(room, clients[0], {**move, field: value}))
                assert not clients[0].ws.latest("cmd_ack")["applied"], field
                assert clients[0].ws.latest("error")["code"] == "invalid"
                assert room.game == before and presentation(room) == meta and not rng.stops
            await server._dispatch(clients[0], command(room, clients[0], move))
            assert clients[0].ws.latest("cmd_ack")["applied"]
            assert room.game.players[0].res["ore"] == 1 and rng.stops == [4]
    asyncio.run(run())


@pytest.mark.parametrize("figure", ["robber", "pirate"])
@pytest.mark.parametrize("trigger", ["seven", "knight"])
def test_weighted_theft_commits_before_ack_is_private_and_replays_once(
        database_url, monkeypatch, figure, trigger):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            game, move = theft_game(figure, "ready")
            if trigger == "knight":
                give_card(game, "knight")
            give_card(game, "victory_point", pid=1)
            room, clients = await pair(names=("Alice", "Bob", "Carol"), map_id=game.map_id)
            await prepare(room, game)
            credentials = proofs(room)
            monkeypatch.setattr(server, "_roll_dice", lambda: (3, 4))
            rng = FixedDraw(3)
            monkeypatch.setattr(rules, "_THEFT_RNG", rng)
            start = {"type": "play_dev", "card": "knight"} if trigger == "knight" else {"type": "roll"}
            await server._dispatch(clients[0], command(room, clients[0], start))
            assert clients[0].ws.latest("cmd_ack")["applied"]
            before = deepcopy(room.game)
            assert not rng.stops  # Legal probes never consume gameplay entropy.
            request = command(room, clients[0], move)
            send_ack = server._send_cmd_ack
            async def checked_ack(ws, *args, **kwargs):
                current = server.manager.rooms[room.room_code]
                bundle = await coord.repository.load(current.id)
                persisted = restore_room(bundle)
                assert persisted.game == current.game
                assert persisted.players[0].last_seq_applied == request["seq"]
                assert any(receipt["cmd_id"] == request["cmd_id"] for receipt in bundle["receipts"])
                await send_ack(ws, *args, **kwargs)
            monkeypatch.setattr(server, "_send_cmd_ack", checked_ack)
            # Identical concurrent submissions are serialized by the real room lock.
            await asyncio.gather(*(server._dispatch(clients[0], request) for _ in range(2)))
            acks = [msg for msg in clients[0].ws.messages
                    if msg["type"] == "cmd_ack" and msg["cmd_id"] == request["cmd_id"]]
            assert [ack["duplicate"] for ack in acks] == [False, True]
            assert [ack["applied"] for ack in acks] == [True, False]
            assert rng.stops == [4]
            assert room.game.players[0].res["ore"] == before.players[0].res["ore"] + 1
            assert room.game.players[1].res["ore"] == before.players[1].res["ore"] - 1
            assert totals(room.game) == totals(before)
            for pid, client in enumerate(clients):
                view = client.ws.latest("match_state")
                private_view(view, pid)
                theft = next(e for e in reversed(view["state"]["game_events"]) if e["type"] == "theft")
                if pid in (0, 1):
                    assert theft["resource"] == "ore"
                else:
                    assert "resource" not in theft
                    opponent = view["state"]["players"][1]
                    assert opponent["vp"] == room.game.players[1].vp - 1
            committed, meta = deepcopy(room.game), presentation(room)
            rng.randrange = no_draw
            fresh, restored = await hydrate(coord, room, monkeypatch)
            assert restored.game == committed and restored.ruleset_id == CURRENT_RULESET
            newcomers = await continue_room(fresh, restored, credentials)
            await server._dispatch(newcomers[0], request)
            ack = newcomers[0].ws.latest("cmd_ack")
            assert ack["duplicate"] and not ack["applied"]
            assert restored.game == committed
            assert (restored.tick, restored.event_serial) == (meta[0], meta[5])
    asyncio.run(run())


@pytest.mark.parametrize("figure", ["robber", "pirate"])
def test_lost_theft_ack_then_recovery_never_steals_again(database_url, monkeypatch, figure):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            game, move = theft_game(figure)
            room, clients = await pair(names=("Alice", "Bob", "Carol"), map_id=game.map_id)
            await prepare(room, game)
            credentials = proofs(room)
            rng = FixedDraw(3)
            monkeypatch.setattr(rules, "_THEFT_RNG", rng)
            request = command(room, clients[0], move)
            send_ack = server._send_cmd_ack
            async def lose_ack(*args, **kwargs):
                raise OSError("lost ACK after COMMIT")
            monkeypatch.setattr(server, "_send_cmd_ack", lose_ack)
            with pytest.raises(OSError, match="lost ACK"):
                await server._dispatch(clients[0], request)
            monkeypatch.setattr(server, "_send_cmd_ack", send_ack)
            assert rng.stops == [4]
            committed = deepcopy(room.game)
            rng.randrange = no_draw
            fresh, restored = await hydrate(coord, room, monkeypatch)
            newcomers = await continue_room(fresh, restored, credentials)
            await server._dispatch(newcomers[0], request)
            assert newcomers[0].ws.latest("cmd_ack")["duplicate"]
            assert restored.game == committed and restored.game.players[0].res["ore"] == 1
    asyncio.run(run())


@pytest.mark.parametrize("figure", ["robber", "pirate"])
def test_failed_transaction_does_not_publish_or_keep_a_theft(database_url, monkeypatch, figure):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            game, move = theft_game(figure)
            room, clients = await pair(names=("Alice", "Bob", "Carol"), map_id=game.map_id)
            await prepare(room, game)
            credentials = proofs(room)
            rng = FixedDraw(3)
            monkeypatch.setattr(rules, "_THEFT_RNG", rng)
            before, meta = deepcopy(room.game), presentation(room)
            counts = [len(client.ws.messages) for client in clients]
            request = command(room, clients[0], move)
            def fail(stage):
                if stage == "before_commit":
                    raise OSError("rollback before COMMIT")
            coord.repository._test_fault = fail
            with pytest.raises(PersistenceUnavailable):
                await server._dispatch(clients[0], request)
            assert room.game == before and presentation(room) == meta
            assert [len(client.ws.messages) for client in clients] == counts
            assert room.persistence_blocked and not coord.ready
            coord.repository._test_fault = None
            fresh, restored = await hydrate(coord, room, monkeypatch)
            assert restored.game == before
            newcomers = await continue_room(fresh, restored, credentials)
            await server._dispatch(newcomers[0], request)
            assert newcomers[0].ws.latest("cmd_ack")["applied"]
            assert restored.game.players[0].res["ore"] == 1
            assert restored.game.players[1].res["ore"] == 0
            assert totals(restored.game) == totals(before)
    asyncio.run(run())


def test_ambiguous_theft_commit_is_resolved_without_another_draw(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            game, move = theft_game()
            room, clients = await pair(names=("Alice", "Bob", "Carol"))
            await prepare(room, game)
            rng = FixedDraw(3)
            monkeypatch.setattr(rules, "_THEFT_RNG", rng)
            def fail(stage):
                if stage == "after_commit":
                    raise OSError("connection lost after COMMIT")
            coord.repository._test_fault = fail
            await server._dispatch(clients[0], command(room, clients[0], move))
            assert clients[0].ws.latest("cmd_ack")["applied"] and rng.stops == [4]
            coord.repository._test_fault = None
            assert restore_room(await coord.repository.load(room.id)).game == room.game
            assert room.game.players[0].res["ore"] == 1
    asyncio.run(run())


@pytest.mark.parametrize("recover_before_roll", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_sea_ring_shortage_is_identical_through_postgres_and_reconnect(
        database_url, monkeypatch, recover_before_roll, reverse):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair(map_id="seafarers_simple_2")
            game = sea_ring_shortage()
            if reverse:
                game.occupied_v = dict(reversed(list(game.occupied_v.items())))
            await prepare(room, game)
            credentials = proofs(room)
            before = deepcopy(room.game)
            if recover_before_roll:
                coord, room = await hydrate(coord, room, monkeypatch)
                clients = await continue_room(coord, room, credentials)
            await server._dispatch(clients[0], command(room, clients[0], {"type": "roll"}))
            assert clients[0].ws.latest("cmd_ack")["applied"]
            assert [p.res["wood"] for p in room.game.players] == [18, 0]
            assert room.game.bank["wood"] == 1 and totals(room.game) == totals(before)
            committed = deepcopy(room.game)
            def forbidden(*args, **kwargs):
                pytest.fail("Hydration cannot redistribute historical resources")
            monkeypatch.setattr(rules, "distribute_for_roll", forbidden)
            monkeypatch.setattr(rules, "_steal_one", forbidden)
            assert decode_snapshot(encode_snapshot(committed)) == committed
            _, restored = await hydrate(coord, room, monkeypatch)
            assert restored.game == committed and restored.ruleset_id == CURRENT_RULESET
    asyncio.run(run())


def test_verified_older_ruleset_keeps_provenance_and_hands_without_recalculation(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, _ = await pair(map_id="seafarers_simple_2")
            await prepare(room, sea_ring_shortage())
            recorded = deepcopy(room.game)
            async with coord.database.sessions() as session:
                await session.execute(update(m.matches).where(m.matches.c.id == room.match_uuid)
                                      .values(ruleset_id=LEGACY_S1_RULESET))
                await session.commit()
            def forbidden(*args, **kwargs):
                pytest.fail("Loading a verified old match cannot run corrected rules")
            monkeypatch.setattr(rules, "distribute_for_roll", forbidden)
            monkeypatch.setattr(rules, "_steal_one", forbidden)
            _, restored = await hydrate(coord, room, monkeypatch)
            assert restored.game == recorded and restored.ruleset_id == LEGACY_S1_RULESET
            assert not restricted(restored)
            assert (await coord.repository.load(room.id))["match"]["ruleset_id"] == LEGACY_S1_RULESET
    asyncio.run(run())
