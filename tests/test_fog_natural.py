"""Whole legal Fog match through the authoritative TCP/PostgreSQL transport."""
import asyncio
import json
import os
from pathlib import Path

from tests.fog_natural_support import FogBackend, play_fog
from tests.test_natural_full_matches import natural_database_url


def test_isolated_lifecycle_admission_retains_host_epoch_active_match_and_public_gates(natural_database_url, tmp_path):
    from uuid import uuid4
    from tests.fog_natural_support import FogMatch
    from tests.fog_live_support import connect
    backend = FogBackend(natural_database_url, tmp_path / "private-bindings.json")
    async def run():
        match = FogMatch(backend)
        stranger = None
        try:
            await match.create()
            before, _ = await match.committed_game()
            for pid, epoch, expected in ((1, 1, "forbidden"), (0, 0, "invalid"), (0, 1, "invalid")):
                peer = match.peers[pid]
                errors = len(peer.errors)
                await peer.send({"type":"rematch","request_id":uuid4().hex,"expected_match_id":epoch})
                await peer.wait(lambda:len(peer.errors)>errors)
                assert peer.errors[-1]["code"] == expected
                after, _ = await match.committed_game()
                assert after == before
            stranger = await connect(f"ws://127.0.0.1:{backend.port}/ws",origin=f"http://127.0.0.1:{backend.port}")
            await stranger.send({"type":"create_room","name":"Ordinary stranger","max_players":2})
            await stranger.wait(lambda:stranger.room is not None and stranger.token is not None)
            from tests.fog_natural_support import recipe
            await stranger.send({"type":"set_map","map_data":recipe(),"trusted_fog":True})
            await stranger.wait(lambda:bool(stranger.errors))
            assert stranger.errors[-1]["code"] == "feature_disabled"
            assert stranger.room["map_id"] == "base_standard" and stranger.state is None
            await stranger.send({"type":"close_room","room_code":stranger.room["room_code"],
                                 "request_id":uuid4().hex,"expected_match_id":0})
            await stranger.wait(lambda:any(f["type"]=="room_closed" for f in stranger.frames))
        finally:
            if stranger: await stranger.close()
            await match.close()
    try:
        backend.start()
        asyncio.run(run())
    finally: backend.close()


def test_natural_fog_match_to_victory_recovery_and_fresh_rematch(natural_database_url, tmp_path):
    backend = FogBackend(natural_database_url, tmp_path / "private-bindings.json")
    try:
        backend.start()
        result = asyncio.run(play_fog(backend))
    finally:
        backend.close()
    output = Path(os.environ.get("CATAN_FULL_MATCH_OUTPUT", str(tmp_path))) / "seafarers_fog_natural.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    assert result["result"]["status"] == "finished"
    assert result["result"]["snapshot_version"] == 4 and result["result"]["engine_compatibility"] == 3
    assert result["conservation_checkpoints"] == result["player_actions"] + 2  # Initial + every command + fresh rematch.
    assert max(result["result"]["final_vp"]) >= 12
    assert result["counters"]["upgrade_city"] and result["counters"]["place_settlement"] > 4
    assert result["paid_routes"][0]["place_road"] and result["paid_routes"][0]["build_ship"]
    assert result["discovery"]["terrain"].get("sea") and result["discovery"]["gold_awarded"]
    assert result["discovery"]["ordinary_awarded"] and result["discovery"]["island_bonus"] == 0
    assert result["discovery"]["revealed"] >= 4
    assert any(k.startswith("place_road/") for k in result["discovery"]["triggers"])
    assert any(k.startswith("build_ship/") for k in result["discovery"]["triggers"])
    assert result["counters"].get("move_robber", 0) + result["counters"].get("move_pirate", 0) > 0
    assert {"restart_during_pending_gold", "restart_after_paid_ship", "controlling_socket_takeover", "client_transport_lost_ack_reconnect_retry",
            "discovery_route_lost_ack", "gold_choice_lost_ack",
            "fresh_fog_assignment_no_rewards_or_history", "atomic_rejected_command"} <= {e["kind"] for e in result["recovery"]}
    print(json.dumps({key: result[key] for key in ("actual_turns", "player_actions", "counters", "discovery", "result")}))
