from __future__ import annotations

import math
from typing import Dict, List, Set, Tuple

from app.engine.state import Tile


SQRT3 = 1.7320508075688772


def axial_to_pixel(q: int, r: int, size: float) -> Tuple[float, float]:
    x = size * SQRT3 * (q + r / 2.0)
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


def build_graph_from_tiles(
    tiles: List[Tile],
    size: float,
) -> Tuple[Dict[int, Tuple[float, float]], Dict[int, List[int]], Set[Tuple[int, int]], Dict[Tuple[int, int], List[int]]]:
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

    vertices = {i: p for i, p in enumerate(v_points)}
    return vertices, v_hexes, edges, edge_hexes
