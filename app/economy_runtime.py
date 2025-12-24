from __future__ import annotations
import random

RES_LIST = ["wood","brick","sheep","wheat","ore"]

DEV_DECK_COUNTS = {
    "knight": 14,
    "vp": 5,
    "road_building": 2,
    "year_of_plenty": 2,
    "monopoly": 2,
}

def _get_player_obj(game, pid: int):
    if hasattr(game, "players"):
        return game.players[pid]
    raise RuntimeError("Game has no .players")

def get_player_res(game, pid: int) -> dict:
    p = _get_player_obj(game, pid)
    if hasattr(p, "res") and isinstance(p.res, dict):
        return p.res
    if isinstance(p, dict) and isinstance(p.get("res"), dict):
        return p["res"]
    # last resort: create dict view
    out = {}
    for r in RES_LIST:
        out[r] = int(getattr(p, r, 0)) if hasattr(p, r) else 0
    # try to store back if possible
    try:
        if hasattr(p, "res"):
            p.res = out
        elif isinstance(p, dict):
            p["res"] = out
    except Exception:
        pass
    return out

def get_player_vp(game, pid: int) -> int:
    p = _get_player_obj(game, pid)
    if hasattr(p, "vp"):
        return int(p.vp)
    if isinstance(p, dict) and "vp" in p:
        return int(p["vp"])
    return 0

def set_player_vp(game, pid: int, vp: int) -> None:
    p = _get_player_obj(game, pid)
    if hasattr(p, "vp"):
        p.vp = int(vp); return
    if isinstance(p, dict):
        p["vp"] = int(vp); return
    raise RuntimeError("Cannot set VP on player")

def ensure_bank(game) -> dict:
    bank = getattr(game, "bank", None)
    if bank is None or not isinstance(bank, dict):
        bank = {r: 19 for r in RES_LIST}
        setattr(game, "bank", bank)
    for r in RES_LIST:
        bank.setdefault(r, 19)
    return bank

def best_trade_rate(game, pid: int, give_res: str) -> int:
    # ports позже; сейчас фикс 4:1
    return 4

def trade_with_bank(game, pid: int, give_res: str, get_res: str, get_qty: int = 1) -> int:
    if give_res == get_res:
        raise ValueError("give/get must differ")
    if give_res not in RES_LIST or get_res not in RES_LIST:
        raise ValueError("unknown resource")
    if get_qty < 1:
        raise ValueError("qty must be >= 1")

    bank = ensure_bank(game)
    pres = get_player_res(game, pid)

    rate = best_trade_rate(game, pid, give_res)
    give_qty = rate * int(get_qty)

    if pres.get(give_res, 0) < give_qty:
        raise ValueError("Not enough resources in hand")
    if bank.get(get_res, 0) < int(get_qty):
        raise ValueError("Bank not enough resource")

    pres[give_res] -= give_qty
    pres[get_res] = pres.get(get_res, 0) + int(get_qty)

    bank[give_res] = bank.get(give_res, 0) + give_qty
    bank[get_res] -= int(get_qty)

    return rate

def ensure_dev_deck(game) -> list:
    deck = getattr(game, "dev_deck", None)
    if isinstance(deck, list) and len(deck) > 0:
        return deck

    deck = []
    for k, n in DEV_DECK_COUNTS.items():
        deck += [k] * int(n)

    rng = getattr(game, "rng", None)
    if isinstance(rng, random.Random):
        rng.shuffle(deck)
    else:
        random.shuffle(deck)

    setattr(game, "dev_deck", deck)
    return deck

def get_dev_hand(game, pid: int) -> list:
    p = _get_player_obj(game, pid)
    if hasattr(p, "dev") and isinstance(p.dev, list):
        return p.dev
    if isinstance(p, dict) and isinstance(p.get("dev"), list):
        return p["dev"]

    hand = []
    try:
        if hasattr(p, "dev"):
            p.dev = hand
        elif isinstance(p, dict):
            p["dev"] = hand
    except Exception:
        pass
    return hand

def buy_dev_card(game, pid: int) -> str:
    pres = get_player_res(game, pid)
    bank = ensure_bank(game)
    deck = ensure_dev_deck(game)

    cost = {"sheep": 1, "wheat": 1, "ore": 1}
    for r, n in cost.items():
        if pres.get(r, 0) < n:
            raise ValueError("Not enough resources to buy dev card")

    if len(deck) == 0:
        raise ValueError("Dev deck is empty")

    for r, n in cost.items():
        pres[r] -= n
        bank[r] += n

    card = deck.pop()
    get_dev_hand(game, pid).append(card)
    return card

def play_dev_card(game, pid: int, card: str, *, choose: list[str] | None = None) -> str:
    hand = get_dev_hand(game, pid)
    if card not in hand:
        raise ValueError("You don't have this dev card")

    # consume card
    hand.remove(card)

    if card == "vp":
        vp = get_player_vp(game, pid)
        set_player_vp(game, pid, vp + 1)
        return "VP +1"

    if card == "year_of_plenty":
        if not choose or len(choose) != 2 or any(c not in RES_LIST for c in choose):
            raise ValueError("Choose exactly 2 resources")
        bank = ensure_bank(game)
        pres = get_player_res(game, pid)
        for r in choose:
            if bank.get(r, 0) <= 0:
                raise ValueError(f"Bank has no {r}")
        for r in choose:
            bank[r] -= 1
            pres[r] = pres.get(r, 0) + 1
        return f"Year of Plenty: +{choose[0]}, +{choose[1]}"

    # остальное расширим позже
    return f"Played: {card} (effect TBD)"

def ensure_economy_api(game) -> None:
    # inject methods on instance so UI can call game.trade_with_bank / game.buy_dev_card / etc
    if not hasattr(game, "trade_with_bank"):
        game.trade_with_bank = lambda pid, give, get, qty=1: trade_with_bank(game, pid, give, get, qty)
    if not hasattr(game, "best_trade_rate"):
        game.best_trade_rate = lambda pid, give: best_trade_rate(game, pid, give)
    if not hasattr(game, "buy_dev_card"):
        game.buy_dev_card = lambda pid: buy_dev_card(game, pid)
    if not hasattr(game, "play_dev_card"):
        game.play_dev_card = lambda pid, card, **kw: play_dev_card(game, pid, card, **kw)
    if not hasattr(game, "ensure_bank"):
        game.ensure_bank = lambda: ensure_bank(game)
    if not hasattr(game, "ensure_dev_deck"):
        game.ensure_dev_deck = lambda: ensure_dev_deck(game)