"""Counterfactual raw TCP/HTTP payloads and F1 ownership on real Fog sockets."""
import asyncio
from datetime import timedelta
import json

import pytest

from app import game_events,server_mp as server
from app.fog_transport import FogMatchAccess
from app.persistence.credentials import utcnow
from app.persistence.recovery import clone_room
from app.persistence.snapshots import encode_snapshot
from tests.fog_live_support import fixture_room,tcp_server,reconnect,connect,http_json
from tests.test_auth import auth_config,account
from tests.test_fog_live import live_fixture,private_views
from tests.test_fog_projection import counterfactual
from tests.test_persistence_postgres import database_url,runtime


def normalize(value):
    # Different rooms have independent IDs/clocks. Retain every gameplay field,
    # legal target, count, error and private projection; remove only these names.
    if isinstance(value,dict):
        return {k:normalize(v) for k,v in value.items() if k not in ("room_code","updated_at","at_ms")}
    if isinstance(value,list): return [normalize(v) for v in value]
    return value


@pytest.mark.parametrize("terrain,number",[("forest",8),("hills",12),("sea",None),("desert",None),("gold",2)])
@pytest.mark.parametrize("setup",[False,True])
def test_counterfactual_actual_ws_http_legal_errors_and_only_legitimate_revelation(database_url,monkeypatch,terrain,number,setup):
    async def run():
        async with runtime(database_url,monkeypatch) as coord:
            games=counterfactual(terrain,number,"setup" if setup else "main")
            fixtures=[await fixture_room(coord,game=g,setup=setup) for g in games]
            scopes=tuple(FogMatchAccess(room.id,room.match_uuid) for room,_,_ in fixtures)
            monkeypatch.setattr(server.app.state,"_fog_fixture_access",scopes,raising=False)
            cookie,_=await account(coord,"Fog account owner")
            async with tcp_server() as uri:
                pairs=[]
                try:
                    for room,proofs,_ in fixtures:
                        peers=[await reconnect(uri,room.room_code,proof) for proof in proofs]
                        pairs.append(peers)
                        status,data=await http_json(uri,"/api/games/claim",{
                            "room_code":room.room_code,"reconnect_token":proofs[1],"connection_nonce":peers[1].nonce},cookie=cookie)
                        assert status==200 and data["claimed"]
                    # Compare the actual JSON-decoded wire objects, not a call to
                    # the projection helper. Two owners have nonempty secret cards.
                    for pid in (0,1):
                        assert normalize(pairs[0][pid].state)==normalize(pairs[1][pid].state)
                        assert normalize(pairs[0][pid].room)==normalize(pairs[1][pid].room)
                    inspected=[]
                    for room,proofs,_ in fixtures:
                        status,data=await http_json(uri,"/api/reconnect/inspect-many",{"credentials":[
                            {"room_code":room.room_code,"reconnect_token":proofs[0]}]})
                        assert status==200
                        inspected.append(normalize(data))
                    assert inspected[0]==inspected[1]
                    status,active=await http_json(uri,"/api/games/active",cookie=cookie)
                    assert status==200
                    summaries=[next(g for g in active["games"] if g["room_code"]==room.room_code) for room,_,_ in fixtures]
                    assert normalize(summaries[0])==normalize(summaries[1])
                    assert "SECRET_ASSIGNMENT" not in json.dumps([inspected,active])
                    if not setup:
                        # Use a REAL Knight pending action: a hidden land/sea
                        # target must not be distinguishable by the refusal.
                        for peers in pairs:
                            await peers[0].execute({"type":"play_dev","card":"knight"})
                        for pid in (0,1):
                            await pairs[1][pid].wait(lambda:pairs[1][pid].state["tick"]==1)
                            assert normalize(pairs[0][pid].state)==normalize(pairs[1][pid].state)
                    errors=[]
                    for (room,_,_),peers in zip(fixtures,pairs):
                        before=encode_snapshot(room.game)
                        hidden=next(i for i,t in enumerate(peers[0].state["state"]["tiles"]) if t["visibility"]=="hidden")
                        invalid={"type":"place_road","eid":[-999,999]} if setup else {"type":"move_robber","tile":hidden}
                        await peers[0].execute(invalid,applied=False)
                        assert encode_snapshot(room.game)==before and not room.game.scenario.fog.revealed
                        errors.append([m for m in peers[0].frames if m["type"] in ("error","cmd_ack")])
                    # Command IDs are caller-controlled, not hidden-data output.
                    for messages in errors:
                        for m in messages: m.pop("cmd_id",None)
                    assert normalize(errors[0])==normalize(errors[1])
                    assert fixtures[0][2]==fixtures[1][2]
                    for (room,_,route),peers in zip(fixtures,pairs):
                        if not setup:
                            tile=peers[0].state["state"]["legal"]["robber_tiles"][0]
                            await peers[0].execute({"type":"move_robber","tile":tile})
                        before_hand=dict(room.game.players[0].res)
                        request,_=await peers[0].execute(route)
                        await peers[1].wait(lambda:peers[1].state["tick"]==room.tick)
                        private_views(peers)
                        revealed=room.game.scenario.fog.revealed
                        assert revealed and len(revealed)<len(room.game.scenario.rules.fog.initially_hidden)
                        expected=dict(before_hand)
                        if not setup:
                            expected["wood"]-=1
                            expected["brick"]-=1
                        ordinary={"forest":"wood","hills":"brick","pasture":"sheep","fields":"wheat","mountains":"ore"}
                        for index in revealed:
                            resource=ordinary.get(room.game.tiles[index].terrain)
                            if resource: expected[resource]+=1
                        assert room.game.players[0].res==expected
                        assert all(room.game.bank[r]+sum(p.res[r] for p in room.game.players)==19 for r in expected)
                        saved=encode_snapshot(room.game)
                        _,ack=await peers[0].execute(route,request=request,applied=False)
                        assert ack["duplicate"] and encode_snapshot(room.game)==saved
                        for pid in (0,1):
                            tiles=peers[pid].state["state"]["tiles"]
                            for index in room.game.scenario.rules.fog.initially_hidden:
                                if index in revealed:
                                    assert (tiles[index]["terrain"],tiles[index]["number"])==(room.game.tiles[index].terrain,room.game.tiles[index].number)
                                else: assert (tiles[index]["terrain"],tiles[index]["number"],tiles[index]["visibility"])==("fog",None,"hidden")
                finally:
                    await asyncio.gather(*(p.close() for pair in pairs for p in pair),return_exceptions=True)
    asyncio.run(run())


@pytest.mark.parametrize("credential",["expired","revoked","takeover"])
def test_live_guest_ownership_and_controlling_socket_takeover(database_url,monkeypatch,credential):
    async def run():
        async with live_fixture(database_url,monkeypatch) as (coord,room,peers,route,uri,scope):
            replacement=None
            before=len(peers[0].frames)
            try:
                if credential=="takeover":
                    replacement=await reconnect(uri,room.room_code,peers[0].token)
                else:
                    candidate=clone_room(room)
                    if credential=="expired": candidate.players[0].token_expires_at=utcnow()-timedelta(seconds=1)
                    else: candidate.players[0].token_revoked_at=utcnow()
                    await server._commit(room,candidate)
                async with room.lock: await server._send_match_state(room)
                if credential!="takeover": await peers[0].wait(lambda:peers[0].closed)
                else:
                    count=len(peers[0].errors)
                    await peers[0].send(peers[0].command(route))
                    await peers[0].wait(lambda:len(peers[0].errors)>count)
                assert not any(m["type"]=="match_state" for m in peers[0].frames[before:])
                assert room.tick==0 and not room.game.scenario.fog.revealed
                if replacement: private_views([replacement,peers[1]])
            finally:
                if replacement: await replacement.close()
    asyncio.run(run())


def test_account_continue_session_revocation_and_publication_order(database_url,monkeypatch):
    async def run():
        async with live_fixture(database_url,monkeypatch) as (coord,room,peers,route,uri,scope):
            cookie,_=await account(coord,"Fog owner")
            status,data=await http_json(uri,"/api/games/claim",{"room_code":room.room_code,
                "reconnect_token":peers[0].token,"connection_nonce":peers[0].nonce},cookie=cookie)
            assert status==200 and data["claimed"]
            owner=await connect(uri,cookie=cookie)
            try:
                other_cookie,_=await account(coord,"Other account")
                stranger=await connect(uri,cookie=other_cookie)
                try:
                    await stranger.send({"type":"account_continue","room_code":room.room_code})
                    await stranger.wait(lambda:bool(stranger.errors))
                    assert stranger.errors[-1]["code"]=="seat_not_owned"
                    assert not any(m["type"]=="match_state" for m in stranger.frames)
                finally: await stranger.close()
                await owner.send({"type":"account_continue","room_code":room.room_code})
                await owner.wait(lambda:owner.state is not None)
                await peers[0].wait(lambda:peers[0].closed)
                private_views([owner,peers[1]])
                connection=next(c for c in server.manager.connections.values() if c.pid==0 and c.room_code==room.room_code)
                original_send=connection.ws.send_text
                entered,release=asyncio.Event(),asyncio.Event()
                async def paused(raw):
                    if json.loads(raw)["type"]=="match_state":
                        entered.set()
                        await release.wait()
                    await original_send(raw)
                monkeypatch.setattr(connection.ws,"send_text",paused)
                async def publish():
                    async with room.lock: await server._send_match_state(room)
                publishing=asyncio.create_task(publish())
                await asyncio.wait_for(entered.wait(),2)
                logout=asyncio.create_task(http_json(uri,"/api/auth/logout",{},cookie=cookie))
                try:
                    await asyncio.sleep(.05)
                    assert not logout.done(), "Logout must order after the authorized frame's session share lock"
                finally: release.set()
                await publishing
                assert (await logout)[0]==200
                before=len(owner.frames)
                async with room.lock: await server._send_match_state(room)
                await owner.wait(lambda:owner.closed)
                assert not any(m["type"]=="match_state" for m in owner.frames[before:])
            finally: await owner.close()
    asyncio.run(run())


def test_live_history_metadata_and_generic_broadcast_cannot_publish_trusted_fields(database_url,monkeypatch):
    async def run():
        async with live_fixture(database_url,monkeypatch) as (coord,room,peers,route,uri,scope):
            candidate=clone_room(room)
            hidden=candidate.game.scenario.rules.fog.initially_hidden[0]
            secret={"FUTURE_SECRET":[vars(t) for t in candidate.game.tiles]}
            candidate.selected_map_meta.update(name=secret,private_pool=secret)
            game_events.record(candidate,"future_discovery",0,tile=hidden,private_pool=secret)
            game_events.record(candidate,"discover_tile",0,tile=hidden,terrain=candidate.game.tiles[hidden].terrain,
                               number=candidate.game.tiles[hidden].number,reward={"kind":"none","quantity":0})
            game_events.record(candidate,"production",0,player_pid=0,quantity=0,private={0:{
                "resources":{"wood":0,"FUTURE_SECRET":9},"future_choices":secret}},secret=secret)
            await server._commit(room,candidate,snapshot=True,trusted_fog=True)
            starts=[len(p.frames) for p in peers]
            async with room.lock:
                await server._send_room_state(room)
                await server._send_match_state(room)
                with pytest.raises(ValueError):
                    await server._broadcast(room,{"type":"match_state","state":secret})
            await asyncio.sleep(.03)
            for p,start in zip(peers,starts):
                raw=json.dumps(p.frames[start:])
                assert "FUTURE_SECRET" not in raw and "private_pool" not in raw and "future_discovery" not in raw
                assert p.state["state"]["game_events"][-1]["type"]=="production"
                assert not any(e["type"]=="discover_tile" for e in p.state["state"]["game_events"])
            status,inspected=await http_json(uri,"/api/reconnect/inspect-many",{"credentials":[
                {"room_code":room.room_code,"reconnect_token":peers[0].token}]})
            assert status==200 and inspected["results"][0]["game"]["map_name"]=="Unknown map"
            assert "FUTURE_SECRET" not in json.dumps(inspected)
    asyncio.run(run())


def test_game_over_still_masks_future_and_public_rematch_stays_closed(database_url,monkeypatch):
    async def run():
        async with live_fixture(database_url,monkeypatch) as (coord,room,peers,route,uri,scope):
            await peers[0].execute(route)
            await peers[0].execute({"type":"choose_gold","res":"ore","qty":room.game.pending_gold[0]})
            # Explicit terminal privacy fixture, NOT a naturally played Fog win.
            candidate=clone_room(room)
            candidate.game.players[0].vp=candidate.game.rules_config.target_vp
            candidate.game.game_over,candidate.game.winner_pid=True,0
            candidate.tick+=1
            await server._commit(room,candidate,snapshot=True,trusted_fog=True)
            async with room.lock: await server._send_match_state(room)
            for p in peers: await p.wait(lambda:p.state["state"]["game_over"])
            private_views(peers)
            assert any(t["visibility"]=="hidden" for t in peers[0].state["state"]["tiles"])
            assert peers[1].state["state"]["players"][0]["vp"]==room.game.players[0].vp
            saved=await coord.repository.load(room.id)
            count=len(peers[0].errors)
            await peers[0].send({"type":"rematch"})
            await peers[0].wait(lambda:len(peers[0].errors)>count)
            assert peers[0].errors[-1]["code"]=="feature_disabled"
            after=await coord.repository.load(room.id)
            assert after["match"]==saved["match"] and after["head"]==saved["head"]
    asyncio.run(run())
