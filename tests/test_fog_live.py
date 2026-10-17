"""Real WS endpoint + PostgreSQL: opt-in integration without public activation."""
import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
import json
import os
import subprocess
import sys
import time
from uuid import uuid4

import pytest
from sqlalchemy import select

from app import net_protocol,server_mp as server
from app.engine import exploration,rules,maps
from app.fog_transport import FogMatchAccess
from app.match_rulesets import OFFICIAL_S3B_RULESET
from app.persistence.coordinator import Coordinator
from app.persistence import models as m
from app.persistence.credentials import utcnow
from app.persistence.recovery import clone_room
from app.persistence.snapshots import encode_snapshot
from tests.test_auth import auth_config
from tests.test_persistence_postgres import database_url,runtime
from tests.test_match_rulesets import unchanged_match
from tests.fog_live_support import fixture_room,tcp_server,reconnect,connect,http_json
from tests.full_match_support import free_port


@asynccontextmanager
async def live_fixture(url,monkeypatch,**kwargs):
    async with runtime(url,monkeypatch) as coord:
        room,proofs,route=await fixture_room(coord,**kwargs)
        scope=FogMatchAccess(room.id,room.match_uuid)
        monkeypatch.setattr(server.app.state,"_fog_fixture_access",(scope,),raising=False)
        async with tcp_server() as uri:
            peers=[await reconnect(uri,room.room_code,proof) for proof in proofs]
            try: yield coord,room,peers,route,uri,scope
            finally: await asyncio.gather(*(p.close() for p in peers),return_exceptions=True)


def private_views(peers):
    for pid,peer in enumerate(peers):
        state=peer.state["state"]
        assert state["you_pid"]==pid and not state["test_mode"] and not state["test_tools"]
        assert {"seed","dev_deck","bank","ships_built_this_turn","ship_moved_this_turn"}.isdisjoint(state)
        for other,player in enumerate(state["players"]):
            assert ("res" in player) is (other==pid)
            assert ("dev_cards" in player) is (other==pid)
        assert set(state["pending_gold"])<= {str(pid)}
        assert set(state["pending_gold_queue"])<= {pid}
        for tile in state["tiles"]:
            if tile["visibility"]=="hidden": assert tile["terrain"]=="fog" and tile["number"] is None
        text=json.dumps(state)
        assert all(key not in text for key in ("assignment_digest","initially_hidden","fog_pool","continuation","discoveries"))
    assert peers[0].state["state"]["tiles"]==peers[1].state["state"]["tiles"]
    for pid in (0,1):
        own=peers[pid].state["state"]["players"][pid]
        other=peers[1-pid].state["state"]["players"][pid]
        hidden=sum(c["type"]=="victory_point" for c in own["dev_cards"])
        assert other["vp"]==own["vp"]-(0 if peers[pid].state["state"]["game_over"] else hidden)
        assert own["resource_count"]==sum(own["res"].values()) and own["dev_count"]==len(own["dev_cards"])


@pytest.mark.parametrize("setup,kind,free",[(True,"place_road",False),(True,"build_ship",False),
    (False,"place_road",False),(False,"build_ship",False),(False,"place_road",True)])
def test_real_route_gold_commit_before_frames_and_ack_once(database_url,monkeypatch,setup,kind,free):
    async def run():
        async with live_fixture(database_url,monkeypatch,setup=setup,kind=kind,free=free) as (coord,room,peers,route,uri,scope):
            private_views(peers)
            assert all(p.room["ruleset_compatibility"]["status"]=="compatible" for p in peers)
            # The ordinary descriptor is still restricted, even in this process.
            assert net_protocol.room_state_message(room)["ruleset_compatibility"]["status"]=="compatibility_required"
            original_publish=server._publish_match_state
            observed=[]
            async def publish(conn,active,pid,slot_id,message):
                bundle=await coord.repository.load(active.id)
                assert bundle["head"]["tick"]==message["tick"]
                assert bundle["head"]["payload"]["engine"]["state"]["scenario"]["fog"]["revealed"]
                assert bundle["receipts"][-1]["outcome"]=="accepted"
                observed.append(message["tick"])
                await original_publish(conn,active,pid,slot_id,message)
            monkeypatch.setattr(server,"_publish_match_state",publish)
            original_ack=server._send_cmd_ack
            async def acknowledge(ws,cmd_id,seq,last_seq_applied,applied,duplicate=False):
                conn=server.manager.connections[ws]
                receipt=await coord.repository.receipt(room.players[conn.pid].match_player_id,seq,cmd_id)
                assert receipt is not None
                assert receipt["outcome"]==("accepted" if applied or duplicate else "rejected")
                await original_ack(ws,cmd_id,seq,last_seq_applied,applied,duplicate)
            monkeypatch.setattr(server,"_send_cmd_ack",acknowledge)
            request,ack=await peers[0].execute(route)
            assert ack["applied"] and observed==[1,1]
            await peers[1].wait(lambda:peers[1].state["tick"]==room.tick)
            private_views(peers)
            assert room.game.pending_action=="choose_gold" and room.game.scenario.fog.discoveries
            async with coord.database.sessions() as session,session.begin():
                assert (await session.execute(select(m.rooms.c.id).where(m.rooms.c.id==room.id)
                    .with_for_update(nowait=True))).scalar_one()==room.id
            assert peers[1].state["state"]["pending_gold"]=={}
            saved=encode_snapshot(room.game)
            _,ack=await peers[0].execute(route,request=request,applied=False)
            assert ack["duplicate"] and encode_snapshot(room.game)==saved
            before=deepcopy(room.game_events)
            await peers[0].execute({"type":"choose_gold","res":"gold"},applied=False)
            assert encode_snapshot(room.game)==saved and room.game_events==before
            count=room.game.pending_gold[0]
            request,_=await peers[0].execute({"type":"choose_gold","res":"ore","qty":count})
            await peers[1].wait(lambda:peers[1].state["tick"]==room.tick)
            assert room.game.pending_action is None and room.game.scenario.fog.continuation is None
            assert room.game.players[0].res["ore"]==count
            assert all(d.reward_status=="awarded" for d in room.game.scenario.fog.discoveries)
            private_views(peers)
            assert peers[0].state["state"]["game_events"][-1]["gained"]=={"ore":count}
            assert "gained" not in peers[1].state["state"]["game_events"][-1]
            saved=encode_snapshot(room.game)
            _,ack=await peers[0].execute(request["cmd"],request=request,applied=False)
            assert ack["duplicate"] and encode_snapshot(room.game)==saved
            if setup: assert room.game.phase=="main" and room.game.setup_idx==4
            if free: assert room.game.free_roads[0]==1 and not room.game.rolled
    asyncio.run(run())


def test_rejected_and_concurrent_commands_cannot_discover_or_reward_twice(database_url,monkeypatch):
    async def run():
        async with live_fixture(database_url,monkeypatch) as (coord,room,peers,route,*_):
            before=encode_snapshot(room.game)
            await peers[0].execute({"type":"place_road","eid":[-999,999]},applied=False)
            assert encode_snapshot(room.game)==before and not room.game_events
            good=peers[0].command(route)
            other=peers[1].command(route)
            await asyncio.gather(peers[0].send(good),peers[1].send(other))
            await peers[0].wait(lambda:good["cmd_id"] in peers[0].acks)
            await peers[1].wait(lambda:other["cmd_id"] in peers[1].acks)
            assert peers[0].acks[good["cmd_id"]]["applied"] and not peers[1].acks[other["cmd_id"]]["applied"]
            ledger=deepcopy(room.game.scenario.fog)
            assert len({d.tile_index for d in ledger.discoveries})==len(ledger.discoveries)
            await peers[0].execute(route,applied=False)
            assert room.game.scenario.fog==ledger
            rows=(await coord.repository.load(room.id))["receipts"]
            assert sum(row["outcome"]=="accepted" for row in rows)==1
    asyncio.run(run())


@pytest.mark.parametrize("stage",["before_commit","after_commit"])
def test_actual_transport_commit_faults_and_lost_ack_retry(database_url,monkeypatch,stage):
    async def run():
        async with live_fixture(database_url,monkeypatch) as (coord,room,peers,route,uri,scope):
            before=encode_snapshot(room.game)
            request=peers[0].command(route)
            proof=peers[0].token
            peers[0].drop_ack_ids.add(request["cmd_id"])
            def fault(point):
                if point==stage: raise OSError("synthetic live Fog COMMIT response fault")
            coord.repository._test_fault=fault
            await peers[0].send(request)
            if stage=="before_commit":
                await peers[0].wait(lambda:peers[0].closed)
                assert encode_snapshot(room.game)==before and not room.game_events
                assert all(not any(m["type"]=="match_state" and m["tick"]>0 for m in p.frames) for p in peers)
            else:
                await peers[0].wait(lambda:peers[0].state["tick"]==1)
                assert request["cmd_id"] not in peers[0].acks
            coord.repository._test_fault=None
            for p in peers: await p.close()
            expected=(await coord.repository.load(room.id))["head"]
            monkeypatch.setattr(server.app.state,"_fog_fixture_access",())
            def forbidden(*args,**kwargs): pytest.fail("Recovery must not execute exploration or gameplay")
            with monkeypatch.context() as guard:
                for name in ("build_game","apply_cmd","check_win","update_longest_road"):
                    guard.setattr(rules,name,forbidden)
                guard.setattr(exploration,"discover_route",forbidden)
                guard.setattr(maps.random,"SystemRandom",forbidden)
                server.manager=server.RoomManager()
                fresh=Coordinator(coord.database)
                await fresh.initialize(server.manager)
            monkeypatch.setattr(server,"persistence",fresh)
            restored=server.manager.rooms[room.room_code]
            assert server._fog_access(restored) is None  # Recovery never activates it.
            assert (await fresh.repository.load(room.id))["head"]==expected
            monkeypatch.setattr(server.app.state,"_fog_fixture_access",(scope,))
            owner=await reconnect(uri,room.room_code,proof)
            try:
                _,ack=await owner.execute(route,request=request,applied=stage=="before_commit")
                assert ack["duplicate"] is (stage=="after_commit")
                assert restored.game.scenario.fog.discoveries
                assert len({d.tile_index for d in restored.game.scenario.fog.discoveries})==len(restored.game.scenario.fog.discoveries)
                # Also lose the Gold choice ACK, reconnect and retry it. The
                # completed reward/continuation must not run a second time.
                count=restored.game.pending_gold[0]
                choice=owner.command({"type":"choose_gold","res":"ore","qty":count})
                owner.drop_ack_ids.add(choice["cmd_id"])
                tick=owner.state["tick"]
                await owner.send(choice)
                await owner.wait(lambda:owner.state["tick"]>tick)
                saved=encode_snapshot(restored.game)
                proof=owner.token
                await owner.close()
                owner=await reconnect(uri,room.room_code,proof)
                _,ack=await owner.execute(choice["cmd"],request=choice,applied=False)
                assert ack["duplicate"] and encode_snapshot(restored.game)==saved
                assert restored.game.players[0].res["ore"]==count
            finally: await owner.close()
    asyncio.run(run())


def test_normal_client_cannot_select_fog_even_beside_an_authorized_fixture(database_url,monkeypatch):
    from tests.test_fog_foundation import fog_recipe
    async def run():
        async with live_fixture(database_url,monkeypatch) as (coord,room,peers,route,uri,scope):
            from app.room_options import TurnTimer
            room.timer=TurnTimer.start(0,1,time.monotonic()-2,time.time()-2)
            timer=deepcopy(room.timer)
            state=encode_snapshot(room.game)
            await server._process_room_timer(room)
            assert room.timer==timer and encode_snapshot(room.game)==state and room.tick==0
            room.timer=None
            stranger=await connect(uri)
            try:
                await stranger.send({"type":"create_room","name":"Ordinary guest","max_players":2})
                await stranger.wait(lambda:stranger.room is not None and stranger.token is not None)
                ordinary=server.manager.rooms[stranger.room["room_code"]]
                source=fog_recipe()
                source["name"]="PRIVATE_SYNTHETIC_RECIPE"
                await stranger.send({"type":"set_map","map_data":source,"trusted_fog":True,
                                     "fog_access":{"room_id":str(room.id),"match_uuid":str(room.match_uuid)}})
                await stranger.wait(lambda:bool(stranger.errors))
                assert stranger.errors[-1]["code"]=="feature_disabled"
                assert "PRIVATE_SYNTHETIC_RECIPE" not in json.dumps(stranger.frames)
                assert ordinary.game is None and ordinary.selected_map_id=="base_standard" and ordinary.map_revision==0
                assert server._fog_access(ordinary) is None
                await stranger.send({"type":"close_room","room_code":ordinary.room_code,
                    "request_id":uuid4().hex,"expected_match_id":0})
                await stranger.wait(lambda:any(m["type"]=="room_closed" for m in stranger.frames))
                assert (await coord.repository.load(ordinary.id))["room"]["status"]=="closed"
            finally: await stranger.close()
    asyncio.run(run())


@pytest.mark.parametrize("account_owner", [False, True])
@pytest.mark.parametrize("forged_environment", [False, True])
def test_normal_production_entry_recovers_fog_without_activating_transport(database_url,monkeypatch,account_owner,forged_environment):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            room,proofs,route=await fixture_room(coord)
            saved=await coord.repository.load(room.id)
            port=free_port()
            uri=f"ws://127.0.0.1:{port}/ws"
            env={**os.environ,"DATABASE_URL":database_url,"CATAN_PERSISTENCE_MODE":"durable",
                 "CATAN_AUTH_MODE":"development","CATAN_AUTH_ORIGINS":"http://test","CATAN_ENABLE_TEST_TOOLS":"0"}
            if forged_environment:
                env.update(CATAN_ENABLE_FOG="1", CATAN_FOG_ENABLED="true",
                           CATAN_FOG_FIXTURE_ACCESS=json.dumps({"room_id":str(room.id),"match_uuid":str(room.match_uuid)}))
            args=[sys.executable,"-B","-m","uvicorn","app.server_mp:app","--host","127.0.0.1",
                  "--port",str(port),"--log-level","error","--no-access-log","--no-proxy-headers"]
            if os.name=="nt": args.extend(["--loop","app.persistence.db:selector_event_loop"])
            process=subprocess.Popen(args,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
            peer=None
            try:
                async def ready():
                    while True:
                        assert process.poll() is None,"Normal production entry failed to start"
                        try:
                            status,health=await http_json(uri,"/health")
                            if status==200 and health["ready"]: return
                        except OSError: pass
                        await asyncio.sleep(.05)
                await asyncio.wait_for(ready(),15)
                peer=await connect(uri)
                await peer.send({"type":"reconnect","room_code":room.room_code,"reconnect_token":proofs[0]})
                await peer.wait(lambda:peer.room is not None and peer.token is not None)
                assert peer.room["ruleset_compatibility"]["status"]=="compatibility_required"
                if account_owner:
                    from tests.test_auth import account
                    cookie,_=await account(coord,"Normal Fog account")
                    status,data=await http_json(uri,"/api/games/claim",{"room_code":room.room_code,
                        "reconnect_token":proofs[0],"connection_nonce":peer.nonce},cookie=cookie)
                    assert status==200 and data["claimed"]
                    await peer.close()
                    peer=await connect(uri,cookie=cookie)
                    await peer.send({"type":"account_continue","room_code":room.room_code})
                    await peer.wait(lambda:peer.room is not None)
                    assert peer.room["ruleset_compatibility"]["status"]=="compatibility_required"
                await peer.send({"type":"cmd","room_code":room.room_code,"match_id":room.match_id,
                    "cmd_id":"public-forged-fog-access","seq":1,"trusted_fog":True,
                    "fog_access":{"room_id":str(room.id),"match_uuid":str(room.match_uuid)},"cmd":route})
                await peer.wait(lambda:bool(peer.errors))
                assert peer.errors[-1]["code"]=="feature_disabled"
                assert not any(frame["type"]=="match_state" for frame in peer.frames)
                after=await coord.repository.load(room.id)
                assert after["head"]==saved["head"] and not after["receipts"]
            finally:
                if peer: await peer.close()
                process.terminate()
                await asyncio.to_thread(process.wait,10)
    asyncio.run(run())


@pytest.mark.parametrize("bad_scope",["none","dict","wrong_room","wrong_match","wrong_marker"])
def test_public_gate_and_exact_scope_remain_fail_closed(database_url,monkeypatch,bad_scope):
    async def run():
        async with live_fixture(database_url,monkeypatch) as (coord,room,peers,route,uri,scope):
            if bad_scope=="wrong_marker":
                room.ruleset_id=OFFICIAL_S3B_RULESET
            value={"room_id":str(room.id),"match_uuid":str(room.match_uuid)} if bad_scope=="dict" else (
                FogMatchAccess(uuid4(),room.match_uuid) if bad_scope=="wrong_room" else
                FogMatchAccess(room.id,uuid4()) if bad_scope=="wrong_match" else None)
            monkeypatch.setattr(server.app.state,"_fog_fixture_access",() if value is None else (value,))
            assert server._fog_access(room) is None
            before=encode_snapshot(room.game)
            error_count=len(peers[0].errors)
            request=peers[0].command({**route,"trusted_fog":True})
            request.update(trusted_fog=True,fog_access={"room_id":str(room.id)})
            await peers[0].send(request)
            await peers[0].wait(lambda:len(peers[0].errors)>error_count)
            assert peers[0].errors[-1]["code"]=="feature_disabled"
            assert encode_snapshot(room.game)==before and room.players[0].last_seq_applied==0
            frames=len(peers[0].frames)
            async with room.lock: await server._send_match_state(room)
            await asyncio.sleep(.03)
            assert not any(m["type"]=="match_state" for m in peers[0].frames[frames:])
    asyncio.run(run())
