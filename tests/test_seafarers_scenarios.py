"""Explicit custom configurations; existing named presets keep their rules.

Setup and expansion use real materialized boards and apply_cmd. Resource grants
are declared test funding, not claims of full natural matches.
"""
from collections import deque
from copy import deepcopy
from pathlib import Path
import json
import random

import pytest

from app.engine import maps, rules, serialize
from app.engine.legal import board_legal_moves
from app.engine.scenario import vertex_islands
from app.engine.state import COST, ScenarioRules, ScenarioState
from app.persistence import snapshots
from tests.test_persistence_snapshots import released_v1_payload, released_v2_payload, released_v3_payload
from tests.test_seafarers_maps import setup, fund, sea_path


def scenario_map(preset="seafarers_gold_haven", *, bonus=2, restricted=True, target=12):
    data = deepcopy(maps.get_preset_map(preset))
    data["name"] = f"S2B-1 custom test: {preset}"
    data["rules"]["target_vp"] = target
    data["rules"]["scenario"] = {"new_island_vp": bonus}
    if restricted:
        data["rules"]["scenario"]["starting_islands"] = [4 if preset == "seafarers_gold_haven" else 9]
    return data


def scenario_game(*, bonus=2, target=12):
    g = rules.build_game(17, 2, map_id="custom-s2b", map_data=scenario_map(bonus=bonus, target=target))
    setup(g, 1, prefer_ship=True)
    rules.apply_cmd(g, g.turn, {"type": "roll", "roll": 2})
    return g


def arrive(g):
    destination, path = sea_path(g, g.turn)
    for edge in path:
        if edge not in g.occupied_ships:
            fund(g, COST["ship"])
            rules.apply_cmd(g, g.turn, {"type": "build_ship", "eid": edge})
    fund(g, COST["settlement"])
    return destination


def second_foreign_settlement(g, anchor):
    roots = vertex_islands(g.board, anchor)
    queue, seen = deque([(anchor, [])]), {anchor}
    while queue:
        v, path = queue.popleft()
        if path and vertex_islands(g.board, v) == roots and rules.can_place_settlement(g, g.turn, v, False):
            for edge in path:
                fund(g, COST["road"])
                rules.apply_cmd(g, g.turn, {"type": "place_road", "eid": edge})
            fund(g, COST["settlement"])
            rules.apply_cmd(g, g.turn, {"type": "place_settlement", "vid": v})
            return v
        for edge in sorted(g.edges):
            if v not in edge or rules._edge_is_sea(g, edge) or edge in g.occupied_ships:
                continue
            other = edge[0] if v == edge[1] else edge[1]
            if (other in seen or g.occupied_v.get(other, (g.turn,))[0] != g.turn
                    or g.occupied_e.get(edge, g.turn) != g.turn):
                continue
            seen.add(other)
            queue.append((other, path + [edge]))
    raise AssertionError("no second legal island settlement")


@pytest.mark.parametrize("preset", ["seafarers_gold_haven", "seafarers_pirate_lanes"])
@pytest.mark.parametrize("players", range(2, 7))
def test_restricted_setup_completes_snake_for_supported_counts_without_deadlocks(preset, players):
    # Different choices/seeds exercise the capacity guard, not ten duplicate tests.
    for seed in range(10):
        g = rules.build_game(seed, players, map_data=scenario_map(preset))
        setup(g, seed, prefer_ship=True)
        allowed = set(g.scenario.rules.starting_islands)
        assert all(vertex_islands(g.board, vid) <= allowed for vid in g.occupied_v)
        assert all(ids == allowed for ids in g.scenario.home_islands.values())
        assert not g.scenario.awarded_islands
        assert all(p.vp == 2 for p in g.players)
        assert len(g.occupied_v) == 2 * players
        assert snapshots.decode_snapshot(snapshots.encode_snapshot(g)) == g


def test_foreign_setup_command_is_atomic_and_legal_projection_filters_it():
    g = rules.build_game(17, 2, map_data=scenario_map())
    plain = deepcopy(g)
    plain.scenario = ScenarioState()
    allowed = board_legal_moves(g, 0)["settlements"]
    foreign = next(v for v in board_legal_moves(plain, 0)["settlements"] if vertex_islands(g.board, v) == {13})
    assert foreign not in allowed and allowed
    before = snapshots.encode_snapshot(g)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": foreign, "setup": True})
    assert snapshots.encode_snapshot(g) == before
    # A coastal opening keeps BOTH anchored route choices.
    vid = next(v for v in allowed if any(rules._edge_has_sea(g, e) and not rules._edge_blocked_by_pirate(g, e)
                                       for e in g.edges if v in e))
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": vid, "setup": True})
    legal = board_legal_moves(g, 0)
    assert legal["roads"] and legal["ships"]


def test_unsafe_opening_is_rejected_before_it_can_deadlock_restricted_setup():
    g = rules.build_game(1, 6, map_data=scenario_map())
    rng = random.Random(0)
    saw_guard = False
    while g.phase == "setup":
        if g.setup_need == "road":
            edge = board_legal_moves(g, g.turn)["roads"][0]
            rules.apply_cmd(g, g.turn, {"type": "place_road", "eid": edge, "setup": True})
            continue
        plain = deepcopy(g)
        plain.scenario.rules = ScenarioRules(None, 2)
        ordinary = {v for v in board_legal_moves(plain, g.turn)["settlements"]
                    if vertex_islands(g.board, v) == {4}}
        legal = set(board_legal_moves(g, g.turn)["settlements"])
        assert legal
        if ordinary - legal:
            saw_guard = True
            before = deepcopy(g)
            with pytest.raises(rules.RuleError):
                rules.apply_cmd(g, g.turn, {"type": "place_settlement", "vid": min(ordinary - legal)})
            assert g == before
        rules.apply_cmd(g, g.turn, {"type": "place_settlement", "vid": rng.choice(sorted(legal))})
    assert saw_guard


@pytest.mark.parametrize("bonus", [0, 1, 2, 3])
def test_configured_bonus_is_added_once_and_cities_further_settlements_do_not_repeat(bonus):
    g = scenario_game(bonus=bonus)
    destination = arrive(g)
    before = g.players[0].vp
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": destination})
    assert g.players[0].vp == before + 1 + bonus
    assert g.scenario.awarded_islands == ({0: {13}} if bonus else {})
    after_first = deepcopy(g)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": destination})
    assert g == after_first
    fund(g, COST["city"])
    before = g.players[0].vp
    rules.apply_cmd(g, 0, {"type": "upgrade_city", "vid": destination})
    assert g.players[0].vp == before + 1
    ledger = deepcopy(g.scenario.awarded_islands)
    second_foreign_settlement(g, destination)
    assert g.scenario.awarded_islands == ledger


def test_each_players_bonus_is_independent_and_home_islands_never_qualify():
    # Real paid ship expansion by each owner, ending/rolling between them.
    g = scenario_game()
    for pid in (0, 1):
        if pid:
            rules.apply_cmd(g, 0, {"type": "end_turn"})
            rules.apply_cmd(g, 1, {"type": "roll", "roll": 2})
        destination = arrive(g)
        rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": destination})
        assert g.scenario.awarded_islands[pid] == {13}
    assert g.scenario.home_islands == {0: {4}, 1: {4}}
    # A second home-island settlement outside setup gives only ordinary VP.
    from tests.test_seafarers_maps import road_expansion
    rules.apply_cmd(g, 1, {"type": "end_turn"})
    rules.apply_cmd(g, 0, {"type": "roll", "roll": 2})
    path = road_expansion(g, 0)
    for edge in path:
        fund(g, COST["road"])
        rules.apply_cmd(g, 0, {"type": "place_road", "eid": edge})
    vertex = next(v for v in path[-1] if rules.can_place_settlement(g, 0, v, True))
    assert vertex_islands(g.board, vertex) == {4}
    ledger = deepcopy(g.scenario.awarded_islands)
    fund(g, COST["settlement"])
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": vertex})
    assert g.scenario.awarded_islands == ledger


def test_unrestricted_setup_can_establish_multiple_home_islands_without_bonus():
    g = rules.build_game(1, 2, map_data=scenario_map(restricted=False))
    opening_roots = [4, 13, 4, 13]
    for root in opening_roots:
        legal = board_legal_moves(g, g.turn)
        vid = next(v for v in legal["settlements"] if vertex_islands(g.board, v) == {root})
        rules.apply_cmd(g, g.turn, {"type": "place_settlement", "vid": vid})
        legal = board_legal_moves(g, g.turn)
        rules.apply_cmd(g, g.turn, {"type": "place_road", "eid": legal["roads"][0]})
    assert g.scenario.home_islands == {0: {4, 13}, 1: {4, 13}}
    assert not g.scenario.awarded_islands and all(p.vp == 2 for p in g.players)


@pytest.mark.parametrize("invalid", ["resource", "owner", "not_rolled", "coordinate"])
def test_rejected_bonus_attempt_never_mutates_history_or_vp(invalid):
    g = scenario_game()
    destination = arrive(g)
    pid, command = 0, {"type": "place_settlement", "vid": destination}
    if invalid == "resource":
        g.players[0].res["wheat"] = 0
    elif invalid == "owner":
        pid = 1
    elif invalid == "not_rolled":
        g.rolled = False
    else:
        command["vid"] = -1
    before = snapshots.encode_snapshot(g)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(g, pid, command)
    assert snapshots.encode_snapshot(g) == before


def test_bonus_public_vp_hidden_dev_vp_and_achievement_points_can_win_only_on_own_turn():
    g = scenario_game(target=8)
    destination = arrive(g)
    # Explicit VP/achievement fixture isolates timing, not a natural full game.
    g.players[0].dev_cards = [{"type": "victory_point", "new": False}]
    g.players[0].vp = 5  # Includes the hidden VP and an existing public achievement.
    g.largest_army_owner, g.largest_army_size = 0, 3
    g.players[0].knights_played = 3
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": destination})
    assert g.players[0].vp == 8 and g.game_over and g.winner_pid == 0
    assert serialize.to_player_dict(g, 1)["players"][0]["vp"] == 8
    g.game_over, g.winner_pid, g.turn = False, None, 1
    own, other = serialize.to_player_dict(g, 0), serialize.to_player_dict(g, 1)
    assert own["players"][0]["vp"] == 8 and other["players"][0]["vp"] == 7
    assert other["players"][0]["special_vp"] == 2
    assert "res" not in other["players"][0] and "dev_cards" not in other["players"][0]
    assert {"seed", "dev_deck", "bank"}.isdisjoint(other)
    rules.check_win(g)
    assert not g.game_over
    g.rolled = True
    rules.apply_cmd(g, 1, {"type": "end_turn"})
    assert g.game_over and g.winner_pid == 0


@pytest.mark.parametrize("bad", [None, [], {"unknown": 2}, {"new_island_vp": True}, {"new_island_vp": -1},
    {"new_island_vp": 11}, {"starting_islands": []}, {"starting_islands": [4, 4]},
    {"starting_islands": [True]}, {"starting_islands": [999]}, {"starting_islands": [0]}])
def test_invalid_scenario_configuration_cannot_create_a_match(bad):
    data = scenario_map()
    data["rules"]["scenario"] = bad
    with pytest.raises(maps.MapValidationError):
        rules.build_game(1, 2, map_data=data)


def test_undersized_starting_region_and_base_scenario_mechanics_are_rejected():
    tiny = {"name": "too small", "tiles": [{"q": 0, "r": 0, "terrain": "forest", "number": 5}],
            "rules": {"enable_seafarers": True, "scenario": {"starting_islands": [0]}}}
    with pytest.raises(maps.MapValidationError, match="fit all opening"):
        rules.build_game(1, 2, map_data=tiny)
    base = deepcopy(maps.get_preset_map("base_standard"))
    base["rules"]["scenario"] = {"new_island_vp": 2}
    with pytest.raises(maps.MapValidationError, match="require Seafarers"):
        rules.build_game(1, 2, map_data=base)


def test_v3_roundtrip_keeps_ledger_without_reexecuting_rules_and_offline_ledger_is_not_optional(monkeypatch):
    g = scenario_game()
    destination = arrive(g)
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": destination})
    payload = released_v3_payload(g)
    assert (payload["snapshot_version"], payload["engine_compatibility"]) == (3, 2)
    def forbidden(*args, **kwargs):
        pytest.fail("Normal recovery must never execute gameplay")
    monkeypatch.setattr(rules, "apply_cmd", forbidden)
    monkeypatch.setattr(rules, "update_longest_road", forbidden)
    assert snapshots.decode_snapshot(payload) == g
    offline = serialize.to_dict(g)
    restored = serialize.from_dict(offline)
    assert restored.scenario == g.scenario and [p.vp for p in restored.players] == [p.vp for p in g.players]
    del offline["scenario"]["home_islands"]
    with pytest.raises(ValueError):
        serialize.from_dict(offline)


def test_erased_award_ledger_is_rejected_instead_of_allowing_duplicate_points_after_restore():
    g = scenario_game()
    destination = arrive(g)
    rules.apply_cmd(g, 0, {"type": "place_settlement", "vid": destination})
    payload = snapshots.encode_snapshot(g)
    payload["state"]["scenario"]["awarded_islands"] = {}
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)
    offline = serialize.to_dict(g)
    offline["scenario"]["awarded_islands"] = {}
    with pytest.raises(ValueError):
        serialize.from_dict(offline)


@pytest.mark.parametrize("version,compat", [(1, 2), (2, 2), (3, 1), (4, 2)])
def test_format_and_engine_compatibility_pairs_cannot_be_relabelled(version, compat):
    g = rules.build_game(1, 2)
    payload = {1: released_v1_payload, 2: released_v2_payload,
               3: released_v3_payload, 4: snapshots.encode_snapshot}[version](g)
    payload["engine_compatibility"] = compat
    with pytest.raises(snapshots.UnsupportedEngineCompatibility):
        snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_ignored_map_metadata_does_not_activate_new_rules_or_rewrite_values(version):
    g = rules.build_game(1, 2)
    g.rules["scenario"] = {"starting_islands": [999], "new_island_vp": 2}
    payload = released_v1_payload(g) if version == 1 else released_v2_payload(g)
    before = deepcopy(payload)
    restored = snapshots.decode_snapshot(payload)
    assert restored.scenario == ScenarioState()
    assert restored.players == g.players and restored.achievements == g.achievements
    assert payload == before


@pytest.mark.parametrize("change", ["missing_state", "missing_history", "unknown_island", "unknown_pid", "home_award", "unowned_award"])
def test_v3_history_is_required_and_references_are_validated(change):
    payload = snapshots.encode_snapshot(scenario_game())
    state = payload["state"]["scenario"]
    if change == "missing_state": del payload["state"]["scenario"]
    elif change == "missing_history": state["home_islands"] = {}
    elif change == "unknown_island": state["home_islands"]["0"] = [999]
    elif change == "unknown_pid": state["home_islands"]["9"] = [4]
    elif change == "home_award": state["awarded_islands"]["0"] = [4]
    else: state["awarded_islands"]["0"] = [13]
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)


def test_all_existing_base_and_seafarers_presets_keep_scenario_disabled_and_victory_targets():
    for preset in maps.PRESET_REGISTRY:
        g = rules.build_game(17, 2, map_id=preset["id"])
        assert g.scenario == ScenarioState()
        source = maps.get_preset_map(preset["id"])["rules"]
        assert g.rules_config.target_vp == source.get("target_vp", source.get("victory_points", 10))
    historical = Path(__file__).with_name("fixtures") / "s1_gold_haven_v2.json"
    legacy = json.loads(historical.read_text())
    restored = snapshots.decode_snapshot(legacy)
    assert released_v2_payload(restored) == legacy
