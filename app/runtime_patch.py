from __future__ import annotations

import random
import types

RES = ("wood", "brick", "sheep", "wheat", "ore")


def _get_player_obj(game, pid: int):
    return game.players[pid]


def _get_player_res(game, pid: int) -> dict:
    # prefer existing helper if present
    fn = getattr(game, "_get_player_res_dict", None)
    if callable(fn):
        return fn(pid)

    p = _get_player_obj(game, pid)
    if hasattr(p, "res") and isinstance(p.res, dict):
        return p.res
    if isinstance(p, dict) and isinstance(p.get("res"), dict):
        return p["res"]

    # fallback: try common dict fields
    out = {}
    for r in RES:
        out[r] = int(getattr(p, r, 0)) if hasattr(p, r) else 0
    # attach a dict so future operations are consistent
    try:
        if hasattr(p, "res"):
            p.res = out
            return p.res
        if isinstance(p, dict):
            p["res"] = out
            return p["res"]
    except Exception:
        pass
    return out


def _ensure_bank(game):
    if not hasattr(game, "bank") or game.bank is None:
        game.bank = {r: 19 for r in RES}
    else:
        for r in RES:
            game.bank.setdefault(r, 19)


def _extract_owner_and_kind(b):
    # buildings can be tuple/list/dict/obj
    if b is None:
        return None, None
    if isinstance(b, (tuple, list)) and len(b) >= 2:
        return b[0], b[1]
    if isinstance(b, dict):
        owner = b.get("owner", b.get("pid", b.get("player")))
        kind = b.get("kind", b.get("type", b.get("building")))
        return owner, kind
    owner = getattr(b, "owner", getattr(b, "pid", getattr(b, "player", None)))
    kind = getattr(b, "kind", getattr(b, "type", getattr(b, "building", None)))
    return owner, kind


def _owned_vertices(game, pid: int) -> set:
    owned = set()

    # pattern 1: game.buildings: {vid: (owner, kind)} or dict/obj
    bmap = getattr(game, "buildings", None)
    if isinstance(bmap, dict):
        for vid, b in bmap.items():
            owner, kind = _extract_owner_and_kind(b)
            if owner == pid and str(kind) in ("settlement", "city"):
                owned.add(vid)

    # pattern 2: separate maps
    vown = getattr(game, "vertex_owner", None)
    vtyp = getattr(game, "vertex_building", None)
    if isinstance(vown, dict) and isinstance(vtyp, dict):
        for vid, owner in vown.items():
            if owner == pid and str(vtyp.get(vid)) in ("settlement", "city"):
                owned.add(vid)

    # pattern 3: settlements/cities sets + owner maps
    for name in ("settlements", "cities"):
        s = getattr(game, name, None)
        if isinstance(s, dict):
            # {vid: owner} or {vid: something}
            for vid, owner in s.items():
                if owner == pid:
                    owned.add(vid)
        elif isinstance(s, (set, list, tuple)):
            # if we also have settlement_owner map
            owner_map = getattr(game, f"{name[:-1]}_owner", None)  # settlement_owner/citie_owner (maybe)
            if isinstance(owner_map, dict):
                for vid in s:
                    if owner_map.get(vid) == pid:
                        owned.add(vid)

    return owned


def _port_endpoints(port):
    # try many shapes
    if port is None:
        return None, None, None

    if isinstance(port, dict):
        kind = port.get("kind", port.get("type", port.get("port_kind")))
        # direct
        a = port.get("a", port.get("v1", port.get("va")))
        b = port.get("b", port.get("v2", port.get("vb")))
        # list endpoints
        for k in ("verts", "vertices", "ends", "endpoints", "vs"):
            v = port.get(k)
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                a, b = v[0], v[1]
                break
        # sometimes nested edge tuple
        e = port.get("edge")
        if isinstance(e, (list, tuple)) and len(e) >= 2:
            a, b = e[0], e[1]
        return kind, a, b

    kind = getattr(port, "kind", getattr(port, "type", getattr(port, "port_kind", None)))

    a = getattr(port, "a", getattr(port, "v1", getattr(port, "va", None)))
    b = getattr(port, "b", getattr(port, "v2", getattr(port, "vb", None)))

    for k in ("verts", "vertices", "ends", "endpoints", "vs"):
        v = getattr(port, k, None)
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            a, b = v[0], v[1]
            break

    e = getattr(port, "edge", None)
    if isinstance(e, (list, tuple)) and len(e) >= 2:
        a, b = e[0], e[1]

    return kind, a, b


def player_ports(game, pid: int) -> set[str]:
    ports = set()
    plist = getattr(game, "ports", None)
    if not plist:
        return ports

    owned = _owned_vertices(game, pid)

    for p in plist:
        kind, a, b = _port_endpoints(p)
        if a is None or b is None:
            continue
        if a in owned or b in owned:
            k = str(kind).strip().lower() if kind is not None else ""
            # normalize generic port
            if k in ("3:1", "3", "generic", "any", "all", "none", "?"):
                ports.add("3:1")
            # resource port
            elif k in RES:
                ports.add(k)
            # sometimes stored like "2:1 wheat"
            elif "wheat" in k: ports.add("wheat")
            elif "wood" in k: ports.add("wood")
            elif "brick" in k: ports.add("brick")
            elif "sheep" in k: ports.add("sheep")
            elif "ore" in k: ports.add("ore")
            elif "3:1" in k:
                ports.add("3:1")

    return ports


def best_trade_rate(game, pid: int, give_res: str) -> int:
    give_res = str(give_res).strip().lower()
    ports = player_ports(game, pid)
    rate = 4
    if "3:1" in ports:
        rate = 3
    if give_res in ports:
        rate = 2
    return rate


def trade_with_bank(game, pid: int, give_res: str, get_res: str, get_qty: int = 1) -> int:
    _ensure_bank(game)

    give_res = str(give_res).strip().lower()
    get_res = str(get_res).strip().lower()
    get_qty = int(get_qty)

    if give_res == get_res:
        raise ValueError("Give and Get must be different.")
    if give_res not in RES or get_res not in RES:
        raise ValueError("Unknown resource.")
    if get_qty < 1:
        raise ValueError("get_qty must be >= 1")

    rate = best_trade_rate(game, pid, give_res)
    give_qty = rate * get_qty

    pres = _get_player_res(game, pid)

    if pres.get(give_res, 0) < give_qty:
        raise ValueError("Not enough resources in hand.")
    if game.bank.get(get_res, 0) < get_qty:
        raise ValueError("Bank doesn't have enough resources.")

    pres[give_res] -= give_qty
    pres[get_res] = pres.get(get_res, 0) + get_qty

    game.bank[give_res] = game.bank.get(give_res, 0) + give_qty
    game.bank[get_res] -= get_qty

    return rate


def _ensure_dev_deck(game):
    if not hasattr(game, "dev_deck") or not game.dev_deck:
        deck = (["knight"] * 14) + (["victory_point"] * 5) + (["road_building"] * 2) + (["year_of_plenty"] * 2) + (["monopoly"] * 2)
        random.shuffle(deck)
        game.dev_deck = deck


def _dev_list(game, pid: int):
    p = _get_player_obj(game, pid)
    # allow multiple field names
    if hasattr(p, "dev_cards"):
        if p.dev_cards is None: p.dev_cards = []
        return p.dev_cards
    if hasattr(p, "dev"):
        if p.dev is None: p.dev = []
        return p.dev
    if isinstance(p, dict):
        if "dev_cards" not in p or p["dev_cards"] is None:
            p["dev_cards"] = []
        return p["dev_cards"]
    setattr(p, "dev_cards", [])
    return p.dev_cards


def buy_dev(game, pid: int):
    pres = _get_player_res(game, pid)
    cost = {"sheep": 1, "wheat": 1, "ore": 1}
    for r, q in cost.items():
        if pres.get(r, 0) < q:
            raise ValueError("Not enough resources (need sheep+wheat+ore).")

    _ensure_bank(game)
    _ensure_dev_deck(game)

    for r, q in cost.items():
        pres[r] -= q
        game.bank[r] = game.bank.get(r, 0) + q

    card = game.dev_deck.pop()
    d = _dev_list(game, pid)
    d.append({"type": card, "new": True})

    # VP applies instantly
    if card == "victory_point":
        p = _get_player_obj(game, pid)
        if hasattr(p, "vp"):
            p.vp = int(getattr(p, "vp", 0)) + 1
        elif isinstance(p, dict):
            p["vp"] = int(p.get("vp", 0)) + 1

    return card


def play_dev(game, pid: int, card_type: str, **kwargs):
    card_type = str(card_type).strip().lower()
    d = _dev_list(game, pid)

    # prefer non-new
    idx = None
    for i, c in enumerate(list(d)):
        if isinstance(c, dict) and c.get("type") == card_type and not c.get("new", False):
            idx = i; break
    if idx is None:
        for i, c in enumerate(list(d)):
            if isinstance(c, dict) and c.get("type") == card_type:
                idx = i; break
    if idx is None:
        raise ValueError(f"No dev card '{card_type}'.")

    d.pop(idx)
    _ensure_bank(game)

    if card_type == "year_of_plenty":
        a = str(kwargs.get("a", "wood")).lower()
        b = str(kwargs.get("b", "brick")).lower()
        qa = int(kwargs.get("qa", 1))
        qb = int(kwargs.get("qb", 1))
        if a not in RES or b not in RES: raise ValueError("Unknown resource")
        if game.bank.get(a, 0) < qa or game.bank.get(b, 0) < qb: raise ValueError("Bank lacks resources")
        pres = _get_player_res(game, pid)
        game.bank[a] -= qa; pres[a] = pres.get(a, 0) + qa
        game.bank[b] -= qb; pres[b] = pres.get(b, 0) + qb
        return {"played": "year_of_plenty"}

    if card_type == "monopoly":
        r = str(kwargs.get("res", "wood")).lower()
        if r not in RES: raise ValueError("Unknown resource")
        pres = _get_player_res(game, pid)
        taken = 0
        for opid in range(len(game.players)):
            if opid == pid: continue
            ores = _get_player_res(game, opid)
            q = int(ores.get(r, 0))
            if q > 0:
                ores[r] -= q
                taken += q
        pres[r] = pres.get(r, 0) + taken
        return {"played": "monopoly", "taken": taken}

    # placeholders for next sprint wiring
    if card_type in ("knight", "road_building"):
        return {"played": card_type, "note": "Wired later"}

    if card_type == "victory_point":
        return {"played": "victory_point"}

    return {"played": card_type}


def ensure_game_api(game, override_ports: bool = True, override_trade: bool = True):
    """
    Attach missing methods directly to game instance (and optionally override port/trade logic).
    This guarantees UI works even if core didn't define these APIs.
    """
    if game is None:
        return

    if override_ports or not hasattr(game, "player_ports"):
        game.player_ports = types.MethodType(player_ports, game)
    if override_ports or not hasattr(game, "best_trade_rate"):
        game.best_trade_rate = types.MethodType(best_trade_rate, game)

    if override_trade or not hasattr(game, "trade_with_bank"):
        game.trade_with_bank = types.MethodType(trade_with_bank, game)

    if not hasattr(game, "buy_dev"):
        game.buy_dev = types.MethodType(buy_dev, game)
    if not hasattr(game, "play_dev"):
        game.play_dev = types.MethodType(play_dev, game)

    _ensure_bank(game)
    _ensure_dev_deck(game)