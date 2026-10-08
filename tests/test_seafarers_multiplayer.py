"""Direct hostile WS commands must obey the shared Seafarers executor.

Small materialized coast fixtures isolate boundaries; Gold Haven separately
exercises real setup, paid construction, turn aging and token takeover.
No production endpoint, command validator or snapshot is replaced.
"""
import asyncio
import json
from copy import deepcopy

import pytest
import websockets

from app import server_mp as server
from app.engine import rules
from app.engine.state import Tile
from tests.test_multiplayer_basic import _send, _send_cmd, _recv_type
from tests.test_server_authority import live_server, start_pair
from tests.test_seafarers_ships import graph_game
from tests.test_persistence_snapshots import seafarers_case


def presentation(room):
    return deepcopy((room.tick, room.dice, room.roll_count, room.dice_bag,
                     room.game_events, room.event_serial, room.next_test_dice,
                     room.timer, room.timer_paused))


def private_view(message, pid):
    state = message["state"]
    assert state["you_pid"] == pid and state["legal"]["pid"] == pid
    assert {"ships_built_this_turn", "ship_moved_this_turn", "seed", "dev_deck",
            "snapshot_version", "engine_compatibility", "bank"}.isdisjoint(state)
    for player in state["players"]:
        if player["pid"] != pid:
            assert "res" not in player and "dev_cards" not in player
    for event in state["game_events"]:
        assert "_private" not in event
        if event["type"] == "theft" and pid not in (event["actor_pid"], event["victim_pid"]):
            assert "resource" not in event


async def outcome(ws, cmd_id):
    messages = []
    while True:
        message = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        messages.append(message)
        if message["type"] == "cmd_ack" and message["cmd_id"] == cmd_id:
            return message, messages


async def reject(room, clients, pid, command):
    before, meta = deepcopy(room.game), presentation(room)
    seq = room.players[pid].last_seq_applied + 1
    cmd_id = await _send_cmd(clients[pid], room.match_id, seq, command)
    ack, messages = await outcome(clients[pid], cmd_id)
    assert any(message["type"] == "error" for message in messages)
    assert not ack["applied"] and not ack["duplicate"]
    assert ack["last_seq_applied"] == seq and room.players[pid].last_seq_applied == seq
    assert cmd_id in room.players[pid].seen_cmd_set
    assert room.game == before and presentation(room) == meta
    # Replay the exact rejected intent with its original identity. A snapshot
    # and duplicate ACK are transport recovery, never another effect/event.
    await _send_cmd(clients[pid], room.match_id, seq, command, cmd_id)
    replay, messages = await outcome(clients[pid], cmd_id)
    assert replay["duplicate"] and not replay["applied"]
    assert not any(message["type"] == "error" for message in messages)
    for message in messages:
        if message["type"] == "match_state":
            private_view(message, pid)
    assert room.game == before and presentation(room) == meta
    return cmd_id


async def accept(room, clients, pid, command):
    seq, tick, serial = room.players[pid].last_seq_applied + 1, room.tick, room.event_serial
    cmd_id = await _send_cmd(clients[pid], room.match_id, seq, command)
    ack, messages = await outcome(clients[pid], cmd_id)
    assert ack["applied"] and not ack["duplicate"], messages
    own = next(message for message in messages if message["type"] == "match_state")
    views = [None, None]
    views[pid] = own
    views[1 - pid] = await _recv_type(clients[1 - pid], "match_state")
    assert room.tick == tick + 1 and room.event_serial > serial
    for viewer, view in enumerate(views):
        private_view(view, viewer)
        assert view["tick"] == room.tick
        assert view["state"]["occupied_ships"] == own["state"]["occupied_ships"]
        assert view["state"]["occupied_e"] == own["state"]["occupied_e"]
    return views


async def age(room, clients):
    owner = room.game.turn
    await accept(room, clients, owner, {"type": "end_turn"})
    while room.game.turn != owner:
        current = room.game.turn
        await accept(room, clients, current, {"type": "roll"})
        await accept(room, clients, current, {"type": "end_turn"})
    await accept(room, clients, owner, {"type": "roll"})


def move(source, target):
    return {"type": "move_ship", "from_eid": list(source), "to_eid": list(target)}


def test_two_island_ship_expansion_is_authoritative_and_broadcast_to_both_clients(live_server):
    from tests.test_seafarers_islands import island_game
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            room, _, _, _, _ = await start_pair(a, b)
            room.game, destination, path = island_game()
            clients = [a, b]
            await reject(room, clients, 0, {"type": "place_settlement", "vid": destination})
            for edge in path:
                await accept(room, clients, 0, {"type": "build_ship", "eid": list(edge)})
            await reject(room, clients, 1, {"type": "place_settlement", "vid": destination})
            before = deepcopy(room.game)
            views = await accept(room, clients, 0, {"type": "place_settlement", "vid": destination})
            assert room.game.players[0].vp == before.players[0].vp + 1
            for view in views:
                assert view["state"]["occupied_v"][str(destination)] == [0, 1]
                assert view["state"]["occupied_ships"] == views[0]["state"]["occupied_ships"]
    asyncio.run(run())


def fixture(case):
    if case == "road_to_ship":
        return graph_game([(0, 1), (1, 2), (2, 3)], roads=[(0, 1), (1, 2)], buildings={0: (0, 1)})
    if case == "foreign_building":
        return graph_game([(0, 1), (1, 2), (2, 3), (3, 4)], ships=[(0, 1), (1, 2)],
                          buildings={0: (0, 1), 2: (1, 1), 4: (0, 1)})
    if case == "second_move":
        return graph_game([(0, 1), (0, 2), (3, 4), (3, 5)], ships=[(0, 1), (3, 4)],
                          buildings={0: (0, 1), 3: (0, 1)})
    g = graph_game([(0, 1), (0, 2), (1, 3), (8, 9)],
                   ships=[] if case in ("new_ship", "fake_free") else [(0, 1)], buildings={0: (0, 1)})
    if case.startswith("pirate_"):
        g.tiles.append(Tile(3, 0, "sea", None, (3.0, 0.0)))
        g.edge_adj_hexes[(0, 2)] = [1, 2]
        g.rules_config.enable_pirate = True
        g.pirate_tile = 0 if case == "pirate_source" else 2
        g.players[0].dev_cards = [{"type": "knight", "new": False}]
    if case == "pending":
        g.pending_action, g.pending_pid = "robber_move", 0
    return g


@pytest.mark.parametrize("case", ["road_to_ship", "foreign_building", "new_ship", "detached", "distant_invalid",
                                   "second_move", "pirate_source", "pirate_destination", "wrong_actor", "pending", "fake_free"])
def test_direct_ws_ship_refusals_are_atomic_consumed_duplicate_safe_and_correctable(live_server, monkeypatch, case):
    monkeypatch.setattr(server, "_roll_dice", lambda: (1, 1))
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            room, _, _, _, _ = await start_pair(a, b)
            room.game = fixture(case)  # Test-only established occupancy; socket execution stays unchanged.
            clients = [a, b]
            if case == "road_to_ship":
                await reject(room, clients, 0, {"type": "build_ship", "eid": [2, 3]})
                await accept(room, clients, 0, {"type": "place_settlement", "vid": 2})
                await accept(room, clients, 0, {"type": "build_ship", "eid": [2, 3]})
            elif case == "foreign_building":
                await reject(room, clients, 0, {"type": "build_ship", "eid": [2, 3]})
                await accept(room, clients, 0, {"type": "build_ship", "eid": [3, 4]})
            elif case == "fake_free":
                await reject(room, clients, 0, {"type": "build_ship", "eid": [0, 1], "free": True})
                await accept(room, clients, 0, {"type": "build_ship", "eid": [0, 1]})
            else:
                source, target, pid = (0, 1), (0, 2), 0
                if case == "new_ship":
                    await accept(room, clients, 0, {"type": "build_ship", "eid": list(source)})
                elif case == "second_move":
                    await accept(room, clients, 0, move(source, target))
                    source, target = (3, 4), (3, 5)
                elif case == "wrong_actor":
                    pid = 1
                elif case == "detached":
                    target = (1, 3)
                elif case == "distant_invalid":
                    target = (8, 9)
                await reject(room, clients, pid, move(source, target))
                if case in ("new_ship", "second_move"):
                    await age(room, clients)
                elif case.startswith("pirate_"):
                    await accept(room, clients, 0, {"type": "play_dev", "card": "knight"})
                    await accept(room, clients, 0, {"type": "move_pirate", "tile": 3})
                elif case == "pending":
                    await accept(room, clients, 0, {"type": "move_robber", "tile": 1})
                if case in ("detached", "distant_invalid"):
                    target = (0, 2)
                await accept(room, clients, 0, move(source, target))
    asyncio.run(run())


def test_gold_haven_ship_age_and_used_move_survive_real_token_takeover(live_server, monkeypatch):
    monkeypatch.setattr(server, "_roll_dice", lambda: (1, 1))
    async def run():
        async with websockets.connect(live_server) as a, websockets.connect(live_server) as b:
            room, token, _, _, _ = await start_pair(a, b)
            room.game = seafarers_case("ship")
            source = next(iter(room.game.occupied_ships))
            assert room.game.ships_built_this_turn == {source}
            async with websockets.connect(live_server) as replacement:
                before, meta = deepcopy(room.game), presentation(room)
                await _send(replacement, {"type": "reconnect", "room_code": room.room_code,
                                          "reconnect_token": token["reconnect_token"]})
                await _recv_type(replacement, "room_state")
                identity = await _recv_type(replacement, "reconnect_token")
                view = await _recv_type(replacement, "match_state")
                private_view(view, 0)
                assert identity["last_seq_applied"] == 0
                assert room.game == before and presentation(room) == meta
                clients = [replacement, b]
                target = next(edge for edge in room.game.edges
                              if rules.can_place_ship(room.game, 0, edge, excluded_edge=source))
                await reject(room, clients, 0, move(source, target))
                await age(room, clients)
                legal = server._snapshot_state(room.game, room, 0)["legal"]["move_ship"]
                assert list(source) in legal["sources"]
                destination = legal["targets"][",".join(map(str, source))][0]
                await accept(room, clients, 0, move(source, destination))
                assert room.game.ship_moved_this_turn
                # A new controller receives the consumed sequence and the exact
                # current game; reconnect cannot restore the already-used move.
                async with websockets.connect(live_server) as next_controller:
                    before, meta = deepcopy(room.game), presentation(room)
                    await _send(next_controller, {"type": "reconnect", "room_code": room.room_code,
                                                  "reconnect_token": token["reconnect_token"]})
                    await _recv_type(next_controller, "room_state")
                    identity = await _recv_type(next_controller, "reconnect_token")
                    view = await _recv_type(next_controller, "match_state")
                    private_view(view, 0)
                    assert identity["last_seq_applied"] == room.players[0].last_seq_applied
                    assert view["state"]["legal"]["move_ship"] == {"sources": [], "targets": {}}
                    assert room.game == before and presentation(room) == meta
                    await reject(room, [next_controller, b], 0, move(destination, source))
                    await a.close()
                    assert room.players[0].connected
    asyncio.run(run())
