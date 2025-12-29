from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

RESOURCES = ["wood", "brick", "sheep", "wheat", "ore"]

TERRAIN_TO_RES = {
    "forest": "wood",
    "hills": "brick",
    "pasture": "sheep",
    "fields": "wheat",
    "mountains": "ore",
    "desert": None,
}

# Base board axial coords: rows 3-4-5-4-3
BASE_AXIAL: List[Tuple[int, int]] = (
    [(0, -2), (1, -2), (2, -2)]
    + [(-1, -1), (0, -1), (1, -1), (2, -1)]
    + [(-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0)]
    + [(-2, 1), (-1, 1), (0, 1), (1, 1)]
    + [(-2, 2), (-1, 2), (0, 2)]
)

COST = {
    "road": {"wood": 1, "brick": 1},
    "settlement": {"wood": 1, "brick": 1, "sheep": 1, "wheat": 1},
    "city": {"wheat": 2, "ore": 3},
}


def axial_to_pixel(q: int, r: int, size: float) -> Tuple[float, float]:
    x = size * 1.7320508075688772 * (q + r / 2.0)
    y = size * 1.5 * r
    return (x, y)


def hex_corners(center: Tuple[float, float], size: float) -> List[Tuple[float, float]]:
    cx, cy = center
    pts = []
    for i in range(6):
        ang = math.radians(30 + 60 * i)
        pts.append((cx + size * math.cos(ang), cy + size * math.sin(ang)))
    return pts


def quant_key(p: Tuple[float, float], step: float = 0.5) -> Tuple[int, int]:
    return (int(round(p[0] / step)), int(round(p[1] / step)))


def edge_neighbors_of_vertex(edges: Set[Tuple[int, int]], vid: int) -> Set[int]:
    out = set()
    for a, b in edges:
        if a == vid:
            out.add(b)
        elif b == vid:
            out.add(a)
    return out


@dataclass
class Tile:
    q: int
    r: int
    terrain: str
    number: Optional[int]
    center: Tuple[float, float]


@dataclass
class PlayerState:
    pid: int
    name: str
    res: Dict[str, int] = field(default_factory=lambda: {r: 0 for r in RESOURCES})
    vp: int = 0
    knights_played: int = 0


@dataclass
class GameState:
    seed: int
    size: float = 58.0
    tiles: List[Tile] = field(default_factory=list)
    vertices: Dict[int, Tuple[float, float]] = field(default_factory=dict)
    vertex_adj_hexes: Dict[int, List[int]] = field(default_factory=dict)
    edges: Set[Tuple[int, int]] = field(default_factory=set)
    edge_adj_hexes: Dict[Tuple[int, int], List[int]] = field(default_factory=dict)

    players: List[PlayerState] = field(default_factory=list)
    bank: Dict[str, int] = field(default_factory=lambda: {r: 19 for r in RESOURCES})
    occupied_v: Dict[int, Tuple[int, int]] = field(default_factory=dict)  # vid -> (pid, level)
    occupied_e: Dict[Tuple[int, int], int] = field(default_factory=dict)  # edge -> pid

    turn: int = 0
    phase: str = "setup"
    rolled: bool = False

    setup_order: List[int] = field(default_factory=list)
    setup_idx: int = 0
    setup_need: str = "settlement"
    setup_anchor_vid: Optional[int] = None
    last_roll: Optional[int] = None

    ports: List[Tuple[Tuple[int, int], str]] = field(default_factory=list)
    robber_tile: int = 0
    pending_action: Optional[str] = None
    pending_pid: Optional[int] = None
    pending_victims: List[int] = field(default_factory=list)

    longest_road_owner: Optional[int] = None
    longest_road_len: int = 0
    largest_army_owner: Optional[int] = None
    largest_army_size: int = 0

    game_over: bool = False
    winner_pid: Optional[int] = None


def make_setup_order(n_players: int) -> List[int]:
    order = list(range(n_players)) + list(range(n_players - 1, -1, -1))
    return order


def build_game(seed: int, max_players: int = 4, size: float = 58.0) -> GameState:
    rng = random.Random(seed)
    g = GameState(seed=seed, size=size)

    terrains = (
        ["forest"] * 4
        + ["hills"] * 3
        + ["pasture"] * 4
        + ["fields"] * 4
        + ["mountains"] * 3
        + ["desert"] * 1
    )
    rng.shuffle(terrains)

    numbers = [2, 3, 3, 4, 4, 5, 5, 6, 6, 8, 8, 9, 9, 10, 10, 11, 11, 12]
    rng.shuffle(numbers)

    tiles: List[Tile] = []
    desert_idx = None
    ni = 0
    for (q, r), terr in zip(BASE_AXIAL, terrains):
        c = axial_to_pixel(q, r, size)
        num = None
        if terr != "desert":
            num = numbers[ni]
            ni += 1
        else:
            desert_idx = len(tiles)
        tiles.append(Tile(q=q, r=r, terrain=terr, number=num, center=c))
    g.tiles = tiles
    g.robber_tile = desert_idx if desert_idx is not None else 0

    v_map: Dict[Tuple[int, int], int] = {}
    v_points: List[Tuple[float, float]] = []
    v_hexes: Dict[int, List[int]] = {}
    edges: Set[Tuple[int, int]] = set()
    edge_hexes: Dict[Tuple[int, int], List[int]] = {}

    for ti, t in enumerate(tiles):
        corners = hex_corners(t.center, size)
        vids = []
        for p in corners:
            k = quant_key(p, 0.5)
            if k not in v_map:
                vid = len(v_points)
                v_map[k] = vid
                v_points.append(p)
                v_hexes[vid] = []
            vid = v_map[k]
            vids.append(vid)
            v_hexes[vid].append(ti)

        for i in range(6):
            a = vids[i]
            b = vids[(i + 1) % 6]
            e = (a, b) if a < b else (b, a)
            edges.add(e)
            edge_hexes.setdefault(e, []).append(ti)

    g.vertices = {i: p for i, p in enumerate(v_points)}
    g.vertex_adj_hexes = v_hexes
    g.edges = edges
    g.edge_adj_hexes = edge_hexes

    coast = [e for e, hx in edge_hexes.items() if len(hx) == 1]
    center = (0.0, 0.0)

    def angle_of_edge(e):
        a, b = e
        p = ((g.vertices[a][0] + g.vertices[b][0]) * 0.5, (g.vertices[a][1] + g.vertices[b][1]) * 0.5)
        return math.atan2(p[1] - center[1], p[0] - center[0])

    coast.sort(key=angle_of_edge)
    if len(coast) >= 9:
        pick_idx = [int(i * len(coast) / 9) for i in range(9)]
        coast9 = [coast[i % len(coast)] for i in pick_idx]
    else:
        coast9 = coast

    port_types = ["3:1"] * 4 + [f"2:1:{r}" for r in RESOURCES]
    rng.shuffle(port_types)
    port_types = port_types[: len(coast9)]
    g.ports = list(zip(coast9, port_types))

    g.players = [PlayerState(pid=i, name=f"P{i+1}") for i in range(max_players)]
    g.setup_order = make_setup_order(max_players)
    g.setup_idx = 0
    g.setup_need = "settlement"
    g.setup_anchor_vid = None

    return g


def can_place_settlement(g: GameState, pid: int, vid: int, require_road: bool) -> bool:
    if vid in g.occupied_v:
        return False
    for nb in edge_neighbors_of_vertex(g.edges, vid):
        if nb in g.occupied_v:
            return False
    if not require_road:
        return True
    for e in g.edges:
        if vid in e and g.occupied_e.get(e) == pid:
            return True
    return False


def can_place_road(g: GameState, pid: int, e: Tuple[int, int], must_touch_vid: Optional[int] = None) -> bool:
    if e in g.occupied_e:
        return False
    a, b = e
    if must_touch_vid is not None and (a != must_touch_vid and b != must_touch_vid):
        return False
    for v in (a, b):
        occ = g.occupied_v.get(v)
        if occ and occ[0] == pid:
            return True
    for ee, owner in g.occupied_e.items():
        if owner == pid and (a in ee or b in ee):
            return True
    return False


def can_upgrade_city(g: GameState, pid: int, vid: int) -> bool:
    occ = g.occupied_v.get(vid)
    return bool(occ and occ[0] == pid and occ[1] == 1)


def can_pay(p: PlayerState, cost: Dict[str, int]) -> bool:
    return all(p.res.get(r, 0) >= q for r, q in cost.items())


def pay_to_bank(g: GameState, pid: int, cost: Dict[str, int]) -> None:
    for r, q in cost.items():
        g.players[pid].res[r] -= q
        g.bank[r] += q


def distribute_for_roll(g: GameState, roll: int) -> None:
    for vid, (pid, level) in g.occupied_v.items():
        for ti in g.vertex_adj_hexes.get(vid, []):
            t = g.tiles[ti]
            if t.number != roll:
                continue
            if ti == g.robber_tile:
                continue
            res = TERRAIN_TO_RES.get(t.terrain)
            if not res:
                continue
            amount = 2 if level == 2 else 1
            give = min(amount, g.bank.get(res, 0))
            if give <= 0:
                continue
            g.bank[res] -= give
            g.players[pid].res[res] += give


def longest_road_length(g: GameState, pid: int) -> int:
    road_edges = [e for e, owner in g.occupied_e.items() if owner == pid]
    if not road_edges:
        return 0

    adj: Dict[int, List[Tuple[int, int]]] = {}
    for e in road_edges:
        a, b = e
        adj.setdefault(a, []).append(e)
        adj.setdefault(b, []).append(e)

    def is_blocked_vertex(vid: int) -> bool:
        occ = g.occupied_v.get(vid)
        return bool(occ and occ[0] != pid)

    def dfs(v: int, used: set, came_from) -> int:
        if is_blocked_vertex(v) and came_from is not None:
            return 0
        best = 0
        for e in adj.get(v, []):
            if e in used:
                continue
            a, b = e
            nxt = b if a == v else a
            used.add(e)
            best = max(best, 1 + dfs(nxt, used, e))
            used.remove(e)
        return best

    ans = 0
    for v in adj.keys():
        ans = max(ans, dfs(v, set(), None))
    return ans


def update_longest_road(g: GameState) -> None:
    lens = [longest_road_length(g, pid) for pid in range(len(g.players))]
    new_owner = None
    new_len = 0
    if lens:
        max_len = max(lens)
        leaders = [i for i, ln in enumerate(lens) if ln == max_len]
        if max_len >= 5 and len(leaders) == 1:
            new_owner = leaders[0]
            new_len = max_len

    if new_owner == g.longest_road_owner and new_len == g.longest_road_len:
        return

    if g.longest_road_owner is not None and new_owner != g.longest_road_owner:
        g.players[g.longest_road_owner].vp -= 2
    if new_owner is not None and new_owner != g.longest_road_owner:
        g.players[new_owner].vp += 2

    g.longest_road_owner = new_owner
    g.longest_road_len = new_len


def update_largest_army(g: GameState) -> None:
    sizes = [p.knights_played for p in g.players]
    if not sizes:
        g.largest_army_owner = None
        g.largest_army_size = 0
        return
    max_k = max(sizes)
    if max_k < 3:
        if g.largest_army_owner is not None:
            g.players[g.largest_army_owner].vp -= 2
        g.largest_army_owner = None
        g.largest_army_size = 0
        return
    leaders = [i for i, k in enumerate(sizes) if k == max_k]
    if len(leaders) != 1:
        if g.largest_army_owner is not None:
            g.players[g.largest_army_owner].vp -= 2
        g.largest_army_owner = None
        g.largest_army_size = max_k
        return
    leader = leaders[0]
    if leader != g.largest_army_owner:
        if g.largest_army_owner is not None:
            g.players[g.largest_army_owner].vp -= 2
        g.players[leader].vp += 2
    g.largest_army_owner = leader
    g.largest_army_size = max_k


def check_win(g: GameState) -> None:
    if g.game_over:
        return
    for i, p in enumerate(g.players):
        if p.vp >= 10:
            g.game_over = True
            g.winner_pid = i
            return
