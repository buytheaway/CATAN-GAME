"""Actual TCP WebSocket + PostgreSQL matches with no grants or live-state edits."""
import asyncio
import json
import os
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from tests.full_match_support import Backend, play_natural


@pytest.fixture
def natural_database_url():
    value = os.environ.get("CATAN_TEST_DATABASE_URL")
    if not value:
        pytest.skip("CATAN_TEST_DATABASE_URL required for natural durable full matches")
    parsed = make_url(value)
    assert parsed.drivername == "postgresql+psycopg" and parsed.database.endswith("_test")
    return value


@pytest.mark.parametrize("map_id,players,target", [
    ("base_standard", 2, 10),
    ("seafarers_official_new_shores_3", 3, 14),
])
def test_natural_full_match_to_durable_victory(natural_database_url, tmp_path, map_id, players, target):
    backend = Backend(natural_database_url)
    try:
        backend.start()
        evidence = asyncio.run(play_natural(backend, players, map_id))
    finally:
        backend.close()
    destination = Path(os.environ.get("CATAN_FULL_MATCH_OUTPUT", str(tmp_path))) / (map_id + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    assert evidence["result"]["status"] == "finished"
    winner = evidence["result"]["winner_pid"]
    assert evidence["result"]["final_vp"][winner] >= target
    assert evidence["counters"]["trade_bank"] > 0
    assert evidence["counters"]["trade_offer_accept"] > 0
    assert evidence["counters"]["buy_dev"] > 0 and evidence["counters"]["play_dev"] > 0
    assert evidence["counters"]["move_robber"] > 0
    # Passive VP cards can legitimately finish the official match before a
    # fourth city; the transcript still requires paid upgrades and island VP.
    assert evidence["counters"]["upgrade_city"] >= (4 if players == 2 else 2)
    assert evidence["result"]["resource_conservation"] and evidence["result"]["development_card_conservation"]
    assert evidence["conservation_checkpoints"] == evidence["player_actions"] + 1
    if players == 2:
        assert evidence["result"]["longest_road_owner"] == winner
    assert any(event["kind"] == "client_transport_lost_ack_reconnect_retry" for event in evidence["recovery"])
    assert any(event["kind"] == "fresh_rematch_preserves_finished_result" for event in evidence["recovery"])
    if players == 3:
        assert evidence["counters"]["build_ship"] > 6
        assert evidence["counters"]["move_pirate"] > 0
        assert len(evidence["result"]["awarded_islands"][str(winner)]) == 2
    assert any(event["kind"] == "backend_restart" and event["game_over"] for event in evidence["recovery"])
    print(json.dumps({key: evidence[key] for key in ("map_id", "actual_turns", "player_actions", "counters", "result")}))


def test_natural_official_four_player_tcp_smoke(natural_database_url):
    backend = Backend(natural_database_url)
    try:
        backend.start()
        evidence = asyncio.run(play_natural(backend, 4, "seafarers_official_new_shores_4", smoke_turns=12))
    finally:
        backend.close()
    assert evidence["actual_turns"] == 12
    assert evidence["counters"]["place_settlement"] == 8
    assert evidence["counters"]["build_ship"] >= 8
    assert evidence["result"]["status"] == "smoke"
