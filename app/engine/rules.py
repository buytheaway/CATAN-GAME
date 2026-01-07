from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

from app.engine.state import (
    AchievementState,
    BoardState,
    COST,
    DEV_TYPES,
    GameState,
    PlayerState,
    RESOURCES,
    TERRAIN_TO_RES,
    Tile,
    TradeOffer,
)


# Base board axial coords: rows 3-4-5-4-3
BASE_AXIAL: List[Tuple[int, int]] = (
    [(0, -2), (1, -2), (2, -2)]
    + [(-1, -1), (0, -1), (1, -1), (2, -1)]
    + [(-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0)]
    + [(-2, 1), (-1, 1), (0, 1), (1, 1)]
    + [(-2, 2), (-1, 2), (0, 2)]
)


class RuleError(Exception):
    def __init__(self, code: str, message: str, details: Optional[Dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


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


def edge_neighbors_of_vertex(edges: set[Tuple[int, int]], vid: int) -> set[int]:
    out = set()
    for a, b in edges:
        if a == vid:
            out.add(b)
        elif b == vid:
            out.add(a)
    return out


def make_setup_order(n_players: int) -> List[int]:
    return list(range(n_players)) + list(range(n_players - 1, -1, -1))


def build_game(
    seed: int,
    max_players: int = 4,
    size: float = 58.0,
    player_names: Optional[List[str]] = None,
) -> GameState:
    rng = random.Random(seed)
    g = GameState(seed=seed, size=size, max_players=max_players)

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

    v_map: Dict[Tuple[int, int], int] = {}
    v_points: List[Tuple[float, float]] = []
    v_hexes: Dict[int, List[int]] = {}
    edges: set[Tuple[int, int]] = set()
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

    coast = [e for e, hx in edge_hexes.items() if len(hx) == 1]
    center = (0.0, 0.0)

    def angle_of_edge(e):
        a, b = e
        p = ((v_points[a][0] + v_points[b][0]) * 0.5, (v_points[a][1] + v_points[b][1]) * 0.5)
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
    ports = list(zip(coast9, port_types))

    g.board = BoardState(
        tiles=tiles,
        vertices={i: p for i, p in enumerate(v_points)},
        vertex_adj_hexes=v_hexes,
        edges=edges,
        edge_adj_hexes=edge_hexes,
        ports=ports,
        occupied_v={},
        occupied_e={},
    )

    g.robber_tile = desert_idx if desert_idx is not None else 0

    if player_names is None:
        player_names = [f"P{i+1}" for i in range(max_players)]
    g.players = [PlayerState(pid=i, name=player_names[i]) for i in range(max_players)]

    g.setup_order = make_setup_order(max_players)
    g.setup_idx = 0
    g.setup_need = "settlement"
    g.setup_anchor_vid = None

    dev_deck = (
        ["knight"] * 14
        + ["victory_point"] * 5
        + ["road_building"] * 2
        + ["year_of_plenty"] * 2
        + ["monopoly"] * 2
    )
    rng.shuffle(dev_deck)
    g.dev_deck = dev_deck
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


def _vertex_owner(g: GameState, vid: int) -> Optional[int]:
    occ = g.occupied_v.get(vid)
    return occ[0] if occ else None


def _is_blocked_vertex(g: GameState, vid: int, pid: int) -> bool:
    owner = _vertex_owner(g, vid)
    return owner is not None and owner != pid


def longest_road_length(g: GameState, pid: int) -> int:
    road_edges = [e for e, owner in g.occupied_e.items() if owner == pid]
    if not road_edges:
        return 0

    adj: Dict[int, List[Tuple[int, int]]] = {}
    for e in road_edges:
        a, b = e
        adj.setdefault(a, []).append(e)
        adj.setdefault(b, []).append(e)

    def dfs(v: int, used: set, came_from) -> int:
        if _is_blocked_vertex(g, v, pid) and came_from is not None:
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


def _normalize_port_kind(kind: Optional[str]) -> Optional[str]:
    if kind is None:
        return None
    s = str(kind).strip().lower()
    if s in RESOURCES:
        return s
    if s in ("3:1", "3", "generic", "any", "all", "none", "?"):
        return "3:1"
    if "3:1" in s or "3/1" in s or "3 to 1" in s or "3to1" in s:
        return "3:1"
    for r in RESOURCES:
        if r in s:
            return r
    return None


def _iter_ports(ports):
    for p in ports:
        a = b = kind = None
        if isinstance(p, dict):
            kind = p.get("kind")
            a = p.get("a", p.get("v1"))
            b = p.get("b", p.get("v2"))
        elif isinstance(p, (tuple, list)) and len(p) == 2:
            edge, kind = p
            if isinstance(edge, (tuple, list)) and len(edge) == 2:
                a, b = edge
        if a is None or b is None:
            continue
        try:
            a = int(a)
            b = int(b)
        except Exception:
            continue
        yield a, b, kind


def player_ports(g: GameState, pid: int) -> set:
    owned = {vid for vid, (owner, _lvl) in g.occupied_v.items() if owner == pid}
    ports = set()
    for a, b, kind in _iter_ports(g.ports):
        if a in owned or b in owned:
            norm = _normalize_port_kind(kind)
            if norm:
                ports.add(norm)
    return ports


def best_trade_rate(g: GameState, pid: int, give_res: str) -> int:
    ports = player_ports(g, pid)
    give_res = str(give_res).strip().lower()
    if give_res in ports:
        return 2
    if "3:1" in ports:
        return 3
    return 4


def trade_with_bank(g: GameState, pid: int, give_res: str, get_res: str, get_qty: int) -> int:
    if g.game_over:
        raise RuleError("game_over", "Game over")
    if g.phase != "main" or pid != g.turn:
        raise RuleError("illegal", "Not your turn")
    give_res = str(give_res).strip().lower()
    get_res = str(get_res).strip().lower()
    if give_res == get_res:
        raise RuleError("invalid", "Give and Get must be different")
    if give_res not in RESOURCES or get_res not in RESOURCES:
        raise RuleError("invalid", "Invalid resource")
    qty = int(get_qty)
    if qty <= 0:
        raise RuleError("invalid", "Invalid quantity")
    rate = best_trade_rate(g, pid, give_res)
    give_qty = rate * qty
    pres = g.players[pid].res
    if pres.get(give_res, 0) < give_qty:
        raise RuleError("illegal", "Not enough resources")
    if g.bank.get(get_res, 0) < qty:
        raise RuleError("illegal", "Bank has not enough resources")
    pres[give_res] -= give_qty
    pres[get_res] += qty
    g.bank[give_res] += give_qty
    g.bank[get_res] -= qty
    return rate


def _find_dev_idx(g: GameState, pid: int, card_type: str, allow_new: bool = False) -> Optional[int]:
    card_type = str(card_type).strip().lower()
    cards = g.players[pid].dev_cards
    for i, c in enumerate(cards):
        if not isinstance(c, dict):
            continue
        if str(c.get("type", "")).strip().lower() == card_type and (allow_new or not c.get("new", False)):
            return i
    if allow_new:
        for i, c in enumerate(cards):
            if isinstance(c, dict) and str(c.get("type", "")).strip().lower() == card_type:
                return i
    return None


def _clear_dev_new_flags(g: GameState, pid: int) -> None:
    for c in g.players[pid].dev_cards:
        if isinstance(c, dict) and c.get("new", False):
            c["new"] = False


def end_turn_cleanup(g: GameState, pid: int) -> None:
    _clear_dev_new_flags(g, pid)
    g.dev_played_turn[pid] = False


def buy_dev(g: GameState, pid: int) -> str:
    if g.game_over:
        raise RuleError("game_over", "Game over")
    if g.phase != "main" or pid != g.turn:
        raise RuleError("illegal", "Not your turn")
    if not g.dev_deck:
        raise RuleError("illegal", "Dev deck is empty")
    if not can_pay(g.players[pid], COST["dev"]):
        raise RuleError("illegal", "Not enough resources for dev card")
    pay_to_bank(g, pid, COST["dev"])
    card = g.dev_deck.pop()
    g.players[pid].dev_cards.append({"type": card, "new": True})
    if card == "victory_point":
        g.players[pid].vp += 1
        check_win(g)
    return card


def play_dev(g: GameState, pid: int, card_type: str, **kwargs) -> Dict:
    card_type = str(card_type).strip().lower()
    if g.game_over:
        raise RuleError("game_over", "Game over")
    if g.phase != "main" or pid != g.turn:
        raise RuleError("illegal", "Not your turn")
    if g.dev_played_turn.get(pid, False):
        raise RuleError("illegal", "Already played a dev card this turn")
    if card_type == "victory_point":
        raise RuleError("illegal", "Victory Point cards are passive")

    idx = _find_dev_idx(g, pid, card_type, allow_new=False)
    if idx is None:
        raise RuleError("illegal", "Cannot play this card now (new or missing)")
    g.players[pid].dev_cards.pop(idx)
    g.dev_played_turn[pid] = True

    if card_type == "knight":
        g.players[pid].knights_played += 1
        update_largest_army(g)
        check_win(g)
        g.pending_action = "robber_move"
        g.pending_pid = pid
        g.pending_victims = []
        return {"played": "knight"}

    if card_type == "road_building":
        g.free_roads[pid] = int(g.free_roads.get(pid, 0)) + 2
        return {"played": "road_building"}

    if card_type == "year_of_plenty":
        a = str(kwargs.get("a", "")).strip().lower()
        b = str(kwargs.get("b", "")).strip().lower()
        qa = int(kwargs.get("qa", 0))
        qb = int(kwargs.get("qb", 0))
        for r, q in ((a, qa), (b, qb)):
            if q <= 0:
                continue
            if r not in RESOURCES:
                raise RuleError("invalid", "Invalid resource")
            if g.bank.get(r, 0) < q:
                raise RuleError("illegal", f"Bank has not enough {r}")
        if qa > 0:
            g.bank[a] -= qa
            g.players[pid].res[a] += qa
        if qb > 0:
            g.bank[b] -= qb
            g.players[pid].res[b] += qb
        return {"played": "year_of_plenty"}

    if card_type == "monopoly":
        r = str(kwargs.get("r", "")).strip().lower()
        if r not in RESOURCES:
            raise RuleError("invalid", "Invalid resource")
        taken = 0
        for op in g.players:
            if op.pid == pid:
                continue
            q = int(op.res.get(r, 0))
            if q > 0:
                op.res[r] -= q
                taken += q
        g.players[pid].res[r] += taken
        return {"played": "monopoly", "taken": taken}

    raise RuleError("invalid", "Unknown dev card")


def _hand_size(g: GameState, pid: int) -> int:
    return sum(int(v) for v in g.players[pid].res.values())


def _discard_needed(g: GameState, pid: int) -> int:
    total = _hand_size(g, pid)
    return total // 2 if total > 7 else 0


def _auto_discard(g: GameState, pid: int, need: int) -> Dict[str, int]:
    pres = g.players[pid].res
    order = sorted(RESOURCES, key=lambda r: (-int(pres.get(r, 0)), r))
    out = {r: 0 for r in RESOURCES}
    remain = need
    for r in order:
        if remain <= 0:
            break
        take = min(int(pres.get(r, 0)), remain)
        if take > 0:
            out[r] = take
            remain -= take
    return out


def _apply_discard(g: GameState, pid: int, discard: Dict[str, int]) -> None:
    pres = g.players[pid].res
    for r, n in discard.items():
        q = min(int(n), int(pres.get(r, 0)))
        if q <= 0:
            continue
        pres[r] -= q
        g.bank[r] += q


def _victims_for_tile(g: GameState, tile: int, thief_pid: int) -> List[int]:
    victims = set()
    for vid, (owner, _level) in g.occupied_v.items():
        if owner == thief_pid:
            continue
        if tile in g.vertex_adj_hexes.get(vid, []):
            if _hand_size(g, owner) > 0:
                victims.add(owner)
    return sorted(victims)


def _steal_one(g: GameState, thief_pid: int, victim_pid: int) -> Optional[str]:
    res = g.players[victim_pid].res
    choices = [r for r, q in res.items() if q > 0]
    if not choices:
        return None
    choices.sort(key=lambda r: (-int(res.get(r, 0)), r))
    r = choices[0]
    res[r] -= 1
    g.players[thief_pid].res[r] += 1
    return r


def _clean_trade_payload(payload: Dict) -> Dict[str, int]:
    out: Dict[str, int] = {}
    if not isinstance(payload, dict):
        return out
    for r, n in payload.items():
        if r not in RESOURCES:
            continue
        q = int(n)
        if q > 0:
            out[r] = q
    return out


def _ensure_trade_payload(payload: Dict, label: str) -> Dict[str, int]:
    clean = _clean_trade_payload(payload)
    if not clean:
        raise RuleError("invalid", f"{label} must have at least one resource")
    return clean


def _sum_payload(payload: Dict[str, int]) -> int:
    return sum(int(v) for v in payload.values())


def _has_resources(res: Dict[str, int], payload: Dict[str, int]) -> bool:
    for r, q in payload.items():
        if int(res.get(r, 0)) < int(q):
            return False
    return True


def _find_offer(g: GameState, offer_id: int) -> Optional[TradeOffer]:
    for o in g.trade_offers:
        if o.offer_id == offer_id:
            return o
    return None


def apply_cmd(g: GameState, pid: int, cmd: Dict) -> Tuple[GameState, List[Dict]]:
    events: List[Dict] = []
    ctype = cmd.get("type")
    if not isinstance(ctype, str):
        raise RuleError("invalid", "cmd.type required")

    if g.game_over and ctype not in ("noop",):
        raise RuleError("game_over", "Game over")

    if g.pending_action == "discard" and ctype != "discard":
        raise RuleError("pending_action", "Resolve discard first")
    if g.pending_action is not None and g.pending_action != "discard" and ctype != "move_robber":
        raise RuleError("pending_action", "Resolve pending action first")

    if ctype == "grant_resources":
        res = cmd.get("res", {})
        for r, n in res.items():
            if r not in RESOURCES:
                continue
            qty = int(n)
            if qty <= 0:
                continue
            if g.bank.get(r, 0) < qty:
                raise RuleError("illegal", f"Bank lacks {r}")
            g.bank[r] -= qty
            g.players[pid].res[r] += qty
        return g, events

    if ctype == "place_settlement":
        vid = int(cmd.get("vid"))
        setup = bool(cmd.get("setup", False)) or g.phase == "setup"
        if setup:
            if g.setup_need != "settlement":
                raise RuleError("illegal", "Not settlement step")
            if not can_place_settlement(g, pid, vid, require_road=False):
                raise RuleError("illegal", "Settlement not allowed")
            before_count = sum(
                1
                for _vid, (owner, level) in g.occupied_v.items()
                if owner == pid and level == 1
            )
            g.occupied_v[vid] = (pid, 1)
            g.players[pid].vp += 1
            update_longest_road(g)
            check_win(g)
            g.setup_need = "road"
            g.setup_anchor_vid = vid
            after_count = before_count + 1
            if after_count == 2:
                granted: Dict[str, int] = {}
                for ti in g.vertex_adj_hexes.get(vid, []):
                    t = g.tiles[ti]
                    res = TERRAIN_TO_RES.get(t.terrain)
                    if not res:
                        continue
                    if int(g.bank.get(res, 0)) <= 0:
                        continue
                    g.bank[res] -= 1
                    g.players[pid].res[res] += 1
                    granted[res] = int(granted.get(res, 0)) + 1
                events.append({
                    "type": "initial_resources",
                    "pid": pid,
                    "vertex": vid,
                    "granted": granted,
                })
            events.append({"type": "place_settlement", "pid": pid, "vid": vid})
            return g, events

        if g.turn != pid or g.phase != "main":
            raise RuleError("illegal", "Not your turn")
        if not can_place_settlement(g, pid, vid, require_road=True):
            raise RuleError("illegal", "Settlement not allowed")
        if not can_pay(g.players[pid], COST["settlement"]):
            raise RuleError("illegal", "Not enough resources")
        pay_to_bank(g, pid, COST["settlement"])
        g.occupied_v[vid] = (pid, 1)
        g.players[pid].vp += 1
        update_longest_road(g)
        check_win(g)
        events.append({"type": "place_settlement", "pid": pid, "vid": vid})
        return g, events

    if ctype == "place_road":
        eid = cmd.get("eid")
        if not isinstance(eid, (list, tuple)) or len(eid) != 2:
            raise RuleError("invalid", "eid required")
        a, b = int(eid[0]), int(eid[1])
        e = (a, b) if a < b else (b, a)
        setup = bool(cmd.get("setup", False)) or g.phase == "setup"
        if setup:
            if g.setup_need != "road":
                raise RuleError("illegal", "Not road step")
            if not can_place_road(g, pid, e, must_touch_vid=g.setup_anchor_vid):
                raise RuleError("illegal", "Road not allowed")
            g.occupied_e[e] = pid
            update_longest_road(g)
            check_win(g)
            g.setup_need = "settlement"
            g.setup_anchor_vid = None
            g.setup_idx += 1
            if g.setup_idx >= len(g.setup_order):
                g.phase = "main"
            events.append({"type": "place_road", "pid": pid, "eid": [a, b]})
            return g, events

        if g.turn != pid or g.phase != "main":
            raise RuleError("illegal", "Not your turn")
        if not can_place_road(g, pid, e):
            raise RuleError("illegal", "Road not allowed")
        use_free = bool(cmd.get("free", False))
        if use_free:
            if int(g.free_roads.get(pid, 0)) <= 0:
                raise RuleError("illegal", "No free roads available")
            g.free_roads[pid] = int(g.free_roads.get(pid, 0)) - 1
        else:
            if not can_pay(g.players[pid], COST["road"]):
                raise RuleError("illegal", "Not enough resources")
            pay_to_bank(g, pid, COST["road"])
        g.occupied_e[e] = pid
        update_longest_road(g)
        check_win(g)
        events.append({"type": "place_road", "pid": pid, "eid": [a, b]})
        return g, events

    if ctype == "upgrade_city":
        vid = int(cmd.get("vid"))
        if g.turn != pid or g.phase != "main":
            raise RuleError("illegal", "Not your turn")
        if not can_upgrade_city(g, pid, vid):
            raise RuleError("illegal", "City upgrade not allowed")
        if not can_pay(g.players[pid], COST["city"]):
            raise RuleError("illegal", "Not enough resources")
        pay_to_bank(g, pid, COST["city"])
        g.occupied_v[vid] = (pid, 2)
        g.players[pid].vp += 1
        update_longest_road(g)
        check_win(g)
        events.append({"type": "upgrade_city", "pid": pid, "vid": vid})
        return g, events

    if ctype == "roll":
        if g.turn != pid or g.phase != "main":
            raise RuleError("illegal", "Not your turn")
        if g.rolled:
            raise RuleError("illegal", "Already rolled")
        roll = cmd.get("roll", cmd.get("forced"))
        if roll is None:
            raise RuleError("invalid", "roll required")
        roll = int(roll)
        g.last_roll = roll
        g.rolled = True
        g.roll_history.append(roll)
        if roll == 7:
            required = {}
            for opid in range(len(g.players)):
                need = _discard_needed(g, opid)
                if need > 0:
                    required[int(opid)] = int(need)
            if required:
                g.pending_action = "discard"
                g.pending_pid = pid
                g.pending_victims = []
                g.discard_required = dict(required)
                g.discard_submitted = set()
                events.append({"type": "roll", "roll": roll, "pending": "discard", "required": dict(required)})
                return g, events
            g.pending_action = "robber_move"
            g.pending_pid = pid
            g.pending_victims = []
            events.append({"type": "roll", "roll": roll, "pending": "robber_move"})
            return g, events
        distribute_for_roll(g, roll)
        events.append({"type": "roll", "roll": roll})
        return g, events

    if ctype == "discard":
        if g.pending_action != "discard":
            raise RuleError("illegal", "No discard pending")
        required = int(g.discard_required.get(pid, 0))
        if required <= 0:
            raise RuleError("illegal", "No discard required for player")
        discards = cmd.get("discards")
        if not isinstance(discards, dict):
            raise RuleError("invalid", "discards must be a dict")
        total = sum(int(v) for v in discards.values())
        if total != required:
            raise RuleError("invalid", "Discard count mismatch", {"pid": pid, "need": required})
        pres = g.players[pid].res
        for r, n in discards.items():
            if r not in RESOURCES:
                raise RuleError("invalid", "Invalid resource")
            if int(n) < 0:
                raise RuleError("invalid", "Negative discard")
            if pres.get(r, 0) < int(n):
                raise RuleError("illegal", "Not enough resources")
        _apply_discard(g, pid, discards)
        g.discard_submitted.add(pid)
        events.append({"type": "discard", "pid": pid, "discards": dict(discards)})
        if set(g.discard_submitted) >= set(g.discard_required.keys()):
            g.discard_required = {}
            g.discard_submitted = set()
            g.pending_action = "robber_move"
            events.append({"type": "discard_complete", "pending": "robber_move"})
        return g, events

    if ctype == "trade_offer_create":
        if g.phase != "main" or g.turn != pid:
            raise RuleError("illegal", "Not your turn")
        give = _ensure_trade_payload(cmd.get("give", {}), "give")
        get = _ensure_trade_payload(cmd.get("get", {}), "get")
        if not _has_resources(g.players[pid].res, give):
            raise RuleError("illegal", "Not enough resources for offer")
        to_pid = cmd.get("to_pid", cmd.get("to"))
        if to_pid is not None:
            to_pid = int(to_pid)
            if to_pid < 0 or to_pid >= len(g.players):
                raise RuleError("invalid", "Invalid to_pid")
            if to_pid == pid:
                raise RuleError("invalid", "Cannot trade with self")
        offer = TradeOffer(
            offer_id=int(g.trade_offer_next_id),
            from_pid=int(pid),
            to_pid=to_pid,
            give=dict(give),
            get=dict(get),
            status="active",
            created_turn=int(g.turn),
            created_tick=int(g.tick),
        )
        g.trade_offer_next_id += 1
        g.trade_offers.append(offer)
        events.append({"type": "trade_offer_created", "offer_id": offer.offer_id})
        return g, events

    if ctype in ("trade_offer_accept", "trade_offer_decline", "trade_offer_cancel"):
        offer_id = int(cmd.get("offer_id", cmd.get("id", -1)))
        offer = _find_offer(g, offer_id)
        if offer is None:
            raise RuleError("invalid", "Offer not found")
        if offer.status != "active":
            raise RuleError("illegal", "Offer not active")

        if ctype == "trade_offer_cancel":
            if offer.from_pid != pid:
                raise RuleError("illegal", "Only creator can cancel")
            offer.status = "canceled"
            events.append({"type": "trade_offer_canceled", "offer_id": offer.offer_id})
            return g, events

        if offer.to_pid is not None and pid != offer.to_pid:
            raise RuleError("illegal", "Offer not addressed to player")
        if offer.from_pid == pid:
            raise RuleError("illegal", "Creator cannot accept/decline own offer")

        if g.phase != "main" or g.turn != offer.from_pid:
            raise RuleError("illegal", "Offer expired")

        if ctype == "trade_offer_decline":
            offer.status = "declined"
            events.append({"type": "trade_offer_declined", "offer_id": offer.offer_id, "pid": pid})
            return g, events

        # accept
        from_p = g.players[offer.from_pid].res
        to_p = g.players[pid].res
        if not _has_resources(from_p, offer.give):
            raise RuleError("illegal", "Offerer lacks resources")
        if not _has_resources(to_p, offer.get):
            raise RuleError("illegal", "Acceptor lacks resources")
        for r, q in offer.give.items():
            from_p[r] -= int(q)
            to_p[r] += int(q)
        for r, q in offer.get.items():
            to_p[r] -= int(q)
            from_p[r] += int(q)
        offer.status = "accepted"
        events.append({"type": "trade_offer_accepted", "offer_id": offer.offer_id, "pid": pid})
        return g, events

    if ctype == "move_robber":
        tile = int(cmd.get("tile"))
        victim = cmd.get("victim", cmd.get("victim_pid"))
        if g.pending_action not in ("robber_move",):
            raise RuleError("illegal", "No robber move pending")
        if g.pending_pid is not None and pid != g.pending_pid:
            raise RuleError("illegal", "Not your robber move")
        if tile == g.robber_tile:
            raise RuleError("illegal", "Same robber tile")
        g.robber_tile = tile
        victims = _victims_for_tile(g, tile, pid)
        stolen = None
        if victims:
            if isinstance(victim, int) and victim in victims:
                victim_pid = int(victim)
            else:
                victim_pid = victims[0]
            stolen = _steal_one(g, pid, victim_pid)
        g.pending_action = None
        g.pending_pid = None
        g.pending_victims = []
        events.append({"type": "move_robber", "tile": tile, "victim": victim, "stolen": stolen})
        return g, events

    if ctype == "trade_bank":
        rate = trade_with_bank(g, pid, cmd.get("give"), cmd.get("get"), int(cmd.get("get_qty", 1)))
        events.append({"type": "trade_bank", "rate": rate})
        return g, events

    if ctype == "buy_dev":
        card = buy_dev(g, pid)
        events.append({"type": "buy_dev", "card": card})
        return g, events

    if ctype == "play_dev":
        card = cmd.get("card")
        extra = {k: v for k, v in cmd.items() if k not in ("type", "card", "pid")}
        result = play_dev(g, pid, card, **extra)
        events.append({"type": "play_dev", "card": card, "result": result})
        return g, events

    if ctype == "end_turn":
        if g.turn != pid:
            raise RuleError("illegal", "Not your turn")
        if g.pending_action is not None:
            raise RuleError("pending_action", "Resolve pending action first")
        canceled = []
        for offer in g.trade_offers:
            if offer.status == "active":
                offer.status = "canceled"
                canceled.append(offer.offer_id)
        if canceled:
            events.append({"type": "trade_offer_canceled_bulk", "offer_ids": list(canceled)})
        end_turn_cleanup(g, pid)
        g.turn = (g.turn + 1) % len(g.players)
        g.rolled = False
        g.last_roll = None
        events.append({"type": "end_turn", "pid": pid})
        return g, events

    if ctype == "noop":
        return g, events

    raise RuleError("invalid", f"Unknown cmd: {ctype}")
