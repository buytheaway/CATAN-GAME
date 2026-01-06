from __future__ import annotations

from typing import Dict, List, Tuple

from app.engine.state import (
    AchievementState,
    BoardState,
    GameState,
    PlayerState,
    RESOURCES,
    Tile,
)


def _edge_key(e: Tuple[int, int]) -> str:
    a, b = e
    return f"{a},{b}"


def to_dict(g: GameState) -> Dict:
    return {
        "state_version": g.state_version,
        "max_players": g.max_players,
        "size": g.size,
        "phase": g.phase,
        "turn": g.turn,
        "rolled": g.rolled,
        "setup_order": list(g.setup_order),
        "setup_idx": g.setup_idx,
        "setup_need": g.setup_need,
        "setup_anchor_vid": g.setup_anchor_vid,
        "last_roll": g.last_roll,
        "robber_tile": g.robber_tile,
        "pending_action": g.pending_action,
        "pending_pid": g.pending_pid,
        "pending_victims": list(g.pending_victims),
        "longest_road_owner": g.longest_road_owner,
        "longest_road_len": g.longest_road_len,
        "largest_army_owner": g.largest_army_owner,
        "largest_army_size": g.largest_army_size,
        "game_over": g.game_over,
        "winner_pid": g.winner_pid,
        "players": [
            {
                "pid": p.pid,
                "name": p.name,
                "vp": p.vp,
                "res": dict(p.res),
                "knights_played": p.knights_played,
            }
            for p in g.players
        ],
        "bank": dict(g.bank),
        "occupied_v": {str(k): [v[0], v[1]] for k, v in g.occupied_v.items()},
        "occupied_e": {_edge_key((a, b)): owner for (a, b), owner in g.occupied_e.items()},
        "tiles": [
            {
                "q": t.q,
                "r": t.r,
                "terrain": t.terrain,
                "number": t.number,
                "center": [t.center[0], t.center[1]],
            }
            for t in g.tiles
        ],
        "vertices": {str(k): [v[0], v[1]] for k, v in g.vertices.items()},
        "edges": [[a, b] for a, b in sorted(g.edges)],
        "vertex_adj_hexes": {str(k): v for k, v in g.vertex_adj_hexes.items()},
        "edge_adj_hexes": {_edge_key((a, b)): v for (a, b), v in g.edge_adj_hexes.items()},
        "ports": [[[a, b], kind] for (a, b), kind in g.ports],
    }


def from_dict(data: Dict) -> GameState:
    seed = int(data.get("seed", 0))
    size = float(data.get("size", 58.0))
    max_players = int(data.get("max_players", 4))

    tiles = []
    for t in data.get("tiles", []):
        center = (float(t["center"][0]), float(t["center"][1]))
        tiles.append(Tile(q=int(t["q"]), r=int(t["r"]), terrain=t["terrain"], number=t.get("number"), center=center))

    vertices = {int(k): (float(v[0]), float(v[1])) for k, v in data.get("vertices", {}).items()}
    vertex_adj_hexes = {int(k): list(v) for k, v in data.get("vertex_adj_hexes", {}).items()}
    edges = set((int(a), int(b)) for a, b in data.get("edges", []))
    edge_adj_hexes = {}
    for k, v in data.get("edge_adj_hexes", {}).items():
        if isinstance(k, str) and "," in k:
            a, b = k.split(",", 1)
            edge_adj_hexes[(int(a), int(b))] = list(v)
    ports = [((int(p[0][0]), int(p[0][1])), p[1]) for p in data.get("ports", [])]
    occupied_v = {int(k): (int(v[0]), int(v[1])) for k, v in data.get("occupied_v", {}).items()}
    occupied_e = {}
    for k, owner in data.get("occupied_e", {}).items():
        if isinstance(k, str) and "," in k:
            a, b = k.split(",", 1)
            e = (int(a), int(b))
            occupied_e[e] = int(owner)

    board = BoardState(
        tiles=tiles,
        vertices=vertices,
        vertex_adj_hexes=vertex_adj_hexes,
        edges=edges,
        edge_adj_hexes=edge_adj_hexes,
        ports=ports,
        occupied_v=occupied_v,
        occupied_e=occupied_e,
    )

    players = []
    for p in data.get("players", []):
        pid = int(p["pid"])
        pl = PlayerState(pid=pid, name=p.get("name", f"P{pid+1}"))
        pl.vp = int(p.get("vp", 0))
        pl.res = {r: int(p.get("res", {}).get(r, 0)) for r in RESOURCES}
        pl.knights_played = int(p.get("knights_played", 0))
        players.append(pl)

    g = GameState(seed=seed, size=size, max_players=max_players, board=board, players=players)
    g.phase = data.get("phase", "setup")
    g.turn = int(data.get("turn", 0))
    g.rolled = bool(data.get("rolled", False))
    g.setup_order = [int(x) for x in data.get("setup_order", [])]
    g.setup_idx = int(data.get("setup_idx", 0))
    g.setup_need = data.get("setup_need", "settlement")
    g.setup_anchor_vid = data.get("setup_anchor_vid", None)
    g.last_roll = data.get("last_roll", None)
    g.robber_tile = int(data.get("robber_tile", 0))
    g.pending_action = data.get("pending_action", None)
    g.pending_pid = data.get("pending_pid", None)
    g.pending_victims = list(data.get("pending_victims", []))
    g.longest_road_owner = data.get("longest_road_owner", None)
    g.longest_road_len = int(data.get("longest_road_len", 0))
    g.largest_army_owner = data.get("largest_army_owner", None)
    g.largest_army_size = int(data.get("largest_army_size", 0))
    g.game_over = bool(data.get("game_over", False))
    g.winner_pid = data.get("winner_pid", None)
    g.bank = {r: int(data.get("bank", {}).get(r, 0)) for r in RESOURCES}
    return g
