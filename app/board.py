from __future__ import annotations
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

RESOURCES = ["wood", "brick", "sheep", "wheat", "ore", "desert"]

@dataclass(frozen=True)
class Node:
    id: int
    x: float
    y: float

@dataclass(frozen=True)
class Edge:
    id: int
    a: int
    b: int

@dataclass(frozen=True)
class Hex:
    id: int
    cx: float
    cy: float
    res: str
    num: Optional[int]  # None for desert

@dataclass
class Board:
    nodes: List[Node]
    edges: List[Edge]
    hexes: List[Hex]
    node_adj_edges: Dict[int, List[int]]
    node_adj_nodes: Dict[int, List[int]]
    node_adj_hexes: Dict[int, List[int]]
    edge_between: Dict[Tuple[int,int], int]  # (min(a,b), max(a,b)) -> edge_id
    robber_hex: int

def _radius2_hexes() -> List[Tuple[int,int]]:
    # axial coords (q,r) for radius 2 hexagon => 19 tiles
    out = []
    R = 2
    for q in range(-R, R+1):
        for r in range(-R, R+1):
            s = -q - r
            if max(abs(q), abs(r), abs(s)) <= R:
                out.append((q,r))
    # stable order
    out.sort(key=lambda t: (t[1], t[0]))
    return out

def _axial_to_xy(q: int, r: int, size: float) -> Tuple[float,float]:
    # pointy-top
    x = size * math.sqrt(3) * (q + r/2.0)
    y = size * 1.5 * r
    return x, y

def _hex_corners(cx: float, cy: float, size: float) -> List[Tuple[float,float]]:
    pts = []
    for i in range(6):
        ang = math.radians(60*i - 30)
        pts.append((cx + size*math.cos(ang), cy + size*math.sin(ang)))
    return pts

def make_board(seed: int | None = None, size: float = 60.0) -> Board:
    rng = random.Random(seed)

    coords = _radius2_hexes()
    centers = []
    for idx,(q,r) in enumerate(coords):
        cx, cy = _axial_to_xy(q, r, size)
        centers.append((idx, cx, cy))

    # resources distribution (base)
    res_bag = (
        ["wood"]*4 + ["brick"]*3 + ["sheep"]*4 + ["wheat"]*4 + ["ore"]*3 + ["desert"]*1
    )
    rng.shuffle(res_bag)

    nums = [2,3,3,4,4,5,5,6,6,8,8,9,9,10,10,11,11,12]
    rng.shuffle(nums)

    hexes: List[Hex] = []
    robber_hex = 0
    n_i = 0
    for hid, cx, cy in centers:
        res = res_bag[hid]
        num = None
        if res != "desert":
            num = nums[n_i]; n_i += 1
        else:
            robber_hex = hid
        hexes.append(Hex(id=hid, cx=cx, cy=cy, res=res, num=num))

    # build nodes/edges by corner dedup (quantize)
    node_key_to_idx: Dict[Tuple[int,int], int] = {}
    node_points: List[Tuple[float,float]] = []
    hex_corner_nodes: Dict[int, List[int]] = {}

    def key(px: float, py: float) -> Tuple[int,int]:
        return (int(round(px*1000)), int(round(py*1000)))

    for h in hexes:
        corners = _hex_corners(h.cx, h.cy, size)
        ids = []
        for (px,py) in corners:
            k = key(px,py)
            if k not in node_key_to_idx:
                node_key_to_idx[k] = len(node_points)
                node_points.append((px,py))
            ids.append(node_key_to_idx[k])
        hex_corner_nodes[h.id] = ids

    # stable node ids: sort by y then x, remap
    idxs = list(range(len(node_points)))
    idxs.sort(key=lambda i: (node_points[i][1], node_points[i][0]))
    old_to_new = {old: new for new, old in enumerate(idxs)}
    nodes = [Node(id=new, x=node_points[old][0], y=node_points[old][1]) for new, old in enumerate(idxs)]

    # edges (unique)
    edge_key_set = {}
    edges_tmp = []
    for hid, corners in hex_corner_nodes.items():
        remapped = [old_to_new[i] for i in corners]
        for i in range(6):
            a = remapped[i]
            b = remapped[(i+1)%6]
            k = (a,b) if a < b else (b,a)
            if k not in edge_key_set:
                edge_key_set[k] = True
                edges_tmp.append(k)

    edges_tmp.sort()
    edges = [Edge(id=i, a=a, b=b) for i,(a,b) in enumerate(edges_tmp)]
    edge_between = {(min(e.a,e.b), max(e.a,e.b)): e.id for e in edges}

    # adjacency
    node_adj_edges: Dict[int, List[int]] = {n.id: [] for n in nodes}
    node_adj_nodes: Dict[int, List[int]] = {n.id: [] for n in nodes}
    for e in edges:
        node_adj_edges[e.a].append(e.id)
        node_adj_edges[e.b].append(e.id)
        node_adj_nodes[e.a].append(e.b)
        node_adj_nodes[e.b].append(e.a)

    node_adj_hexes: Dict[int, List[int]] = {n.id: [] for n in nodes}
    for h in hexes:
        corners = [old_to_new[i] for i in hex_corner_nodes[h.id]]
        for nid in corners:
            node_adj_hexes[nid].append(h.id)

    return Board(
        nodes=nodes,
        edges=edges,
        hexes=hexes,
        node_adj_edges=node_adj_edges,
        node_adj_nodes=node_adj_nodes,
        node_adj_hexes=node_adj_hexes,
        edge_between=edge_between,
        robber_hex=robber_hex,
    )
