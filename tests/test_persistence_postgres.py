"""Opt-in real PostgreSQL tests; never silently substitute SQLite.

Use CATAN_TEST_DATABASE_URL pointing to an explicitly isolated *_test database.
Only the migration test downgrades that disposable schema. Production URLs fail.
"""
import asyncio
import json
import os
import uuid
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import select, update, insert, func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app import server_mp as server
from app.engine import rules, get_preset_map
from app.persistence import models as m
from app.persistence.coordinator import Coordinator
from app.persistence.credentials import token_hash, utcnow, valid_token
from app.persistence.db import Database
from app.persistence.errors import PersistenceUnavailable
from app.persistence.recovery import clone_room, restore_room, resume_timer
from app.persistence.snapshots import encode_snapshot
from app.room_options import RoomSettings, TurnTimer
from tests.test_persistence_snapshots import build_case, seafarers_case, gold_game, assert_equivalent
from tests.test_pirate_lifecycle import finish_setup
from tests.test_multiplayer_basic import _find_free_port, _send, _recv_type, _recv_error, _recv_cmd_ack
import websockets

@pytest.fixture
def database_url():
    value = os.getenv("CATAN_TEST_DATABASE_URL")
    if not value:
        pytest.skip("Real PostgreSQL required: set CATAN_TEST_DATABASE_URL to an isolated *_test database")
    url = make_url(value)
    if url.drivername != "postgresql+psycopg" or not url.database.endswith("_test"):
        pytest.fail("Persistence tests require an explicitly isolated PostgreSQL *_test database")
    return value


class Socket:
    def __init__(self):
        self.messages = []

    async def send_text(self, raw):
        self.messages.append(json.loads(raw))

    def latest(self, kind):
        return next(msg for msg in reversed(self.messages) if msg["type"] == kind)


@asynccontextmanager
async def runtime(url, monkeypatch):
    db = Database(url)
    await db.migrate()
    coordinator = Coordinator(db)
    coordinator.ready = True
    coordinator.reserved_codes = set(await coordinator.repository.codes())
    monkeypatch.setattr(server, "manager", server.RoomManager())
    monkeypatch.setattr(server, "persistence", coordinator)
    try:
        yield coordinator
    finally:
        await db.close()


async def pair(capacity=4, settings=None, names=("Alice", "Bob"), map_id="base_standard"):
    clients = [server.ClientConn(Socket()) for _ in names]
    for c in clients:
        server.manager.connections[c.ws] = c
    await server._dispatch(clients[0], {"type": "create_room", "name": names[0], "max_players": capacity})
    code = clients[0].room_code
    if map_id != "base_standard":
        await server._dispatch(clients[0], {"type": "set_map", "map_id": map_id})
    await server._dispatch(clients[0], {"type": "set_settings", "settings": {
        "starting_player": "host", "bank_visibility": "hidden", **(settings or {})}})
    for c, name in zip(clients[1:], names[1:]):
        await server._dispatch(c, {"type": "join_room", "name": name, "room_code": code})
    room = server.manager.rooms[code]
    await server._dispatch(clients[0], {"type": "start_match", "request_id": str(uuid.uuid4()), "expected_match_id": 0})
    return room, clients


async def prepare(room, game=None):
    candidate = clone_room(room)
    if game is None:
        finish_setup(candidate.game)
    else:
        candidate.game = deepcopy(game)
        candidate.seed = game.seed
        candidate.selected_map_id = game.map_id
        candidate.selected_map_data = deepcopy(get_preset_map(game.map_id))
        for p, slot in zip(candidate.game.players, candidate.players):
            p.name = slot.name
    server._sync_timer(candidate)
    await server._commit(room, candidate, snapshot=True)


def command(room, client, cmd, *, cmd_id=None, seq=None):
    return {"type": "cmd", "room_code": room.room_code, "match_id": room.match_id,
            "seq": seq or room.players[client.pid].last_seq_applied + 1,
            "cmd_id": cmd_id or str(uuid.uuid4()), "cmd": cmd}


async def recovered(coord, room):
    return restore_room(await coord.repository.load(room.id))


def test_migrations_empty_upgrade_downgrade_and_reupgrade(database_url):
    async def run():
        db = Database(database_url)
        try:
            await db.migrate()
            await db.migrate("base")  # URL fixture refuses every non-disposable DB.
            async with db.sessions() as session:
                names = (await session.execute(select(func.to_regclass("public.rooms")))).scalar()
                assert names is None
            await db.migrate()
            async with db.sessions() as session:
                assert (await session.execute(select(func.to_regclass("public.command_receipts")))).scalar()
        finally:
            await db.close()
    asyncio.run(run())


def test_lobby_configuration_custom_source_members_colors_and_hash_only_tokens(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            a = server.ClientConn(Socket())
            server.manager.connections[a.ws] = a
            await server._dispatch(a, {"type": "create_room", "name": "Lobby", "max_players": 4})
            room = server.manager.rooms[a.room_code]
            raw = a.ws.latest("reconnect_token")["reconnect_token"]
            source = deepcopy(get_preset_map("seafarers_gold_haven"))
            await server._dispatch(a, {"type": "set_map", "map_id": "my-gold", "map_data": source})
            await server._dispatch(a, {"type": "set_color", "color": "white", "request_id": "color"})
            await server._dispatch(a, {"type": "set_settings", "settings": {"dice_mode": "balanced"}, "request_id": "settings"})
            b = server.ClientConn(Socket())
            server.manager.connections[b.ws] = b
            await server._dispatch(b, {"type": "join_room", "room_code": room.room_code, "name": "Peer"})
            bundle = await coord.repository.load(room.id)
            restored = restore_room(bundle)
            assert restored.status == "lobby" and len(restored.players) == 4
            assert restored.selected_map_id == "my-gold" and restored.selected_map_data == source
            assert restored.settings.dice_mode == "balanced" and restored.settings.target_vp is None
            assert restored.config_revision == room.config_revision and restored.map_revision == 1
            assert [(p.id, p.name, p.color) for p in restored.players[:2]] == [(p.id, p.name, p.color) for p in room.players[:2]]
            assert all(not p.connected and p.active_ws is None for p in restored.players)
            assert valid_token(restored.players[0], raw) and restored.players[0].reconnect_token is None
            assert raw not in str(bundle) and bundle["tokens"][room.players[0].id]["token_hash"] == token_hash(raw)
    asyncio.run(run())


@pytest.mark.parametrize("case", ["new", "mid_setup", "before_roll", "after_roll", "discard", "partly_discarded",
                                  "robber", "trade", "knight", "road_two", "road_one", "road_zero", "road_ended",
                                  "newly_bought", "hidden_vp", "game_over", "ship", "moved_ship", "pirate_pending", "gold"])
def test_full_private_state_survives_real_jsonb_and_continues(database_url, monkeypatch, case):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            game = gold_game() if case == "gold" else seafarers_case(case) if case in ("ship", "moved_ship", "pirate_pending") else build_case(case)
            names = tuple(f"Participant{i}" for i in range(game.max_players))
            room, clients = await pair(capacity=6, names=names, map_id=game.map_id)
            await prepare(room, game)
            restored = await recovered(coord, room)
            assert_equivalent(room.game, restored.game)
            assert room.seed == restored.seed and room.match_uuid == restored.match_uuid
            assert_equivalent(room.game.dev_deck, restored.game.dev_deck)
            own = server._snapshot_state(restored.game, restored, 0)
            assert "seed" not in own and "dev_deck" not in own and "bank" not in own
            assert "res" not in own["players"][1] and "dev_cards" not in own["players"][1]
            if case == "before_roll":
                await server._dispatch(clients[0], command(room, clients[0], {"type": "roll"}))
                assert (await recovered(coord, room)).game.rolled
            if case == "road_one":
                before_roads = dict(restored.game.occupied_e)
                rules.apply_cmd(restored.game, 0, {"type": "roll", "roll": 2})
                rules.apply_cmd(restored.game, 0, {"type": "end_turn"})
                assert restored.game.free_roads[0] == 0 and restored.game.occupied_e == before_roads
    asyncio.run(run())


def test_balanced_order_refresh_boundary_public_faces_and_rejected_roll(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair(settings={"dice_mode": "balanced"})
            await prepare(room)
            bag = [(a,b) for a in range(1,7) for b in range(1,7)]
            candidate = clone_room(room); candidate.dice_bag = bag[:13]
            await server._commit(room, candidate, snapshot=True)
            await server._dispatch(clients[0], command(room, clients[0], {"type": "roll"}))
            state = await recovered(coord, room)
            assert state.dice == bag[12] and state.dice_bag == bag[:12] and state.roll_count == 1
            assert state.dice_algorithm == "balanced_v1"
            before = deepcopy(room.game), list(room.dice_bag), room.dice, room.tick
            await server._dispatch(clients[0], command(room, clients[0], {"type": "roll"}))
            assert (room.game, room.dice_bag, room.dice, room.tick) == before
            assert (await recovered(coord, room)).dice_bag == bag[:12]
    asyncio.run(run())


@pytest.mark.parametrize("stage,seconds", [("turn",60),("grace",10),("turn",-100),("blocked",-100),("stopped",-100)])
def test_timer_recovery_pause_utc_grace_and_mandatory_stage(database_url, monkeypatch, stage, seconds):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, _ = await pair(settings={"turn_timer": 60})
            await prepare(room, build_case("road_two") if stage == "blocked" else None)
            candidate = clone_room(room)
            candidate.timer = TurnTimer.start(candidate.game.turn, seconds, server.time.monotonic(), server.time.time(), stage)
            await server._commit(room, candidate, snapshot=True)
            state = await recovered(coord, room)
            assert state.timer_paused and state.timer.stage == stage
            saved = encode_snapshot(state.game)
            server.manager.rooms[state.room_code] = state
            await server._process_room_timer(state)
            assert encode_snapshot(state.game) == saved  # No offline automatic commands.
            assert server._snapshot_state(state.game, state, 0)["turn_timer"]["paused"]
            assert resume_timer(state)
            assert not state.timer_paused
            if stage in ("turn", "grace"):
                assert state.timer.deadline - server.time.monotonic() >= 19.9
            else:
                assert state.timer.stage == stage and state.timer.deadline_ms == room.timer.deadline_ms
            assert state.game.free_roads == room.game.free_roads
    asyncio.run(run())


def test_chat_bounded_and_canonical_private_feed_projection_survive(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, _ = await pair()
            await prepare(room)
            candidate = clone_room(room)
            for i in range(57):
                candidate.players[0].chat_times.clear()  # Simulate separate rate windows, not bypass on wire.
                server._append_chat(candidate, 0, f"<text>{i}</text>")
            for i in range(87):
                server.game_events.record(candidate, "theft", 0, victim_pid=1, quantity=1,
                                          private={0:{"resource":"ore"},1:{"resource":"ore"}})
            candidate.tick += 1
            await server._commit(room, candidate, snapshot=True)
            state = await recovered(coord, room)
            assert len(state.chat_history) == 50 and state.chat_history == room.chat_history
            assert state.chat_revision == 57 and not state.players[0].chat_times
            assert len(state.game_events) == 80 and state.game_events == room.game_events
            assert set(state.game_events[-1]["_private"]) == {0,1}
            assert server.game_events.project(state,0)[-1]["resource"] == "ore"
            assert "resource" not in server.game_events.project(state,5)[-1]
            assert "_private" not in server.game_events.project(state,0)[-1]
    asyncio.run(run())


@pytest.mark.parametrize("point", ["before_write", "before_commit"])
def test_failed_write_discards_candidate_without_success_publication_or_ack(database_url, monkeypatch, point):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair(settings={"dice_mode":"balanced"})
            await prepare(room)
            before = deepcopy(room.game), list(room.dice_bag), room.tick, room.players[0].last_seq_applied
            count = len(clients[0].ws.messages)
            def fail(stage):
                if stage == point:
                    assert len(clients[0].ws.messages) == count  # COMMIT is the publication gate.
                    raise OSError("injected failure")
            coord.repository._test_fault = fail
            with pytest.raises(PersistenceUnavailable):
                await server._dispatch(clients[0], command(room, clients[0], {"type":"roll"}))
            assert (room.game, room.dice_bag, room.tick, room.players[0].last_seq_applied) == before
            assert len(clients[0].ws.messages) == count and room.persistence_blocked and not coord.ready
            coord.repository._test_fault = None
            state = await recovered(coord, room)
            assert_equivalent(before[0],state.game)
            assert state.tick == before[2] and state.players[0].last_seq_applied == 0
    asyncio.run(run())


@pytest.mark.parametrize("effect", ["roll", "theft", "dev"])
def test_commit_then_lost_ack_and_restart_retry_never_reexecutes_effect(database_url, monkeypatch, effect):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients = await pair(settings={"dice_mode":"balanced"})
            game = build_case("robber" if effect == "theft" else "monopoly_ready" if effect == "dev" else "before_roll")
            if effect == "theft":
                # Fund the fixture before re-entering the genuine pending movement state.
                pending = game.pending_action
                game.pending_action = None
                rules.apply_cmd(game,1,{"type":"grant_resources","res":{"wood":2}})
                game.pending_action = pending
                tile = next(t for t in range(len(game.tiles)) if t != game.robber_tile and 1 in rules._victims_for_tile(game,t,0))
                cmd = {"type":"move_robber","tile":tile,"victim":1}
            else:
                cmd = {"type":"play_dev","card":"monopoly","r":"wood"} if effect == "dev" else {"type":"roll"}
            await prepare(room,game)
            message = command(room,clients[0],cmd)
            original_send = server._send_cmd_ack
            async def lose_ack(*args,**kwargs):
                raise OSError("lost ACK after commit")
            monkeypatch.setattr(server,"_send_cmd_ack",lose_ack)
            with pytest.raises(OSError):
                await server._dispatch(clients[0],message)
            monkeypatch.setattr(server,"_send_cmd_ack",original_send)
            state = await recovered(coord,room)
            committed = deepcopy(state.game), list(state.dice_bag), state.tick, state.event_serial
            server.manager.rooms[state.room_code] = state
            new = server.ClientConn(Socket()); server.manager.connections[new.ws] = new
            await server._dispatch(new,{"type":"reconnect","room_code":state.room_code,"reconnect_token":clients[0].ws.latest("reconnect_token")["reconnect_token"]})
            await server._dispatch(new,message)
            ack = new.ws.latest("cmd_ack")
            assert ack["duplicate"] and not ack["applied"]
            assert (state.game,state.dice_bag,state.tick,state.event_serial) == committed
            assert new.ws.latest("match_state")["tick"] == committed[2]
    asyncio.run(run())


def test_ambiguous_commit_is_resolved_by_head_without_executing_again(database_url, monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients = await pair(settings={"dice_mode":"balanced"})
            await prepare(room)
            def fault(stage):
                if stage == "after_commit":
                    raise OSError("connection lost after durable commit")
            coord.repository._test_fault = fault
            await server._dispatch(clients[0],command(room,clients[0],{"type":"roll"}))
            assert room.roll_count == 1 and room.tick == 1 and len(room.dice_bag) == 35
            assert clients[0].ws.latest("cmd_ack")["applied"]
            coord.repository._test_fault = None
            assert (await recovered(coord,room)).dice_bag == room.dice_bag
    asyncio.run(run())


def test_ambiguous_commit_lookup_failure_fences_then_recovery_finds_receipt(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients = await pair(settings={"dice_mode":"balanced"})
            await prepare(room)
            before = deepcopy(room.game)
            request = command(room,clients[0],{"type":"roll"})
            def fault(stage):
                if stage == "after_commit": raise OSError("unknown outcome")
            original_load = coord.repository.load
            async def fail_read(*args): raise OSError("DB down")
            coord.repository._test_fault = fault
            coord.repository.load = fail_read
            with pytest.raises(PersistenceUnavailable): await server._dispatch(clients[0],request)
            assert room.game == before and room.persistence_blocked and room.roll_count == 0
            coord.repository.load = original_load; coord.repository._test_fault = None
            state = await coord.resolve(room); server._promote(room,state); coord.ready=True
            assert room.roll_count == 1 and room.players[0].last_seq_applied == 1
            await server._dispatch(clients[0],request)
            assert clients[0].ws.latest("cmd_ack")["duplicate"] and room.roll_count == 1
    asyncio.run(run())


@pytest.mark.parametrize("cmd", [{"type":"play_dev","card":"bogus"},{"type":"place_road","eid":[-1,999]},
                                 {"type":"roll","dice":[6,6]},{"type":"grant_resources","res":{"wood":1}}])
def test_rejection_consumes_sequence_only_and_remains_duplicate_after_recovery(database_url,monkeypatch,cmd):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients = await pair(); await prepare(room)
            before = deepcopy(room.game),room.tick
            msg=command(room,clients[0],cmd)
            await server._dispatch(clients[0],msg)
            state=await recovered(coord,room)
            assert (state.game,state.tick)==before and state.players[0].last_seq_applied==1
            assert not clients[0].ws.latest("cmd_ack")["applied"]
            receipt=await coord.repository.receipt(state.players[0].match_player_id,1,msg["cmd_id"])
            assert receipt["outcome"]=="rejected"
            server.manager.rooms[state.room_code]=state
            new=server.ClientConn(Socket()); server.manager.connections[new.ws]=new
            await server._dispatch(new,{"type":"reconnect","room_code":state.room_code,"reconnect_token":clients[0].ws.latest("reconnect_token")["reconnect_token"]})
            await server._dispatch(new,msg)
            assert new.ws.latest("cmd_ack")["duplicate"] and (state.game,state.tick)==before
    asyncio.run(run())


def test_rematch_compacts_identity_revokes_excluded_token_and_is_idempotent(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients=await pair(capacity=4,names=("Alice","Bob","Carol"))
            ids=[p.id for p in room.players]
            tokens=[c.ws.latest("reconnect_token")["reconnect_token"] for c in clients]
            first_match=room.match_uuid
            server.manager.leave_room(clients[0])
            request={"type":"rematch","request_id":"compact","expected_match_id":1}
            await server._dispatch(clients[1],request)
            assert room.host_pid==0 and room.match_id==2 and room.tick==0
            assert [p.id for p in room.players]==ids[1:] and room.game.max_players==2
            assert all(p.last_seq_applied==0 for p in room.players)
            second=room.match_uuid
            await server._dispatch(clients[1],request)
            assert room.match_uuid==second
            state=await recovered(coord,room)
            assert state.match_uuid==second and state.players[0].id==ids[1] and valid_token(state.players[0],tokens[1])
            assert not any(valid_token(p,tokens[0]) for p in state.players)
            async with coord.database.sessions() as session:
                assert (await session.execute(select(m.matches.c.status).where(m.matches.c.id==first_match))).scalar_one()=="superseded"
                assert (await session.execute(select(m.seat_tokens.c.revoked_at).where(m.seat_tokens.c.room_player_id==ids[0]))).scalar_one()
            with pytest.raises(rules.RuleError):
                await server._dispatch(clients[1],{**request,"request_id":"new-stale"})
    asyncio.run(run())


@pytest.mark.parametrize("credential", ["wrong","expired","revoked"])
def test_unusable_reconnect_cannot_steal_seat_or_renew_credential(database_url,monkeypatch,credential):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients=await pair()
            raw=clients[0].ws.latest("reconnect_token")["reconnect_token"]
            if credential!="wrong":
                async with coord.database.sessions() as session,session.begin():
                    patch={"expires_at":utcnow()-timedelta(seconds=1)} if credential=="expired" else {"revoked_at":utcnow()}
                    await session.execute(update(m.seat_tokens).where(m.seat_tokens.c.room_player_id==room.players[0].id).values(**patch))
            else: raw="not-a-token"
            state=await recovered(coord,room); server.manager.rooms[state.room_code]=state
            intruder=server.ClientConn(Socket());server.manager.connections[intruder.ws]=intruder
            with pytest.raises(rules.RuleError,match="Invalid reconnect token"):
                await server._dispatch(intruder,{"type":"reconnect","room_code":room.room_code,"reconnect_token":raw,"pid":0,"name":"Alice"})
            assert not state.players[0].connected and intruder.pid is None
    asyncio.run(run())


def test_unique_constraints_cross_room_foreign_keys_and_transaction_rollback(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,_=await pair(); other,_=await pair()
            async with coord.database.sessions() as session:
                with pytest.raises(IntegrityError):
                    async with session.begin():
                        await session.execute(update(m.rooms).where(m.rooms.c.id==room.id).values(room_code=other.room_code))
                assert (await session.execute(select(m.rooms.c.room_code).where(m.rooms.c.id==room.id))).scalar_one()==room.room_code
            async with coord.database.sessions() as session:
                with pytest.raises(IntegrityError):
                    async with session.begin():
                        await session.execute(update(m.rooms).where(m.rooms.c.id==room.id).values(host_room_player_id=other.players[0].id))
            async with coord.database.sessions() as session:
                with pytest.raises(IntegrityError):
                    async with session.begin():
                        await session.execute(update(m.room_players).where(m.room_players.c.id==room.players[1].id).values(color=room.players[0].color))
            assert (await recovered(coord,room)).host_pid==0
    asyncio.run(run())


def test_corrupt_latest_head_quarantines_without_rollback_and_healthy_room_recovers(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            bad,_=await pair(); await prepare(bad)
            good,_=await pair()
            bundle=await coord.repository.load(bad.id)
            async with coord.database.sessions() as session,session.begin():
                await session.execute(update(m.game_snapshots).where(m.game_snapshots.c.id==bundle["head"]["id"]).values(payload={"corrupt":True}))
            fresh=Coordinator(coord.database);manager=server.RoomManager()
            await fresh.initialize(manager)
            assert bad.room_code not in manager.rooms and bad.room_code in fresh.quarantined_codes
            assert good.room_code in manager.rooms and fresh.ready
            async with coord.database.sessions() as session:
                assert (await session.execute(select(m.rooms.c.status).where(m.rooms.c.id==bad.id))).scalar_one()=="quarantined"
            again=Coordinator(coord.database);await again.initialize(server.RoomManager())
            assert bad.room_code in again.quarantined_codes
    asyncio.run(run())


def test_closed_expired_abandoned_and_test_rooms_are_not_restored(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            closed,_=await pair(); await server.close_room(closed.room_code)
            test,_=await pair()
            candidate=clone_room(test);candidate.test_mode=True;await server._commit(test,candidate,snapshot=True)
            expired,_=await pair()
            abandoned,_=await pair()
            async with coord.database.sessions() as session,session.begin():
                await session.execute(update(m.rooms).where(m.rooms.c.id==expired.id).values(expires_at=utcnow()-timedelta(seconds=1)))
                await session.execute(update(m.rooms).where(m.rooms.c.id==abandoned.id).values(status="abandoned"))
            manager=server.RoomManager();fresh=Coordinator(coord.database);await fresh.initialize(manager)
            for room in (closed,test,expired,abandoned):assert room.room_code not in manager.rooms
            assert closed.room_code in fresh.reserved_codes
    asyncio.run(run())


def test_snapshot_and_receipt_history_are_bounded_and_old_seq_still_deduplicates(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients=await pair()
            first=command(room,clients[0],{"type":"noop"})
            await server._dispatch(clients[0],first)
            for _ in range(257):
                await server._dispatch(clients[0],command(room,clients[0],{"type":"noop"}))
            async with coord.database.sessions() as session:
                assert (await session.execute(select(func.count()).select_from(m.game_snapshots).where(m.game_snapshots.c.match_id==room.match_uuid))).scalar_one()==3
                assert (await session.execute(select(func.count()).select_from(m.command_receipts).where(m.command_receipts.c.match_player_id==room.players[0].match_player_id))).scalar_one()==256
            assert first["cmd_id"] not in room.players[0].seen_cmd_set
            tick=room.tick
            await server._dispatch(clients[0],first)
            assert room.tick==tick and clients[0].ws.latest("cmd_ack")["duplicate"]
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["join", "map", "settings", "color", "start", "rematch", "chat", "close"])
def test_lifecycle_failure_never_leaves_half_committed_room(database_url,monkeypatch,kind):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients=await pair(capacity=4)
            if kind in ("join","map","settings","color","start"):
                # A fresh genuine lobby is needed; do not turn an active match into a fake lobby.
                a=server.ClientConn(Socket());server.manager.connections[a.ws]=a
                await server._dispatch(a,{"type":"create_room","name":"Lifecycle host","max_players":4})
                room=server.manager.rooms[a.room_code]
                b=server.ClientConn(Socket());server.manager.connections[b.ws]=b
                await server._dispatch(b,{"type":"join_room","name":"Lifecycle peer","room_code":room.room_code})
                clients=[a,b]
            before=await coord.repository.load(room.id)
            public=deepcopy(server.net_protocol.room_state_message(room))
            message={
                "map":{"type":"set_map","map_id":"seafarers_gold_haven"},
                "settings":{"type":"set_settings","settings":{"dice_mode":"balanced"},"request_id":"fault-config"},
                "color":{"type":"set_color","color":"white","request_id":"fault-color"},
                "start":{"type":"start_match","request_id":"fault-start","expected_match_id":0},
                "rematch":{"type":"rematch","request_id":"fault-rematch","expected_match_id":1},
                "chat":{"type":"chat","text":"must not survive failed commit"},
                "join":{"type":"join_room","name":"Third","room_code":room.room_code},
            }.get(kind)
            actor=clients[0]
            if kind=="join":
                actor=server.ClientConn(Socket());server.manager.connections[actor.ws]=actor
            counts=[len(c.ws.messages) for c in clients]
            def fail(stage):
                if stage=="before_commit":raise OSError("injected lifecycle failure")
            coord.repository._test_fault=fail
            with pytest.raises(PersistenceUnavailable):
                if kind=="close":await server.close_room(room.room_code)
                else:await server._dispatch(actor,message)
            coord.repository._test_fault=None
            assert server.net_protocol.room_state_message(room)==public
            assert [len(c.ws.messages) for c in clients]==counts
            after=await coord.repository.load(room.id)
            assert after==before
    asyncio.run(run())


def test_gap_ownership_and_conflicting_payload_do_not_advance_durable_sequence(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients=await pair();await prepare(room)
            msg=command(room,clients[0],{"type":"roll"},seq=2)
            before=await coord.repository.load(room.id)
            with pytest.raises(rules.RuleError,match="Out of order"):
                await server._dispatch(clients[0],msg)
            stranger=server.ClientConn(Socket(),room_code=room.room_code,pid=0)
            with pytest.raises(rules.RuleError,match="membership"):
                await server._dispatch(stranger,{**msg,"seq":1})
            assert await coord.repository.load(room.id)==before
            first={**msg,"seq":1};await server._dispatch(clients[0],first)
            with pytest.raises(rules.RuleError,match="payload conflict"):
                await server._dispatch(clients[0],{**first,"cmd":{"type":"end_turn"}})
            assert room.roll_count==1 and room.players[0].last_seq_applied==1
    asyncio.run(run())


def test_gameplay_intent_before_start_cannot_create_receipt_or_block_database(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            client=server.ClientConn(Socket());server.manager.connections[client.ws]=client
            await server._dispatch(client,{"type":"create_room","name":"Lobby owner","max_players":2})
            room=server.manager.rooms[client.room_code]
            before=await coord.repository.load(room.id)
            with pytest.raises(rules.RuleError,match="Match not started"):
                await server._dispatch(client,command(room,client,{"type":"roll"}))
            assert await coord.repository.load(room.id)==before
            assert coord.ready and not room.persistence_blocked and room.players[0].last_seq_applied==0
            assert not any(msg["type"]=="cmd_ack" for msg in client.ws.messages)
    asyncio.run(run())


def test_concurrent_same_sequence_serializes_to_one_durable_effect(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients=await pair(settings={"dice_mode":"balanced"});await prepare(room)
            msg=command(room,clients[0],{"type":"roll"})
            await asyncio.gather(server._dispatch(clients[0],msg),server._dispatch(clients[0],msg))
            assert room.roll_count==1 and room.tick==1 and room.players[0].last_seq_applied==1
            acks=[m for m in clients[0].ws.messages if m["type"]=="cmd_ack"]
            assert [a["applied"] for a in acks]==[True,False] and acks[1]["duplicate"]
            assert (await recovered(coord,room)).dice_bag==room.dice_bag
    asyncio.run(run())


def test_reconnect_waits_for_commit_and_fences_previous_socket(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients=await pair();await prepare(room)
            original=coord.repository.save
            entered,release=asyncio.Event(),asyncio.Event()
            async def delayed(*args,**kwargs):
                entered.set();await release.wait();return await original(*args,**kwargs)
            coord.repository.save=delayed
            msg=command(room,clients[0],{"type":"roll"})
            task=asyncio.create_task(server._dispatch(clients[0],msg))
            await entered.wait()
            replacement=server.ClientConn(Socket());server.manager.connections[replacement.ws]=replacement
            raw=clients[0].ws.latest("reconnect_token")["reconnect_token"]
            takeover=asyncio.create_task(server._dispatch(replacement,{"type":"reconnect","room_code":room.room_code,"reconnect_token":raw}))
            await asyncio.sleep(0)
            assert not takeover.done() and room.players[0].active_ws is clients[0].ws
            release.set();await asyncio.gather(task,takeover)
            assert room.players[0].active_ws is replacement.ws and clients[0].pid is None
            assert replacement.ws.latest("reconnect_token")["last_seq_applied"]==1
            server.manager.leave_room(clients[0])
            assert room.players[0].connected
            assert (await recovered(coord,room)).roll_count==1
    asyncio.run(run())


def test_timer_write_failure_is_fenced_and_never_advances_in_ram(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,_=await pair(settings={"turn_timer":30,"dice_mode":"balanced"});await prepare(room)
            candidate=clone_room(room);candidate.timer=TurnTimer.start(0,-5,server.time.monotonic(),server.time.time())
            await server._commit(room,candidate,snapshot=True)
            before=deepcopy(room.game),room.tick,room.dice,room.roll_count
            def fail(stage):
                if stage=="before_commit":raise OSError("timer DB outage")
            coord.repository._test_fault=fail
            with pytest.raises(PersistenceUnavailable):await server._process_room_timer(room)
            assert (room.game,room.tick,room.dice,room.roll_count)==before
            coord.repository._test_fault=None
            restored=await recovered(coord,room)
            assert restored.timer_paused and restored.players[0].last_seq_applied==0
    asyncio.run(run())


def test_finished_result_metadata_contains_total_vp_and_preserves_finished_time(database_url,monkeypatch):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients=await pair();await prepare(room,build_case("game_over"))
            before=await coord.repository.load(room.id)
            assert before["match"]["finished_at"] and before["match"]["winner_match_player_id"]==room.players[0].match_player_id
            assert [p["final_vp"] for p in sorted(before["participants"],key=lambda p:p["pid"])]==[p.vp for p in room.game.players]
            await server._dispatch(clients[0],{"type":"chat","text":"finished game chat"})
            after=await coord.repository.load(room.id)
            assert after["match"]["finished_at"]==before["match"]["finished_at"]
            assert (await recovered(coord,room)).game.game_over
    asyncio.run(run())


def test_actual_backend_process_restart_ws_credentials_sequences_and_revocation(database_url):
    """Separate process, real PostgreSQL and real WS, not a replaced RoomManager fixture."""
    port=_find_free_port()
    env={**os.environ,"DATABASE_URL":database_url,"CATAN_PERSISTENCE_MODE":"durable","CATAN_ENABLE_TEST_TOOLS":"0",
         "CATAN_HOST":"127.0.0.1","CATAN_PORT":str(port)}
    processes=[]
    def start():
        p=subprocess.Popen([sys.executable,"-B","-m","app.server_mp"],
                           cwd=Path(__file__).resolve().parents[1],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                           creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        processes.append(p)
        end=time.monotonic()+20
        while time.monotonic()<end:
            if p.poll() is not None:pytest.fail("Isolated durable backend exited before readiness")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health",timeout=1) as response:
                    if json.load(response)["ready"]:return p
            except OSError:pass
            time.sleep(.05)
        pytest.fail("Isolated durable backend readiness timeout")
    async def run():
        process=await asyncio.to_thread(start)
        url=f"ws://127.0.0.1:{port}/ws"
        a,b=await websockets.connect(url),await websockets.connect(url)
        try:
            await _send(a,{"type":"create_room","name":"Process Alice","max_players":2})
            rs=await _recv_type(a,"room_state");ta=await _recv_type(a,"reconnect_token");code=rs["room_code"]
            await _send(a,{"type":"set_settings","settings":{"starting_player":"host","dice_mode":"balanced","bank_visibility":"hidden"}})
            await _recv_type(a,"room_state")
            await _send(b,{"type":"join_room","room_code":code,"name":"Process Bob"})
            await _recv_type(b,"room_state");tb=await _recv_type(b,"reconnect_token")
            await _send(a,{"type":"start_match","request_id":"process-start","expected_match_id":0})
            ma=await _recv_type(a,"match_state");mb=await _recv_type(b,"match_state")
            seq=[0,0]
            while ma["state"]["phase"]=="setup":
                s=ma["state"];pid=s["turn"];socket=(a,b)[pid]
                legal=(ma,mb)[pid]["state"]["legal"]
                cmd={"type":"place_settlement","vid":legal["settlements"][0]} if s["setup_need"]=="settlement" else {"type":"place_road","eid":legal["roads"][0]}
                seq[pid]+=1;cid=str(uuid.uuid4())
                await _send(socket,{"type":"cmd","match_id":ma["match_id"],"seq":seq[pid],"cmd_id":cid,"cmd":cmd})
                ma=await _recv_type(a,"match_state");mb=await _recv_type(b,"match_state")
                assert (await _recv_cmd_ack(socket,cid))["applied"]
            seq[0]+=1;cid=str(uuid.uuid4())
            rolled={"type":"cmd","match_id":ma["match_id"],"seq":seq[0],"cmd_id":cid,"cmd":{"type":"roll"}}
            await _send(a,rolled)
            ma=await _recv_type(a,"match_state");mb=await _recv_type(b,"match_state")
            await _recv_cmd_ack(a,cid)
            process.kill();await asyncio.to_thread(process.wait)
            process=await asyncio.to_thread(start)
            a2,b2=await websockets.connect(url),await websockets.connect(url)
            try:
                for sock,token,expected in ((a2,ta,ma),(b2,tb,mb)):
                    await _send(sock,{"type":"reconnect","room_code":code,"reconnect_token":token["reconnect_token"],"pid":999,"name":"not ownership"})
                    await _recv_type(sock,"room_state");issued=await _recv_type(sock,"reconnect_token")
                    restored=await _recv_type(sock,"match_state")
                    assert issued["reconnect_token"]==token["reconnect_token"] and restored==expected
                await _send(a2,rolled)
                assert (await _recv_type(a2,"match_state"))["tick"]==ma["tick"]
                assert (await _recv_cmd_ack(a2,cid))["duplicate"]
                async with websockets.connect(url) as wrong:
                    await _send(wrong,{"type":"reconnect","room_code":code,"reconnect_token":"wrong-token","pid":0})
                    await _recv_error(wrong,"forbidden")
                db=Database(database_url)
                async with db.sessions() as session,session.begin():
                    await session.execute(update(m.seat_tokens).where(m.seat_tokens.c.token_hash==token_hash(ta["reconnect_token"])).values(revoked_at=utcnow()))
                await db.close()
            finally:
                await a2.close();await b2.close()
            process.kill();await asyncio.to_thread(process.wait);process=await asyncio.to_thread(start)
            async with websockets.connect(url) as revoked:
                await _send(revoked,{"type":"reconnect","room_code":code,"reconnect_token":ta["reconnect_token"]})
                await _recv_error(revoked,"forbidden")
            async with websockets.connect(url) as valid:
                await _send(valid,{"type":"reconnect","room_code":code,"reconnect_token":tb["reconnect_token"],"pid":0})
                assert (await _recv_type(valid,"reconnect_token"))["pid"]==1
                assert (await _recv_type(valid,"match_state"))["tick"]==ma["tick"]
        finally:
            await a.close();await b.close()
    try:asyncio.run(run())
    finally:
        for process in processes:
            if process.poll() is None:process.kill()
            process.wait(timeout=5)
