from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.engine import rules as engine_rules
from tests.harness.engine import GameDriver


def _find_path_edges(g, start_vid: int, length: int) -> List[Tuple[int, int]]:
    adj: Dict[int, List[Tuple[int, int]]] = {}
    for e in g.edges:
        a, b = e
        adj.setdefault(a, []).append(e)
        adj.setdefault(b, []).append(e)

    def dfs(v: int, used: set, remaining: int) -> List[Tuple[int, int]]:
        if remaining == 0:
            return []
        for e in adj.get(v, []):
            if e in used:
                continue
            a, b = e
            nxt = b if a == v else a
            used.add(e)
            sub = dfs(nxt, used, remaining - 1)
            if sub is not None:
                return [e] + sub
            used.remove(e)
        return None

    res = dfs(start_vid, set(), length)
    if res is None:
        return []
    return res


def _pick_isolated_vertex(g) -> int:
    for vid in g.vertices.keys():
        if vid in g.occupied_v:
            continue
        # avoid vertices on existing roads
        blocked = False
        for e in g.occupied_e.keys():
            if vid in e:
                blocked = True
                break
        if blocked:
            continue
        ok = True
        for nb in engine_rules.edge_neighbors_of_vertex(g.edges, vid):
            if nb in g.occupied_v:
                ok = False
                break
        if ok:
            return vid
    raise ValueError("no isolated vertex")


def run(driver: GameDriver) -> Dict[str, Any]:
    g = driver.game
    g.phase = "main"
    g.turn = 0
    g.rolled = True

    # place a settlement for player 0 to anchor roads
    start = _pick_isolated_vertex(g)
    g.occupied_v[start] = (0, 1)
    g.players[0].vp += 1
    engine_rules.update_longest_road(g)

    path = _find_path_edges(g, start, 5)
    if len(path) < 5:
        driver.fail("could not find road path length 5", kind="assertion")

    driver.do({"type": "grant_resources", "pid": 0, "res": {"wood": 5, "brick": 5}})
    for e in path:
        res = driver.do({"type": "place_road", "pid": 0, "eid": e})
        if not res.get("ok"):
            driver.fail("place road failed", kind="assertion", details=res)

    if g.longest_road_owner != 0 or g.longest_road_len < 5:
        driver.fail("longest road not awarded", kind="assertion", details={
            "owner": g.longest_road_owner,
            "len": g.longest_road_len,
        })

    # build longer road for player 1
    g.turn = 1
    start2 = _pick_isolated_vertex(g)
    g.occupied_v[start2] = (1, 1)
    g.players[1].vp += 1
    engine_rules.update_longest_road(g)

    path2 = _find_path_edges(g, start2, 6)
    if len(path2) < 6:
        driver.fail("could not find road path length 6", kind="assertion")

    driver.do({"type": "grant_resources", "pid": 1, "res": {"wood": 6, "brick": 6}})
    for e in path2:
        res = driver.do({"type": "place_road", "pid": 1, "eid": e})
        if not res.get("ok"):
            driver.fail("place road failed for p1", kind="assertion", details=res)

    if g.longest_road_owner != 1:
        driver.fail("longest road did not transfer", kind="assertion", details={"owner": g.longest_road_owner})

    # blocking settlement should reduce road length (recompute only)
    before_len = engine_rules.longest_road_length(g, 0)
    blocker = None
    for e in path:
        for vid in e:
            if vid in g.occupied_v:
                continue
            ok = True
            for nb in engine_rules.edge_neighbors_of_vertex(g.edges, vid):
                if nb in g.occupied_v:
                    ok = False
                    break
            if ok:
                blocker = vid
                break
        if blocker is not None:
            break
    if blocker is None:
        driver.fail("no blocker vertex found", kind="assertion")

    g.occupied_v[blocker] = (1, 1)
    g.players[1].vp += 1
    engine_rules.update_longest_road(g)
    after_len = engine_rules.longest_road_length(g, 0)
    if after_len > before_len:
        driver.fail("blocking settlement did not reduce road", kind="assertion", details={
            "before": before_len,
            "after": after_len,
        })

    return {
        "steps": driver.steps,
        "summary": driver.snapshot(),
    }
