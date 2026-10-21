"""Offline public NS4 opening, constructed by two real authoritative commands.

Not a new preset, saved match, debug endpoint or Fog recipe. All generated
players/hands are disposable synthetic data and only a closed view leaves here.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.engine import legal, rules, serialize


def legal_outer_ship():
    game = rules.build_game(17, 4, map_id="seafarers_official_new_shores_4")
    commands = [
        {"type": "place_settlement", "vid": 12, "setup": True},
        {"type": "build_ship", "eid": [12, 17], "setup": True},
    ]
    assert 12 in legal.board_legal_moves(game, 0)["settlements"]
    game, first = rules.apply_cmd(game, 0, commands[0])
    assert [12, 17] in legal.board_legal_moves(game, 0)["ships"]
    game, second = rules.apply_cmd(game, 0, commands[1])
    assert game.occupied_ships[(12, 17)] == 0
    assert len(game.edge_adj_hexes[(12, 17)]) == 1
    assert all(game.tiles[index].terrain == "sea" for index in game.edge_adj_hexes[(12, 17)])
    public = serialize.to_player_dict(game, 0)
    fields = (
        "size", "tiles", "vertices", "edges", "edge_adj_hexes", "ports",
        "robber_tile", "robbers", "pirate_tile", "rules_config", "occupied_v",
        "occupied_e", "occupied_ships", "phase", "setup_need", "turn", "players",
        "bank_available", "pending_action", "free_roads", "game_over",
        "scenario", "rolled", "setup_order", "setup_idx", "setup_anchor_vid",
        "winner_pid", "pending_pid", "pending_victims", "pending_gold",
        "discard_required", "discard_submitted", "dev_played_turn",
    )
    state = {key: public[key] for key in fields if key in public}
    state["you_pid"] = 0
    state["legal"] = legal.board_legal_moves(game, 0)
    state["map_id"] = "seafarers_official_new_shores_4"
    state["map_meta"] = {"name": "New Shores4 - actual legal opening, two engine commands"}
    return {"state": state, "provenance": {
        "map_id": state["map_id"], "seed": 17, "pid": 0, "commands": commands,
        "edge": [12, 17], "edge_adjacent_tiles": game.edge_adj_hexes[(12, 17)],
        "accepted_event_types": [event["type"] for event in first + second],
        "scope": "Offline synthetic public state after real legal setup commands; not a network match",
    }}


if __name__ == "__main__":
    print(json.dumps(legal_outer_ship(), separators=(",", ":")))
