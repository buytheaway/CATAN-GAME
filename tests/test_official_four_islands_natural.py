"""Grant-free authoritative Four Islands matches, using the existing TCP agents."""
import asyncio
import json
import os
from pathlib import Path

import pytest

from tests.full_match_support import Backend, play_natural
from tests.test_natural_full_matches import natural_database_url


@pytest.mark.parametrize("players",[3,4])
def test_natural_four_islands_to_durable_victory(natural_database_url,tmp_path,players):
    preset=f"seafarers_official_four_islands_{players}"
    backend=Backend(natural_database_url)
    try:
        backend.start()
        evidence=asyncio.run(play_natural(backend,players,preset))
    finally:
        backend.close()
    destination=Path(os.environ.get("CATAN_FULL_MATCH_OUTPUT",str(tmp_path)))/(preset+".json")
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    result=evidence["result"]
    winner=result["winner_pid"]
    assert result["status"]=="finished" and result["final_vp"][winner]>=13
    assert result["resource_conservation"] and result["development_card_conservation"]
    assert result["awarded_islands"][str(winner)]
    assert evidence["counters"]["build_ship"]>players*2 and evidence["counters"]["upgrade_city"]>0
    assert evidence["conservation_checkpoints"]==evidence["player_actions"]+1
    kinds={entry["kind"] for entry in evidence["recovery"]}
    assert {"backend_restart","client_transport_lost_ack_reconnect_retry","fresh_rematch_preserves_finished_result"}<=kinds
    assert any(entry["kind"]=="backend_restart" and entry["game_over"] for entry in evidence["recovery"])
    print(json.dumps({key:evidence[key] for key in ("map_id","actual_turns","player_actions","counters","result")}))
