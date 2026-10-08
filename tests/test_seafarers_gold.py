"""Gold production/setup and pending choices through authoritative commands.

Shortage checks cover finite supply and progress, without inventing an ordering
rule for competing Gold requests or changing ordinary Base production.
"""
from copy import deepcopy
from dataclasses import replace

import pytest

from app import server_mp as server
from app.engine import rules
from app.engine.state import RESOURCES


def totals(g):
    return {r: g.bank[r] + sum(p.res[r] for p in g.players) for r in RESOURCES}


def rejected_unchanged(g, pid, cmd):
    before = deepcopy(g)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(g, pid, cmd)
    assert g == before


def assert_gold_complete(g):
    assert g.pending_action is None and g.pending_pid is None
    assert g.pending_gold == {} and g.pending_gold_queue == []
    assert min(g.bank.values()) >= 0


def gold_game(levels=None, turn=0):
    """Use preset geometry with isolated, distance-compliant Gold producers."""
    g = rules.build_game(1, 3, map_id="seafarers_gold_haven")
    g.phase, g.turn = "main", turn
    tile = next(i for i, t in enumerate(g.tiles) if t.terrain == "gold")
    g.robber_tile = next(i for i, t in enumerate(g.tiles) if t.terrain not in ("gold", "sea"))
    g.robbers = [g.robber_tile]
    for pid, level in (levels or {0: 2}).items():
        vertex = next(v for v, adjacent in sorted(g.vertex_adj_hexes.items())
                      if tile in adjacent and rules.can_place_settlement(g, pid, v, False))
        g.occupied_v[vertex] = (pid, level)
        g.players[pid].vp = level
    return g, tile


def set_bank(g, available):
    """Keep all 19 cards of each type in the bank or a trusted fixture hand."""
    g.bank = {r: available.get(r, 0) for r in RESOURCES}
    for p in g.players:
        p.res = {r: 0 for r in RESOURCES}
    g.players[-1].res = {r: 19 - g.bank[r] for r in RESOURCES}


def roll_gold(g, tile):
    rules.apply_cmd(g, g.turn, {"type": "roll", "roll": g.tiles[tile].number})


@pytest.mark.parametrize("level", [1, 2])
@pytest.mark.parametrize("blocker", ["primary", "secondary"])
def test_robber_blocks_gold_settlement_and_city(level, blocker):
    g, tile = gold_game({0: level})
    if blocker == "primary":
        g.robber_tile, g.robbers = tile, [tile]
    else:
        g.rules_config.robber_count = 2
        g.robbers.append(tile)
    before = deepcopy(g)
    roll_gold(g, tile)
    assert [p.res for p in g.players] == [p.res for p in before.players]
    assert g.bank == before.bank
    assert_gold_complete(g)
    rules.apply_cmd(g, g.turn, {"type": "end_turn"})


@pytest.mark.parametrize("level,choices", [(1, ["ore"]), (2, ["ore", "ore"]),
                                            (2, ["ore", "wheat"])])
def test_gold_resources_remain_manual_and_city_choices_may_differ(level, choices):
    g, tile = gold_game({0: level})
    before, supply = deepcopy(g), totals(g)
    roll_gold(g, tile)
    assert g.pending_gold == {0: level} and g.pending_pid == 0
    assert [p.res for p in g.players] == [p.res for p in before.players]
    for index, resource in enumerate(choices):
        rules.apply_cmd(g, 0, {"type": "choose_gold", "res": resource, "qty": 1})
        assert totals(g) == supply
        if index + 1 < len(choices):
            assert g.pending_action == "choose_gold" and g.pending_gold == {0: 1}
    assert g.players[0].res == {r: choices.count(r) for r in RESOURCES}
    assert_gold_complete(g)


def test_multiple_gold_recipients_resolve_outside_the_active_turn():
    g, tile = gold_game({0: 1, 1: 2, 2: 1}, turn=2)
    supply = totals(g)
    roll_gold(g, tile)
    assert g.pending_gold_queue == [0, 1, 2]  # Preserve the existing numeric queue.
    for pid, choices in ((0, ["brick"]), (1, ["ore", "wheat"]), (2, ["wood"])):
        assert g.turn == 2 and g.pending_pid == pid
        rejected_unchanged(g, (pid + 1) % 3,
                           {"type": "choose_gold", "res": "sheep", "qty": 1})
        for resource in choices:
            rules.apply_cmd(g, pid, {"type": "choose_gold", "res": resource, "qty": 1})
        assert g.players[pid].res == {r: choices.count(r) for r in RESOURCES}
    assert totals(g) == supply
    assert_gold_complete(g)
    rules.apply_cmd(g, 2, {"type": "end_turn"})


@pytest.mark.parametrize("levels", [{0: 2}, {0: 2, 1: 1}])
def test_empty_bank_does_not_create_impossible_gold_choices(levels):
    g, tile = gold_game(levels)
    set_bank(g, {})
    before = deepcopy(g)
    roll_gold(g, tile)
    assert [p.res for p in g.players] == [p.res for p in before.players]
    assert totals(g) == totals(before)
    assert_gold_complete(g)
    rules.apply_cmd(g, 0, {"type": "end_turn"})


def test_ordinary_production_can_consume_last_bank_card_before_gold_choices():
    g, tile = gold_game({0: 2})
    producing = next(i for i, t in enumerate(g.tiles)
                     if t.number == g.tiles[tile].number and t.terrain == "pasture")
    vertex = next(v for v, adjacent in sorted(g.vertex_adj_hexes.items())
                  if producing in adjacent and rules.can_place_settlement(g, 1, v, False))
    g.occupied_v[vertex] = (1, 1)
    set_bank(g, {"sheep": 1})
    before = deepcopy(g)
    roll_gold(g, tile)
    assert g.players[1].res["sheep"] == before.players[1].res["sheep"] + 1
    assert g.players[0].res == before.players[0].res
    assert totals(g) == totals(before) and sum(g.bank.values()) == 0
    assert_gold_complete(g)
    rules.apply_cmd(g, 0, {"type": "end_turn"})


@pytest.mark.parametrize("levels", [{0: 2}, {0: 2, 1: 1}])
def test_last_available_card_clears_unfulfillable_gold_remainders(levels):
    g, tile = gold_game(levels)
    set_bank(g, {"ore": 1})
    roll_gold(g, tile)
    before = deepcopy(g)
    rejected_unchanged(g, 0, {"type": "choose_gold", "res": "ore", "qty": 2})
    rules.apply_cmd(g, 0, {"type": "choose_gold", "res": "ore", "qty": 1})
    assert g.players[0].res["ore"] == before.players[0].res["ore"] + 1
    assert [p.res for p in g.players[1:]] == [p.res for p in before.players[1:]]
    assert totals(g) == totals(before) and sum(g.bank.values()) == 0
    assert_gold_complete(g)
    rejected_unchanged(g, 0, {"type": "choose_gold", "res": "wood", "qty": 1})
    rules.apply_cmd(g, 0, {"type": "end_turn"})


def test_partial_gold_choice_keeps_remaining_available_card_manual():
    g, tile = gold_game({0: 2, 1: 1})
    set_bank(g, {"ore": 1, "wheat": 1})
    supply = totals(g)
    roll_gold(g, tile)
    rules.apply_cmd(g, 0, {"type": "choose_gold", "res": "ore", "qty": 1})
    assert g.pending_action == "choose_gold" and g.pending_pid == 0
    assert g.pending_gold == {0: 1, 1: 1} and g.bank["wheat"] == 1
    assert g.players[0].res["wheat"] == g.players[1].res["wheat"] == 0
    rejected_unchanged(g, 0, {"type": "choose_gold", "res": "ore", "qty": 1})
    rules.apply_cmd(g, 0, {"type": "choose_gold", "res": "wheat", "qty": 1})
    assert g.players[0].res["ore"] == g.players[0].res["wheat"] == 1
    assert all(q == 0 for q in g.players[1].res.values())
    assert totals(g) == supply
    assert_gold_complete(g)


@pytest.mark.parametrize("qty", [0, -1, 3, True, None, "1", 1.0])
def test_invalid_gold_quantity_preserves_full_pending_state(qty):
    g, tile = gold_game()
    roll_gold(g, tile)
    rejected_unchanged(g, 0, {"type": "choose_gold", "res": "ore", "qty": qty})
    rules.apply_cmd(g, 0, {"type": "choose_gold", "res": "ore", "qty": 2})
    assert_gold_complete(g)


def second_gold_setup():
    g = rules.build_game(1, 2, map_id="seafarers_gold_haven")
    target = next(v for v, adjacent in sorted(g.vertex_adj_hexes.items())
                  if any(g.tiles[t].terrain == "gold" for t in adjacent)
                  and any(g.tiles[t].terrain == "sea" for t in adjacent))
    forbidden = {target} | {b if a == target else a for a, b in g.edges if target in (a, b)}
    while g.setup_idx < 2:
        pid = g.turn
        if g.setup_need == "settlement":
            vertex = next(v for v in sorted(g.vertices) if v not in forbidden
                          and rules.can_place_settlement(g, pid, v, False)
                          and all(g.tiles[t].terrain != "gold" for t in g.vertex_adj_hexes[v]))
            rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": vertex})
        else:
            edge = next(e for e in sorted(g.edges)
                        if rules.can_place_road(g, pid, e, g.setup_anchor_vid))
            rules.apply_cmd(g, pid, {"type": "place_road", "eid": list(edge)})
    assert rules.can_place_settlement(g, g.turn, target, False)
    return g, target


@pytest.mark.parametrize("route", ["place_road", "build_ship"])
def test_second_setup_settlement_gold_choice_resumes_connected_route(route):
    g, vertex = second_gold_setup()
    pid, setup_index, before = g.turn, g.setup_idx, deepcopy(g)
    rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": vertex})
    assert g.pending_action == "choose_gold" and g.pending_pid == pid
    assert g.pending_gold == {pid: 1}
    assert g.setup_idx == setup_index and g.setup_need == "road" and g.setup_anchor_vid == vertex
    ordinary = {r: 0 for r in RESOURCES}
    for tile in g.vertex_adj_hexes[vertex]:
        resource = rules.TERRAIN_TO_RES[g.tiles[tile].terrain]
        if resource:
            ordinary[resource] += 1
    assert g.players[pid].res == {r: before.players[pid].res[r] + ordinary[r] for r in RESOURCES}
    edge = next(e for e in sorted(g.edges) if vertex in e and
                (rules.can_place_road(g, pid, e, vertex) if route == "place_road"
                 else rules.can_place_ship(g, pid, e)))
    rejected_unchanged(g, pid, {"type": route, "eid": list(edge)})
    rejected_unchanged(g, 1 - pid, {"type": "choose_gold", "res": "ore", "qty": 1})
    rules.apply_cmd(g, pid, {"type": "choose_gold", "res": "ore", "qty": 1})
    assert_gold_complete(g)
    assert g.phase == "setup" and g.setup_idx == setup_index and g.setup_anchor_vid == vertex
    assert g.players[pid].res["ore"] == before.players[pid].res["ore"] + ordinary["ore"] + 1
    funded = deepcopy(g.players[pid].res)
    rules.apply_cmd(g, pid, {"type": route, "eid": list(edge)})
    assert g.players[pid].res == funded and g.setup_idx == setup_index + 1
    assert (g.occupied_e if route == "place_road" else g.occupied_ships)[edge] == pid
    assert totals(g) == totals(before)


def test_first_setup_gold_settlement_does_not_grant_initial_resources():
    g = rules.build_game(1, 2, map_id="seafarers_gold_haven")
    vertex = next(v for v, adjacent in sorted(g.vertex_adj_hexes.items())
                  if any(g.tiles[t].terrain == "gold" for t in adjacent))
    before = deepcopy(g)
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": vertex})
    assert [p.res for p in g.players] == [p.res for p in before.players]
    assert g.bank == before.bank
    assert_gold_complete(g)


def test_empty_bank_during_setup_still_allows_the_required_free_route():
    g, vertex = second_gold_setup()
    set_bank(g, {})
    pid, supply = g.turn, totals(g)
    rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": vertex})
    assert_gold_complete(g)
    edge = next(e for e in sorted(g.edges) if rules.can_place_road(g, pid, e, vertex))
    rules.apply_cmd(g, pid, {"type": "place_road", "eid": list(edge)})
    assert g.setup_idx == 3 and totals(g) == supply


def room_for(g, visibility="hidden"):
    room = server.Room(room_code="GOLD", max_players=len(g.players), host_pid=0,
                       players=[server.PlayerSlot(pid=p.pid, name=p.name) for p in g.players])
    room.settings = replace(room.settings, bank_visibility=visibility)
    room.game = g
    room.ruleset_id = server.CURRENT_RULESET
    return room


@pytest.mark.parametrize("visibility", ["hidden", "visible"])
def test_server_gold_choices_and_events_are_private_to_the_recipient(visibility, monkeypatch):
    g, tile = gold_game({0: 2, 1: 1}, turn=2)
    room = room_for(g, visibility)
    total = g.tiles[tile].number
    monkeypatch.setattr(server, "_roll_dice", lambda: (1, total - 1))
    assert server._apply_cmd(room, 2, {"type": "roll"}) is None
    before = deepcopy(room)
    error = server._apply_cmd(room, 1, {"type": "choose_gold", "res": "ore", "qty": 1})
    assert error["type"] == "error" and room == before
    assert server._apply_cmd(room, 0, {"type": "choose_gold", "res": "ore", "qty": 1}) is None
    before = deepcopy(g)
    for pid in range(3):
        state = server._snapshot_state(g, room, pid)
        assert state["pending_gold"] == ({str(pid): g.pending_gold[pid]} if pid in g.pending_gold else {})
        assert "seed" not in state and "dev_deck" not in state
        assert ("bank" in state) == (visibility == "visible")
        assert all("res" not in p and "dev_cards" not in p for p in state["players"] if p["pid"] != pid)
        event = state["game_events"][-1]
        assert event["type"] == "choose_gold" and event["actor_pid"] == 0 and event["quantity"] == 1
        assert "_private" not in event
        if pid == 0:
            assert event["gained"] == {"ore": 1}
        else:
            assert "gained" not in event and "paid" not in event and "res" not in event
            assert "ore" not in str(event)
        assert g == before


@pytest.mark.parametrize("trigger", ["seven", "knight"])
@pytest.mark.parametrize("piece", ["robber", "pirate"])
def test_seven_and_knight_allow_one_piece_and_one_private_theft(trigger, piece):
    g, land = gold_game({1: 1})
    sea = next(i for i, t in enumerate(g.tiles) if t.terrain == "sea" and i != g.pirate_tile)
    edge = next(e for e, adjacent in g.edge_adj_hexes.items() if sea in adjacent)
    g.occupied_ships[edge] = 1
    rules.apply_cmd(g, 1, {"type": "grant_resources", "res": {"wood": 8}})
    room = room_for(g)
    if trigger == "seven":
        rules.apply_cmd(g, 0, {"type": "roll", "roll": 7})
        rejected_unchanged(g, 0, {"type": "move_pirate", "tile": sea, "victim": 1})
        rules.apply_cmd(g, 1, {"type": "discard", "discards": {"wood": 4}})
    else:
        g.players[0].dev_cards = [{"type": "knight", "new": False}]
        rules.apply_cmd(g, 0, {"type": "play_dev", "card": "knight"})
        assert not g.rolled
    tile = sea if piece == "pirate" else land
    cmd = {"type": "move_" + piece, "tile": tile}
    if trigger == "seven":
        cmd["victim"] = 1  # Knight cases also verify the existing implicit victim.
    before = deepcopy(room)
    error = server._apply_cmd(room, 0, {**cmd, "victim": 0})
    assert error["type"] == "error" and room == before
    assert server._apply_cmd(room, 0, cmd) is None
    assert sum(g.players[0].res.values()) == sum(before.game.players[0].res.values()) + 1
    assert sum(g.players[1].res.values()) == sum(before.game.players[1].res.values()) - 1
    assert totals(g) == totals(before.game)
    assert g.pending_action is None and g.pending_pid is None and g.pending_victims == []
    other = "robber" if piece == "pirate" else "pirate"
    assert getattr(g, other + "_tile") == getattr(before.game, other + "_tile")
    before = deepcopy(room)
    error = server._apply_cmd(room, 0, cmd)
    assert error["type"] == "error" and room == before
    for pid in range(3):
        event = server._snapshot_state(g, room, pid)["game_events"][-1]
        assert event["type"] == "theft" and event["victim_pid"] == 1 and event["quantity"] == 1
        if pid in (0, 1):
            assert event["resource"] == "wood"
        else:
            assert "resource" not in event
    if trigger == "knight":
        rules.apply_cmd(g, 0, {"type": "roll", "roll": 2})
    rules.apply_cmd(g, 0, {"type": "end_turn"})
