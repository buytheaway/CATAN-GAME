"""S2A topology plus executable setup/expansion; funding is explicit test setup."""
import json
import random
from collections import deque
from copy import deepcopy
from pathlib import Path

import pytest

from app.engine import maps, rules, serialize
from app.engine.legal import board_legal_moves
from app.engine.state import COST, RESOURCES
from app.engine.topology import coastal_edges, island_ids, land_components
from app.persistence import snapshots

SEAFARERS = [p["id"] for p in maps.PRESET_REGISTRY if p["id"].startswith("seafarers_")]
EXPECTED = {"seafarers_simple_1": (19, [13], 6),
            "seafarers_simple_2": (37, [19], 18),
            "seafarers_gold_haven": (37, [8, 7], 22),
            "seafarers_pirate_lanes": (37, [7, 6], 24)}


def sea_components(board):
    remaining = {i for i, t in enumerate(board.tiles) if t.terrain == "sea"}
    result = []
    while remaining:
        todo, found = [min(remaining)], set()
        while todo:
            tile = todo.pop()
            if tile in found:
                continue
            found.add(tile)
            todo.extend(i for adjacent in board.edge_adj_hexes.values() if tile in adjacent
                        for i in adjacent if i in remaining and i not in found)
        remaining.difference_update(found)
        result.append(found)
    return result


def choose_gold(g):
    while g.pending_action == "choose_gold":
        resource = next(r for r in RESOURCES if g.bank[r])
        rules.apply_cmd(g, g.pending_pid, {"type": "choose_gold", "res": resource})


def setup(g, seed=0, prefer_ship=False):
    rng = random.Random(seed)
    while g.phase == "setup":
        choose_gold(g)
        pid = g.turn
        if g.setup_need == "settlement":
            legal = [v for v in sorted(g.vertices) if rules.can_place_settlement(g, pid, v, False)]
            assert legal, "setup must not run out of land intersections"
            if prefer_ship:
                coastal = [v for v in legal if any(rules._edge_has_sea(g, e)
                           and not rules._edge_blocked_by_pirate(g, e) for e in g.edges if v in e)]
                legal = coastal or legal
            rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": rng.choice(legal), "setup": True})
        else:
            roads = [e for e in sorted(g.edges) if rules.can_place_road(g, pid, e, g.setup_anchor_vid)]
            ships = [e for e in sorted(g.edges) if rules.can_place_ship(g, pid, e, g.setup_anchor_vid)]
            choices = ships if prefer_ship and ships else roads or ships
            assert choices, "every chosen starting settlement needs an anchored route"
            edge = rng.choice(choices)
            rules.apply_cmd(g, pid, {"type": "build_ship" if choices is ships else "place_road",
                                      "eid": edge, "setup": True})
    choose_gold(g)


def fund(g, cost):
    missing = {r: max(0, q - g.players[g.turn].res[r]) for r, q in cost.items()}
    rules.apply_cmd(g, g.turn, {"type": "grant_resources", "res": missing})


def sea_path(g, pid):
    islands = island_ids(g.board)
    for anchor, (owner, _) in sorted(g.occupied_v.items()):
        if owner != pid:
            continue
        home = {islands[i] for i in g.vertex_adj_hexes[anchor] if i in islands}
        queue, visited = deque([(anchor, [])]), {anchor}
        while queue:
            vertex, path = queue.popleft()
            destination = {islands[i] for i in g.vertex_adj_hexes[vertex] if i in islands}
            if path and destination - home and rules.can_place_settlement(g, pid, vertex, False):
                return vertex, path
            for edge in sorted(g.edges):
                if vertex not in edge or not rules._edge_has_sea(g, edge) or rules._edge_blocked_by_pirate(g, edge):
                    continue
                if edge in g.occupied_e or g.occupied_ships.get(edge, pid) != pid:
                    continue
                neighbor = edge[0] if vertex == edge[1] else edge[1]
                if neighbor in visited or g.occupied_v.get(neighbor, (pid,))[0] != pid:
                    continue
                visited.add(neighbor)
                queue.append((neighbor, path + [edge]))
    raise AssertionError("no navigable ship path to a free intersection on another island")


def road_expansion(g, pid):
    starts = {v for v, (owner, _) in g.occupied_v.items() if owner == pid}
    starts.update(v for edge, owner in g.occupied_e.items() if owner == pid for v in edge)
    queue, visited = deque((v, []) for v in sorted(starts)), set(starts)
    while queue:
        vertex, path = queue.popleft()
        if path and rules.can_place_settlement(g, pid, vertex, False):
            return path
        for edge in sorted(g.edges):
            if vertex not in edge or rules._edge_is_sea(g, edge) or edge in g.occupied_ships:
                continue
            if g.occupied_e.get(edge, pid) != pid:
                continue
            neighbor = edge[0] if edge[1] == vertex else edge[1]
            if neighbor in visited or g.occupied_v.get(neighbor, (pid,))[0] != pid:
                continue
            visited.add(neighbor)
            queue.append((neighbor, path + [edge]))
    raise AssertionError("no road expansion to an available land intersection")


@pytest.mark.parametrize("preset", [p["id"] for p in maps.PRESET_REGISTRY])
def test_all_presets_have_deterministic_nonoverlapping_geometry_and_real_ports(preset):
    for seed in range(1, 21):
        g = rules.build_game(seed, 2, map_id=preset)
        assert g == rules.build_game(seed, 2, map_id=preset)
        assert len({(t.q, t.r) for t in g.tiles}) == len(g.tiles)
        assert all(len(h) in (1, 2) for h in g.edge_adj_hexes.values())
        assert all(len(h) <= 3 for h in g.vertex_adj_hexes.values())
        assert len(g.ports) == 9
        assert {e for e, _ in g.ports} <= coastal_edges(g.board)
        assert len({v for e, _ in g.ports for v in e}) == 18
        assert sorted(kind for _, kind in g.ports) == sorted(maps.DEFAULT_PORT_DECK)
        ids = island_ids(g.board)
        assert ids == island_ids(snapshots.loads_snapshot(snapshots.dumps_snapshot(g)).board)
        assert set(ids) == {i for i, t in enumerate(g.tiles) if t.terrain != "sea"}
        if preset in EXPECTED:
            tiles, sizes, sea = EXPECTED[preset]
            assert len(g.tiles) == tiles
            assert [len(c) for c in land_components(g.board).values()] == sizes
            assert sum(t.terrain == "sea" for t in g.tiles) == sea
            assert {rules.TERRAIN_TO_RES[t.terrain] for t in g.tiles} >= set(RESOURCES)
            if len(sizes) > 1:
                assert len(sea_components(g.board)) == 1
                # Even vertex-level contact cannot create an accidental land bridge.
                assert all(len({ids[i] for i in h if i in ids}) <= 1 for h in g.vertex_adj_hexes.values())
        else:
            assert len(g.tiles) == 19 and len(land_components(g.board)) == 1


@pytest.mark.parametrize("preset", SEAFARERS)
@pytest.mark.parametrize("players", range(2, 7))
def test_seafarers_setup_completes_for_room_player_counts_without_start_island_restrictions(preset, players):
    for seed in range(1, 31):
        g = rules.build_game(seed, players, map_id=preset)
        setup(g, seed, prefer_ship=seed % 2 == 0)
        assert g.phase == "main" and g.turn == 0
        assert all(sum(owner == pid for owner, _ in g.occupied_v.values()) == 2 for pid in range(players))
        assert len(g.occupied_e) + len(g.occupied_ships) == 2 * players
        assert not g.ships_built_this_turn and not g.ship_moved_this_turn
        assert all(g.bank[r] >= 0 for r in RESOURCES)


@pytest.mark.parametrize("preset", ["seafarers_gold_haven", "seafarers_pirate_lanes"])
def test_real_preset_paid_ships_reach_other_island_and_ordinary_settlement(preset):
    g = rules.build_game(17, 2, map_id=preset)
    setup(g, 17, prefer_ship=True)
    rules.apply_cmd(g, 0, {"type": "roll", "roll": 2})
    choose_gold(g)
    destination, path = sea_path(g, 0)
    ids = island_ids(g.board)
    home = {ids[t] for t in g.vertex_adj_hexes[path[0][0]] if t in ids} | {
        ids[t] for t in g.vertex_adj_hexes[path[0][1]] if t in ids}
    assert {ids[t] for t in g.vertex_adj_hexes[destination] if t in ids} - home
    for edge in path:
        if edge in g.occupied_ships:
            continue
        fund(g, COST["ship"])
        assert list(edge) in board_legal_moves(g, 0)["ships"]
        rules.apply_cmd(g, 0, {"type": "build_ship", "eid": edge})
    fund(g, COST["settlement"])
    assert destination in board_legal_moves(g, 0)["settlements"]
    before = deepcopy(g)
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": destination})
    assert g.occupied_v[destination] == (0, 1)
    assert g.players[0].vp == before.players[0].vp + 1  # No S2B island reward.
    assert snapshots.loads_snapshot(snapshots.dumps_snapshot(g)) == g


@pytest.mark.parametrize("preset", SEAFARERS)
def test_existing_victory_target_is_reachable_with_legal_paid_actions(preset):
    g = rules.build_game(17, 2, map_id=preset)
    setup(g, 17)
    rules.apply_cmd(g, 0, {"type": "roll", "roll": 2})
    choose_gold(g)
    for _ in range(60):
        if g.game_over:
            break
        settlements = [v for v, (owner, level) in g.occupied_v.items() if owner == 0 and level == 1]
        cities = rules._count_cities(g, 0)
        if settlements and cities < g.rules_config.max_cities:
            fund(g, COST["city"])
            rules.apply_cmd(g, 0, {"type": "upgrade_city", "vid": settlements[0]})
            continue
        legal = [v for v in sorted(g.vertices) if rules.can_place_settlement(g, 0, v, True)]
        if legal:
            fund(g, COST["settlement"])
            rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": legal[0]})
            continue
        path = road_expansion(g, 0)
        for edge in path:
            if edge not in g.occupied_e:
                fund(g, COST["road"])
                rules.apply_cmd(g, 0, {"type": "place_road", "eid": edge})
                if g.game_over:
                    break
    assert g.game_over and g.winner_pid == 0 and g.players[0].vp >= g.rules_config.target_vp == 10
    assert all(n >= 0 for n in g.bank.values())
    assert snapshots.loads_snapshot(snapshots.dumps_snapshot(g)) == g


@pytest.mark.parametrize("preset", SEAFARERS)
def test_each_required_resource_has_working_production_and_bank_trade(preset):
    initial = rules.build_game(17, 2, map_id=preset)
    for resource in RESOURCES:
        g = deepcopy(initial)
        tile = next(i for i, t in enumerate(g.tiles) if rules.TERRAIN_TO_RES[t.terrain] == resource)
        vertex = next(v for v, h in g.vertex_adj_hexes.items() if tile in h)
        assert rules.can_place_settlement(g, 0, vertex, False)
        g.occupied_v[vertex] = (0, 1)  # Controlled production fixture, not natural setup.
        g.phase = "main"
        rules.apply_cmd(g, 0, {"type": "roll", "roll": g.tiles[tile].number})
        assert g.players[0].res[resource] >= 1
        choose_gold(g)
        fund(g, {resource: 4})
        target = next(r for r in RESOURCES if r != resource)
        rate = rules.best_trade_rate(g, 0, resource)
        before = g.players[0].res[target]
        rules.apply_cmd(g, 0, {"type": "trade_bank", "give": resource, "get": target})
        assert g.players[0].res[target] == before + 1 and rate in (2, 3, 4)


@pytest.mark.parametrize("trigger", ["seven", "knight"])
@pytest.mark.parametrize("figure", ["robber", "pirate"])
def test_offboard_robber_seven_knight_and_single_figure_choice(trigger, figure):
    g = rules.build_game(11, 2, map_id="seafarers_gold_haven")
    assert g.robber_tile == -1 and g.robbers == [-1]
    assert snapshots.loads_snapshot(snapshots.dumps_snapshot(g)) == g
    setup(g, 4)
    # Keep small hands for the trigger; no resource scarcity policy is under test.
    for player in g.players:
        for r in RESOURCES:
            g.bank[r] += player.res[r]
            player.res[r] = 0
    if trigger == "seven":
        rules.apply_cmd(g, 0, {"type": "roll", "roll": 7})
    else:
        g.dev_deck.remove("knight")
        g.players[0].dev_cards = [{"type": "knight", "new": False}]
        rules.apply_cmd(g, 0, {"type": "play_dev", "card": "knight"})
    before = deepcopy(g)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(g, 0, {"type": "move_robber", "tile": -1})
    assert g == before
    legal = board_legal_moves(g, 0)
    assert legal["robber_tiles"] == [i for i, t in enumerate(g.tiles) if t.terrain != "sea"]
    tile = legal[figure + "_tiles"][0]
    rules.apply_cmd(g, 0, {"type": "move_" + figure, "tile": tile})
    assert g.pending_action is None
    if figure == "robber":
        assert g.robbers == [tile] and g.robber_tile == tile
    else:
        assert g.robbers == [-1] and g.robber_tile == -1 and g.pirate_tile == tile
    assert snapshots.loads_snapshot(snapshots.dumps_snapshot(g)) == g
    rejected = deepcopy(g)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(g, 0, {"type": "move_" + figure, "tile": tile})
    assert g == rejected


def test_historical_s1_board_is_not_regenerated_or_port_repaired_on_decode(monkeypatch):
    raw = Path(__file__).with_name("fixtures").joinpath("s1_gold_haven_v2.json").read_text()
    def forbidden(*args, **kwargs):
        raise AssertionError("recovery must not rebuild the preset")
    monkeypatch.setattr(rules, "build_game", forbidden)
    monkeypatch.setattr(maps, "build_board_from_map", forbidden)
    g = snapshots.loads_snapshot(raw)
    assert len(g.tiles) == 19 and len(land_components(g.board)) == 1
    assert g.robber_tile == 0 and g.tiles[0].terrain == "gold"
    assert any(e not in coastal_edges(g.board) for e, _ in g.ports)
    from tests.test_persistence_snapshots import released_v2_payload
    assert released_v2_payload(g) == json.loads(raw)
    assert snapshots.decode_snapshot(snapshots.encode_snapshot(g)) == g
    assert snapshots.loads_snapshot(snapshots.dumps_snapshot(g)) == g


def test_authored_ports_keep_identity_order_and_correct_maritime_rates():
    g = rules.build_game(1, 2, map_id="seafarers_gold_haven")
    data = deepcopy(maps.get_preset_map(g.map_id))
    data["ports"] = [{"edge": list(edge), "type": kind} for edge, kind in g.ports]
    authored = rules.build_game(1, 2, map_data=data)
    assert authored.ports == g.ports
    assert rules.best_trade_rate(authored, 0, "wood") == 4
    for edge, kind in authored.ports:
        authored.occupied_v = {edge[0]: (0, 1)}
        for resource in RESOURCES:
            expected = 3 if kind == "3:1" else 2 if kind == "2:1:" + resource else 4
            assert rules.best_trade_rate(authored, 0, resource) == expected


@pytest.mark.parametrize("bad", ["duplicate", "boolean_coordinate", "terrain_deck", "number_deck",
                                 "sea_robber", "land_pirate", "interior_port", "sea_port", "overlap_port"])
def test_invalid_map_topology_and_figure_or_port_references_reject_without_mutating_input(bad):
    data = deepcopy(maps.get_preset_map("seafarers_gold_haven"))
    g = rules.build_game(1, 2, map_data=data)
    if bad == "duplicate":
        data["tiles"].append(deepcopy(data["tiles"][0]))
    elif bad == "boolean_coordinate":
        data["tiles"][0]["q"] = True
    elif bad == "terrain_deck":
        data["terrain_deck"][0] = "lava"
    elif bad == "number_deck":
        data["number_deck"][0] = 7
    elif bad == "sea_robber":
        data["robber_tile"] = next(i for i, t in enumerate(g.tiles) if t.terrain == "sea")
    elif bad == "land_pirate":
        data["pirate_tile"] = next(i for i, t in enumerate(g.tiles) if t.terrain != "sea")
    elif bad == "overlap_port":
        edge = next(iter(coastal_edges(g.board)))
        data["ports"] = [{"edge": list(edge), "type": "3:1"}] * 2
    else:
        edges = (e for e, h in g.edge_adj_hexes.items()
                 if all(g.tiles[i].terrain == "sea" for i in h)) if bad == "sea_port" else (
                     e for e, h in g.edge_adj_hexes.items()
                     if len(h) == 2 and all(g.tiles[i].terrain != "sea" for i in h))
        edge = next(edges)
        data["ports"] = [{"edge": list(edge), "type": "3:1"}]
    before = deepcopy(data)
    with pytest.raises(maps.MapValidationError):
        rules.build_game(1, 2, map_data=data)
    assert data == before


@pytest.mark.parametrize("field,value", [("robber_tile", -2), ("robbers", [-2]), ("pirate_tile", -1)])
def test_offboard_extension_does_not_accept_other_invalid_snapshot_references(field, value):
    payload = snapshots.encode_snapshot(rules.build_game(1, 2, map_id="seafarers_gold_haven"))
    payload["state"][field] = value
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)


def test_frozen_v1_does_not_accept_v2_offboard_domain():
    from tests.test_persistence_snapshots import released_v2_payload
    payload = released_v2_payload(rules.build_game(1, 2, map_id="seafarers_gold_haven"))
    payload["snapshot_version"] = 1
    del payload["state"]["ships_built_this_turn"]
    del payload["state"]["ship_moved_this_turn"]
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("preset", ["seafarers_gold_haven", "seafarers_pirate_lanes"])
def test_browser_geometry_fixture_matches_actual_python_snapshot(preset):
    path = Path(__file__).resolve().parents[1] / "web/tests/fixtures/s2a-boards.json"
    fixture = json.loads(path.read_text())[preset]
    actual = serialize.to_player_dict(rules.build_game(17, 2, map_id=preset), 0)
    assert fixture == {key: actual[key] for key in fixture}
