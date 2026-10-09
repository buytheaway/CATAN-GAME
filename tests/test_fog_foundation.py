"""Trusted foundation only: no production discovery/reward executor is enabled."""
from collections import Counter
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import random

import pytest

from app.engine import maps, rules, serialize
from app.engine.exploration import (FOG_PROFILE, FogUnavailableError, assignment_digest,
    initially_visible_coasts, validate_fog_state, validate_fog_transition)
from app.engine.scenario import valid_starting_vertex
from app.engine.state import FogContinuation, FogDiscovery, ScenarioState
from app.match_rulesets import (CURRENT_RULESET, LEGACY_S1_RULESET, LEGACY_S2B1_RULESET, compatibility)
from app.persistence import snapshots
from tests.test_persistence_snapshots import (released_v1_payload, released_v2_payload,
                                            released_v3_payload, assert_equivalent)


def fog_recipe():
    base = rules.build_game(9, 2, map_id="seafarers_simple_2")
    hidden = [i for i, t in enumerate(base.tiles) if t.terrain == "sea"][:8]
    tiles = [{"q": t.q, "r": t.r, "terrain": "fog" if i in hidden else t.terrain,
              "number": None if i in hidden else t.number} for i, t in enumerate(base.tiles)]
    return {"version": 2, "name": "Private fog fixture", "tiles": tiles, "ports": [],
            "fog_pool": {"terrain": ["forest", "hills", "pasture", "fields", "mountains", "gold", "sea", "desert"],
                         "numbers": [3, 4, 5, 6, 8, 9]},
            "rules": {"enable_seafarers": True, "enable_gold": True, "enable_pirate": True,
                      "enable_move_ship": True, "target_vp": 12,
                      "scenario": {"fog": {"profile": FOG_PROFILE}}}}


def fog_game(*, public_seed=91, private_seed=7, data=None):
    return rules.build_game(public_seed, 2, map_data=data or fog_recipe(),
                            fog_rng=random.Random(private_seed))


def recorded_fog(*, pending=False):
    """Explicit trusted history fixture, not a claim of playable fog commands."""
    g = fog_game()
    ids = g.scenario.rules.fog.initially_hidden
    forest = next(i for i in ids if g.tiles[i].terrain == "forest")
    sea = next(i for i in ids if g.tiles[i].terrain == "sea")
    gold = next(i for i in ids if g.tiles[i].terrain == "gold")
    entries = (FogDiscovery(forest, 0, "awarded", "wood"), FogDiscovery(sea, 0, "none"),
               FogDiscovery(gold, 0, "pending" if pending else "awarded", None if pending else "ore"))
    continuation = None
    if pending:
        g.phase, g.setup_idx, g.turn, g.rolled = "main", len(g.setup_order), 0, True
        edge = min(g.edges)
        g.occupied_e[edge] = 0
        g.pending_action, g.pending_pid = "choose_gold", 0
        g.pending_gold, g.pending_gold_queue = {0: 1}, [0]
        continuation = FogContinuation("place_road", 0, edge)
    g.scenario.fog = replace(g.scenario.fog, revealed=frozenset(e.tile_index for e in entries),
                             discoveries=entries, continuation=continuation)
    return g


def test_exact_pools_stable_geometry_and_detached_recipe():
    source = fog_recipe()
    before = deepcopy(source)
    g = fog_game(data=source)
    ids = g.scenario.rules.fog.initially_hidden
    assert Counter(g.tiles[i].terrain for i in ids) == Counter(source["fog_pool"]["terrain"])
    assert Counter(g.tiles[i].number for i in ids if g.tiles[i].number is not None) == Counter(source["fog_pool"]["numbers"])
    assert [(t.q, t.r) for t in g.tiles] == [(t["q"], t["r"]) for t in source["tiles"]]
    assert not g.scenario.fog.revealed and not g.scenario.fog.discoveries
    assert source == before
    source["fog_pool"]["terrain"].clear()
    assert g == fog_game(data=before)


def test_private_rng_injection_is_independent_of_public_seed(monkeypatch):
    called = []
    def private_rng():
        called.append(True)
        return random.Random(1234)
    monkeypatch.setattr(maps.random, "SystemRandom", private_rng)
    a = rules.build_game(1, 2, map_data=fog_recipe())
    b = rules.build_game(9999, 2, map_data=fog_recipe())
    assert len(called) == 2 and a.tiles == b.tiles
    assert a.tiles == fog_game(public_seed=27, private_seed=1234).tiles
    assert a.tiles != fog_game(private_seed=5678).tiles


@pytest.mark.parametrize("bad", ["no_profile", "unknown_profile", "island_bonus", "starting_islands", "base",
    "extra_terrain", "missing_terrain", "extra_number", "missing_number", "number_bool", "hidden_number",
    "coordinate_bool", "duplicate_coordinate", "client_seed", "full_assignment", "v1_fog", "no_slots",
    "robber_hidden", "pirate_hidden", "gold_disabled", "raw_indices"])
def test_invalid_recipes_are_rejected_without_materialization(bad, monkeypatch):
    data = fog_recipe()
    hidden = next(i for i, t in enumerate(data["tiles"]) if t["terrain"] == "fog")
    if bad == "no_profile": data["rules"]["scenario"] = {}
    elif bad == "unknown_profile": data["rules"]["scenario"]["fog"]["profile"] = "private-per-player"
    elif bad == "island_bonus": data["rules"]["scenario"]["new_island_vp"] = 2
    elif bad == "starting_islands": data["rules"]["scenario"]["starting_islands"] = [0]
    elif bad == "base": data["rules"]["enable_seafarers"] = False
    elif bad == "extra_terrain": data["fog_pool"]["terrain"].append("sea")
    elif bad == "missing_terrain": data["fog_pool"]["terrain"].pop()
    elif bad == "extra_number": data["fog_pool"]["numbers"].append(3)
    elif bad == "missing_number": data["fog_pool"]["numbers"].pop()
    elif bad == "number_bool": data["fog_pool"]["numbers"][0] = True
    elif bad == "hidden_number": data["tiles"][hidden]["number"] = 8
    elif bad == "coordinate_bool": data["tiles"][0]["q"] = True
    elif bad == "duplicate_coordinate": data["tiles"][1].update(q=data["tiles"][0]["q"], r=data["tiles"][0]["r"])
    elif bad == "client_seed": data["seed"] = 123
    elif bad == "full_assignment": data["tiles"][hidden]["actual_terrain"] = "gold"
    elif bad == "v1_fog": data["version"] = 1
    elif bad == "no_slots":
        for t in data["tiles"]:
            if t["terrain"] == "fog": t["terrain"] = "sea"
    elif bad == "robber_hidden": data["robber_tile"] = hidden
    elif bad == "pirate_hidden": data["pirate_tile"] = hidden
    elif bad == "gold_disabled": data["rules"]["enable_gold"] = False
    else: data["rules"]["scenario"]["fog"]["initially_hidden"] = [True, 999]
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid recipe must not assign hidden contents")
    monkeypatch.setattr(maps.random, "SystemRandom", forbidden)
    with pytest.raises(maps.MapValidationError):
        rules.build_game(1, 2, map_data=data)


def test_initial_regions_and_ports_do_not_depend_on_hidden_assignments():
    source = fog_recipe()
    source.pop("ports")
    source["ports_auto"] = {"count": 4}
    a, b = fog_game(private_seed=1, data=source), fog_game(private_seed=2, data=source)
    assert a.ports == b.ports
    assert a.pirate_tile == b.pirate_tile
    assert [valid_starting_vertex(a, v) for v in a.vertices] == [valid_starting_vertex(b, v) for v in b.vertices]
    assert all(e in initially_visible_coasts(a.board, a.scenario.rules.fog.initially_hidden) for e, _ in a.ports)
    hidden = set(a.scenario.rules.fog.initially_hidden)
    edge = next(e for e, adjacent in a.edge_adj_hexes.items() if hidden.intersection(adjacent))
    source["ports"] = [{"edge": list(edge), "type": "3:1"}]
    with pytest.raises(maps.MapValidationError, match="coastline"):
        fog_game(data=source)


def test_hidden_land_cannot_supply_setup_capacity():
    source = fog_recipe()
    for t in source["tiles"]:
        if t["terrain"] != "fog": t.update(terrain="sea", number=None)
    with pytest.raises(maps.MapValidationError, match="fit all opening"):
        fog_game(data=source)


@pytest.mark.parametrize("pending", [False, True])
def test_v4_real_json_roundtrip_preserves_full_trusted_history_without_rules(pending, monkeypatch):
    g = recorded_fog(pending=pending)
    g.players[0].vp, g.players[1].vp = 7, 3
    g.largest_army_owner, g.largest_army_size = 0, 3
    before = deepcopy(g)
    payload = snapshots.encode_snapshot(g)
    assert (payload["snapshot_version"], payload["engine_compatibility"]) == (4, 3)
    def forbidden(*args, **kwargs):
        pytest.fail("Recovery must not execute rules, awards or randomness")
    for name in ("build_game", "apply_cmd", "check_win", "update_longest_road", "update_largest_army"):
        monkeypatch.setattr(rules, name, forbidden)
    monkeypatch.setattr(maps.random, "SystemRandom", forbidden)
    restored = snapshots.loads_snapshot(json.dumps(payload))
    assert_equivalent(before, restored)
    assert snapshots.dumps_snapshot(restored) == snapshots.dumps_snapshot(g)
    assert g == before


@pytest.mark.parametrize("bad", ["reveal_outside", "reveal_bool", "duplicate", "missing_entry", "unknown_pid",
    "missing_continuation", "changed_terrain", "changed_number", "unsorted_mask", "duplicate_mask",
    "invalid_status", "wrong_resource", "pending_count", "pending_edge", "mask_bool", "mask_outside", "no_fog_rules"])
def test_invalid_trusted_fog_snapshots_fail_closed(bad):
    payload = snapshots.encode_snapshot(recorded_fog(pending=True))
    scenario = payload["state"]["scenario"]
    fog = scenario["fog"]
    if bad == "reveal_outside": fog["revealed"].append(9999)
    elif bad == "reveal_bool": fog["revealed"].append(True)
    elif bad == "duplicate": fog["discoveries"].append(deepcopy(fog["discoveries"][0]))
    elif bad == "missing_entry": fog["discoveries"].pop()
    elif bad == "unknown_pid": fog["discoveries"][0]["pid"] = 99
    elif bad == "missing_continuation": fog["continuation"] = None
    elif bad == "changed_terrain": payload["state"]["board"]["tiles"][0]["terrain"] = "mountains"
    elif bad == "changed_number": payload["state"]["board"]["tiles"][0]["number"] = 12
    elif bad == "unsorted_mask": scenario["rules"]["fog"]["initially_hidden"].reverse()
    elif bad == "duplicate_mask": scenario["rules"]["fog"]["initially_hidden"].append(scenario["rules"]["fog"]["initially_hidden"][0])
    elif bad == "invalid_status": fog["discoveries"][0]["reward_status"] = "repeat"
    elif bad == "wrong_resource": fog["discoveries"][0]["resource"] = "ore"
    elif bad == "pending_count": payload["state"]["pending_gold"]["0"] = 2
    elif bad == "pending_edge": fog["continuation"]["edge"] = [9998, 9999]
    elif bad == "mask_bool": scenario["rules"]["fog"]["initially_hidden"][0] = True
    elif bad == "mask_outside": scenario["rules"]["fog"]["initially_hidden"].append(9999)
    else: scenario["rules"]["fog"] = None
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("bad", ["hide_again", "rewrite_reward", "reassign", "geometry"])
def test_transition_fence_preserves_monotonic_discovery_and_one_reward(bad):
    before = recorded_fog()
    after = deepcopy(before)
    state = after.scenario.fog
    if bad == "hide_again": after.scenario.fog = replace(state, revealed=frozenset(), discoveries=())
    elif bad == "rewrite_reward":
        after.scenario.fog = replace(state, discoveries=(replace(state.discoveries[0], pid=1), *state.discoveries[1:]))
    elif bad == "reassign":
        tile = after.tiles[state.discoveries[0].tile_index]
        tile.number = 12 if tile.number != 12 else 11
        after.scenario.fog = replace(state, assignment_digest=assignment_digest(after.board))
    else: after.vertices[0] = (999.0, 999.0)
    validate_fog_state(after)  # A single valid state cannot prove history monotonicity.
    with pytest.raises(ValueError):
        validate_fog_transition(before, after)


def test_immutable_history_and_assignment_mutation_is_not_persistable():
    g = fog_game()
    with pytest.raises(FrozenInstanceError): g.scenario.rules.fog.profile = "other"
    with pytest.raises(FrozenInstanceError): g.scenario.fog.revealed = frozenset({0})
    g.tiles[g.scenario.rules.fog.initially_hidden[0]].number = 12
    with pytest.raises(snapshots.SnapshotValidationError): snapshots.encode_snapshot(g)


@pytest.mark.parametrize("version", [1, 2, 3])
def test_frozen_legacy_schema_is_fog_disabled_and_preserves_recorded_values(version, monkeypatch):
    g = rules.build_game(17, 2)
    g.players[0].vp, g.players[1].vp = 9, 4
    g.longest_road_owner, g.longest_road_len = 1, 5
    payload = {1: released_v1_payload, 2: released_v2_payload, 3: released_v3_payload}[version](g)
    payload["state"]["rules"]["scenario"] = {"fog": {"profile": FOG_PROFILE}}
    before = deepcopy(payload)
    def forbidden(*args, **kwargs): pytest.fail("Historical recovery cannot run gameplay")
    for name in ("build_game", "apply_cmd", "check_win", "update_longest_road"):
        monkeypatch.setattr(rules, name, forbidden)
    restored = snapshots.decode_snapshot(payload)
    assert restored.scenario == ScenarioState()
    assert restored.players == g.players and restored.achievements == g.achievements
    assert restored.tiles == g.tiles and payload == before
    if version == 3:
        payload["state"]["scenario"]["rules"]["fog"] = None
        with pytest.raises(snapshots.SnapshotValidationError): snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("marker", [None, "unknown", LEGACY_S1_RULESET, LEGACY_S2B1_RULESET, CURRENT_RULESET])
def test_ruleset_provenance_and_feature_availability_are_independent(marker):
    normal = rules.build_game(1, 2)
    assert compatibility(marker, normal)["status"] == ("compatible" if marker in
            (LEGACY_S1_RULESET, LEGACY_S2B1_RULESET, CURRENT_RULESET) else "compatibility_required")
    assert compatibility(marker, fog_game())["status"] == "compatibility_required"


@pytest.mark.parametrize("preset", [p["id"] for p in maps.list_presets()])
def test_existing_presets_stay_fog_disabled_and_public(preset):
    g = rules.build_game(17, 2, map_id=preset)
    assert g.scenario.rules.fog is None and g.scenario.fog is None
    historical = snapshots.decode_snapshot(released_v3_payload(g))
    assert_equivalent(g, historical)
    assert serialize.to_player_dict(g, 0) == serialize.to_player_dict(historical, 0)


@pytest.mark.parametrize("finished", [False, True])
def test_public_and_offline_serializers_never_fall_back_to_full_fog_map(finished):
    g = recorded_fog()
    g.game_over, g.winner_pid = finished, 0 if finished else None
    for operation in (lambda: serialize.to_dict(g), lambda: serialize.to_player_dict(g, 0),
                      lambda: serialize.to_player_dict(g, 1), lambda: serialize.from_dict(fog_recipe())):
        with pytest.raises(FogUnavailableError): operation()


@pytest.mark.parametrize("command", [{"type": "noop"}, {"type": "roll"}, {"type": "end_turn"},
    {"type": "place_road", "edge": [0, 1]}, {"type": "grant_resources", "res": {"wood": 1}}])
def test_shared_executor_blocks_all_fog_commands_without_mutation(command):
    g = fog_game()
    before = deepcopy(g)
    with pytest.raises(rules.RuleError) as error: rules.apply_cmd(g, 0, command)
    assert error.value.code == "feature_disabled" and g == before
