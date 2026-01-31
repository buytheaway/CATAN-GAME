from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver


def _find_edge_path(g, min_len: int) -> tuple[list[Tuple[int, int]], list[int]] | None:
    edges = list(g.edges)
    adj: Dict[int, List[Tuple[int, int]]] = {}
    for a, b in edges:
        adj.setdefault(a, []).append((a, b))
        adj.setdefault(b, []).append((a, b))

    def dfs(v: int, used: set, verts: List[int], path: List[Tuple[int, int]]):
        if len(path) >= min_len:
            return path, verts
        for e in adj.get(v, []):
            if e in used:
                continue
            a, b = e
            nxt = b if a == v else a
            used.add(e)
            path.append(e)
            verts.append(nxt)
            res = dfs(nxt, used, verts, path)
            if res:
                return res
            verts.pop()
            path.pop()
            used.remove(e)
        return None

    for v in adj.keys():
        res = dfs(v, set(), [v], [])
        if res:
            return res
    return None


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    # clear any existing placements for deterministic graph test
    g.occupied_v.clear()
    g.occupied_e.clear()

    found = _find_edge_path(g, 6) or _find_edge_path(g, 5)
    if not found:
        driver.fail("no path found for longest road test", kind="assertion")
    path, verts = found
    path_len = len(path)

    for e in path:
        g.occupied_e[e] = 0

    engine_rules.update_longest_road(g)
    if path_len >= 5 and g.longest_road_owner != 0:
        driver.fail("longest road not awarded to player 0", kind="assertion", details={"len": path_len})

    # block in the middle with enemy settlement
    k = max(1, min(path_len - 1, path_len // 2))
    block_vid = verts[k]
    g.occupied_v[block_vid] = (1, 1)
    expected = max(k, path_len - k)
    actual = engine_rules.longest_road_length(g, 0)
    if actual != expected:
        driver.fail("blocked longest road length mismatch", kind="assertion", details={
            "expected": expected,
            "actual": actual,
            "path_len": path_len,
            "block_vid": block_vid,
        })

    engine_rules.update_longest_road(g)
    if expected < 5:
        if g.longest_road_owner is not None:
            driver.fail("longest road owner should clear when below 5", kind="assertion")
    return {"steps": driver.steps, "summary": driver.snapshot()}
