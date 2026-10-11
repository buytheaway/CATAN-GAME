"""Public-shaped trusted projections; public Fog endpoints remain disabled."""
from copy import deepcopy
from dataclasses import replace
import json
import pytest

from app import game_events, net_protocol, server_mp as server
from app.engine import rules
from app.engine.exploration import assignment_digest, validate_fog_state, tile_is_known, FogUnavailableError
from app.engine.legal import board_legal_moves
from app.engine.serialize import project_fog_player_dict, to_dict, to_player_dict
from app.engine.state import RESOURCES
from app.persistence.snapshots import encode_snapshot
from app.match_rulesets import CURRENT_RULESET
from tests.test_fog_foundation import fog_recipe, recorded_fog
from tests.test_fog_exploration import exploration_game, route_edge, anchor_and_fund, execute
from tests.test_private_publication import guest_game


def projection_room(game=None):
    game = exploration_game() if game is None else game
    return server.Room("FOGPROJECTION", 2, 0,
        [server.PlayerSlot(i, f"P{i}") for i in range(2)], game=game,
        ruleset_id=CURRENT_RULESET, match_id=1, status="in_match",
        selected_map_id="fog-fixture", selected_map_meta={"id": "fog-fixture", "name": "Fog fixture", "description": ""},
        selected_rules_config=vars(game.rules_config).copy())


def test_room_metadata_drops_nested_private_fields():
    room = projection_room()
    private = {"SECRET_ASSIGNMENT": fog_recipe()["fog_pool"]}
    room.selected_map_meta["fog_pool"] = private
    room.selected_rules_config["scenario"] = private
    room.map_presets = [{"id": "base_standard", "name": "Base", "description": "", "private": private}]
    before = deepcopy((room.selected_map_meta, room.selected_rules_config, room.map_presets))
    message = net_protocol.room_state_message(room)
    assert "SECRET_ASSIGNMENT" not in json.dumps(message)
    assert set(message["map_meta"]) == {"id", "name", "description"}
    assert (room.selected_map_meta, room.selected_rules_config, room.map_presets) == before


def test_approved_metadata_keys_cannot_smuggle_nested_values_into_settings_or_labels():
    room = projection_room()
    private = {"SECRET_ASSIGNMENT": [vars(t) for t in room.game.tiles]}
    room.selected_map_meta["name"] = room.selected_map_meta["description"] = private
    room.selected_rules_config["target_vp"] = room.selected_rules_config["enable_gold"] = private
    result = net_protocol.room_state_message(room)
    assert "SECRET_ASSIGNMENT" not in json.dumps(result)
    assert result["map_meta"] == {"id": "fog-fixture"}
    assert result["settings"]["target_vp"] == room.game.rules_config.target_vp


def test_event_projection_drops_unlisted_fields_and_private_nested_keys():
    room = projection_room()
    game_events.record(room, "production", 0, player_pid=0, quantity=1,
        raw_terrain="SECRET_ASSIGNMENT", private={0: {"resources": {"wood": 1, "SECRET_ASSIGNMENT": 8},
                                                       "future_tiles": "SECRET_ASSIGNMENT"}})
    before = deepcopy(room.game_events)
    projected = game_events.project(room, 0)
    assert "SECRET_ASSIGNMENT" not in json.dumps(projected)
    assert projected[0]["resources"] == {"wood": 1}
    assert room.game_events == before


def counterfactual(terrain, number, stage="main"):
    a = recorded_fog(pending=True) if stage == "pending" else exploration_game(setup=stage == "setup")
    if stage == "robber":
        a.pending_action, a.pending_pid = "robber_move", 0
    elif stage == "free":
        a.rolled = False
        a.players[0].dev_cards = [{"type": "road_building", "new": False}]
        execute(a, {"type": "play_dev", "card": "road_building"})
    b = deepcopy(a)
    for index in b.scenario.rules.fog.initially_hidden:
        if index not in b.scenario.fog.revealed:
            b.tiles[index].terrain, b.tiles[index].number = terrain, number
    b.scenario.fog = replace(b.scenario.fog, assignment_digest=assignment_digest(b.board))
    for g in (a, b):
        g.map_meta["private"] = {"assignments": [{"terrain": t.terrain, "number": t.number} for t in g.tiles], "seed": g.seed}
        g.rules["private"] = {"pool": [[t.terrain, t.number] for t in g.tiles]}
        validate_fog_state(g)
        encode_snapshot(g)  # Both alternatives are valid trusted v4 states.
    return a, b


def observable(room, pid):
    return {"room": net_protocol.room_state_message(room),
            "match": net_protocol.match_state_message(room, server._project_fog_snapshot(room, pid)),
            "events": game_events.project(room, pid)}


@pytest.mark.parametrize("terrain,number", [("forest", 8), ("hills", 12), ("sea", None), ("desert", None), ("gold", 2)])
@pytest.mark.parametrize("stage", ["main", "setup", "robber", "free", "pending"])
def test_counterfactual_whole_outbound_views_and_legal_are_identical(terrain, number, stage):
    a, b = counterfactual(terrain, number, stage)
    before = deepcopy((a, b))
    for pid in (0, 1):
        assert observable(projection_room(a), pid) == observable(projection_room(b), pid)
        assert board_legal_moves(a, pid, trusted_fog=True) == board_legal_moves(b, pid, trusted_fog=True)
    assert (a, b) == before


def nested_keys(value):
    if isinstance(value, dict):
        return set(value).union(*(nested_keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(nested_keys(v) for v in value))
    return set()


@pytest.mark.parametrize("finished", [False, True])
def test_exact_tile_shape_metadata_and_other_players_privacy_even_after_game_over(finished):
    g = recorded_fog(pending=not finished)
    g.game_over, g.winner_pid = finished, 0 if finished else None
    g.players[0].dev_cards = [{"type": "knight", "new": False}]
    g.players[1].dev_cards = [{"type": "victory_point", "new": False}, {"type": "monopoly", "new": False}]
    g.players[1].vp = 4
    g.players[1].res["ore"] = 3
    g.map_meta.update(seed=g.seed, hidden_layout=[vars(t) for t in g.tiles], terrain_pool="PRIVATE_POOL")
    g.rules.update(seed=g.seed, private={"number_pool": "PRIVATE_POOL"})
    before = deepcopy(g)
    own = project_fog_player_dict(g, 0)
    peer = project_fog_player_dict(g, 1)
    for index, tile in enumerate(own["tiles"]):
        assert set(tile) == {"index", "q", "r", "center", "visibility", "terrain", "number"}
        assert tile["index"] == index and tile["q"] == g.tiles[index].q and tile["r"] == g.tiles[index].r
        assert tile["center"] == list(g.tiles[index].center)
        if tile_is_known(g, index):
            assert tile["visibility"] == "revealed"
            assert (tile["terrain"], tile["number"]) == (g.tiles[index].terrain, g.tiles[index].number)
        else:
            assert (tile["visibility"], tile["terrain"], tile["number"]) == ("hidden", "fog", None)
    forbidden = {"seed", "hidden_layout", "terrain_pool", "number_pool", "fog_pool", "assignment_digest",
                 "initially_hidden", "discoveries", "continuation", "dev_deck", "ships_built_this_turn", "ship_moved_this_turn"}
    assert forbidden.isdisjoint(nested_keys(own)) and "PRIVATE_POOL" not in json.dumps(own)
    assert own["tiles"] == peer["tiles"] and own["scenario"] == peer["scenario"]
    assert own["players"][0]["dev_cards"] == g.players[0].dev_cards
    assert {"res", "dev_cards"}.isdisjoint(own["players"][1])
    assert own["players"][1]["vp"] == (4 if finished else 3)
    assert "bank" not in own and set(own["bank_available"]) == set(RESOURCES)
    if not finished:
        assert own["pending_gold"] == {"0": g.pending_gold[0]}
        assert not peer["pending_gold"] and not peer["pending_gold_queue"]
    assert g == before
    own["tiles"][0]["center"][0] += 1
    own["players"][0]["res"]["wood"] += 1
    assert g == before


@pytest.mark.parametrize("command", [
    {"type": "move_robber", "tile": 0}, {"type": "move_pirate", "tile": 0},
    {"type": "place_road", "eid": [9998, 9999]}, {"type": "build_ship", "eid": [9998, 9999]},
    {"type": "place_settlement", "vid": 9999}, {"type": "upgrade_city", "vid": 9999},
    {"type": "play_dev", "card": "not_a_card"}, {"type": "choose_gold", "res": "gold"},
])
def test_equivalent_rejected_command_errors_are_not_a_hidden_terrain_oracle(command):
    a, b = counterfactual("sea", None, "robber" if "tile" in command else "main")
    errors = []
    for g in (a, b):
        before = deepcopy(g)
        with pytest.raises(rules.RuleError) as error:
            execute(g, command)
        errors.append(net_protocol.error_message(error.value.code, error.value.message))
        assert g == before
    assert errors[0] == errors[1]


@pytest.mark.parametrize("command", [{"type": "choose_gold", "res": "gold"},
    {"type": "choose_gold", "res": "ore", "qty": 0}, {"type": "end_turn"}, {"type": "roll"}])
def test_pending_gold_errors_and_private_options_are_counterfactually_equal(command):
    a, b = counterfactual("sea", None, "pending")
    responses = []
    for g in (a, b):
        before = deepcopy(g)
        with pytest.raises(rules.RuleError) as error:
            execute(g, command)
        responses.append((error.value.code, error.value.message, observable(projection_room(g), 0)))
        assert g == before
    assert responses[0] == responses[1]


@pytest.mark.parametrize("card,extra", [("knight", {}), ("road_building", {}),
                                      ("year_of_plenty", {"a": "wood", "qa": 1, "b": "ore", "qb": 1}),
                                      ("monopoly", {"r": "wood"})])
def test_dev_card_choices_and_targets_do_not_depend_on_hidden_assignments(monkeypatch, card, extra):
    monkeypatch.setattr(game_events.time, "time", lambda: 1000)  # Identical public display time.
    a, b = counterfactual("gold", 12)
    views = []
    for g in (a, b):
        g.players[0].dev_cards = [{"type": card, "new": False}]
        room = projection_room(g)
        before = game_events.resources_before(g)
        cmd = {"type": "play_dev", "card": card, **extra}
        _, events = execute(g, cmd)
        game_events.committed(room, 0, cmd, events, before, g.robber_tile, g.pirate_tile)
        room.game_events[-1]["future_assignments"] = g.map_meta["private"]
        room.game_events[-1]["_private"][0] = {"future_assignments": g.map_meta["private"]}
        views.append([observable(room, pid) for pid in (0, 1)])
        assert game_events.project(room, 0)[-1]["card"] == card
    assert views[0] == views[1]


@pytest.mark.parametrize("terrain,number", [("sea", None), ("forest", 12)])
def test_different_assignments_become_visible_only_after_accepted_discovery(terrain, number):
    a, b = counterfactual(terrain, number)
    edge = route_edge(a)
    for g in (a, b):
        anchor_and_fund(g, edge)
    assert project_fog_player_dict(a, 0) == project_fog_player_dict(b, 0)
    for g in (a, b):
        execute(g, {"type": "place_road", "eid": edge})
    assert a.scenario.fog.revealed == b.scenario.fog.revealed
    av, bv = project_fog_player_dict(a, 0), project_fog_player_dict(b, 0)
    for index in a.scenario.rules.fog.initially_hidden:
        if index not in a.scenario.fog.revealed:
            assert av["tiles"][index] == bv["tiles"][index]
    assert any(av["tiles"][i] != bv["tiles"][i] for i in a.scenario.fog.revealed)


def test_committed_discovery_events_order_rewards_and_gold_choices_are_personal():
    g = exploration_game("gold")
    edge = route_edge(g, minimum=3)
    anchor_and_fund(g, edge)
    room = projection_room(g)
    before = game_events.resources_before(g)
    cmd = {"type": "place_road", "eid": edge}
    _, events = execute(g, cmd)
    game_events.committed(room, 0, cmd, events, before, g.robber_tile, g.pirate_tile)
    projected = game_events.project(room, 1)
    discoveries = projected[1:]
    assert [e["type"] for e in projected] == ["place_road"] + ["discover_tile"] * 3
    assert [e["tile"] for e in discoveries] == sorted(g.scenario.fog.revealed)
    assert [e["id"] for e in projected] == list(range(1, 5))
    assert all(e["tick"] == 1 for e in projected)
    assert all(e["terrain"] == "gold" and e["number"] == 5
               and e["reward"] == {"kind": "gold_choice", "quantity": 1} for e in discoveries)
    before = game_events.resources_before(g)
    cmd = {"type": "choose_gold", "res": "ore"}
    _, events = execute(g, cmd)
    game_events.committed(room, 0, cmd, events, before, g.robber_tile, g.pirate_tile)
    assert game_events.project(room, 0)[-1]["gained"] == {"ore": 1}
    assert {"paid", "gained", "resource"}.isdisjoint(game_events.project(room, 1)[-1])
    assert game_events.project(room, 1)[:-1] == projected
    for _ in range(game_events.EVENT_LIMIT + 2):
        game_events.record(room, "end_turn", 0)
    assert len(room.game_events) == len(game_events.project(room, 0)) == game_events.EVENT_LIMIT


def test_unknown_future_events_unrevealed_targets_and_fog_debug_do_not_escape():
    room = projection_room()
    hidden = room.game.scenario.rules.fog.initially_hidden[0]
    for kind in ("discover_tile", "move_robber", "move_pirate"):
        game_events.record(room, kind, 0, tile=hidden, terrain=room.game.tiles[hidden].terrain,
                           number=room.game.tiles[hidden].number, future_tiles="SECRET_ASSIGNMENT")
    game_events.record(room, "future_engine_event", 0, hidden_layout="SECRET_ASSIGNMENT")
    game_events.record(room, "debug", 0, action="SECRET_ASSIGNMENT")
    assert game_events.project(room, 0) == game_events.project(room, 1) == []


@pytest.mark.parametrize("pid", [-1, 2, True, None])
def test_fog_personal_projection_requires_a_real_player_not_a_spectator(pid):
    with pytest.raises(ValueError, match="valid player"):
        project_fog_player_dict(exploration_game(), pid)


def test_projection_helpers_do_not_open_default_serialization_or_generic_publication(guest_game):
    import asyncio
    room, clients = guest_game
    room.game = exploration_game()
    for projector in (to_dict, lambda g: to_player_dict(g, 0)):
        with pytest.raises(FogUnavailableError):
            projector(room.game)
    message = net_protocol.match_state_message(room, server._project_fog_snapshot(room, 0))
    async def run():
        with pytest.raises(ValueError, match="per-recipient"):
            await server._broadcast(room, message)
        await server._publish_match_state(clients[0], room, 0, room.players[0].id, message)
        await server._send_match_state(room)
        assert all(not c.ws.states() for c in clients)
        assert all(c.ws.messages[-1]["type"] == "room_state" for c in clients)
    asyncio.run(run())


@pytest.mark.parametrize("terrain,stock", [("forest", None), ("sea", None), ("desert", None), ("mountains", 0)])
def test_discovery_event_uses_only_revealed_tile_and_public_reward(terrain, stock):
    g = exploration_game(terrain)
    edge = route_edge(g)
    anchor_and_fund(g, edge)
    if stock is not None:
        g.bank["ore"] = stock
    room = projection_room(g)
    before = game_events.resources_before(g)
    cmd = {"type": "place_road", "eid": edge}
    _, events = execute(g, cmd)
    game_events.committed(room, 0, cmd, events, before, g.robber_tile, g.pirate_tile)
    for event in game_events.project(room, 1)[1:]:
        assert event["terrain"] == terrain and event["number"] == g.tiles[event["tile"]].number
        if terrain in ("sea", "desert"):
            assert event["reward"] == {"kind": "none", "quantity": 0}
        else:
            assert event["reward"] == {"kind": "resource", "resource": "wood" if terrain == "forest" else "ore",
                                       "quantity": 1 if stock is None else 0}


@pytest.mark.parametrize("marker", [None, "unknown", "catan-seafarers-s1", "catan-seafarers-s2b-1"])
def test_internal_snapshot_projection_cannot_classify_unknown_provenance_as_current(marker):
    room = projection_room()
    room.ruleset_id = marker
    with pytest.raises(rules.RuleError) as error:
        server._project_fog_snapshot(room, 0)
    assert error.value.code == "compatibility_required"
