"""Named development-only actions. Validate on a copy before committing.

The caller must enforce server flag, explicit test room and active host ownership.
Nothing here is a general state editor or code execution interface.
"""
from copy import deepcopy

from app.engine.rules import RuleError, apply_cmd, check_win, end_turn_cleanup
from app.engine.state import DEV_TYPES, RESOURCES


def integer(value, label, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise RuleError("invalid", f"{label} must be {minimum}..{maximum}")
    return value


def execute(room, cmd):
    action = cmd.get("action")
    shapes = {
        "give_resources": {"player", "resource", "amount"},
        "remove_resources": {"player", "resource", "amount"},
        "give_dev": {"player", "card"}, "set_next_dice": {"dice"},
        "force_turn": {"player"}, "set_vp": {"player", "vp"}, "trigger_seven": set(),
    }
    if not isinstance(action, str) or action not in shapes or set(cmd) != {"type", "action", *shapes[action]}:
        raise RuleError("invalid", "Unknown test action or fields")
    g = deepcopy(room.game)
    if g.game_over or g.phase != "main":
        raise RuleError("illegal", "Test actions require an active main-phase match")
    if g.pending_action and action != "set_next_dice":
        raise RuleError("illegal", "Resolve mandatory choice before changing test state")
    pid = integer(cmd.get("player"), "player", 0, len(g.players) - 1) if "player" in cmd else g.turn
    p = g.players[pid]
    dice = None
    events = []
    if action in ("give_resources", "remove_resources"):
        r = cmd["resource"]
        if r not in RESOURCES:
            raise RuleError("invalid", "Unknown resource")
        qty = integer(cmd["amount"], "amount", 1, 100)
        if (g.bank[r] if action == "give_resources" else p.res[r]) < qty:
            raise RuleError("illegal", "Not enough cards in source")
        sign = 1 if action == "give_resources" else -1
        p.res[r] += sign * qty
        g.bank[r] -= sign * qty
    elif action == "give_dev":
        card = cmd["card"]
        if card not in DEV_TYPES or card not in g.dev_deck:
            raise RuleError("invalid", "Requested card is unavailable")
        g.dev_deck.remove(card)
        p.dev_cards.append({"type": card, "new": False})
        if card == "victory_point":
            p.vp += 1
            check_win(g)
    elif action == "set_next_dice":
        pair = cmd["dice"]
        if not isinstance(pair, list) or len(pair) != 2:
            raise RuleError("invalid", "dice must contain two faces")
        dice = tuple(integer(v, "face", 1, 6) for v in pair)
    elif action == "force_turn":
        if g.pending_action:
            raise RuleError("illegal", "Resolve mandatory choice before changing turn")
        end_turn_cleanup(g, g.turn)
        for offer in g.trade_offers:
            if offer.status == "active":
                offer.status = "canceled"
        g.turn, g.rolled, g.last_roll = pid, False, None
    elif action == "set_vp":
        value = integer(cmd["vp"], "vp", 0, 30)
        hidden = sum(c["type"] == "victory_point" for c in p.dev_cards)
        if value < hidden:
            raise RuleError("invalid", "Total VP cannot be below held VP cards")
        p.vp = value
        check_win(g)
    elif action == "trigger_seven":
        if g.rolled or g.pending_action:
            raise RuleError("illegal", "Use an unrolled turn without a mandatory choice")
        _, events = apply_cmd(g, g.turn, {"type": "roll", "roll": 7})
        dice = (6, 1)
    # All validations succeeded. Commit exactly once; no rejected action mutates Room.
    room.game = g
    if action == "set_next_dice":
        room.next_test_dice = dice
    elif action == "trigger_seven":
        room.dice, room.roll_count = dice, room.roll_count + 1
    if action == "force_turn":
        room.timer = None
    return action, pid, events
