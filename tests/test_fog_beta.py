"""Production Fog beta: public TCP/HTTP admission and durable lifecycle gates."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from app.fog_beta import BETA_MAP_ID, BETA_RULESET, beta_recipe
from tests.fog_beta_support import (BetaBackend, BetaMatch, lobby, select_beta, start,
                                    rejection, close_lobby, durable_state)
from tests.fog_live_support import connect, http_json
from tests.fog_natural_support import play_fog
from tests.test_fog_live import private_views
from tests.test_fog_live_privacy import normalize
from tests.test_natural_full_matches import natural_database_url
from tests.test_auth import auth_config
from tests.test_persistence_postgres import runtime


@pytest.mark.parametrize("attempt", ["id", "upload", "forged_flags", "unknown_id"])
def test_default_disabled_cannot_admit_fog_by_public_input(natural_database_url, attempt):
    backend = BetaBackend(natural_database_url, admission=False)
    async def run():
        peers = await lobby(backend)
        try:
            host = peers[0]
            before = await durable_state(backend.database_url, host.room["room_code"])
            assert BETA_MAP_ID not in {p["id"] for p in host.room["map_presets"]}
            payload = {"type": "set_map", "map_id": BETA_MAP_ID}
            if attempt == "upload": payload["map_data"] = beta_recipe()
            if attempt == "unknown_id": payload["map_id"] = "seafarers_fog_beta_3"
            if attempt == "forged_flags":
                payload.update(trusted_fog=True, enable_fog=True, fog_beta=True,
                               fog_access={"room_id": str(uuid4()), "match_uuid": str(uuid4())})
            await rejection(host, payload)
            assert await durable_state(backend.database_url, host.room["room_code"]) == before
            assert all(p.state is None for p in peers)
            # A refused selection does not poison the ordinary Base lifecycle.
            await host.send({"type": "start_match", "request_id": uuid4().hex, "expected_match_id": 0})
            await asyncio.gather(*(p.wait(lambda p=p: p.state is not None) for p in peers))
            assert host.state["state"]["map_id"] == "base_standard"
            for pid, peer in enumerate(peers):
                for other, player in enumerate(peer.state["state"]["players"]):
                    assert ("res" in player) is (other == pid)
                    assert ("dev_cards" in player) is (other == pid)
        finally: await close_lobby(peers)
    try:
        backend.start()
        asyncio.run(run())
    finally: backend.close()


@pytest.mark.parametrize("count", [3, 4])
def test_enabled_beta_rejects_unsupported_player_counts_atomically(natural_database_url, count):
    backend = BetaBackend(natural_database_url)
    async def run():
        peers = await lobby(backend, count=count)
        try:
            await select_beta(peers)
            code = peers[0].room["room_code"]
            before = await durable_state(backend.database_url, code)
            await rejection(peers[0], {"type": "start_match", "request_id": uuid4().hex,
                                       "expected_match_id": 0}, "invalid")
            assert await durable_state(backend.database_url, code) == before
            assert all(p.state is None for p in peers)
        finally: await close_lobby(peers)
    try:
        backend.start()
        asyncio.run(run())
    finally: backend.close()


@pytest.mark.parametrize("mutation", ["canonical_upload", "terrain", "target", "pool", "disguised_id"])
def test_enabled_beta_rejects_noncanonical_or_uploaded_recipes(natural_database_url, mutation):
    backend = BetaBackend(natural_database_url)
    async def run():
        peers = await lobby(backend)
        try:
            data = beta_recipe()
            if mutation == "terrain": data["tiles"][0]["terrain"] = "gold"
            if mutation == "target": data["rules"]["target_vp"] = 3
            if mutation == "pool": data["fog_pool"]["terrain"][0] = "gold"
            before = await durable_state(backend.database_url, peers[0].room["room_code"])
            await rejection(peers[0], {"type": "set_map", "map_id": "base_standard" if mutation == "disguised_id" else BETA_MAP_ID,
                                       "map_data": data})
            assert await durable_state(backend.database_url, peers[0].room["room_code"]) == before
        finally: await close_lobby(peers)
    try:
        backend.start()
        asyncio.run(run())
    finally: backend.close()


@pytest.mark.parametrize("settings", [{"turn_timer": 30}, {"target_vp": 3}, {"discard_threshold": 8}])
def test_beta_cannot_enable_unsupported_timer_or_rule_overrides(natural_database_url, settings):
    backend = BetaBackend(natural_database_url)
    async def run():
        peers = await lobby(backend)
        try:
            await select_beta(peers)
            before = await durable_state(backend.database_url, peers[0].room["room_code"])
            await rejection(peers[0], {"type": "set_settings", "settings": settings}, "invalid")
            assert await durable_state(backend.database_url, peers[0].room["room_code"]) == before
        finally: await close_lobby(peers)
    try:
        backend.start()
        asyncio.run(run())
    finally: backend.close()


def test_public_beta_host_authority_takeover_start_receipt_and_reconnect(natural_database_url):
    backend = BetaBackend(natural_database_url)
    async def run():
        peers = await lobby(backend)
        extra = None
        try:
            await rejection(peers[1], {"type": "set_map", "map_id": BETA_MAP_ID}, "forbidden")
            await select_beta(peers)
            before = await durable_state(backend.database_url, peers[0].room["room_code"])
            await rejection(peers[1], {"type": "start_match", "request_id": uuid4().hex,
                                       "expected_match_id": 0}, "forbidden")
            assert await durable_state(backend.database_url, peers[0].room["room_code"]) == before
            extra = await connect(f"ws://127.0.0.1:{backend.port}/ws", origin=f"http://127.0.0.1:{backend.port}")
            await extra.send({"type": "reconnect", "room_code": peers[0].room["room_code"],
                              "reconnect_token": peers[0].token})
            await extra.wait(lambda: extra.room is not None and extra.token is not None)
            await rejection(peers[0], {"type": "start_match", "request_id": uuid4().hex,
                                       "expected_match_id": 0}, "not_found")
            request = {"type": "start_match", "request_id": uuid4().hex, "expected_match_id": 0}
            await extra.send(request)
            await extra.wait(lambda: extra.state is not None)
            await peers[1].wait(lambda: peers[1].state is not None)
            assert peers[0].state is None  # Old controller never receives the hand.
            private_views([extra, peers[1]])
            assert extra.room["ruleset_compatibility"]["ruleset_id"] == BETA_RULESET
            before = await durable_state(backend.database_url, extra.room["room_code"])
            await extra.send(request)
            await extra.wait(lambda: extra.room.get("request_id") == request["request_id"])
            assert await durable_state(backend.database_url, extra.room["room_code"]) == before
        finally:
            if extra:
                await peers[0].close()
                peers[0] = extra
            await close_lobby(peers)
    try:
        backend.start()
        asyncio.run(run())
    finally: backend.close()


def test_existing_beta_survives_admission_off_emergency_pause_and_resume(natural_database_url):
    backend = BetaBackend(natural_database_url)
    async def run():
        peers = await lobby(backend)
        code = peers[0].room["room_code"]
        proofs = [p.token for p in peers]
        async def reconnect_all():
            resumed = []
            for proof in proofs:
                peer = await connect(f"ws://127.0.0.1:{backend.port}/ws", origin=f"http://127.0.0.1:{backend.port}")
                resumed.append(peer)
                await peer.send({"type": "reconnect", "room_code": code, "reconnect_token": proof})
                await peer.wait(lambda: peer.room is not None and peer.token is not None)
            return resumed
        try:
            await start(peers)
            saved = [deepcopy(p.state) for p in peers]
            await asyncio.gather(*(p.close() for p in peers))
            backend.stop()
            backend.admission = False
            backend.start()
            peers = await reconnect_all()
            await asyncio.gather(*(p.wait(lambda p=p: p.state is not None) for p in peers))
            assert [p.state for p in peers] == saved
            assert BETA_MAP_ID not in {p["id"] for p in peers[0].room["map_presets"]}
            vertex = peers[0].state["state"]["legal"]["settlements"][0]
            await peers[0].execute({"type": "place_settlement", "vid": vertex})
            await peers[1].wait(lambda: peers[1].state["tick"] == 1)
            saved = [deepcopy(p.state) for p in peers]
            before = (await durable_state(backend.database_url, code))[2]
            await asyncio.gather(*(p.close() for p in peers))
            backend.stop()
            backend.stopped = True
            backend.start()
            peers = await reconnect_all()
            assert all(p.state is None for p in peers)
            assert peers[0].room["ruleset_compatibility"]["reason"] == "fog_beta_paused"
            assert (await durable_state(backend.database_url, code))[2] == before
            await rejection(peers[0], {"type": "cmd", "cmd_id": uuid4().hex, "seq": 2,
                                       "match_id": saved[0]["match_id"], "cmd": {"type": "noop"}}, "compatibility_required")
            assert (await durable_state(backend.database_url, code))[2] == before
            assert not any(f["type"] == "match_state" for p in peers for f in p.frames)
            await asyncio.gather(*(p.close() for p in peers))
            backend.stop()
            backend.stopped = False
            backend.start()
            peers = await reconnect_all()
            await asyncio.gather(*(p.wait(lambda p=p: p.state is not None) for p in peers))
            assert [p.state for p in peers] == saved
            private_views(peers)
        finally: await close_lobby(peers)
    try:
        backend.start()
        asyncio.run(run())
    finally: backend.close()


@pytest.mark.parametrize("emergency", [False, True])
def test_selected_lobby_cannot_start_after_admission_is_disabled(natural_database_url, emergency):
    backend = BetaBackend(natural_database_url)
    async def run():
        peers = await lobby(backend)
        proofs = [p.token for p in peers]
        code = peers[0].room["room_code"]
        try:
            await select_beta(peers)
            await asyncio.gather(*(p.close() for p in peers))
            backend.stop()
            backend.admission, backend.stopped = False, emergency
            backend.start()
            peers = []
            for proof in proofs:
                peer = await connect(f"ws://127.0.0.1:{backend.port}/ws", origin=f"http://127.0.0.1:{backend.port}")
                peers.append(peer)
                await peer.send({"type": "reconnect", "room_code": code, "reconnect_token": proof})
                await peer.wait(lambda: peer.room is not None and peer.token is not None)
            before = await durable_state(backend.database_url, code)
            await rejection(peers[0], {"type": "start_match", "request_id": uuid4().hex,
                                       "expected_match_id": 0}, "feature_disabled")
            assert await durable_state(backend.database_url, code) == before
            assert all(p.state is None for p in peers)
            revision = peers[0].room["map_revision"]
            await peers[0].send({"type": "set_map", "map_id": "base_standard"})
            await peers[0].wait(lambda: peers[0].room["map_revision"] > revision)
            await peers[0].send({"type": "start_match", "request_id": uuid4().hex, "expected_match_id": 0})
            await asyncio.gather(*(p.wait(lambda p=p: p.state is not None) for p in peers))
            assert peers[0].state["state"]["map_id"] == "base_standard"
        finally: await close_lobby(peers)
    try:
        backend.start()
        asyncio.run(run())
    finally: backend.close()


def test_public_beta_hidden_assignments_do_not_change_wire_or_http_views(natural_database_url):
    backends = [BetaBackend(natural_database_url, assignment_seed=seed) for seed in (501, 502)]
    async def run():
        pairs = []
        try:
            for backend in backends:
                peers = await lobby(backend)
                pairs.append(peers)
                await start(peers)
                private_views(peers)
            # Only private assignment RNG differs; every legal public byte is
            # compared after removing room codes and publication timestamps.
            for pid in (0, 1):
                assert normalize(pairs[0][pid].state) == normalize(pairs[1][pid].state)
                assert normalize(pairs[0][pid].room) == normalize(pairs[1][pid].room)
            payloads = [(await durable_state(b.database_url, p[0].room["room_code"]))[2]
                        for b, p in zip(backends, pairs)]
            assert payloads[0]["engine"] != payloads[1]["engine"]
            inspections = []
            for backend, peers in zip(backends, pairs):
                uri = f"ws://127.0.0.1:{backend.port}/ws"
                status, data = await http_json(uri, "/api/reconnect/inspect-many", {"credentials": [
                    {"room_code": peers[0].room["room_code"], "reconnect_token": peers[0].token}]},
                    origin=f"http://127.0.0.1:{backend.port}")
                assert status == 200
                inspections.append(normalize(data))
            assert inspections[0] == inspections[1]
            assert not any(word in json.dumps(inspections) for word in ("fog_pool", "assignment_digest", "initially_hidden"))
            errors = []
            for peers in pairs:
                await peers[0].execute({"type": "place_road", "eid": [-999, 999]}, applied=False)
                errors.append(normalize([{k: v for k, v in f.items() if k != "cmd_id"} for f in peers[0].frames
                                         if f["type"] in ("error", "cmd_ack")]))
            assert errors[0] == errors[1]
        finally:
            for peers in pairs: await close_lobby(peers)
    try:
        for backend in backends: backend.start()
        asyncio.run(run())
    finally:
        for backend in backends: backend.close()


def test_public_beta_natural_victory_recovery_and_toggle_rematch(natural_database_url, tmp_path):
    backend = BetaBackend(natural_database_url)
    try:
        backend.start()
        result = asyncio.run(play_fog(backend, match_factory=lambda b: BetaMatch(b, verify_toggles=True)))
    finally: backend.close()
    destination = Path(os.environ.get("CATAN_FULL_MATCH_OUTPUT", str(tmp_path))) / (BETA_MAP_ID + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2), encoding="utf-8")
    assert result["result"]["ruleset_id"] == BETA_RULESET
    assert result["result"]["status"] == "finished"
    assert result["result"]["final_vp"] == [13, 3]
    assert result["conservation_checkpoints"] == result["player_actions"] + 2
    assert result["discovery"]["revealed"] == 8 and result["discovery"]["gold_awarded"] == 1
    assert result["paid_routes"][0]["place_road"] and result["paid_routes"][0]["build_ship"]
    assert {"restart_during_pending_gold", "gold_choice_lost_ack", "discovery_route_lost_ack",
            "restart_after_paid_ship", "controlling_socket_takeover",
            "admission_off_during_pending_gold",
            "admission_off_preserves_finished_match_rejects_rematch",
            "fresh_fog_assignment_no_rewards_or_history"} <= {e["kind"] for e in result["recovery"]}
    print(json.dumps({k: result[k] for k in ("actual_turns", "player_actions", "discovery", "result")}))


@pytest.mark.parametrize("credential", ["expired", "revoked"])
def test_beta_open_guest_socket_loses_private_publication_with_credential(natural_database_url, monkeypatch, credential):
    from datetime import timedelta
    from app import server_mp as server
    from app.persistence.credentials import utcnow
    from app.persistence.recovery import clone_room
    from tests.fog_live_support import tcp_server
    monkeypatch.setenv("CATAN_FOG_BETA_ADMISSION", "1")
    monkeypatch.setenv("CATAN_FOG_BETA_EMERGENCY_STOP", "0")
    async def run():
        async with runtime(natural_database_url, monkeypatch):
            async with tcp_server() as uri:
                backend = type("Endpoint", (), {"port": int(uri.split(":")[-1].split("/")[0])})()
                # This server's auth fixture allows http://test, matching the
                # actual request origin used by the normal TCP helpers below.
                monkeypatch.setenv("CATAN_AUTH_ORIGINS", f"http://127.0.0.1:{backend.port}")
                peers = await lobby(backend)
                try:
                    await start(peers)
                    room = server.manager.rooms[peers[0].room["room_code"]]
                    before = len(peers[0].frames)
                    candidate = clone_room(room)
                    if credential == "expired": candidate.players[0].token_expires_at = utcnow() - timedelta(seconds=1)
                    else: candidate.players[0].token_revoked_at = utcnow()
                    async with room.lock:
                        await server._commit(room, candidate)
                        await server._send_match_state(room)
                    await peers[0].wait(lambda: peers[0].closed)
                    assert not any(f["type"] == "match_state" for f in peers[0].frames[before:])
                    assert peers[1].state["tick"] == 0 and room.tick == 0
                finally: await close_lobby(peers)
    asyncio.run(run())


def test_beta_account_claim_continue_wrong_account_and_logout_privacy(natural_database_url, monkeypatch):
    from app import server_mp as server
    from tests.test_auth import account
    from tests.fog_live_support import tcp_server
    monkeypatch.setenv("CATAN_FOG_BETA_ADMISSION", "1")
    monkeypatch.setenv("CATAN_FOG_BETA_EMERGENCY_STOP", "0")
    async def run():
        async with runtime(natural_database_url, monkeypatch) as coord:
            owner_cookie, _ = await account(coord, "Beta owner")
            other_cookie, _ = await account(coord, "Another account")
            async with tcp_server() as uri:
                port = int(uri.split(":")[-1].split("/")[0])
                backend = type("Endpoint", (), {"port": port})()
                origin = f"http://127.0.0.1:{port}"
                monkeypatch.setenv("CATAN_AUTH_ORIGINS", origin)
                peers = await lobby(backend)
                owner = wrong = None
                try:
                    await start(peers)
                    code = peers[0].room["room_code"]
                    status, body = await http_json(uri, "/api/games/claim", {"room_code": code,
                        "reconnect_token": peers[0].token, "connection_nonce": peers[0].nonce},
                        cookie=owner_cookie, origin=origin)
                    assert status == 200 and body["claimed"]
                    status, active = await http_json(uri, "/api/games/active", cookie=owner_cookie, origin=origin)
                    assert status == 200
                    summary = next(g for g in active["games"] if g["room_code"] == code)
                    assert summary["ruleset_compatibility"]["status"] == "compatible"
                    assert not any(k in json.dumps(summary) for k in ("fog_pool", "assignment_digest", '"res"', "dev_cards"))
                    wrong = await connect(uri, cookie=other_cookie, origin=origin)
                    await rejection(wrong, {"type": "account_continue", "room_code": code}, "seat_not_owned")
                    assert wrong.state is None
                    owner = await connect(uri, cookie=owner_cookie, origin=origin)
                    await owner.send({"type": "account_continue", "room_code": code})
                    await owner.wait(lambda: owner.state is not None)
                    private_views([owner, peers[1]])
                    await peers[0].wait(lambda: peers[0].closed)
                    before = len(owner.frames)
                    status, _ = await http_json(uri, "/api/auth/logout", {}, cookie=owner_cookie, origin=origin)
                    assert status == 200
                    await owner.wait(lambda: owner.closed)
                    room = server.manager.rooms[code]
                    async with room.lock: await server._send_match_state(room)
                    assert not any(f["type"] == "match_state" for f in owner.frames[before:])
                finally:
                    if owner: await owner.close()
                    if wrong: await wrong.close()
                    await close_lobby(peers)
    asyncio.run(run())


@pytest.mark.parametrize("fault", ["before_write", "before_commit", "after_commit"])
def test_beta_commit_gate_and_receipt_recovery_after_write_failure(natural_database_url, monkeypatch, fault):
    from app import server_mp as server
    from tests.fog_live_support import tcp_server
    monkeypatch.setenv("CATAN_FOG_BETA_ADMISSION", "1")
    monkeypatch.setenv("CATAN_FOG_BETA_EMERGENCY_STOP", "0")
    async def run():
        async with runtime(natural_database_url, monkeypatch) as coord:
            async with tcp_server() as uri:
                port = int(uri.split(":")[-1].split("/")[0])
                monkeypatch.setenv("CATAN_AUTH_ORIGINS", f"http://127.0.0.1:{port}")
                peers = await lobby(type("Endpoint", (), {"port": port})())
                try:
                    await start(peers)
                    room = server.manager.rooms[peers[0].room["room_code"]]
                    before = await coord.repository.load(room.id)
                    request = peers[0].command({"type": "place_settlement", "vid": peers[0].state["state"]["legal"]["settlements"][0]})
                    frames = [len(p.frames) for p in peers]
                    def inject(point):
                        if point == fault:
                            assert not any(f["type"] in ("cmd_ack", "match_state") for p, n in zip(peers, frames) for f in p.frames[n:])
                            raise OSError("Synthetic beta transaction failure")
                    coord.repository._test_fault = inject
                    await peers[0].send(request)
                    await peers[0].wait(lambda: bool(peers[0].acks) if fault == "after_commit" else bool(peers[0].errors))
                    after = await coord.repository.load(room.id)
                    if fault == "after_commit":
                        assert peers[0].acks[request["cmd_id"]]["applied"]
                        assert len(after["receipts"]) == 1 and room.tick == 1
                    else:
                        assert not peers[0].acks and room.tick == 0 and not coord.ready
                        assert after["head"] == before["head"] and not after["receipts"]
                        assert not any(f["type"] in ("cmd_ack", "match_state") for p, n in zip(peers, frames) for f in p.frames[n:])
                    coord.repository._test_fault = None
                    code, proofs = room.room_code, [p.token for p in peers]
                finally: await close_lobby(peers)
        # Fresh real production startup restores persisted materialized state;
        # retry consumes the original receipt or applies the uncommitted draw.
        backend = BetaBackend(natural_database_url, admission=False)
        resumed = []
        try:
            backend.start()
            for proof in proofs:
                peer = await connect(f"ws://127.0.0.1:{backend.port}/ws", origin=f"http://127.0.0.1:{backend.port}")
                resumed.append(peer)
                await peer.send({"type": "reconnect", "room_code": code, "reconnect_token": proof})
                await peer.wait(lambda: peer.state is not None)
            _, ack = await resumed[0].execute(request["cmd"], request=request, applied=fault != "after_commit")
            assert ack["duplicate"] is (fault == "after_commit")
            assert resumed[0].state["tick"] == 1
            assert len(resumed[0].state["state"]["occupied_v"]) == 1
        finally:
            await close_lobby(resumed)
            backend.close()
    asyncio.run(run())


def test_paused_native_beta_account_continue_is_metadata_only_then_resumes(natural_database_url, monkeypatch):
    from app import server_mp as server
    from tests.test_auth import account
    from tests.fog_live_support import tcp_server
    monkeypatch.setenv("CATAN_FOG_BETA_ADMISSION", "1")
    monkeypatch.setenv("CATAN_FOG_BETA_EMERGENCY_STOP", "0")
    async def run():
        async with runtime(natural_database_url, monkeypatch) as coord:
            cookie, identity = await account(coord, "Paused beta owner")
            async with tcp_server() as uri:
                port = int(uri.split(":")[-1].split("/")[0])
                origin = f"http://127.0.0.1:{port}"
                monkeypatch.setenv("CATAN_AUTH_ORIGINS", origin)
                peers = await lobby(type("Endpoint", (), {"port": port})())
                owner = resumed = None
                try:
                    await start(peers)
                    code = peers[0].room["room_code"]
                    status, body = await http_json(uri, "/api/games/claim", {"room_code": code,
                        "reconnect_token": peers[0].token, "connection_nonce": peers[0].nonce},
                        cookie=cookie, origin=origin)
                    assert status == 200 and body["claimed"]
                    room = server.manager.rooms[code]
                    assert room.players[0].user_id == identity["user_id"]
                    saved = deepcopy(peers[0].state)
                    before = await coord.repository.load(room.id)
                    await peers[0].close()
                    monkeypatch.setenv("CATAN_FOG_BETA_EMERGENCY_STOP", "1")
                    owner = await connect(uri, cookie=cookie, origin=origin)
                    await owner.send({"type": "account_continue", "room_code": code})
                    await owner.wait(lambda: owner.room is not None and any(f["type"] == "seat_identity" for f in owner.frames))
                    assert owner.room["ruleset_compatibility"]["reason"] == "fog_beta_paused"
                    assert owner.state is None
                    assert room.players[0].user_id == identity["user_id"]
                    assert any(f["type"] == "seat_identity" and f["ownership"] == "account" and f["pid"] == 0
                               for f in owner.frames)
                    async with room.lock: await server._send_match_state(room)
                    await rejection(owner, {"type": "cmd", "match_id": saved["match_id"], "seq": 1,
                                            "cmd_id": uuid4().hex, "cmd": {"type": "noop"}}, "compatibility_required")
                    assert not any(f["type"] in ("match_state", "cmd_ack", "reconnect_token") for f in owner.frames)
                    after = await coord.repository.load(room.id)
                    assert after["head"] == before["head"] and after["match"] == before["match"]
                    assert after["receipts"] == before["receipts"]
                    assert next(p for p in after["members"] if p["id"] == room.players[0].id)["user_id"] == identity["user_id"]
                    status, active = await http_json(uri, "/api/games/active", cookie=cookie, origin=origin)
                    assert status == 200
                    summary = next(g for g in active["games"] if g["room_code"] == code)
                    assert summary["ruleset_compatibility"]["reason"] == "fog_beta_paused"
                    assert not any(k in json.dumps(summary) for k in ("fog_pool", "assignment_digest", "dev_cards", '"res"'))
                    monkeypatch.setenv("CATAN_FOG_BETA_EMERGENCY_STOP", "0")
                    resumed = await connect(uri, cookie=cookie, origin=origin)
                    await resumed.send({"type": "account_continue", "room_code": code})
                    await resumed.wait(lambda: resumed.state is not None)
                    await owner.wait(lambda: owner.closed)
                    assert resumed.state == saved
                    private_views([resumed, peers[1]])
                    assert (await coord.repository.load(room.id))["head"] == before["head"]
                finally:
                    if owner: await owner.close()
                    if resumed: await resumed.close()
                    await close_lobby(peers)
    asyncio.run(run())


def test_native_beta_terminal_future_assignments_remain_counterfactually_private(natural_database_url, monkeypatch):
    """Prepared terminal PRIVACY fixture; never a natural gameplay victory claim."""
    import random
    from app import server_mp as server
    from app.persistence.recovery import clone_room
    from tests.test_auth import account
    from tests.fog_live_support import tcp_server
    monkeypatch.setenv("CATAN_FOG_BETA_ADMISSION", "1")
    monkeypatch.setenv("CATAN_FOG_BETA_EMERGENCY_STOP", "0")
    build = server.build_game
    seeds = iter((501, 502))
    def private_assignment(*args, **kwargs):
        return build(*args, **kwargs, fog_rng=random.Random(next(seeds)))
    monkeypatch.setattr(server, "build_game", private_assignment)
    async def run():
        async with runtime(natural_database_url, monkeypatch) as coord:
            cookie, _ = await account(coord, "Terminal beta owner")
            async with tcp_server() as uri:
                port = int(uri.split(":")[-1].split("/")[0])
                origin = f"http://127.0.0.1:{port}"
                monkeypatch.setenv("CATAN_AUTH_ORIGINS", origin)
                pairs, rooms = [], []
                try:
                    for _ in range(2):
                        peers = await lobby(type("Endpoint", (), {"port": port})())
                        pairs.append(peers)
                        await start(peers)  # Real public host admission and native marker.
                        room = server.manager.rooms[peers[0].room["room_code"]]
                        rooms.append(room)
                        assert room.ruleset_id == BETA_RULESET
                        assert not getattr(server.app.state, "_fog_fixture_access", ())
                        status, body = await http_json(uri, "/api/games/claim", {"room_code": room.room_code,
                            "reconnect_token": peers[0].token, "connection_nonce": peers[0].nonce},
                            cookie=cookie, origin=origin)
                        assert status == 200 and body["claimed"]
                        # Explicitly prepare only the terminal privacy boundary.
                        # No command, victory calculation, reward or historical
                        # recovery is claimed by this artificial state.
                        candidate = clone_room(room)
                        candidate.game.players[0].vp = candidate.game.rules_config.target_vp
                        candidate.game.game_over, candidate.game.winner_pid = True, 0
                        candidate.tick += 1
                        async with room.lock:
                            await server._commit(room, candidate, snapshot=True)
                            await server._send_room_state(room)
                            await server._send_match_state(room)
                        await asyncio.gather(*(p.wait(lambda p=p: p.state["state"]["game_over"]) for p in peers))
                    assert rooms[0].game.scenario.fog.assignment_digest != rooms[1].game.scenario.fog.assignment_digest
                    for peers, room in zip(pairs, rooms):
                        assert not room.game.scenario.fog.revealed
                        private_views(peers)
                        for peer in peers:
                            hidden = [t for t in peer.state["state"]["tiles"] if t["visibility"] == "hidden"]
                            assert len(hidden) == 8
                            assert all(t["terrain"] == "fog" and t["number"] is None for t in hidden)
                            assert peer.state["state"]["players"][0]["vp"] == 12
                    for pid in (0, 1):
                        assert normalize(pairs[0][pid].state) == normalize(pairs[1][pid].state)
                        assert normalize(pairs[0][pid].room) == normalize(pairs[1][pid].room)
                    inspected = []
                    for peers in pairs:
                        status, body = await http_json(uri, "/api/reconnect/inspect-many", {"credentials": [{
                            "room_code": peers[1].room["room_code"], "reconnect_token": peers[1].token}]}, origin=origin)
                        assert status == 200
                        inspected.append(normalize(body))
                    assert inspected[0] == inspected[1]
                    status, active = await http_json(uri, "/api/games/active", cookie=cookie, origin=origin)
                    assert status == 200
                    summaries = [next(g for g in active["games"] if g["room_code"] == r.room_code) for r in rooms]
                    assert all(g["status"] == "game_over" for g in summaries)
                    assert normalize(summaries[0]) == normalize(summaries[1])
                    outcomes = []
                    for peers, room in zip(pairs, rooms):
                        before = await coord.repository.load(room.id)
                        index = len(peers[0].frames)
                        await peers[0].execute({"type": "roll"}, applied=False)
                        frames = [f for f in peers[0].frames[index:] if f["type"] in ("error", "cmd_ack")]
                        assert any(f["type"] == "error" and f["code"] == "game_over" for f in frames)
                        outcomes.append(normalize([{k: v for k, v in f.items() if k != "cmd_id"} for f in frames]))
                        assert (await coord.repository.load(room.id))["head"] == before["head"]
                    assert outcomes[0] == outcomes[1]
                    assert not any(key in json.dumps([inspected, summaries, outcomes]) for key in (
                        "assignment_digest", "fog_pool", "initially_hidden", "continuation", "dev_cards", '"res"'))
                finally:
                    for peers in pairs: await close_lobby(peers)
    asyncio.run(run())
