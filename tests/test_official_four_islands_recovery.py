"""Four Islands through dispatch/COMMIT/JSONB/recovery and private publication.

Opening actions are real. Funding, roll and terminal fixture are explicitly
limited to these atomicity tests; natural TCP matches live in a separate test.
"""
import asyncio
import json
from random import Random

import pytest
from sqlalchemy import select, update

from app import server_mp as server
from app.engine import maps, rules
from app.engine.scenario import vertex_islands
from app.engine.state import COST
from app.match_rulesets import OFFICIAL_S3A_RULESET, OFFICIAL_S3B_RULESET, restricted
from app.persistence import models as m
from app.persistence.coordinator import Coordinator
from app.persistence.errors import PersistenceUnavailable
from app.persistence.recovery import clone_room, restore_room
from app.persistence.snapshots import encode_snapshot
from tests.test_auth import connection
from tests.test_match_rulesets import unchanged_match
from tests.test_persistence_postgres import database_url, runtime, pair, command
from tests.test_seafarers_scenario_recovery import execute
from tests.test_seafarers_maps import fund
from tests.test_official_four_islands import setup_choice, next_island


async def prepare_arrival(players,homes=1):
    room,clients=await pair(capacity=players,names=tuple(f"Participant {p}" for p in range(players)),
                            map_id=f"seafarers_official_four_islands_{players}")
    rng=Random(0)
    while room.game.phase=="setup":
        await execute(room,clients,setup_choice(room.game,rng,homes))
    assert len(room.game.scenario.home_islands[0])==homes
    candidate=clone_room(room)
    rules.apply_cmd(candidate.game,0,{"type":"roll","roll":2})
    destination,path=next_island(candidate.game,0)
    fund(candidate.game,{"wood":len(path)+1,"sheep":len(path)+1,"wheat":1,"brick":1})
    for player in candidate.game.players:
        candidate.game.dev_deck.remove("knight")
        player.dev_cards.append({"type":"knight","new":False})
    await server._commit(room,candidate,snapshot=True)
    for edge in path:
        if edge not in room.game.occupied_ships:
            await execute(room,clients,{"type":"build_ship","eid":edge})
    return room,clients,destination


@pytest.mark.parametrize("players",[3,4])
@pytest.mark.parametrize("homes",[1,2])
def test_award_lost_ack_recovery_privacy_city_and_rematch(database_url,monkeypatch,players,homes):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients,destination=await prepare_arrival(players,homes)
            foreign,=vertex_islands(room.game.board,destination)
            before_vp=room.game.players[0].vp
            request=command(room,clients[0],{"type":"place_settlement","vid":destination})
            original_send=clients[0].ws.send_text
            dropped=[]
            async def observe_and_lose_ack(raw):
                message=json.loads(raw)
                if message["type"]=="match_state":
                    saved=await coord.repository.load(room.id)
                    receipt=await coord.repository.receipt(room.players[0].match_player_id,request["seq"],request["cmd_id"])
                    assert receipt["outcome"]=="accepted" and saved["head"]["tick"]==message["tick"]
                    assert saved["head"]["payload"]["engine"]["state"]["scenario"]["awarded_islands"]=={"0":[foreign]}
                if message["type"]=="cmd_ack" and message["cmd_id"]==request["cmd_id"]:
                    dropped.append(message)
                    return
                await original_send(raw)
            monkeypatch.setattr(clients[0].ws,"send_text",observe_and_lose_ack)
            await server._dispatch(clients[0],request)
            assert dropped[0]["applied"] and not dropped[0]["duplicate"]
            assert room.game.players[0].vp==before_vp+3
            saved=await coord.repository.load(room.id)
            assert saved["head"]["snapshot_version"]==4 and saved["head"]["engine_compatibility"]==3
            assert saved["match"]["ruleset_id"]==OFFICIAL_S3B_RULESET
            proofs=[c.ws.latest("reconnect_token")["reconnect_token"] for c in clients]
            def forbidden(*args,**kwargs):
                pytest.fail("Normal recovery must not execute gameplay or regenerate/validate recipes")
            with monkeypatch.context() as guard:
                guard.setattr(rules,"apply_cmd",forbidden)
                guard.setattr(rules,"build_game",forbidden)
                guard.setattr(maps,"official_preset_meta",forbidden)
                server.manager=server.RoomManager()
                fresh=Coordinator(coord.database)
                await fresh.initialize(server.manager)
            monkeypatch.setattr(server,"persistence",fresh)
            restored=server.manager.rooms[room.room_code]
            assert restored.game==room.game and restored.ruleset_id==OFFICIAL_S3B_RULESET
            clients=[await connection() for _ in range(players)]
            for pid,c in enumerate(clients):
                await server._dispatch(c,{"type":"reconnect","room_code":room.room_code,"reconnect_token":proofs[pid]})
                view=c.ws.latest("match_state")["state"]
                assert server._owns(c,restored) and view["players"][0]["special_vp"]==2
                assert view["scenario"]["awarded_islands"]=={"0":[foreign]}
                assert len(view["scenario"]["home_islands"]["0"])==homes
                assert {"seed","dev_deck","bank","ships_built_this_turn","ship_moved_this_turn"}.isdisjoint(view)
                for other,p in enumerate(view["players"]):
                    assert ("res" in p) is (other==pid) and ("dev_cards" in p) is (other==pid)
                    if other==pid: assert p["dev_cards"]==[{"type":"knight","new":False}]
            state=encode_snapshot(restored.game)
            await server._dispatch(clients[0],request)
            assert clients[0].ws.latest("cmd_ack")["duplicate"] and encode_snapshot(restored.game)==state
            candidate=clone_room(restored)
            fund(candidate.game,COST["city"])
            await server._commit(restored,candidate,snapshot=True)
            await execute(restored,clients,{"type":"upgrade_city","vid":destination})
            assert restored.game.scenario.awarded_islands=={0:{foreign}}
            assert restored.game.players[0].vp==before_vp+4

            candidate=clone_room(restored)
            candidate.game.players[0].vp=13
            candidate.game.game_over,candidate.game.winner_pid=True,0
            await server._commit(restored,candidate,snapshot=True)
            old_uuid=restored.match_uuid
            old=await fresh.repository.load(restored.id)
            # A disconnect cannot reinterpret this official variant or erase it.
            await server._dispatch(clients[-1],{"type":"leave_room"})
            with pytest.raises(rules.RuleError,match="exactly"):
                await server._dispatch(clients[0],{"type":"rematch"})
            replacement=await connection()
            await server._dispatch(replacement,{"type":"reconnect","room_code":room.room_code,"reconnect_token":proofs[-1]})
            clients[-1]=replacement
            connected=await fresh.repository.load(restored.id)
            assert connected["head"]==old["head"]
            for field in ("finished_at","winner_match_player_id","latest_snapshot_id"):
                assert connected["match"][field]==old["match"][field]
            old=connected  # Presence writes may update metadata, never the result.
            await server._dispatch(clients[0],{"type":"rematch"})
            assert restored.match_uuid!=old_uuid and restored.match_id==2 and restored.tick==0
            assert restored.ruleset_id==OFFICIAL_S3B_RULESET and restored.game.rules_config.target_vp==13
            assert restored.game.scenario.home_islands=={pid:set() for pid in range(players)}
            assert not restored.game.scenario.awarded_islands and all(p.last_seq_applied==0 for p in restored.players)
            assert all(c.ws.latest("match_state")["state"]["phase"]=="setup" for c in clients)
            async with coord.database.sessions() as session:
                old_match=(await session.execute(select(m.matches).where(m.matches.c.id==old_uuid))).mappings().one()
                old_head=(await session.execute(select(m.game_snapshots).where(m.game_snapshots.c.id==old["head"]["id"]))).mappings().one()
            assert old_match==old["match"] and old_head==old["head"]
    asyncio.run(run())


@pytest.mark.parametrize("players",[3,4])
def test_failed_award_commit_publishes_nothing_and_changes_no_durable_state(database_url,monkeypatch,players):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients,destination=await prepare_arrival(players)
            saved=await coord.repository.load(room.id)
            before=encode_snapshot(room.game)
            messages=[len(c.ws.messages) for c in clients]
            def fail(point):
                if point=="before_commit": raise OSError("synthetic S3B commit fault")
            coord.repository._test_fault=fail
            try:
                with pytest.raises(PersistenceUnavailable):
                    await execute(room,clients,{"type":"place_settlement","vid":destination})
            finally:
                coord.repository._test_fault=None
            assert encode_snapshot(room.game)==before and messages==[len(c.ws.messages) for c in clients]
            unchanged_match(saved,await coord.repository.load(room.id))
    asyncio.run(run())


@pytest.mark.parametrize("players",[3,4])
def test_wrong_historical_marker_preserves_read_only_ownership_not_execution(database_url,monkeypatch,players):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,clients=await pair(capacity=players,names=tuple(f"Player {p}" for p in range(players)),
                                    map_id=f"seafarers_official_four_islands_{players}")
            proof=clients[0].ws.latest("reconnect_token")["reconnect_token"]
            async with coord.database.sessions() as session,session.begin():
                await session.execute(update(m.matches).where(m.matches.c.id==room.match_uuid).values(ruleset_id=OFFICIAL_S3A_RULESET))
            original=await coord.repository.load(room.id)
            restored=restore_room(original)
            server.manager.rooms[room.room_code]=restored
            assert restricted(restored)
            c=await connection()
            await server._dispatch(c,{"type":"reconnect","room_code":room.room_code,"reconnect_token":proof})
            assert server._owns(c,restored) and c.ws.latest("room_state")["ruleset_compatibility"]["status"]=="compatibility_required"
            assert not any(message["type"]=="match_state" for message in c.ws.messages)
            with pytest.raises(rules.RuleError) as error:
                await server._dispatch(c,command(restored,c,{"type":"noop"}))
            assert error.value.code=="compatibility_required"
            unchanged_match(original,await coord.repository.load(room.id))
    asyncio.run(run())
