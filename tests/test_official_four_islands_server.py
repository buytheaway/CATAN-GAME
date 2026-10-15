"""Canonical Four Islands identity, selection and authoritative start gates."""
import asyncio
from copy import deepcopy

import pytest

from app import server_mp as server
from app.engine import maps, rules
from app.engine.public_projection import public_map_metadata
from app.match_rulesets import OFFICIAL_S3B_RULESET
from tests.test_official_new_shores_server import lobby, unchanged_fields
from tests.test_room_creation_limits import configure, client


@pytest.mark.parametrize("players", [3,4])
@pytest.mark.parametrize("online", [1,2,3,4,5,6])
def test_exact_variant_count_and_personalized_authoritative_start(monkeypatch, players, online):
    preset=f"seafarers_official_four_islands_{players}"
    if online!=players:
        with pytest.raises(maps.MapValidationError,match="exactly"):
            rules.build_game(17,online,map_id=preset)
    configure(monkeypatch,rate=20)
    async def run():
        room,clients=await lobby(online)
        await server._dispatch(clients[0],{"type":"set_map","map_id":preset})
        for c in clients:
            published=next(m for m in reversed(c.ws.messages) if m["type"]=="room_state")
            assert published["map_meta"]["official_scenario"]=="the_four_islands"
            assert published["map_meta"]["required_players"]==players
            descriptor=next(m for m in published["map_presets"] if m["id"]==preset)
            assert descriptor["required_players"]==players and descriptor["official_scenario"]=="the_four_islands"
        before=unchanged_fields(room)
        if online!=players:
            with pytest.raises(rules.RuleError,match="connected players"):
                await server._dispatch(clients[0],{"type":"start_match"})
            assert unchanged_fields(room)==before
        else:
            await server._dispatch(clients[0],{"type":"start_match"})
            assert room.ruleset_id==OFFICIAL_S3B_RULESET
            assert room.game.rules_config.target_vp==13 and room.game.scenario.rules.starting_islands is None
            for c in clients:
                view=next(m["state"] for m in reversed(c.ws.messages) if m["type"]=="match_state")
                assert view["map_id"]==preset and view["rules_config"]["target_vp"]==13
                assert view["map_meta"]["official_scenario"]=="the_four_islands"
                assert all("res" not in p and "dev_cards" not in p for p in view["players"] if p["pid"]!=c.pid)
        assert server.persistence.ready
    asyncio.run(run())


def test_public_descriptor_remains_closed_typed_and_contains_no_recipe():
    meta=maps.get_preset_meta("seafarers_official_four_islands_3")
    projected=public_map_metadata({**meta,"secret_assignments":{"synthetic":True},"seed":17})
    assert projected==meta
    for patch in ({"required_players":True},{"required_players":3.0},{"official_scenario":"heading_for_new_shores"},
                  {"id":"custom-four-islands"}):
        assert "official_scenario" not in public_map_metadata({**meta,**patch})


@pytest.mark.parametrize("tamper", ["tile","target","starts","ports","frame","players","id_type","pages","missing","alias"])
def test_modified_custom_cannot_impersonate_official_or_mutate_room(monkeypatch,tamper):
    configure(monkeypatch)
    preset="seafarers_official_four_islands_3"
    source=deepcopy(maps.get_preset_map(preset))
    if tamper=="tile": source["tiles"][0]["number"]=11
    elif tamper=="target": source["rules"]["target_vp"]=14
    elif tamper=="starts": source["rules"]["scenario"]["starting_islands"]=[0]
    elif tamper=="ports": source["ports"]=[]
    elif tamper=="frame": source["rules"]["sea_frame"]=False
    elif tamper=="players": source["official_scenario"]["players"]=True
    elif tamper=="id_type": source["official_scenario"]["id"]=[]
    elif tamper=="pages": source["official_scenario"]["source_pages"]=[11,13]
    elif tamper=="missing": del source["official_scenario"]
    else: source=maps.get_preset_map("base_standard")
    with pytest.raises(maps.MapValidationError):
        rules.build_game(17,3,map_id=preset,map_data=source)
    room=server.manager.create_room("Host",6)
    before=unchanged_fields(room)
    with pytest.raises(rules.RuleError) as error:
        server._set_map(room,0,{"map_id":preset,"map_data":source})
    assert error.value.code=="invalid" and unchanged_fields(room)==before and server.persistence.ready


@pytest.mark.parametrize("players",[3,4])
def test_canonical_upload_clears_custom_overrides_and_locks_verified_rules(monkeypatch,players):
    configure(monkeypatch)
    room=server.manager.create_room("Host",6)
    server._set_room_settings(room,0,{"target_vp":10,"discard_threshold":12,"turn_timer":60})
    preset=f"seafarers_official_four_islands_{players}"
    source=maps.get_preset_map(preset)
    server._set_map(room,0,{"map_id":"upload","map_data":source})
    assert room.selected_map_id==preset and room.selected_map_meta==maps.get_preset_meta(preset)
    assert room.selected_rules_config["target_vp"]==13 and room.settings.target_vp is None
    assert room.settings.discard_threshold==7 and room.settings.turn_timer==60
    before=unchanged_fields(room)
    for patch in ({"target_vp":14},{"discard_threshold":8}):
        with pytest.raises(rules.RuleError,match="13 VP"):
            server._set_room_settings(room,0,patch)
        assert unchanged_fields(room)==before
    server._set_room_settings(room,0,{"target_vp":13,"discard_threshold":7})


def test_host_and_controlling_socket_are_required_for_official_selection(monkeypatch):
    configure(monkeypatch,rate=20)
    async def run():
        room,clients=await lobby()
        message={"type":"set_map","map_id":"seafarers_official_four_islands_3"}
        before=unchanged_fields(room)
        with pytest.raises(rules.RuleError):
            await server._dispatch(clients[1],message)
        assert unchanged_fields(room)==before
        replacement=client("198.51.100.45")
        proof=next(m["reconnect_token"] for m in clients[0].ws.messages if m["type"]=="reconnect_token")
        await server._dispatch(replacement,{"type":"reconnect","room_code":room.room_code,"reconnect_token":proof})
        with pytest.raises(rules.RuleError):
            await server._dispatch(clients[0],message)
        await server._dispatch(replacement,message)
        assert room.selected_map_id==message["map_id"]
    asyncio.run(run())
