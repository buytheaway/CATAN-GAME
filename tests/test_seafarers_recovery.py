"""Seafarers lifecycle recovery through real PostgreSQL aggregate commits.

Only the explicitly isolated *_test database is accepted by the shared fixture.
Hydration uses a fresh RoomManager/Coordinator and ordinary verified ownership.
"""
import asyncio
from copy import deepcopy

import pytest
from sqlalchemy import select, update, func

from app import server_mp as server
from app.auth.service import AuthService
from app.engine import rules
from app.persistence import models as m
from app.persistence.coordinator import Coordinator
from app.persistence.recovery import checksum
from tests.test_auth import account, connection
from tests.test_persistence_postgres import database_url, runtime, pair, prepare, command
from tests.test_persistence_snapshots import seafarers_case, assert_equivalent, give_card
from tests.test_seafarers_multiplayer import presentation, private_view, move
from tests.test_seafarers_ships import graph_game


@pytest.fixture(autouse=True)
def local_auth(monkeypatch):
    monkeypatch.setenv("CATAN_AUTH_MODE", "development")
    monkeypatch.setenv("CATAN_AUTH_ORIGINS", "http://test")
    monkeypatch.setattr(server, "_roll_dice", lambda: (1, 1))


async def create_room(coord, ownership, map_id="seafarers_gold_haven"):
    if ownership == "guest":
        room, clients = await pair(map_id=map_id)
        proofs = [("guest", room.players[p.pid].reconnect_token) for p in clients]
        return room, clients, proofs
    raw, who = await account(coord, "Maritime Account")
    owner, guest = await connection(who), await connection()
    await server._dispatch(owner, {"type": "create_room", "name": "Account", "max_players": 2})
    room = server.manager.rooms[owner.room_code]
    await server._dispatch(owner, {"type": "set_map", "map_id": map_id})
    await server._dispatch(owner, {"type": "set_settings", "settings": {
        "starting_player": "host", "bank_visibility": "hidden"}})
    await server._dispatch(guest, {"type": "join_room", "name": "Guest", "room_code": room.room_code})
    await server._dispatch(owner, {"type": "start_match"})
    return room, [owner, guest], [("account", raw), ("guest", room.players[1].reconnect_token)]


async def hydrate(coord, old_room, monkeypatch):
    manager = server.RoomManager()
    fresh = Coordinator(coord.database)
    await fresh.initialize(manager)
    monkeypatch.setattr(server, "manager", manager)
    monkeypatch.setattr(server, "persistence", fresh)
    room = manager.rooms[old_room.room_code]
    assert all(not slot.connected and slot.active_ws is None for slot in room.players)
    assert not manager.connections
    assert room is not old_room and room.game is not old_room.game
    return fresh, room


async def continue_room(coord, room, proofs):
    clients = []
    for pid, (ownership, proof) in enumerate(proofs):
        if ownership == "account":
            who = await AuthService(coord.database).resolve(proof)
            client = await connection(who)
            await server._dispatch(client, {"type": "account_continue", "room_code": room.room_code})
            assert client.ws.latest("seat_identity")["ownership"] == "account"
            assert room.players[pid].user_id == who["user_id"] and room.players[pid].token_hash is None
        else:
            client = await connection()
            await server._dispatch(client, {"type": "reconnect", "room_code": room.room_code, "reconnect_token": proof})
            assert client.ws.latest("reconnect_token")["reconnect_token"] == proof
        assert client.pid == pid
        private_view(client.ws.latest("match_state"), pid)
        clients.append(client)
    return clients


async def dispatch(room, client, cmd, applied=True):
    message = command(room, client, cmd)
    before, meta = deepcopy(room.game), presentation(room)
    await server._dispatch(client, message)
    ack = client.ws.latest("cmd_ack")
    assert ack["cmd_id"] == message["cmd_id"] and ack["applied"] == applied and not ack["duplicate"]
    assert room.players[client.pid].last_seq_applied == message["seq"]
    if not applied:
        assert_equivalent(before, room.game)
        assert presentation(room) == meta
    return message


@pytest.mark.parametrize("ownership", ["guest", "account"])
@pytest.mark.parametrize("case", ["ship", "moved_ship"])
def test_ship_lifecycle_committed_checkpoint_fresh_hydration_and_end_unlock(database_url, monkeypatch, ownership, case):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients, proofs = await create_room(coord, ownership)
            await prepare(room, seafarers_case(case))
            before, meta = deepcopy(room.game), presentation(room)
            bundle = await coord.repository.load(room.id)
            assert bundle["head"]["snapshot_version"] == 3
            fresh, restored = await hydrate(coord, room, monkeypatch)
            assert_equivalent(before, restored.game)
            assert presentation(restored) == meta
            clients = await continue_room(fresh, restored, proofs)
            source = next(iter(restored.game.occupied_ships))
            target = next(edge for edge in restored.game.edges
                          if rules.can_place_ship(restored.game, 0, edge, excluded_edge=source))
            msg = await dispatch(restored, clients[0], move(source, target), applied=False)
            receipt = await fresh.repository.receipt(restored.players[0].match_player_id, msg["seq"], msg["cmd_id"])
            assert receipt["outcome"] == "rejected"
            assert (await fresh.repository.load(restored.id))["head"]["id"] == bundle["head"]["id"]
            fresh, again = await hydrate(fresh, restored, monkeypatch)
            clients = await continue_room(fresh, again, proofs)
            before, meta = deepcopy(again.game), presentation(again)
            await server._dispatch(clients[0], msg)
            assert clients[0].ws.latest("cmd_ack")["duplicate"]
            assert_equivalent(before, again.game)
            assert presentation(again) == meta
            await dispatch(again, clients[0], {"type": "end_turn"})
            assert not again.game.ships_built_this_turn and not again.game.ship_moved_this_turn
            fresh, after_end = await hydrate(fresh, again, monkeypatch)
            assert not after_end.game.ships_built_this_turn and not after_end.game.ship_moved_this_turn
            clients = await continue_room(fresh, after_end, proofs)
            await dispatch(after_end, clients[1], {"type": "roll"})
            await dispatch(after_end, clients[1], {"type": "end_turn"})
            await dispatch(after_end, clients[0], {"type": "roll"})
            await dispatch(after_end, clients[0], move(source, target))
            assert after_end.game.ship_moved_this_turn and after_end.game.occupied_ships[target] == 0
    asyncio.run(run())


def test_rejected_ship_receipt_pruning_cannot_restore_move_after_hydration(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients, proofs = await create_room(coord, "guest")
            await prepare(room, seafarers_case("ship"))
            source = next(iter(room.game.occupied_ships))
            target = next(edge for edge in room.game.edges if rules.can_place_ship(room.game, 0, edge, excluded_edge=source))
            first = await dispatch(room, clients[0], move(source, target), applied=False)
            first_receipt = await coord.repository.receipt(room.players[0].match_player_id, first["seq"], first["cmd_id"])
            assert first_receipt["outcome"] == "rejected"
            head = (await coord.repository.load(room.id))["head"]["id"]
            for _ in range(256):
                await dispatch(room, clients[0], move(source, target), applied=False)
            assert await coord.repository.receipt(room.players[0].match_player_id, first["seq"], first["cmd_id"]) is None
            async with coord.database.sessions() as session:
                count = await session.execute(select(func.count()).select_from(m.command_receipts).where(
                    m.command_receipts.c.match_player_id == room.players[0].match_player_id))
                assert count.scalar_one() == 256
            assert (await coord.repository.load(room.id))["head"]["id"] == head
            fresh, restored = await hydrate(coord, room, monkeypatch)
            clients = await continue_room(fresh, restored, proofs)
            before, meta = deepcopy(restored.game), presentation(restored)
            await server._dispatch(clients[0], first)
            ack = clients[0].ws.latest("cmd_ack")
            assert ack["duplicate"] and not ack["applied"] and ack["last_seq_applied"] == 257
            assert_equivalent(before, restored.game)
            assert presentation(restored) == meta
    asyncio.run(run())


def gold_setup_choice():
    g = rules.build_game(1, 2, map_id="seafarers_gold_haven")
    while g.pending_action != "choose_gold":
        pid = g.turn
        if g.setup_need == "settlement":
            legal = [v for v in sorted(g.vertices) if rules.can_place_settlement(g, pid, v, False)]
            gold = [v for v in legal if any(g.tiles[t].terrain == "gold" for t in g.vertex_adj_hexes[v])]
            rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": (gold or legal)[0]})
        else:
            edge = next(e for e in sorted(g.edges) if rules.can_place_road(g, pid, e, g.setup_anchor_vid))
            rules.apply_cmd(g, pid, {"type": "place_road", "eid": edge})
        assert g.phase == "setup"
    return g


@pytest.mark.parametrize("ownership", ["guest", "account"])
def test_gold_setup_pending_choice_anchor_and_following_route_recover_exactly(database_url, monkeypatch, ownership):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, _, proofs = await create_room(coord, ownership)
            await prepare(room, gold_setup_choice())
            before = deepcopy(room.game)
            anchor, pid, setup_idx = before.setup_anchor_vid, before.pending_pid, before.setup_idx
            assert anchor is not None and before.setup_need == "road"
            fresh, restored = await hydrate(coord, room, monkeypatch)
            assert_equivalent(before, restored.game)
            clients = await continue_room(fresh, restored, proofs)
            assert clients[pid].ws.latest("match_state")["state"]["pending_gold"] == {str(pid): before.pending_gold[pid]}
            assert clients[1 - pid].ws.latest("match_state")["state"]["pending_gold"] == {}
            await dispatch(restored, clients[1 - pid], {"type": "choose_gold", "res": "ore", "qty": 1}, applied=False)
            while restored.game.pending_action == "choose_gold":
                await dispatch(restored, clients[pid], {"type": "choose_gold", "res": "ore", "qty": 1})
            fresh, after_choice = await hydrate(fresh, restored, monkeypatch)
            assert after_choice.game.setup_anchor_vid == anchor and after_choice.game.setup_idx == setup_idx
            assert after_choice.game.setup_need == "road" and after_choice.game.pending_action is None
            clients = await continue_room(fresh, after_choice, proofs)
            legal = clients[pid].ws.latest("match_state")["state"]["legal"]
            kind, edge = ("build_ship", legal["ships"][0]) if legal["ships"] else ("place_road", legal["roads"][0])
            assert anchor in edge
            await dispatch(after_choice, clients[pid], {"type": kind, "eid": edge, "setup": True})
            fresh, after_route = await hydrate(fresh, after_choice, monkeypatch)
            assert after_route.game.setup_idx == setup_idx + 1 and after_route.game.setup_anchor_vid is None
            assert not after_route.game.ships_built_this_turn and not after_route.game.ship_moved_this_turn
    asyncio.run(run())


@pytest.mark.parametrize("ownership", ["guest", "account"])
def test_mixed_route_award_vp_private_hand_and_new_ship_survive_recovery(database_url, monkeypatch, ownership):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, clients, proofs = await create_room(coord, ownership, map_id="base_standard")
            g = graph_game([(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)], roads=[(0, 1), (1, 2)],
                           ships=[(2, 3), (3, 4)], buildings={0: (0, 1), 2: (0, 1)})
            g.players[0].vp = 2
            g.dev_deck = ["knight", "victory_point"]
            give_card(g, "victory_point")
            rules.update_longest_road(g)
            assert g.longest_road_owner is None
            await prepare(room, g)
            await dispatch(room, clients[0], {"type": "build_ship", "eid": [4, 5]})
            assert room.game.longest_road_owner == 0 and room.game.longest_road_len == 5
            assert room.game.players[0].vp == 5 and room.game.ships_built_this_turn == {(4, 5)}
            before, meta = deepcopy(room.game), presentation(room)
            fresh, restored = await hydrate(coord, room, monkeypatch)
            assert_equivalent(before, restored.game)
            assert presentation(restored) == meta
            clients = await continue_room(fresh, restored, proofs)
            own, other = [client.ws.latest("match_state")["state"] for client in clients]
            assert own["longest_road_owner"] == other["longest_road_owner"] == 0
            assert own["longest_road_len"] == other["longest_road_len"] == 5
            assert own["players"][0]["vp"] == 5 and other["players"][0]["vp"] == 4
            assert own["players"][0]["dev_cards"] == [{"type": "victory_point", "new": False}]
            assert restored.game.dev_deck == ["knight"]
    asyncio.run(run())


def test_verified_s1_match_with_v1_format_locks_unknown_history_then_end_upgrades_to_v2(database_url, monkeypatch):
    async def run():
        async with runtime(database_url, monkeypatch) as coord:
            room, _, proofs = await create_room(coord, "guest")
            await prepare(room, seafarers_case("ship"))
            head = (await coord.repository.load(room.id))["head"]
            payload = deepcopy(head["payload"])
            from tests.test_persistence_snapshots import released_v1_payload
            payload["engine"] = released_v1_payload(room.game)
            async with coord.database.sessions() as session, session.begin():
                await session.execute(update(m.game_snapshots).where(m.game_snapshots.c.id == head["id"]).values(
                    payload=payload, checksum=checksum(payload), snapshot_version=1, engine_compatibility=1))
            fresh, restored = await hydrate(coord, room, monkeypatch)
            assert restored.ruleset_id == server.CURRENT_RULESET  # Known rules, older codec only.
            assert restored.game.ship_moved_this_turn and not restored.game.ships_built_this_turn
            clients = await continue_room(fresh, restored, proofs)
            source = next(iter(restored.game.occupied_ships))
            target = next(edge for edge in restored.game.edges if rules.can_place_ship(restored.game, 0, edge, excluded_edge=source))
            await dispatch(restored, clients[0], move(source, target), applied=False)
            assert (await fresh.repository.load(restored.id))["head"]["snapshot_version"] == 1
            await dispatch(restored, clients[0], {"type": "end_turn"})
            latest = (await fresh.repository.load(restored.id))["head"]
            assert latest["snapshot_version"] == 3 and not restored.game.ship_moved_this_turn
            fresh, after_end = await hydrate(fresh, restored, monkeypatch)
            assert not after_end.game.ship_moved_this_turn and not after_end.game.ships_built_this_turn
    asyncio.run(run())
