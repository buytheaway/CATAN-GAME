"""Official recipes use the shared engine and existing authoritative dispatch.

Count/settings rejection tests do not claim a complete natural match. Canonical
board inventories and full paid exploration are verified separately.
"""
import asyncio
from copy import deepcopy

import pytest

from app import net_protocol, server_mp as server
from app.engine import maps, rules
from app.match_rulesets import OFFICIAL_S3A_RULESET
from app.persistence.snapshots import encode_snapshot
from tests.test_room_creation_limits import configure, client


OFFICIAL = tuple(maps.OFFICIAL_NEW_SHORES_PRESETS.items())
CUSTOM = ("seafarers_simple_1", "seafarers_simple_2", "seafarers_gold_haven", "seafarers_pirate_lanes")


async def lobby(players=3):
    clients = [client(f"198.51.100.{20 + i}") for i in range(players)]
    await server._dispatch(clients[0], {"type": "create_room", "name": "Host", "max_players": 6})
    room = server.manager.rooms[clients[0].room_code]
    for i, conn in enumerate(clients[1:], 1):
        await server._dispatch(conn, {"type": "join_room", "room_code": room.room_code, "name": f"Player {i}"})
    return room, clients


def unchanged_fields(room):
    return (deepcopy(net_protocol.room_state_message(room)), room.durable_revision, room.match_uuid,
            encode_snapshot(room.game) if room.game is not None else None,
            [(slot.id, slot.token_hash, slot.token_expires_at, slot.token_revoked_at) for slot in room.players])


@pytest.mark.parametrize("preset,players", OFFICIAL)
def test_official_recipe_creation_preserves_explicit_identity_and_existing_codec(preset, players):
    source = maps.get_preset_map(preset)
    assert maps.official_preset_meta(source)["required_players"] == players
    assert next(meta for meta in maps.list_presets() if meta["id"] == preset) == maps.get_preset_meta(preset)
    game = rules.build_game(17, players, map_id=preset)
    assert game.map_id == preset and game.map_meta["official_scenario"] == "heading_for_new_shores"
    assert game.rules_config.target_vp == 14 and game.rules_config.discard_threshold == 7
    assert game.scenario.rules.new_island_vp == 2 and game.scenario.rules.starting_islands
    payload = encode_snapshot(game)
    assert (payload["snapshot_version"], payload["engine_compatibility"]) == (4, 3)


@pytest.mark.parametrize("preset,required", OFFICIAL)
@pytest.mark.parametrize("players", [1, 2, 3, 4, 5, 6])
def test_official_builders_enforce_the_exact_variant_player_count(preset, required, players):
    if players == required:
        assert len(rules.build_game(17, players, map_id=preset).players) == players
    else:
        with pytest.raises(maps.MapValidationError, match="exactly"):
            rules.build_game(17, players, map_id=preset)


@pytest.mark.parametrize("tamper", ["tile", "target", "starting_island", "ports", "edition", "players", "pages", "missing_marker", "unknown_marker"])
def test_official_claims_require_the_exact_shipped_recipe_without_mutating_lobby(monkeypatch, tamper):
    configure(monkeypatch, rate=20)
    preset = "seafarers_official_new_shores_3"
    source = deepcopy(maps.get_preset_map(preset))
    if tamper == "tile": source["tiles"][0]["terrain"] = "forest"
    elif tamper == "target": source["rules"]["target_vp"] = 12
    elif tamper == "starting_island": source["rules"]["scenario"]["starting_islands"] = [999]
    elif tamper == "ports": source["ports"] = []
    elif tamper == "edition": source["official_scenario"]["edition"] = "unknown"
    elif tamper == "players": source["official_scenario"]["players"] = True
    elif tamper == "pages": source["official_scenario"]["source_pages"] = [8.0, 9]
    elif tamper == "missing_marker": del source["official_scenario"]
    else: source["official_scenario"]["unverified"] = True
    with pytest.raises(maps.MapValidationError):
        rules.build_game(17, 3, map_id=preset, map_data=source)
    room = server.manager.create_room("Host", 6)
    before = unchanged_fields(room)
    with pytest.raises(rules.RuleError) as error:
        server._set_map(room, 0, {"map_id": preset, "map_data": source})
    assert error.value.code == "invalid" and unchanged_fields(room) == before and server.persistence.ready


@pytest.mark.parametrize("preset,required", OFFICIAL)
def test_custom_upload_cannot_spoof_an_official_map_id(monkeypatch, preset, required):
    configure(monkeypatch)
    source = maps.get_preset_map("base_standard")
    with pytest.raises(maps.MapValidationError):
        rules.build_game(17, required, map_id=preset, map_data=source)
    room = server.manager.create_room("Host", 6)
    before = unchanged_fields(room)
    with pytest.raises(rules.RuleError):
        server._set_map(room, 0, {"map_id": preset, "map_data": source})
    assert unchanged_fields(room) == before


def test_canonical_upload_normalizes_identity_and_does_not_inherit_custom_overrides(monkeypatch):
    configure(monkeypatch)
    room = server.manager.create_room("Host", 6)
    server._set_room_settings(room, 0, {"target_vp": 10, "discard_threshold": 12, "turn_timer": 60})
    preset = "seafarers_official_new_shores_3"
    source = maps.get_preset_map(preset)
    server._set_map(room, 0, {"map_id": "uploaded-file", "map_data": source})
    assert room.selected_map_id == preset and room.selected_map_data == source
    assert room.selected_map_meta == maps.get_preset_meta(preset)
    assert room.settings.target_vp is None and room.settings.discard_threshold == 7
    assert room.settings.turn_timer == 60 and room.selected_rules_config["target_vp"] == 14
    assert rules.build_game(17, 3, map_id="uploaded-file", map_data=source).map_id == preset


@pytest.mark.parametrize("patch", [{"target_vp": 10}, {"discard_threshold": 8}, {"target_vp": 14, "discard_threshold": 6}])
def test_official_match_rule_overrides_are_rejected_atomically(monkeypatch, patch):
    configure(monkeypatch, rate=20)
    async def run():
        room, clients = await lobby()
        await server._dispatch(clients[0], {"type": "set_map", "map_id": "seafarers_official_new_shores_3"})
        before = unchanged_fields(room)
        with pytest.raises(rules.RuleError, match="14 VP"):
            await server._dispatch(clients[0], {"type": "set_settings", "settings": patch})
        assert unchanged_fields(room) == before and server.persistence.ready
        await server._dispatch(clients[0], {"type": "set_settings", "settings": {"target_vp": 14, "discard_threshold": 7}})
        await server._dispatch(clients[0], {"type": "start_match"})
        assert room.game.rules_config.target_vp == 14 and room.game.rules_config.discard_threshold == 7
    asyncio.run(run())


@pytest.mark.parametrize("preset,required", OFFICIAL)
def test_dispatch_counts_connected_players_not_lobby_capacity_and_publishes_exact_variant(monkeypatch, preset, required):
    configure(monkeypatch, rate=20)
    async def run():
        room, clients = await lobby(required - 1)
        await server._dispatch(clients[0], {"type": "set_map", "map_id": preset})
        before = unchanged_fields(room)
        with pytest.raises(rules.RuleError, match="connected players"):
            await server._dispatch(clients[0], {"type": "start_match"})
        assert unchanged_fields(room) == before and room.max_players == 6 and room.game is None
        extra = client("198.51.100.40")
        await server._dispatch(extra, {"type": "join_room", "room_code": room.room_code, "name": "Last player"})
        clients.append(extra)
        await server._dispatch(clients[0], {"type": "start_match"})
        assert room.game.map_id == preset and room.ruleset_id == OFFICIAL_S3A_RULESET and len(room.game.players) == required
        for conn in clients:
            view = next(message["state"] for message in reversed(conn.ws.messages) if message["type"] == "match_state")
            assert view["map_id"] == preset and view["rules_config"]["target_vp"] == 14
            assert view["scenario"]["rules"]["new_island_vp"] == 2
            assert len(view["players"]) == required and "seed" not in view and "dev_deck" not in view
            assert all("res" not in player and "dev_cards" not in player for player in view["players"] if player["pid"] != conn.pid)
    asyncio.run(run())


def test_official_host_and_current_socket_authority_remain_required(monkeypatch):
    configure(monkeypatch, rate=20)
    async def run():
        room, clients = await lobby()
        before = unchanged_fields(room)
        with pytest.raises(rules.RuleError) as error:
            await server._dispatch(clients[1], {"type": "set_map", "map_id": "seafarers_official_new_shores_3"})
        assert error.value.code == "forbidden" and unchanged_fields(room) == before
        fresh = client("198.51.100.45")
        await server._dispatch(fresh, {"type": "reconnect", "room_code": room.room_code,
                                       "reconnect_token": room.players[0].reconnect_token})
        before = unchanged_fields(room)
        with pytest.raises(rules.RuleError) as error:
            await server._dispatch(clients[0], {"type": "set_map", "room_code": room.room_code,
                                               "map_id": "seafarers_official_new_shores_3"})
        # The real takeover clears the old socket's server-side room binding;
        # a client-supplied code does not recreate that binding.
        assert error.value.code == "not_found" and unchanged_fields(room) == before
        await server._dispatch(fresh, {"type": "set_map", "map_id": "seafarers_official_new_shores_3"})
        await server._dispatch(fresh, {"type": "start_match"})
        assert room.game.map_id == "seafarers_official_new_shores_3"
    asyncio.run(run())


@pytest.mark.parametrize("preset,required", OFFICIAL)
def test_official_rematch_cannot_change_variant_player_count_or_old_match(monkeypatch, preset, required):
    configure(monkeypatch, rate=20)
    async def run():
        room, clients = await lobby(required)
        await server._dispatch(clients[0], {"type": "set_map", "map_id": preset})
        await server._dispatch(clients[0], {"type": "start_match"})
        # Synthetic completed fixture isolates lifecycle; full victory is tested separately.
        room.game.game_over, room.game.winner_pid = True, 0
        await server._dispatch(clients[-1], {"type": "leave_room"})
        before = unchanged_fields(room)
        with pytest.raises(rules.RuleError, match="connected players"):
            await server._dispatch(clients[0], {"type": "rematch"})
        assert unchanged_fields(room) == before
        fresh = client("198.51.100.46")
        await server._dispatch(fresh, {"type": "reconnect", "room_code": room.room_code,
                                       "reconnect_token": room.players[required - 1].reconnect_token})
        old_uuid, old_epoch = room.match_uuid, room.match_id
        await server._dispatch(clients[0], {"type": "rematch"})
        assert room.match_uuid != old_uuid and room.match_id == old_epoch + 1 and room.tick == 0
        assert room.game.map_id == preset and len(room.game.players) == required
        assert room.game.scenario.awarded_islands == {} and room.game.scenario.home_islands == {i: set() for i in range(required)}
    asyncio.run(run())


@pytest.mark.parametrize("preset", CUSTOM)
def test_existing_custom_seafarers_keep_two_player_setup_and_host_rule_overrides(monkeypatch, preset):
    configure(monkeypatch, rate=20)
    async def run():
        room, clients = await lobby(2)
        await server._dispatch(clients[0], {"type": "set_map", "map_id": preset})
        await server._dispatch(clients[0], {"type": "set_settings", "settings": {"target_vp": 12, "discard_threshold": 8}})
        await server._dispatch(clients[0], {"type": "start_match"})
        assert room.game.rules_config.target_vp == 12 and room.game.rules_config.discard_threshold == 8
        assert room.game.scenario.rules.starting_islands is None and room.game.scenario.rules.new_island_vp == 0
        assert "official_scenario" not in room.game.map_meta and "required_players" not in room.game.map_meta
    asyncio.run(run())


def test_malformed_map_name_is_a_client_rejection_not_a_persistence_outage(monkeypatch):
    configure(monkeypatch)
    room = server.manager.create_room("Host", 6)
    source = maps.get_preset_map("base_standard")
    source["name"] = []
    before = unchanged_fields(room)
    with pytest.raises(rules.RuleError):
        server._set_map(room, 0, {"map_data": source})
    assert unchanged_fields(room) == before and server.persistence.ready


@pytest.mark.parametrize("preset,required", OFFICIAL)
def test_official_frame_shipping_uses_existing_graph_and_round_trips_without_new_hexes(preset, required):
    from app.engine.topology import island_ids
    from app.persistence.snapshots import decode_snapshot
    game = rules.build_game(17, required, map_id=preset)
    source = maps.get_preset_map(preset)
    assert len(game.tiles) == len(source["tiles"]) and game.rules["sea_frame"] is True
    roots = island_ids(game.board)
    main = set(game.scenario.rules.starting_islands)
    edge = next(edge for edge, adjacent in sorted(game.edge_adj_hexes.items())
                if len(adjacent) == 1 and roots.get(adjacent[0]) in main
                and any(rules.can_place_settlement(game, game.turn, vertex, False) for vertex in edge))
    vertex = next(vertex for vertex in edge if rules.can_place_settlement(game, game.turn, vertex, False))
    assert not any(game.tiles[index].terrain == "sea" for index in game.edge_adj_hexes[edge])
    assert rules._edge_has_sea(game, edge)
    rules.apply_cmd(game, game.turn, {"type": "place_settlement", "vid": vertex})
    assert rules.can_place_ship(game, game.turn, edge, vertex)
    rules.apply_cmd(game, game.turn, {"type": "build_ship", "eid": edge})
    assert game.occupied_ships[edge] == 0
    restored = decode_snapshot(encode_snapshot(game))
    assert restored == game and rules._edge_has_sea(restored, edge)
    base = rules.build_game(17, 2)
    boundary = next(edge for edge, adjacent in base.edge_adj_hexes.items() if len(adjacent) == 1)
    assert not rules._edge_has_sea(base, boundary)


@pytest.mark.parametrize("preset,required", OFFICIAL)
def test_official_harbor_types_shuffle_only_at_fixed_authoritative_anchors(preset, required):
    source = maps.get_preset_map(preset)
    expected_edges = [tuple(sorted(port["edge"])) for port in source["ports"]]
    expected_types = sorted(port["type"] for port in source["ports"])
    arrangements = set()
    for seed in range(10):
        game = rules.build_game(seed, required, map_id=preset)
        assert [edge for edge, _ in game.ports] == expected_edges
        assert sorted(kind for _, kind in game.ports) == expected_types
        arrangements.add(tuple(kind for _, kind in game.ports))
        assert game.ports == rules.build_game(seed, required, map_id=preset).ports
    assert len(arrangements) > 1


@pytest.mark.parametrize("flag", [True, 1, "true", []])
def test_custom_maps_cannot_activate_official_frame_semantics(flag):
    source = maps.get_preset_map("base_standard")
    source["rules"]["sea_frame"] = flag
    with pytest.raises(maps.MapValidationError):
        rules.build_game(17, 2, map_data=source)
