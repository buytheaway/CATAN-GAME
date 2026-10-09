"""Full-state persistence tests; existing network serialization is not a save codec."""
from copy import deepcopy
from dataclasses import fields, is_dataclass
import json

import pytest

from app.engine import maps, rules, serialize
from app.engine.state import RESOURCES, TradeOffer
from app.persistence import snapshots
from tests.test_pirate_lifecycle import finish_setup, finish_discards


def assert_equivalent(expected, actual):
    """Compare nested internal values AND types, including secret fields and key types."""
    assert type(actual) is type(expected)
    if is_dataclass(expected):
        for field in fields(expected):
            assert_equivalent(getattr(expected, field.name), getattr(actual, field.name))
    elif isinstance(expected, dict):
        assert expected.keys() == actual.keys()
        for key in expected:
            assert any(type(key) is type(other) and key == other for other in actual)
            assert_equivalent(expected[key], actual[key])
    elif isinstance(expected, (list, tuple)):
        assert len(expected) == len(actual)
        for a, b in zip(expected, actual):
            assert_equivalent(a, b)
    elif isinstance(expected, set):
        assert expected == actual
        for item in expected:
            other = next(x for x in actual if x == item)
            assert_equivalent(item, other)
    else:
        assert expected == actual


def rich_state():
    """Synthetic characterization probe, not a claim of legal command history."""
    g = rules.build_game(1847, 3, map_id="seafarers_gold_haven")
    g.players[0].dev_cards = [{"type": "victory_point", "new": True}]
    g.players[0].vp = 1
    g.dev_played_turn = {0: True, 1: False}
    g.free_roads = {0: 1, 2: 0}
    g.tick, g.state_version = 19, 4
    g.last_roll, g.roll_history = 7, [4, 8, 7]
    g.pending_action, g.pending_pid, g.pending_victims = "robber_move", 0, [1, 2]
    g.discard_required, g.discard_submitted = {1: 4}, {1}
    g.pending_gold, g.pending_gold_queue = {2: 1}, [2]
    g.trade_offers = [TradeOffer(9, 0, 1, {"wood": 1}, {"ore": 2}, created_tick=17)]
    g.trade_offer_next_id = 10
    g.achievements.longest_road_owner, g.achievements.longest_road_len = 1, 5
    g.achievements.largest_army_owner, g.achievements.largest_army_size = 2, 3
    return g


@pytest.mark.parametrize("field", ["seed", "dev_deck", "players", "dev_played_turn",
                                  "free_roads", "tick", "state_version", "roll_history"])
def test_existing_serializer_loses_private_or_engine_state(field):
    g = rich_state()
    restored = serialize.from_dict(json.loads(json.dumps(serialize.to_dict(g))))
    assert getattr(g, field) != getattr(restored, field)


@pytest.mark.parametrize("field", ["board", "bank", "achievements", "rules_config",
                                  "pending_action", "pending_pid", "pending_victims",
                                  "discard_required", "discard_submitted", "pending_gold",
                                  "pending_gold_queue", "trade_offers", "trade_offer_next_id",
                                  "setup_order", "setup_idx", "setup_need", "setup_anchor_vid",
                                  "robber_tile", "robbers", "pirate_tile", "last_roll"])
def test_existing_serializer_already_preserves_these_fields(field):
    g = rich_state()
    restored = serialize.from_dict(json.loads(json.dumps(serialize.to_dict(g))))
    assert_equivalent(getattr(g, field), getattr(restored, field))


def test_existing_view_equality_can_hide_secret_state_loss():
    g = rich_state()
    g.state_version = 1
    restored = serialize.from_dict(json.loads(json.dumps(serialize.to_dict(g))))
    assert serialize.to_dict(g) == serialize.to_dict(restored)
    assert g.players[0].res == restored.players[0].res
    assert g.players[0].vp == restored.players[0].vp  # Score survives; its hidden card does not.
    assert restored.players[0].dev_cards == []
    with pytest.raises(AssertionError):
        assert_equivalent(g, restored)


def restore(g):
    # Always cross actual JSON text, not an in-process Python dictionary alone.
    result = snapshots.loads_snapshot(snapshots.dumps_snapshot(g))
    assert_equivalent(g, result)
    return result


def main_game(map_id="base_standard", players=2):
    g = rules.build_game(1, players, map_id=map_id)
    while g.phase == "setup":
        pid = g.turn
        if g.pending_action == "choose_gold":
            rules.apply_cmd(g, g.pending_pid, {"type": "choose_gold", "res": "ore", "qty": 1})
        elif g.setup_need == "settlement":
            legal = [v for v in sorted(g.vertices) if rules.can_place_settlement(g, pid, v, False)]
            coast = [v for v in legal if any(g.tiles[t].terrain == "sea" for t in g.vertex_adj_hexes[v])]
            rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": (coast or legal)[0]})
        else:
            edge = next(e for e in sorted(g.edges) if rules.can_place_road(g, pid, e, g.setup_anchor_vid))
            rules.apply_cmd(g, pid, {"type": "place_road", "eid": edge})
    return g


def give_card(g, kind, pid=0, new=False):
    g.dev_deck.remove(kind)
    g.players[pid].dev_cards.append({"type": kind, "new": new})
    if kind == "victory_point":
        g.players[pid].vp += 1


def roll(g, total=2):
    rules.apply_cmd(g, g.turn, {"type": "roll", "roll": total})


def age_ship_through_turns(g):
    owner = g.turn
    benign = next(n for n in (2, 3, 4, 5, 6, 8, 9, 10, 11, 12)
                  if n not in {t.number for t in g.tiles if t.terrain == "gold"})
    rules.apply_cmd(g, owner, {"type": "end_turn"})
    while g.turn != owner:
        roll(g, benign)
        rules.apply_cmd(g, g.turn, {"type": "end_turn"})
    roll(g, benign)


def free_road(g):
    edge = next(e for e in sorted(g.edges) if rules.can_place_road(g, g.turn, e))
    return {"type": "place_road", "eid": list(edge), "free": True}


def build_case(name):
    if name == "new":
        return rules.build_game(900, 2)
    if name == "mid_setup":
        g = rules.build_game(77, 3, starting_pid=1)
        vertex = next(v for v in sorted(g.vertices) if rules.can_place_settlement(g, 1, v, False))
        rules.apply_cmd(g, 1, {"type": "place_settlement", "vid": vertex})
        return g
    g = main_game()
    if name == "before_roll":
        return g
    if name == "after_roll":
        roll(g, 6)
    elif name in ("discard", "partly_discarded", "robber"):
        if name != "robber":
            for pid in (0, 1):
                resource = "wood" if pid == 0 else "wheat"
                rules.apply_cmd(g, pid, {"type": "grant_resources", "res": {resource: 10}})
        roll(g, 7)
        if name == "partly_discarded":
            need = g.discard_required[0]
            rules.apply_cmd(g, 0, {"type": "discard", "discards": {"wood": need}})
            assert g.pending_action == "discard" and g.discard_submitted == {0}
    elif name == "multiple_victims":
        for seed in range(1, 30):
            g = rules.build_game(seed, 3)
            finish_setup(g)
            for pid in (1, 2):
                rules.apply_cmd(g, pid, {"type": "grant_resources", "res": {"wood": 1}})
            roll(g, 7)
            if any(len(rules._victims_for_tile(g, t, 0)) == 2
                   for t in range(len(g.tiles)) if t != g.robber_tile):
                break
        else:
            pytest.fail("No multi-victim fixture found")
    elif name == "trade":
        roll(g)
        rules.apply_cmd(g, 0, {"type": "grant_resources", "res": {"wood": 2}})
        rules.apply_cmd(g, 1, {"type": "grant_resources", "res": {"ore": 2}})
        rules.apply_cmd(g, 0, {"type": "trade_offer_create", "give": {"wood": 1},
                               "get": {"ore": 1}, "to_pid": 1})
    elif name in ("knight", "road_two", "road_one", "road_zero", "road_ended"):
        give_card(g, "knight" if name == "knight" else "road_building")
        rules.apply_cmd(g, 0, {"type": "play_dev", "card": g.players[0].dev_cards[-1]["type"]})
        if name in ("road_one", "road_zero", "road_ended"):
            rules.apply_cmd(g, 0, free_road(g))
        if name == "road_zero":
            rules.apply_cmd(g, 0, free_road(g))
        if name == "road_ended":
            roll(g)
            rules.apply_cmd(g, 0, {"type": "end_turn"})
    elif name in ("plenty_ready", "plenty_done", "monopoly_ready", "monopoly_done"):
        kind = "year_of_plenty" if name.startswith("plenty") else "monopoly"
        give_card(g, kind)
        if kind == "monopoly":
            rules.apply_cmd(g, 1, {"type": "grant_resources", "res": {"wood": 3}})
        if name.endswith("done"):
            rules.apply_cmd(g, 0, {"type": "play_dev", "card": kind,
                                   **({"a": "wood", "qa": 1, "b": "ore", "qb": 1}
                                      if kind == "year_of_plenty" else {"r": "wood"})})
    elif name == "hidden_vp":
        give_card(g, "victory_point")
    elif name == "newly_bought":
        roll(g)
        rules.apply_cmd(g, 0, {"type": "grant_resources", "res": {"sheep": 1, "wheat": 1, "ore": 1}})
        g.dev_deck.remove("knight")
        g.dev_deck.append("knight")
        rules.apply_cmd(g, 0, {"type": "buy_dev"})
    elif name in ("near_victory", "game_over"):
        g.rules_config.target_vp = 3  # Supported room option, no score fabrication.
        roll(g)
        g.dev_deck.remove("victory_point")
        g.dev_deck.append("victory_point")
        rules.apply_cmd(g, 0, {"type": "grant_resources", "res": {"sheep": 1, "wheat": 1, "ore": 1}})
        if name == "game_over":
            rules.apply_cmd(g, 0, {"type": "buy_dev"})
            assert g.game_over and g.winner_pid == 0
    else:
        raise AssertionError(name)
    return g


BASE_CASES = ["new", "mid_setup", "before_roll", "after_roll", "discard", "partly_discarded",
              "robber", "multiple_victims", "trade", "knight", "road_two", "road_one", "road_zero",
              "road_ended", "plenty_ready", "plenty_done", "monopoly_ready", "monopoly_done",
              "hidden_vp", "newly_bought", "near_victory", "game_over"]


@pytest.mark.parametrize("case", BASE_CASES)
def test_base_lifecycle_full_round_trip(case):
    restore(build_case(case))


@pytest.mark.parametrize("preset", [p["id"] for p in maps.PRESET_REGISTRY])
def test_every_preset_preserves_materialized_board_ids_and_order(preset, monkeypatch):
    g = rules.build_game(123456, 2, map_id=preset)
    def prohibited(*args, **kwargs):
        pytest.fail("Restore must not build/shuffle/materialize anything")
    monkeypatch.setattr(rules, "build_game", prohibited)
    monkeypatch.setattr(maps, "build_board_from_map", prohibited)
    restore(g)


def seafarers_case(name):
    g = main_game("seafarers_gold_haven")
    roll(g)
    rules.apply_cmd(g, 0, {"type": "grant_resources", "res": {"wood": 2, "sheep": 2}})
    source = next(e for e in sorted(g.edges) if rules.can_place_ship(g, 0, e))
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": list(source)})
    if name == "ship":
        return g
    if name == "moved_ship":
        age_ship_through_turns(g)
        for edge in sorted(g.edges):
            probe = deepcopy(g)
            try:
                rules.apply_cmd(probe, 0, {"type": "move_ship", "from_eid": source, "to_eid": edge})
            except rules.RuleError:
                continue
            assert source not in probe.occupied_ships and edge in probe.occupied_ships
            return probe
        pytest.fail("No legal ship destination")
    rules.apply_cmd(g, 0, {"type": "end_turn"})
    roll(g, 7)
    finish_discards(g)
    assert g.pending_pid == 1 and g.pending_action == "robber_move"
    if name == "pirate_pending":
        return g
    tile = next(t for t, h in enumerate(g.tiles) if h.terrain == "sea" and t != g.pirate_tile)
    rules.apply_cmd(g, 1, {"type": "move_pirate", "tile": tile})
    assert g.pending_action is None and g.pirate_tile == tile
    return g


@pytest.mark.parametrize("case", ["ship", "moved_ship", "pirate_pending", "pirate_moved"])
def test_seafarers_ship_and_pirate_lifecycle(case):
    restore(seafarers_case(case))


def released_v1_payload(g):
    # V1 predates offboard initialization. Model its real on-board position,
    # rather than relabeling a new S2A-only value as a released-v1 snapshot.
    legacy = deepcopy(g)
    if legacy.robber_tile == -1:
        legacy.robber_tile = next(i for i, t in enumerate(legacy.tiles) if t.terrain != "sea")
        legacy.robbers = [legacy.robber_tile if i == -1 else i for i in legacy.robbers]
    payload = snapshots.encode_snapshot(legacy)
    payload["snapshot_version"] = 1
    del payload["state"]["ships_built_this_turn"]
    del payload["state"]["ship_moved_this_turn"]
    return payload


def test_v2_preserves_new_ship_history_and_rejected_move_after_json_restore():
    g = seafarers_case("ship")
    source = next(iter(g.occupied_ships))
    assert g.ships_built_this_turn == {source}
    payload = snapshots.encode_snapshot(g)
    assert payload["snapshot_version"] == 2 and payload["engine_compatibility"] == 1
    assert payload["state"]["ships_built_this_turn"] == [list(source)]
    r = restore(g)
    destination = next(edge for edge in g.edges if rules.can_place_ship(g, 0, edge, excluded_edge=source))
    cmd = {"type": "move_ship", "from_eid": source, "to_eid": destination}
    for state in (g, r):
        before = deepcopy(state)
        with pytest.raises(rules.RuleError):
            rules.apply_cmd(state, 0, cmd)
        assert_equivalent(before, state)
    age_ship_through_turns(g)
    age_ship_through_turns(r)
    assert not g.ships_built_this_turn and not g.ship_moved_this_turn
    assert_equivalent(g, r)


def test_v2_preserves_move_used_and_mixed_route_achievements():
    g = seafarers_case("moved_ship")
    assert g.ship_moved_this_turn and not g.ships_built_this_turn
    assert g.occupied_e and g.occupied_ships
    r = restore(g)
    source = next(iter(g.occupied_ships))
    destination = next(edge for edge in g.edges if rules.can_place_ship(g, 0, edge, excluded_edge=source))
    cmd = {"type": "move_ship", "from_eid": source, "to_eid": destination}
    for state in (g, r):
        before = deepcopy(state)
        with pytest.raises(rules.RuleError):
            rules.apply_cmd(state, 0, cmd)
        assert_equivalent(before, state)
    assert_equivalent(g.achievements, r.achievements)


@pytest.mark.parametrize("phase,rolled,seafarers,movable,locked", [
    ("setup", False, True, True, False), ("main", False, True, True, True),
    ("main", True, True, True, True), ("main", True, False, True, False),
    ("main", True, True, False, False), ("main", True, False, False, False),
])
def test_exact_v1_migration_preserves_state_and_locks_only_unknown_active_ship_history(
        phase, rolled, seafarers, movable, locked):
    g = rules.build_game(1, 2, map_id="seafarers_gold_haven") if phase == "setup" else main_game("seafarers_gold_haven")
    g.rolled = rolled
    g.rules_config.enable_seafarers, g.rules_config.enable_move_ship = seafarers, movable
    payload = released_v1_payload(g)
    before = deepcopy(payload)
    migrated = snapshots.loads_snapshot(json.dumps(payload))
    expected = deepcopy(g)
    expected.robber_tile = payload["state"]["robber_tile"]
    expected.robbers = payload["state"]["robbers"]
    expected.ships_built_this_turn = set()
    expected.ship_moved_this_turn = locked
    assert_equivalent(expected, migrated)
    assert_equivalent(before, payload)
    assert snapshots.encode_snapshot(migrated)["snapshot_version"] == 2


def test_v1_conservative_ship_lock_expires_only_on_normal_end_turn():
    g = seafarers_case("ship")
    age_ship_through_turns(g)
    migrated = snapshots.decode_snapshot(released_v1_payload(g))
    assert migrated.ship_moved_this_turn
    source = next(iter(migrated.occupied_ships))
    before = deepcopy(migrated)
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(migrated, 0, {"type": "move_ship", "from_eid": source, "to_eid": next(
            e for e in g.edges if rules.can_place_ship(g, 0, e, excluded_edge=source))})
    assert_equivalent(before, migrated)
    age_ship_through_turns(migrated)
    assert not migrated.ship_moved_this_turn
    accepted = False
    for edge in sorted(migrated.edges):
        try:
            rules.apply_cmd(deepcopy(migrated), 0, {"type": "move_ship", "from_eid": source, "to_eid": edge})
        except rules.RuleError:
            continue
        accepted = True
        break
    assert accepted


def test_v1_unrolled_free_ship_history_cannot_be_erased_by_recovery():
    g = main_game("seafarers_gold_haven")
    give_card(g, "road_building")
    rules.apply_cmd(g, 0, {"type": "play_dev", "card": "road_building"})
    source = next(e for e in sorted(g.edges) if rules.can_place_ship(g, 0, e))
    rules.apply_cmd(g, 0, {"type": "build_ship", "eid": source, "free": True})
    assert not g.rolled
    migrated = snapshots.decode_snapshot(released_v1_payload(g))
    assert migrated.ship_moved_this_turn
    roll(migrated, 2)
    before = deepcopy(migrated)
    target = next(e for e in sorted(g.edges) if rules.can_place_ship(g, 0, e, excluded_edge=source))
    with pytest.raises(rules.RuleError):
        rules.apply_cmd(migrated, 0, {"type": "move_ship", "from_eid": source, "to_eid": target})
    assert_equivalent(before, migrated)


@pytest.mark.parametrize("pending", ["discard", "robber_move", "choose_gold"])
def test_v2_pending_choices_preserve_ship_lifecycle_without_new_entitlement(pending):
    g = seafarers_case("ship")
    g.pending_action, g.pending_pid = pending, g.turn
    if pending == "choose_gold":
        g.pending_gold, g.pending_gold_queue = {g.turn: 1}, [g.turn]
    elif pending == "discard":
        g.discard_required = {g.turn: 1}
    restore(g)


@pytest.mark.parametrize("corruption", ["unknown", "new_field", "missing", "type"])
def test_v1_migration_rejects_nonreleased_shape_before_defaults(corruption):
    payload = released_v1_payload(main_game("seafarers_gold_haven"))
    state = payload["state"]
    if corruption == "unknown":
        state["future_history"] = []
    elif corruption == "new_field":
        state["ship_moved_this_turn"] = False
    elif corruption == "missing":
        del state["dev_deck"]
    else:
        state["rolled"] = 1
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("corruption", ["missing", "foreign", "unoccupied", "duplicate", "reversed", "boolean", "setup", "moved_type"])
def test_v2_ship_lifecycle_references_fail_closed(corruption):
    g = seafarers_case("ship")
    payload = snapshots.encode_snapshot(g)
    state = payload["state"]
    source = state["ships_built_this_turn"][0]
    if corruption == "missing":
        state["ships_built_this_turn"] = [[9998, 9999]]
    elif corruption == "foreign":
        state["board"]["occupied_ships"][",".join(map(str, source))] = 1
    elif corruption == "unoccupied":
        state["board"]["occupied_ships"] = {}
    elif corruption == "duplicate":
        state["ships_built_this_turn"].append(source)
    elif corruption == "reversed":
        state["ships_built_this_turn"] = [list(reversed(source))]
    elif corruption == "boolean":
        state["ships_built_this_turn"] = [[False, source[1]]]
    elif corruption == "setup":
        payload = snapshots.encode_snapshot(rules.build_game(1, 2, map_id="seafarers_gold_haven"))
        payload["state"]["ship_moved_this_turn"] = True
    else:
        state["ship_moved_this_turn"] = 1
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("case", ["ship", "moved_ship"])
def test_offline_ship_lifecycle_round_trip_stays_private_on_network(case):
    g = seafarers_case(case)
    data = json.loads(json.dumps(serialize.to_dict(g)))
    r = serialize.from_dict(data)
    assert_equivalent(g.ships_built_this_turn, r.ships_built_this_turn)
    assert_equivalent(g.ship_moved_this_turn, r.ship_moved_this_turn)
    for pid in (0, 1):
        assert {"ships_built_this_turn", "ship_moved_this_turn"}.isdisjoint(serialize.to_player_dict(g, pid))
    del data["ships_built_this_turn"]
    del data["ship_moved_this_turn"]
    legacy = serialize.from_dict(data)
    assert not legacy.ships_built_this_turn and legacy.ship_moved_this_turn


def test_qt_compatible_serializer_defaults_do_not_grant_old_ship_movement():
    g = seafarers_case("ship")
    class OlderModel:
        def __getattr__(self, key):
            if key in ("ships_built_this_turn", "ship_moved_this_turn"):
                raise AttributeError(key)
            return getattr(g, key)
    view = serialize.to_dict(OlderModel())
    assert view["ships_built_this_turn"] == [] and view["ship_moved_this_turn"]


def gold_game():
    g = rules.build_game(1, 2, map_id="seafarers_gold_haven")
    while g.phase == "setup":
        pid = g.turn
        if g.pending_action == "choose_gold":
            rules.apply_cmd(g, g.pending_pid, {"type": "choose_gold", "res": "ore", "qty": 1})
        elif g.setup_need == "settlement":
            candidates = [v for v in sorted(g.vertices) if rules.can_place_settlement(g, pid, v, False)]
            gold = [v for v in candidates if any(g.tiles[t].terrain == "gold" for t in g.vertex_adj_hexes[v])]
            rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": (gold or candidates)[0]})
        else:
            edge = next(e for e in sorted(g.edges) if rules.can_place_road(g, pid, e, g.setup_anchor_vid))
            rules.apply_cmd(g, pid, {"type": "place_road", "eid": edge})
    number = next(t.number for i, t in enumerate(g.tiles) if t.terrain == "gold" and i not in g.robbers
                  and any(i in g.vertex_adj_hexes[v] for v in g.occupied_v))
    roll(g, number)
    assert g.pending_action == "choose_gold" and g.pending_gold
    return g


def test_gold_queue_restores_and_choices_finish_identically():
    g = gold_game()
    restored = restore(g)
    while g.pending_gold:
        pid = g.pending_pid
        cmd = {"type": "choose_gold", "res": "ore", "qty": 1}
        assert rules.apply_cmd(g, pid, cmd)[1] == rules.apply_cmd(restored, pid, cmd)[1]
        assert_equivalent(g, restored)
        restored = restore(restored)


@pytest.mark.parametrize("case", ["before_roll", "after_roll", "trade", "road_two", "road_one",
                                  "plenty_ready", "monopoly_ready", "near_victory", "newly_bought"])
def test_restored_state_continues_with_identical_command_outcome(case):
    g = build_case(case)
    r = restore(g)
    if case == "before_roll":
        pid, cmd = 0, {"type": "roll", "roll": 6}
    elif case == "after_roll":
        pid, cmd = 0, {"type": "end_turn"}
    elif case == "trade":
        pid, cmd = 1, {"type": "trade_offer_accept", "offer_id": g.trade_offers[0].offer_id}
    elif case.startswith("road"):
        pid, cmd = 0, free_road(g)
    elif case == "plenty_ready":
        pid, cmd = 0, {"type": "play_dev", "card": "year_of_plenty", "a": "wood", "qa": 2, "b": "", "qb": 0}
    elif case == "monopoly_ready":
        pid, cmd = 0, {"type": "play_dev", "card": "monopoly", "r": "wood"}
    elif case == "near_victory":
        pid, cmd = 0, {"type": "buy_dev"}
    else:
        pid, cmd = 0, {"type": "play_dev", "card": "knight"}
    if case == "newly_bought":
        for state in (g, r):
            before = deepcopy(state)
            with pytest.raises(rules.RuleError, match="new or missing"):
                rules.apply_cmd(state, pid, cmd)
            assert_equivalent(before, state)
    else:
        assert rules.apply_cmd(g, pid, cmd)[1] == rules.apply_cmd(r, pid, cmd)[1]
    assert_equivalent(g, r)


def test_restored_road_credit_expires_and_keeps_built_road():
    g = restore(build_case("road_one"))
    roads = dict(g.occupied_e)
    roll(g)
    rules.apply_cmd(g, 0, {"type": "end_turn"})
    g = restore(g)
    assert g.free_roads[0] == 0 and g.occupied_e == roads
    roll(g)
    rules.apply_cmd(g, 1, {"type": "end_turn"})
    g = restore(g)
    roll(g)
    for resource, count in g.players[0].res.items():
        g.bank[resource] += count
        g.players[0].res[resource] = 0
    cmd = free_road(g)
    for paid in (False, True):
        before = deepcopy(g)
        if paid:
            cmd.pop("free", None)
        with pytest.raises(rules.RuleError):
            rules.apply_cmd(g, 0, cmd)
        assert_equivalent(before, g)


@pytest.mark.parametrize("change", ["deck_order", "free_roads", "hidden_card", "key_type", "victim", "tick"])
def test_equivalence_helper_detects_secret_and_type_differences(change):
    g = rich_state()
    r = deepcopy(g)
    if change == "deck_order":
        # Swap different card types, not identical neighboring knights.
        i = next(i for i, c in enumerate(r.dev_deck) if c != r.dev_deck[0])
        r.dev_deck[0], r.dev_deck[i] = r.dev_deck[i], r.dev_deck[0]
    elif change == "free_roads":
        r.free_roads[0] += 1
    elif change == "hidden_card":
        r.players[0].dev_cards.clear()
    elif change == "key_type":
        r.dev_played_turn = {str(k): v for k, v in r.dev_played_turn.items()}
    elif change == "victim":
        r.pending_victims.pop()
    else:
        r.tick += 1
    with pytest.raises(AssertionError):
        assert_equivalent(g, r)


def test_complete_field_guard_and_all_nondefault_fields():
    for cls, schema in snapshots._SCHEMAS:
        assert {f.name for f in fields(cls)} == set(schema)
    restore(rich_state())


def test_encoding_is_deterministic_and_nested_data_is_detached():
    g = rich_state()
    g.map_meta["nested"] = {"items": [1, False, None, {"value": "雪"}]}
    before = deepcopy(g)
    payload = snapshots.encode_snapshot(g)
    r = snapshots.decode_snapshot(payload)
    assert snapshots.dumps_snapshot(g) == snapshots.dumps_snapshot(r)
    restored_before = deepcopy(r)
    payload["state"]["board"]["vertex_adj_hexes"]["0"].clear()
    payload["state"]["map_meta"]["nested"]["items"].append(8)
    assert_equivalent(restored_before, r)
    payload_before = deepcopy(payload)
    r.players[0].res["wood"] += 1
    r.players[0].dev_cards[0]["new"] = False
    r.board.vertex_adj_hexes[0].append(0)
    r.dev_deck.pop()
    r.trade_offers[0].give["wood"] += 2
    r.map_meta["nested"]["items"].append(9)
    r.free_roads[0] = 0
    assert_equivalent(payload_before, payload)
    assert_equivalent(before, g)
    assert_equivalent(before, snapshots.loads_snapshot(snapshots.dumps_snapshot(g)))


@pytest.mark.parametrize("finished", [False, True])
def test_private_codec_never_changes_network_projection(finished):
    from app import server_mp as server
    g = build_case("hidden_vp")
    g.game_over, g.winner_pid = finished, 0 if finished else None
    room = server.Room("PRIVATE", 2, 0, [server.PlayerSlot(pid=i) for i in range(2)],
                       settings=server.RoomSettings(bank_visibility="hidden"), game=g,
                       ruleset_id=server.CURRENT_RULESET)
    views = [server._snapshot_state(g, room, pid) for pid in (0, 1)]
    payload = snapshots.encode_snapshot(g)
    assert payload["state"]["seed"] == g.seed
    assert payload["state"]["dev_deck"] == g.dev_deck
    assert payload["state"]["bank"] == g.bank
    assert payload["state"]["players"][0]["dev_cards"] == g.players[0].dev_cards
    r = restore(g)
    for pid in (0, 1):
        assert serialize.to_player_dict(g, pid) == serialize.to_player_dict(r, pid)
        assert server._snapshot_state(r, room, pid) == views[pid]
        view = views[pid]
        assert {"seed", "dev_deck", "bank", "snapshot_version", "engine_compatibility", "state"}.isdisjoint(view)
        assert "res" not in view["players"][1 - pid]
        assert "dev_cards" not in view["players"][1 - pid]
    assert views[1]["players"][0]["vp"] == g.players[0].vp - (0 if finished else 1)


def set_path(data, path, value):
    for key in path[:-1]:
        data = data[key]
    data[path[-1]] = value


@pytest.mark.parametrize("path,value", [
    (("seed",), True), (("seed",), "1"), (("tick",), 1.0),
    (("state_version",), 0), (("rolled",), 1), (("size",), float("nan")),
    (("turn",), 3), (("pending_pid",), 3), (("pending_victims",), [3]),
    (("pending_action",), "build_anything"), (("phase",), "game_over"),
    (("players", 1, "pid"), 0), (("players", 0, "res", "wood"), -1),
    (("players", 0, "dev_cards", 0, "new"), 1),
    (("dev_deck",), ["unknown_card"]), (("bank", "ore"), False),
    (("dev_played_turn",), {"01": True}), (("free_roads",), {"x": 2}),
    (("pending_gold",), {"3": 1}), (("discard_submitted",), [1, 1]),
    (("setup_idx",), 99), (("setup_anchor_vid",), 9999),
    (("robber_tile",), 99), (("robbers",), [99]), (("pirate_tile",), 99),
    (("board", "vertices", "0"), [0]),
    (("board", "vertices", "0"), [True, 0]),
    (("board", "vertex_adj_hexes", "0"), [999]),
    (("board", "vertex_adj_hexes", "0"), [0, 0]),
    (("board", "vertex_adj_hexes", "0"), []),
    (("board", "edges"), [[0, 1], [0, 1]]),
    (("board", "edges"), [[0, 9999]]),
    (("board", "edge_adj_hexes"), {"0-1": [0]}),
    (("board", "edge_adj_hexes"), {"1,0": [0]}),
    (("board", "occupied_v"), {"9999": [0, 1]}),
    (("board", "occupied_v"), {"0": [3, 1]}),
    (("board", "occupied_e"), {"9998,9999": 0}),
    (("board", "occupied_ships"), {"9998,9999": 0}),
    (("board", "ports"), [[[9998, 9999], "3:1"]]),
    (("trade_offers", 0, "to_pid"), 99),
    (("trade_offer_next_id",), 9),
    (("achievements", "largest_army_owner"), 99),
    (("roll_history",), [1]),
])
def test_corrupt_types_and_references_are_cleanly_rejected(path, value):
    payload = snapshots.encode_snapshot(rich_state())
    set_path(payload["state"], path, value)
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("version", [-1, 0, 3, 999])
def test_unsupported_snapshot_version_has_explicit_error(version):
    payload = snapshots.encode_snapshot(main_game())
    payload["snapshot_version"] = version
    with pytest.raises(snapshots.UnsupportedSnapshotVersion):
        snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("version", [0, 2])
def test_unsupported_engine_compatibility_has_explicit_error(version):
    payload = snapshots.encode_snapshot(main_game())
    payload["engine_compatibility"] = version
    with pytest.raises(snapshots.UnsupportedEngineCompatibility):
        snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("path", [("snapshot_version",), ("engine_compatibility",), ("state",),
                                  ("state", "dev_deck"), ("state", "free_roads"),
                                  ("state", "ships_built_this_turn"), ("state", "ship_moved_this_turn"),
                                  ("state", "board", "vertices"), ("state", "players", 0, "dev_cards")])
def test_required_fields_never_silently_default(path):
    payload = snapshots.encode_snapshot(main_game())
    parent = payload
    for key in path[:-1]:
        parent = parent[key]
    del parent[path[-1]]
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("payload", [None, [], "{}", {"snapshot_version": True},
                                    {"snapshot_version": 1, "engine_compatibility": 1, "state": {}}])
def test_invalid_envelope_shape(payload):
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("text", ["", "{", "{}", "null", "[]", "{\"seed\": NaN}",
                                 "{\"seed\": Infinity}", "{\"a\":1,\"a\":2}"])
def test_corrupt_truncated_nonfinite_or_duplicate_json(text):
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.loads_snapshot(text)


def test_duplicate_vertex_keys_are_rejected_before_json_parser_discards_them():
    text = snapshots.dumps_snapshot(main_game())
    text = text.replace('"vertices":{', '"vertices":{"0":[0,0],', 1)
    with pytest.raises(snapshots.SnapshotValidationError, match="duplicate JSON object key"):
        snapshots.loads_snapshot(text)


def test_duplicate_offers_overlapping_occupancy_and_unknown_fields_rejected():
    base = snapshots.encode_snapshot(rich_state())
    for corruption in ("offer", "overlap", "unknown"):
        payload = deepcopy(base)
        state = payload["state"]
        if corruption == "offer":
            state["trade_offers"].append(deepcopy(state["trade_offers"][0]))
        elif corruption == "overlap":
            edge = state["board"]["edges"][0]
            key = ",".join(map(str, edge))
            state["board"]["occupied_e"][key] = 0
            state["board"]["occupied_ships"][key] = 0
        else:
            state["unknown_future_field"] = 123
        with pytest.raises(snapshots.SnapshotValidationError):
            snapshots.decode_snapshot(payload)


@pytest.mark.parametrize("value", [{0: "non-json-key"}, {"value": (1, 2)},
                                  {"value": object()}, {"value": float("inf")}])
def test_metadata_is_json_only_without_unsafe_constructors(value):
    payload = snapshots.encode_snapshot(main_game())
    payload["state"]["map_meta"] = value
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)


def test_parse_and_structure_budgets_and_version_types(monkeypatch):
    payload = snapshots.encode_snapshot(main_game())
    for value in (True, 1.0, "1", None):
        invalid = deepcopy(payload)
        invalid["snapshot_version"] = value
        with pytest.raises(snapshots.SnapshotValidationError):
            snapshots.decode_snapshot(invalid)
    monkeypatch.setattr(snapshots, "MAX_JSON_NODES", 5)
    with pytest.raises(snapshots.SnapshotValidationError, match="limits"):
        snapshots.decode_snapshot(payload)
    monkeypatch.setattr(snapshots, "MAX_JSON_NODES", 200_000)
    recursive = []
    recursive.append(recursive)
    with pytest.raises(snapshots.SnapshotValidationError, match="limits"):
        snapshots.decode_snapshot(recursive)
    monkeypatch.setattr(snapshots, "MAX_JSON_BYTES", 10)
    with pytest.raises(snapshots.SnapshotValidationError, match="limits"):
        snapshots.loads_snapshot(" " * 11)


def test_encoder_rejects_silent_non_json_loss_and_does_not_mutate():
    g = main_game()
    g.map_meta["bad"] = (1, 2)
    before = deepcopy(g)
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.encode_snapshot(g)
    assert_equivalent(before, g)


@pytest.mark.parametrize("players", [1, 2, 3, 4, 6])
def test_player_count_rotated_setup_and_nondefault_geometry(players):
    g = rules.build_game(2**64 - 1, players, size=43, starting_pid=players - 1)
    g.rules_config.discard_threshold = 13
    restore(g)


def test_fixed_codec_preserves_imperfect_current_map_semantics():
    g = rules.build_game(1, 2, map_id="base_20vp_multi_robbers")
    assert len(g.robbers) == 2 and g.robbers[0] == g.robbers[1]
    # Ports can repeat or be inaccessible; codec validates IDs without redesigning maps.
    g.ports.append(g.ports[0])
    g.rules_config.max_roads = -1  # Existing map parser permits this limit.
    g.rules["custom_metadata"] = {"unchanged": [False, 3.5, None]}
    restore(g)


def test_encoder_rejects_python_type_changes_instead_of_normalizing_them():
    for field, value in (("edges", list(main_game().edges)), ("discard_submitted", [0]),
                         ("ports", [[main_game().ports[0][0], "3:1"]]),
                         ("ships_built_this_turn", []), ("ship_moved_this_turn", 1)):
        g = main_game()
        setattr(g, field, value)
        with pytest.raises(snapshots.SnapshotValidationError):
            snapshots.encode_snapshot(g)


def test_fifty_hex_custom_fixture_round_trip():
    terrain = ["forest", "hills", "pasture", "fields", "mountains", "desert", "sea", "gold"]
    data = {"version": 1, "name": "fifty_hex_codec_fixture", "tiles": [
        {"q": i % 10 + 7, "r": i // 10 - 6, "terrain": terrain[i % 8],
         "number": None if terrain[i % 8] in ("desert", "sea") else 5}
        for i in range(50)
    ]}
    g = rules.build_game(1, 2, map_data=data)
    assert len(g.tiles) == 50
    restore(g)


def test_restored_robber_moves_and_theft_remain_equivalent():
    g = build_case("multiple_victims")
    tile = next(t for t in range(len(g.tiles)) if t != g.robber_tile
                and len(rules._victims_for_tile(g, t, 0)) == 2)
    r = restore(g)
    cmd = {"type": "move_robber", "tile": tile, "victim": 2}
    assert rules.apply_cmd(g, 0, cmd)[1] == rules.apply_cmd(r, 0, cmd)[1]
    assert_equivalent(g, r)


def test_restored_discard_completion_remains_equivalent():
    g = build_case("partly_discarded")
    r = restore(g)
    need = g.discard_required[1]
    cmd = {"type": "discard", "discards": {"wheat": need}}
    assert rules.apply_cmd(g, 1, cmd)[1] == rules.apply_cmd(r, 1, cmd)[1]
    assert g.pending_action == "robber_move" and not g.discard_required
    assert_equivalent(g, r)


def test_huge_coordinate_and_json_scalar_types_have_persistence_errors():
    payload = snapshots.encode_snapshot(main_game())
    payload["state"]["board"]["vertices"]["0"][0] = 10**400
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.decode_snapshot(payload)
    with pytest.raises(snapshots.SnapshotValidationError):
        snapshots.loads_snapshot(b"{}")


def test_codec_fails_closed_when_engine_adds_a_field(monkeypatch):
    from types import SimpleNamespace
    from app.engine.state import GameState
    actual_fields = snapshots.fields
    monkeypatch.setattr(snapshots, "fields", lambda cls: (
        (*actual_fields(cls), SimpleNamespace(name="new_gameplay_field"))
        if cls is GameState else actual_fields(cls)
    ))
    with pytest.raises(snapshots.SnapshotValidationError, match="compatibility review"):
        snapshots.encode_snapshot(main_game())


def test_unicode_strings_round_trip_but_invalid_surrogates_fail_closed():
    g = main_game()
    g.players[0].name = "Игрок 雪 🎲"
    restore(g)
    payload = snapshots.encode_snapshot(g)
    payload["state"]["players"][0]["name"] = "\ud800"
    text = json.dumps(payload, ensure_ascii=True)
    with pytest.raises(snapshots.SnapshotValidationError, match="UTF-8"):
        snapshots.loads_snapshot(text)
