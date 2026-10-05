"""Test-only initializer. Never loaded by the production Docker command.

All browser commands still use the real protocol, ownership, executor and snapshots.
Only the first match in a room receives a prepared state; rematch is unmodified.
"""
from copy import deepcopy
from app import server_mp as server
from app.engine import rules
from app.engine.legal import board_legal_moves

original_start = server._start_match
original_apply = server._apply_cmd


def initialize(room):
    original_start(room)
    if room.match_id != 1 or not room.players[0].name.startswith("fixture-"):
        return
    mode = room.players[0].name.split()[0].removeprefix("fixture-")
    g = room.game
    port_vertices = {v for edge, _ in g.ports for v in edge}
    desired = "3:1" if mode == "bank3" else "wood" if mode == "bank2" else None
    while g.phase == "setup":
        pid = g.turn
        legal = board_legal_moves(g, pid)
        if g.setup_need == "settlement":
            choices = legal["settlements"]
            if pid == 0:
                first = not any(owner == pid for owner, _ in g.occupied_v.values())
                preferred = [v for edge, kind in g.ports for v in edge if v in choices and desired and desired in kind]
                inland = [v for v in choices if v not in port_vertices]
                choices = preferred if first and desired and preferred else inland or choices
            rules.apply_cmd(g, pid, {"type": "place_settlement", "vid": choices[0], "setup": True})
        else:
            rules.apply_cmd(g, pid, {"type": "place_road", "eid": legal["roads"][0], "setup": True})
    # Controlled funded hands, with the normal total of 19 per resource preserved.
    for p in g.players:
        p.res = {r: 5 for r in rules.RESOURCES}
    g.bank = {r: 19 - sum(p.res[r] for p in g.players) for r in rules.RESOURCES}
    g.rolled = mode not in ("knight", "road")
    g.players[0].dev_cards = [{"type": c, "new": False} for c in
                              ("knight", "road_building", "year_of_plenty", "monopoly", "victory_point")]
    g.players[0].vp += 1
    g.players[1].dev_cards = [{"type": "victory_point", "new": False}, {"type": "knight", "new": False}]
    g.players[1].vp += 1
    for p in g.players:
        for card in p.dev_cards:
            g.dev_deck.remove(card["type"])
    if mode == "buy":
        for card in g.players[0].dev_cards:
            g.dev_deck.append(card["type"])
        g.players[0].dev_cards = []
        g.players[0].vp -= 1
        g.dev_deck.remove("knight")
        g.dev_deck.append("knight")
    if mode == "plenty":
        excess = g.bank["wood"] - 1
        g.bank["wood"] = 1
        g.players[1].res["wood"] += excess
    if mode == "results":
        g.players[0].vp = 9
        g.players[1].vp = 7
        g.dev_deck.remove("victory_point")
        g.dev_deck.append("victory_point")
    if mode.startswith("bank"):
        expected = {"bank4": 4, "bank3": 3, "bank2": 2}[mode]
        assert rules.best_trade_rate(g, 0, "wood") == expected


def verify_rejection(room, pid, cmd):
    before = deepcopy(room.game)
    error = original_apply(room, pid, cmd)
    if error:
        assert room.game == before, "Rejected command mutated GameState"
    return error


server._start_match = initialize
server._apply_cmd = verify_rejection
server._roll_dice = lambda: 2  # Deterministic test progression only; production uses secrets.
app = server.app
