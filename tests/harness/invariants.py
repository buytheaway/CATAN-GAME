from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app import ui_v6


def _edge_key(e: Tuple[int, int]) -> Tuple[int, int]:
    a, b = e
    return (a, b) if a < b else (b, a)


def _recompute_longest_road(g) -> Tuple[Optional[int], int]:
    lens = [ui_v6.longest_road_length(g, pid) for pid in range(len(g.players))]
    if not lens:
        return None, 0
    if lens[0] >= 5 and lens[0] > lens[1]:
        return 0, lens[0]
    if lens[1] >= 5 and lens[1] > lens[0]:
        return 1, lens[1]
    return None, 0


def _recompute_largest_army(g) -> Tuple[Optional[int], int]:
    sizes = [p.knights_played for p in g.players]
    if not sizes:
        return None, 0
    max_k = max(sizes)
    if max_k < 3:
        return None, 0
    leaders = [i for i, k in enumerate(sizes) if k == max_k]
    if len(leaders) != 1:
        return None, max_k
    return leaders[0], max_k


def check_invariants(game, expected_totals: Optional[Dict[str, int]] = None) -> List[Dict[str, Any]]:
    fails: List[Dict[str, Any]] = []

    # bank + player resources non-negative ints
    for r, q in game.bank.items():
        if not isinstance(q, int):
            fails.append({"code": "bank_type", "message": f"Bank {r} not int", "details": {"res": r, "value": q}})
        if int(q) < 0:
            fails.append({"code": "bank_negative", "message": f"Bank {r} negative", "details": {"res": r, "value": q}})

    for pid, p in enumerate(game.players):
        for r, q in p.res.items():
            if not isinstance(q, int):
                fails.append({"code": "player_type", "message": f"Player {pid} {r} not int", "details": {"pid": pid, "res": r, "value": q}})
            if int(q) < 0:
                fails.append({"code": "player_negative", "message": f"Player {pid} {r} negative", "details": {"pid": pid, "res": r, "value": q}})

    # resource conservation
    if expected_totals:
        totals = {r: int(game.bank.get(r, 0)) for r in ui_v6.RESOURCES}
        for p in game.players:
            for r, q in p.res.items():
                totals[r] += int(q)
        for r, total in totals.items():
            if total != int(expected_totals.get(r, total)):
                fails.append({
                    "code": "resource_conservation",
                    "message": f"Resource total mismatch for {r}",
                    "details": {"res": r, "expected": expected_totals.get(r), "actual": total},
                })

    # occupied keys validity
    for vid in game.occupied_v.keys():
        if vid not in game.vertices:
            fails.append({"code": "invalid_vertex", "message": "Occupied vertex missing", "details": {"vid": vid}})

    edge_set = {_edge_key(e) for e in game.edges}
    for e in game.occupied_e.keys():
        if _edge_key(e) not in edge_set:
            fails.append({"code": "invalid_edge", "message": "Occupied edge missing", "details": {"edge": e}})

    # distance rule
    for vid in game.occupied_v.keys():
        for nb in ui_v6.edge_neighbors_of_vertex(game.edges, vid):
            if nb in game.occupied_v:
                fails.append({"code": "distance_rule", "message": "Adjacent settlements detected", "details": {"vid": vid, "neighbor": nb}})
                break

    # longest road consistent
    exp_owner, exp_len = _recompute_longest_road(game)
    if game.longest_road_owner != exp_owner or game.longest_road_len != exp_len:
        fails.append({
            "code": "longest_road",
            "message": "Longest road state mismatch",
            "details": {
                "expected_owner": exp_owner,
                "expected_len": exp_len,
                "actual_owner": game.longest_road_owner,
                "actual_len": game.longest_road_len,
            },
        })

    # largest army consistent
    exp_owner, exp_size = _recompute_largest_army(game)
    if game.largest_army_pid != exp_owner or game.largest_army_size != exp_size:
        fails.append({
            "code": "largest_army",
            "message": "Largest army state mismatch",
            "details": {
                "expected_owner": exp_owner,
                "expected_size": exp_size,
                "actual_owner": game.largest_army_pid,
                "actual_size": game.largest_army_size,
            },
        })

    # game over consistency
    if game.game_over:
        if game.winner_pid is None:
            fails.append({"code": "game_over", "message": "Game over without winner", "details": {}})
        else:
            if game.players[game.winner_pid].vp < 10:
                fails.append({"code": "game_over", "message": "Winner has <10 VP", "details": {"pid": game.winner_pid}})

    # pending action consistency
    if game.pending_action is not None and game.pending_pid is None:
        fails.append({"code": "pending_action", "message": "Pending action without pending_pid", "details": {"pending": game.pending_action}})
    if game.pending_action == "robber_steal" and not game.pending_victims:
        fails.append({"code": "pending_action", "message": "Robber steal without victims", "details": {}})

    return fails
