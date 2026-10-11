"""Internal exploration acceptance. No public fog creation/projection is enabled."""
from copy import deepcopy
import json

import pytest

from app.engine import rules
from app.engine.exploration import (
    assignment_digest, is_known_land, is_known_sea, tile_is_known,
    initial_fog_state, validate_fog_state, validate_fog_transition,
)
from app.engine.legal import board_legal_moves
from app.engine.state import COST, RESOURCES, TERRAIN_TO_RES, FogRules, ScenarioRules
from app.persistence.snapshots import encode_snapshot, loads_snapshot
from tests.test_fog_foundation import fog_game, fog_recipe


def exploration_game(terrain="forest", *, setup=False):
    source = fog_recipe()
    source["fog_pool"] = {"terrain": [terrain] * 8,
                          "numbers": [] if terrain in ("sea", "desert") else [5] * 8}
    source["rules"]["target_vp"] = 24
    g = fog_game(data=source)
    if not setup:
        g.phase, g.setup_idx, g.turn, g.rolled = "main", len(g.setup_order), 0, True
    return g


def execute(g, cmd, pid=None):
    return rules.apply_cmd(g, g.turn if pid is None else pid, cmd, trusted_fog=True)


def adjacent_hidden(g, edge):
    return sorted(set(g.scenario.rules.fog.initially_hidden).intersection(
        set(g.vertex_adj_hexes[edge[0]]) | set(g.vertex_adj_hexes[edge[1]])))


def route_edge(g, kind="place_road", *, vertex_only=False, minimum=1):
    known = is_known_land if kind == "place_road" else is_known_sea
    return next(e for e in sorted(g.edges)
                if any(known(g, i) for i in g.edge_adj_hexes[e])
                and g.pirate_tile not in g.edge_adj_hexes[e]
                and len(adjacent_hidden(g, e)) >= minimum
                and (not vertex_only or not set(g.edge_adj_hexes[e]).intersection(g.scenario.rules.fog.initially_hidden)))


def anchor_and_fund(g, edge, *, kind="place_road", setup=False):
    g.occupied_v[edge[0]] = (g.turn, 1)
    g.players[g.turn].vp = 1
    if setup:
        g.setup_need, g.setup_anchor_vid = "road", edge[0]
    else:
        for r, q in COST["road" if kind == "place_road" else "ship"].items():
            g.bank[r] -= q
            g.players[g.turn].res[r] += q


def reject(g, cmd, *, pid=None, code=None):
    before = deepcopy(g)
    with pytest.raises(rules.RuleError) as error:
        execute(g, cmd, pid)
    if code:
        assert error.value.code == code
    assert g == before
    assert encode_snapshot(g) == encode_snapshot(before)


@pytest.mark.parametrize("kind", ["place_road", "build_ship"])
@pytest.mark.parametrize("mode", ["paid", "setup", "road_building"])
def test_accepted_construction_discovers_endpoint_tiles_once(kind, mode):
    g = exploration_game(setup=mode == "setup")
    edge = route_edge(g, kind)
    anchor_and_fund(g, edge, kind=kind, setup=mode == "setup")
    cmd = {"type": kind, "eid": list(reversed(edge))}
    if mode == "road_building":
        g.rolled = False
        g.players[0].dev_cards = [{"type": "road_building", "new": False}]
        execute(g, {"type": "play_dev", "card": "road_building"})
        cmd["free"] = True
    before, expected = deepcopy(g), adjacent_hidden(g, edge)
    _, events = execute(g, cmd)
    assert g.scenario.fog.revealed == frozenset(expected)
    assert [d.tile_index for d in g.scenario.fog.discoveries] == expected
    assert all((d.pid, d.reward_status, d.resource) == (0, "awarded", "wood") for d in g.scenario.fog.discoveries)
    cost = COST["road" if kind == "place_road" else "ship"].get("wood", 0) if mode == "paid" else 0
    assert g.players[0].res["wood"] == before.players[0].res["wood"] - cost + len(expected)
    assert [e["tile"] for e in events if e["type"] == "discover_tile"] == expected
    assert g.tiles == before.tiles and assignment_digest(g.board) == before.scenario.fog.assignment_digest
    if mode == "setup":
        assert g.setup_idx == before.setup_idx + 1 and g.turn == 1
    if mode == "road_building":
        assert g.free_roads[0] == 1 and not g.rolled
    if kind == "build_ship" and mode != "setup":
        assert edge in g.ships_built_this_turn
    validate_fog_transition(before, g)
    assert loads_snapshot(json.dumps(encode_snapshot(g))) == g
    reject(g, cmd, pid=0)  # Retry of the same route cannot duplicate discoveries.


def test_vertex_only_discovery_multiple_order_and_touch_deduplication():
    g = exploration_game()
    edge = route_edge(g, vertex_only=True)
    assert not set(g.edge_adj_hexes[edge]).intersection(g.scenario.rules.fog.initially_hidden)
    anchor_and_fund(g, edge)
    execute(g, {"type": "place_road", "eid": edge})
    discovered = g.scenario.fog.discoveries
    assert discovered and g.scenario.fog.revealed == frozenset(adjacent_hidden(g, edge))
    # A distinct accepted connected road touches the same hex: its entry stays
    # byte-for-byte unchanged, even if the route also opens more territory.
    second = next(e for e in sorted(g.edges) if e != edge and set(e).intersection(edge)
                  and set(adjacent_hidden(g, e)).intersection(g.scenario.fog.revealed)
                  and rules.can_place_road(g, 0, e))
    for r, n in COST["road"].items():
        g.bank[r] -= n
        g.players[0].res[r] += n
    _, events = execute(g, {"type": "place_road", "eid": second})
    assert g.scenario.fog.discoveries[:len(discovered)] == discovered
    newly = [e["tile"] for e in events if e["type"] == "discover_tile"]
    assert newly == sorted(newly) and not set(newly).intersection(d.tile_index for d in discovered)
    assert len(g.scenario.fog.discoveries) == len(g.scenario.fog.revealed)


@pytest.mark.parametrize("terrain", ["forest", "hills", "pasture", "fields", "mountains", "sea", "desert"])
def test_standard_and_nonproducing_discovery_rewards(terrain):
    g = exploration_game(terrain)
    edge = route_edge(g, minimum=3)
    anchor_and_fund(g, edge)
    before = deepcopy(g)
    execute(g, {"type": "place_road", "eid": edge})
    resource = TERRAIN_TO_RES[terrain]
    for r in RESOURCES:
        reward = 3 if r == resource else 0
        assert g.players[0].res[r] == before.players[0].res[r] - COST["road"].get(r, 0) + reward
        assert g.bank[r] == before.bank[r] + COST["road"].get(r, 0) - reward
    assert [d.reward_status for d in g.scenario.fog.discoveries] == ["awarded" if resource else "none"] * 3
    assert g.pending_action is None and g.scenario.fog.continuation is None


def test_standard_bank_shortage_is_processed_once_without_cancelling_route():
    g = exploration_game("mountains")
    edge = route_edge(g, minimum=3)
    anchor_and_fund(g, edge)
    g.bank["ore"] = 1
    execute(g, {"type": "place_road", "eid": edge})
    entries = g.scenario.fog.discoveries
    assert [d.reward_status for d in entries] == ["awarded", "unavailable", "unavailable"]
    assert entries[0].resource == "ore" and g.bank["ore"] == 0 and g.players[0].res["ore"] == 1
    assert g.occupied_e[edge] == 0
    g.bank["ore"] = 5
    reject(g, {"type": "place_road", "eid": edge})
    assert g.scenario.fog.discoveries == entries and g.players[0].res["ore"] == 1


def test_mixed_standard_gold_and_desert_rewards_share_one_ordered_discovery():
    g = fog_game(private_seed=6)  # Adjacent original IDs 0/1/4: Gold/Desert/Forest.
    g.phase, g.setup_idx, g.turn, g.rolled = "main", len(g.setup_order), 0, True
    edge = (0, 1)
    anchor_and_fund(g, edge)
    before = deepcopy(g)
    _, events = execute(g, {"type": "place_road", "eid": edge})
    assert [(d.tile_index, d.reward_status, d.resource) for d in g.scenario.fog.discoveries] == [
        (0, "pending", None), (1, "none", None), (4, "awarded", "wood")]
    assert g.players[0].res["wood"] == before.players[0].res["wood"]
    assert [e["tile"] for e in events if e["type"] == "discover_tile"] == [0, 1, 4]
    assert g.pending_gold == {0: 1}
    execute(g, {"type": "choose_gold", "res": "sheep"})
    assert g.scenario.fog.discoveries[0].resource == "sheep" and g.scenario.fog.continuation is None
    validate_fog_transition(before, g)


@pytest.mark.parametrize("reason", ["no_resources", "no_owner", "bad_edge", "supply", "not_turn", "not_rolled", "invalid_free"])
def test_rejected_road_leaves_entire_trusted_state_unchanged(reason):
    g = exploration_game("gold")
    edge = route_edge(g)
    anchor_and_fund(g, edge)
    cmd = {"type": "place_road", "eid": edge}
    pid = 0
    if reason == "no_resources": g.players[0].res["wood"] = 0
    elif reason == "no_owner": g.occupied_v.clear()
    elif reason == "bad_edge": cmd["eid"] = [9998, 9999]
    elif reason == "supply": g.rules_config.max_roads = 0
    elif reason == "not_turn": pid = 1
    elif reason == "not_rolled": g.rolled = False
    else: cmd["free"] = 1
    reject(g, cmd, pid=pid)


def test_unknown_terrain_does_not_affect_route_settlement_or_robber_legality():
    a, b = exploration_game("forest"), exploration_game("sea")
    # Both layouts have exactly the same public board/visibility. No actual
    # hidden land/sea assignment may decide any available command target.
    for g in (a, b):
        anchor_and_fund(g, route_edge(g))
        for r in RESOURCES:
            g.players[0].res[r] = 5
    assert board_legal_moves(a, 0, trusted_fog=True) == board_legal_moves(b, 0, trusted_fog=True)
    hidden = set(a.scenario.rules.fog.initially_hidden)
    unknown_edge = next(e for e, adj in a.edge_adj_hexes.items() if set(adj) <= hidden)
    unknown_vertex = next(v for v, adj in a.vertex_adj_hexes.items() if set(adj) <= hidden)
    for g in (a, b):
        assert not rules.can_place_road(g, 0, unknown_edge)
        assert not rules.can_place_ship(g, 0, unknown_edge)
        assert not rules.can_place_settlement(g, 0, unknown_vertex, require_road=False)
        g.pending_action, g.pending_pid = "robber_move", 0
    assert board_legal_moves(a, 0, trusted_fog=True) == board_legal_moves(b, 0, trusted_fog=True)
    for g in (a, b):
        for tile in hidden:
            for cmd in ("move_robber", "move_pirate"):
                reject(g, {"type": cmd, "tile": tile})


def test_unknown_production_and_second_setup_grant_no_hidden_resources_or_choices():
    g = exploration_game("gold", setup=True)
    g.setup_idx, g.turn = len(g.setup_order) - 1, 0
    legal = board_legal_moves(g, 0, trusted_fog=True)
    vertex = next(v for v in legal["settlements"]
                  if set(g.vertex_adj_hexes[v]).intersection(g.scenario.rules.fog.initially_hidden))
    # One existing settlement makes this the second accepted one for player 0.
    far = next(v for v in g.vertices if v != vertex and all(vertex not in e or v not in e for e in g.edges))
    g.occupied_v[far] = (0, 1)
    g.players[0].vp = 1
    before = deepcopy(g)
    _, events = execute(g, {"type": "place_settlement", "vid": vertex})
    known = [i for i in g.vertex_adj_hexes[vertex] if tile_is_known(g, i)]
    expected = {r: sum(TERRAIN_TO_RES[g.tiles[i].terrain] == r for i in known) for r in RESOURCES}
    assert g.players[0].res == expected and g.pending_action is None
    assert g.scenario.fog == before.scenario.fog
    assert not any(e["type"] == "discover_tile" for e in events)
    g.phase, g.setup_idx, g.rolled = "main", len(g.setup_order), False
    execute(g, {"type": "roll", "roll": 5})
    assert g.pending_action is None and not g.pending_gold
    assert g.scenario.fog == before.scenario.fog


def test_hidden_ordinary_production_is_ignored_until_revealed_and_city_does_not_reveal():
    g = exploration_game("forest")
    edge = route_edge(g)
    anchor_and_fund(g, edge)
    # Number 5 on every unknown forest. Isolate known production by blocking
    # their existing number-5 tiles; this changes no private assignment.
    g.robbers = [i for i, t in enumerate(g.tiles) if tile_is_known(g, i) and t.number == 5]
    g.robber_tile = g.robbers[0] if g.robbers else -1
    g.rolled = False
    before = dict(g.players[0].res)
    execute(g, {"type": "roll", "roll": 5})
    assert g.players[0].res == before and not g.scenario.fog.revealed
    for r, n in COST["city"].items():
        g.bank[r] -= n
        g.players[0].res[r] += n
    execute(g, {"type": "upgrade_city", "vid": edge[0]})
    assert not g.scenario.fog.revealed
    execute(g, {"type": "place_road", "eid": edge})
    assert g.scenario.fog.revealed
    g.rolled = False
    before = g.players[0].res["wood"]
    revealed_adjacent = len(set(g.vertex_adj_hexes[edge[0]]) & g.scenario.fog.revealed)
    execute(g, {"type": "roll", "roll": 5})
    assert g.players[0].res["wood"] == before + 2 * revealed_adjacent


def test_main_settlement_does_not_discover_adjacent_fog():
    g = exploration_game("gold")
    edge = route_edge(g)
    g.occupied_e[edge] = 0
    for r, n in COST["settlement"].items():
        g.bank[r] -= n
        g.players[0].res[r] += n
    before = deepcopy(g)
    execute(g, {"type": "place_settlement", "vid": edge[0]})
    assert g.occupied_v[edge[0]] == (0, 1)
    assert g.scenario.fog == before.scenario.fog and g.pending_action is None


def test_newly_known_land_can_anchor_later_settlement_and_known_gold_production():
    g = exploration_game("gold")
    edge = route_edge(g, minimum=3)
    anchor_and_fund(g, edge)
    unknown_vertex = next(v for v, adj in g.vertex_adj_hexes.items()
                          if set(adj) <= set(g.scenario.rules.fog.initially_hidden)
                          and set(adj).intersection(adjacent_hidden(g, edge)))
    assert not rules.can_place_settlement(g, 0, unknown_vertex, require_road=False)
    execute(g, {"type": "place_road", "eid": edge})
    execute(g, {"type": "choose_gold", "res": "ore", "qty": g.pending_gold[0]})
    assert any(is_known_land(g, i) for i in g.vertex_adj_hexes[unknown_vertex])
    # A separate established coastal arrival supplies road/ship connectivity;
    # distance remains authoritative even after the land becomes known.
    assert rules.can_place_settlement(g, 0, unknown_vertex, require_road=False) == all(
        v not in g.occupied_v for v in rules.edge_neighbors_of_vertex(g.edges, unknown_vertex))
    g.occupied_v[edge[0]] = (0, 2)
    before = deepcopy(g)
    g.rolled = False
    execute(g, {"type": "roll", "roll": 5})
    expected = 2 * sum(tile_is_known(g, i) and g.tiles[i].terrain == "gold" for i in g.vertex_adj_hexes[edge[0]])
    assert g.pending_gold == {0: expected}
    assert g.scenario.fog == before.scenario.fog and g.scenario.fog.continuation is None
    execute(g, {"type": "choose_gold", "res": "sheep", "qty": expected})
    assert g.scenario.fog == before.scenario.fog


@pytest.mark.parametrize("kind", ["place_road", "build_ship"])
@pytest.mark.parametrize("setup", [False, True])
def test_gold_continuation_resumes_exactly_once_after_last_choice(kind, setup):
    g = exploration_game("gold", setup=setup)
    if setup:
        g.setup_idx, g.turn = len(g.setup_order) - 1, 0
    edge = route_edge(g, kind)
    anchor_and_fund(g, edge, kind=kind, setup=setup)
    before = deepcopy(g)
    execute(g, {"type": kind, "eid": edge})
    count = len(adjacent_hidden(g, edge))
    assert g.pending_gold == {0: count} and g.pending_gold_queue == [0] and g.pending_pid == 0
    assert g.scenario.fog.continuation.command == kind
    assert g.scenario.fog.continuation.setup == setup
    assert g.setup_idx == before.setup_idx and g.turn == 0
    for cmd in ({"type": "end_turn"}, {"type": "roll", "roll": 2},
                {"type": "play_dev", "card": "road_building"}, {"type": "noop"},
                {"type": "place_road", "eid": edge}, {"type": "trade_bank", "give": "wood", "get": "ore"}):
        reject(g, cmd, code="pending_action")
    reject(g, {"type": "choose_gold", "res": "ore"}, pid=1)
    for remaining in range(count, 0, -1):
        before = deepcopy(g)
        execute(g, {"type": "choose_gold", "res": "ore"})
        assert g.players[0].res["ore"] == count - remaining + 1
        validate_fog_transition(before, g)
        if remaining > 1:
            assert g.setup_idx == before.setup_idx and g.pending_gold == {0: remaining - 1}
            g = loads_snapshot(json.dumps(encode_snapshot(g)))
    assert g.pending_action is None and g.pending_gold == {} and g.pending_gold_queue == []
    assert g.scenario.fog.continuation is None
    assert all(d.reward_status == "awarded" and d.resource == "ore" for d in g.scenario.fog.discoveries)
    if setup:
        assert g.setup_idx == len(g.setup_order) and g.phase == "main" and g.setup_anchor_vid is None
    reject(g, {"type": "choose_gold", "res": "ore"})
    assert loads_snapshot(json.dumps(encode_snapshot(g))) == g


@pytest.mark.parametrize("cmd", [
    {"type": "choose_gold", "res": "gold"}, {"type": "choose_gold", "res": "ore", "qty": 0},
    {"type": "choose_gold", "res": "ore", "qty": 99}, {"type": "choose_gold", "res": "ore", "qty": True},
    {"type": "choose_gold", "res": "ore", "qty": 1},
])
def test_invalid_pending_gold_preserves_entitlement_and_rewards(cmd):
    g = exploration_game("gold")
    edge = route_edge(g, minimum=3)
    anchor_and_fund(g, edge)
    execute(g, {"type": "place_road", "eid": edge})
    g.bank["ore"] = 0
    reject(g, cmd)
    assert g.pending_gold == {0: 3} and all(d.reward_status == "pending" for d in g.scenario.fog.discoveries)


def test_multiple_gold_resources_and_empty_bank_complete_remaining_as_unavailable():
    g = exploration_game("gold", setup=True)
    edge = route_edge(g, minimum=3)
    anchor_and_fund(g, edge, setup=True)
    g.bank = {r: 0 for r in RESOURCES}
    g.bank["ore"], g.bank["sheep"] = 1, 1
    execute(g, {"type": "place_road", "eid": edge})
    execute(g, {"type": "choose_gold", "res": "sheep"})
    execute(g, {"type": "choose_gold", "res": "ore"})
    assert [(d.reward_status, d.resource) for d in g.scenario.fog.discoveries] == [
        ("awarded", "sheep"), ("awarded", "ore"), ("unavailable", None)]
    assert g.setup_idx == 1 and g.turn == 1 and g.pending_action is None
    assert all(n == 0 for n in g.bank.values()) and g.scenario.fog.continuation is None
    validate_fog_state(g)


def test_non_host_discovery_assigns_gold_to_the_actual_current_player():
    g = exploration_game("gold")
    g.turn = 1
    edge = route_edge(g, minimum=3)
    anchor_and_fund(g, edge)
    execute(g, {"type": "place_road", "eid": edge})
    assert g.pending_gold == {1: 3} and g.pending_gold_queue == [1] and g.pending_pid == 1
    assert all(d.pid == 1 for d in g.scenario.fog.discoveries)
    reject(g, {"type": "choose_gold", "res": "ore"}, pid=0)
    execute(g, {"type": "choose_gold", "res": "ore", "qty": 3})
    assert g.players[1].res["ore"] == 3 and g.players[0].res["ore"] == 0
    assert g.scenario.fog.continuation is None


def test_initially_empty_bank_does_not_leave_impossible_gold_or_double_setup_advance():
    g = exploration_game("gold", setup=True)
    edge = route_edge(g, minimum=3)
    anchor_and_fund(g, edge, setup=True)
    g.bank = {r: 0 for r in RESOURCES}
    execute(g, {"type": "place_road", "eid": edge})
    assert g.occupied_e[edge] == 0 and g.setup_idx == 1 and g.turn == 1
    assert g.pending_action is None and not g.pending_gold and g.scenario.fog.continuation is None
    assert all(d.reward_status == "unavailable" for d in g.scenario.fog.discoveries)
    validate_fog_state(g)


def test_road_building_gold_does_not_lose_or_repeat_second_free_action():
    g = exploration_game("gold")
    edge = route_edge(g)
    anchor_and_fund(g, edge)
    g.players[0].dev_cards = [{"type": "road_building", "new": False}]
    g.rolled = False
    execute(g, {"type": "play_dev", "card": "road_building"})
    execute(g, {"type": "place_road", "eid": edge, "free": True})
    assert g.free_roads[0] == 1
    reject(g, {"type": "place_road", "eid": edge, "free": True}, code="pending_action")
    count = g.pending_gold[0]
    execute(g, {"type": "choose_gold", "res": "ore", "qty": count})
    assert g.free_roads[0] == 1 and not g.rolled
    second = next(e for e in sorted(g.edges) if rules.can_place_road(g, 0, e))
    execute(g, {"type": "place_road", "eid": second, "free": True})
    if g.pending_action:
        execute(g, {"type": "choose_gold", "res": "ore", "qty": g.pending_gold[0]})
    assert g.free_roads[0] == 0 and len(g.occupied_e) == 2
    execute(g, {"type": "roll", "roll": 2})
    execute(g, {"type": "end_turn"})
    assert g.free_roads[0] == 0 and len(g.occupied_e) == 2


def movement_fixture(terrain="forest"):
    g = exploration_game(terrain)
    target = route_edge(g, "build_ship")
    # Source at a different edge, but the destination is anchored by the same
    # own coastal building without relying on the ship being removed.
    source = next(e for e in sorted(g.edges) if e != target and target[0] in e
                  and rules._edge_has_sea(g, e) and not rules._edge_blocked_by_pirate(g, e))
    g.occupied_v[target[0]], g.occupied_ships[source] = (0, 1), 0
    return g, source, target


def test_move_ship_discovers_only_destination_and_preserves_movement_lifecycle():
    g, source, target = movement_fixture("gold")
    expected = adjacent_hidden(g, target)
    source_only = set(adjacent_hidden(g, source)) - set(expected)
    before = deepcopy(g)
    _, events = execute(g, {"type": "move_ship", "from_eid": source, "to_eid": target})
    assert source not in g.occupied_ships and g.occupied_ships[target] == 0
    assert g.scenario.fog.revealed == frozenset(expected) and not source_only.intersection(g.scenario.fog.revealed)
    assert [e["tile"] for e in events if e["type"] == "discover_tile"] == expected
    assert g.ship_moved_this_turn and g.scenario.fog.continuation.command == "move_ship"
    validate_fog_transition(before, g)
    g = loads_snapshot(json.dumps(encode_snapshot(g)))
    execute(g, {"type": "choose_gold", "res": "ore", "qty": len(expected)})
    reject(g, {"type": "move_ship", "from_eid": target, "to_eid": source})
    execute(g, {"type": "end_turn"})
    assert not g.ship_moved_this_turn and not g.ships_built_this_turn


def test_source_removal_does_not_reveal_a_source_only_hidden_tile():
    source = fog_recipe()
    original = rules.build_game(9, 2, map_id="seafarers_simple_2")
    hidden = {0, 4, 8, 14, 21, 27, 32, 36}
    source["tiles"] = [{"q": t.q, "r": t.r, "terrain": "fog" if i in hidden else t.terrain,
                        "number": None if i in hidden else t.number} for i, t in enumerate(original.tiles)]
    source["fog_pool"] = {"terrain": ["gold"] * 8, "numbers": [5] * 8}
    g = fog_game(data=source)
    g.phase, g.setup_idx, g.turn, g.rolled = "main", len(g.setup_order), 0, True
    from_edge, to_edge = (19, 20), (10, 15)
    assert adjacent_hidden(g, from_edge) == [4] and adjacent_hidden(g, to_edge) == [8]
    g.occupied_v = {19: (0, 1), 10: (0, 1)}
    g.occupied_ships[from_edge] = 0
    execute(g, {"type": "move_ship", "from_eid": from_edge, "to_eid": to_edge})
    assert g.scenario.fog.revealed == frozenset({8})
    assert 4 not in g.scenario.fog.revealed and g.pending_gold == {0: 1}


def test_built_ship_age_survives_gold_completion_and_snapshot_recovery():
    g = exploration_game("gold")
    edge = route_edge(g, "build_ship")
    anchor_and_fund(g, edge, kind="build_ship")
    execute(g, {"type": "build_ship", "eid": edge})
    g = loads_snapshot(json.dumps(encode_snapshot(g)))
    execute(g, {"type": "choose_gold", "res": "ore", "qty": g.pending_gold[0]})
    destination = next(e for e in sorted(g.edges) if rules.can_place_ship(g, 0, e, excluded_edge=edge))
    reject(g, {"type": "move_ship", "from_eid": edge, "to_eid": destination})
    assert edge in g.ships_built_this_turn and not g.ship_moved_this_turn


@pytest.mark.parametrize("restriction", ["source_pirate", "target_pirate", "new_ship", "already_moved", "foreign_owner"])
def test_rejected_move_cannot_reveal_or_award(restriction):
    g, source, target = movement_fixture()
    if restriction == "source_pirate":
        g.pirate_tile = next(i for i in g.edge_adj_hexes[source] if is_known_sea(g, i))
    elif restriction == "target_pirate":
        g.pirate_tile = next(i for i in g.edge_adj_hexes[target] if is_known_sea(g, i))
    elif restriction == "new_ship": g.ships_built_this_turn.add(source)
    elif restriction == "already_moved": g.ship_moved_this_turn = True
    else: g.occupied_ships[source] = 1
    reject(g, {"type": "move_ship", "from_eid": source, "to_eid": target})


@pytest.mark.parametrize("state", ["setup", "build", "free", "move", "robber", "pending_gold"])
def test_legal_simulation_leaves_live_board_history_bank_events_and_continuation_isolated(state):
    g = exploration_game("gold", setup=state == "setup")
    edge = route_edge(g)
    anchor_and_fund(g, edge, setup=state == "setup")
    if state == "free": g.free_roads[0] = 2
    if state == "move": g, _, _ = movement_fixture("gold")
    if state == "robber": g.pending_action, g.pending_pid = "robber_move", 0
    if state == "pending_gold": execute(g, {"type": "place_road", "eid": edge})
    before = deepcopy(g)
    first = board_legal_moves(g, g.turn, trusted_fog=True)
    assert board_legal_moves(g, g.turn, trusted_fog=True) == first
    assert g == before and encode_snapshot(g) == encode_snapshot(before)
    if state not in ("robber", "pending_gold"):
        assert first["roads"] or first["ships"] or first["move_ship"]["sources"]


def test_fog_current_player_victory_waits_for_gold_not_for_another_players_turn():
    g = exploration_game("gold")
    edge = route_edge(g, minimum=3)
    anchor_and_fund(g, edge)
    g.players[0].vp, g.players[1].vp = 24, 30
    execute(g, {"type": "place_road", "eid": edge})
    assert not g.game_over and g.pending_gold
    execute(g, {"type": "choose_gold", "res": "ore", "qty": g.pending_gold[0]})
    assert g.game_over and g.winner_pid == 0 and g.scenario.fog.continuation is None


@pytest.mark.parametrize("starting_vp", [7, 8])
def test_actual_longest_route_award_checks_only_current_player_after_gold(starting_vp):
    from tests.test_seafarers_routes import path
    from tests.test_seafarers_ships import graph_game
    edges = path(0, 5)
    g = graph_game(edges, roads=edges[:4], buildings={0: (0, 1)})
    g.tiles[2].terrain, g.tiles[2].number = "gold", 5
    g.vertex_adj_hexes[5].append(2)
    g.rules_config.enable_gold, g.rules_config.target_vp = True, 10
    g.scenario.rules = ScenarioRules(fog=FogRules(initially_hidden=(2,)))
    g.scenario.fog = initial_fog_state(g.board, g.scenario.rules.fog)
    g.players[0].vp, g.players[1].vp = starting_vp, 10
    execute(g, {"type": "place_road", "eid": edges[-1]})
    assert g.longest_road_owner == 0 and g.longest_road_len == 5
    assert g.players[0].vp == starting_vp + 2 and not g.game_over and g.pending_gold == {0: 1}
    execute(g, {"type": "choose_gold", "res": "ore"})
    if starting_vp == 8:
        assert g.game_over and g.winner_pid == 0
    else:
        assert not g.game_over
        execute(g, {"type": "end_turn"})
        assert g.turn == 1 and g.game_over and g.winner_pid == 1


def test_pending_setup_gold_before_route_remains_distinct_from_discovery_continuation():
    source = fog_recipe()
    # Visible Gold is a normal initial-resource entitlement, not an exploration.
    visible = next(t for t in source["tiles"] if t["terrain"] == "forest")
    visible["terrain"] = "gold"
    g = fog_game(data=source)
    g.setup_idx, g.turn = len(g.setup_order) - 1, 0
    gold = next(i for i, t in enumerate(g.tiles) if tile_is_known(g, i) and t.terrain == "gold")
    vertex = next(v for v in board_legal_moves(g, 0, trusted_fog=True)["settlements"] if gold in g.vertex_adj_hexes[v])
    far = next(v for v in g.vertices if v != vertex and all(vertex not in e or v not in e for e in g.edges))
    g.occupied_v[far] = (0, 1)
    execute(g, {"type": "place_settlement", "vid": vertex})
    assert g.pending_gold and g.scenario.fog.continuation is None
    execute(g, {"type": "choose_gold", "res": "ore", "qty": g.pending_gold[0]})
    assert g.phase == "setup" and g.setup_idx == 3 and g.setup_need == "road" and g.setup_anchor_vid == vertex
    assert not g.scenario.fog.revealed
