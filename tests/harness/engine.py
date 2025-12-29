from __future__ import annotations

import random
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

from app import ui_v6
from app.runtime_patch import ensure_game_api


class ScenarioFailure(Exception):
    def __init__(self, message: str, kind: str = "assertion", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.kind = kind
        self.details = details or {}


class GameDriver:
    def __init__(self, seed: int):
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.game = ui_v6.build_board(seed=self.seed, size=62.0)
        self.logs: List[str] = []
        self.steps: List[Dict[str, Any]] = []
        self.on_step: Optional[Callable[["GameDriver", Dict[str, Any], Dict[str, Any]], None]] = None
        self.expected_totals = self._compute_resource_totals()

    def _log(self, msg: str) -> None:
        self.logs.append(str(msg))

    def _compute_resource_totals(self) -> Dict[str, int]:
        totals = {r: int(self.game.bank.get(r, 0)) for r in ui_v6.RESOURCES}
        for p in self.game.players:
            for r, q in p.res.items():
                totals[r] += int(q)
        return totals

    def replace_game(self, game) -> None:
        self.game = game
        self.expected_totals = self._compute_resource_totals()

    def snapshot(self) -> Dict[str, Any]:
        g = self.game
        return {
            "seed": g.seed,
            "phase": g.phase,
            "turn": g.turn,
            "vp": [p.vp for p in g.players],
            "longest_road": {
                "owner": g.longest_road_owner,
                "len": g.longest_road_len,
            },
            "largest_army": {
                "owner": g.largest_army_pid,
                "size": g.largest_army_size,
            },
            "bank": dict(g.bank),
        }

    def fail(self, message: str, kind: str = "assertion", details: Optional[Dict[str, Any]] = None) -> None:
        raise ScenarioFailure(message, kind=kind, details=details)

    def do(self, action: Dict[str, Any]) -> Dict[str, Any]:
        result = self.apply_action(action)
        self.steps.append(dict(action))
        if self.on_step:
            self.on_step(self, action, result)
        return result

    def legal_settlement_vertices(self, pid: int, require_road: bool) -> List[int]:
        out = []
        for vid in self.game.vertices.keys():
            if ui_v6.can_place_settlement(self.game, pid, vid, require_road=require_road):
                out.append(vid)
        return out

    def legal_city_vertices(self, pid: int) -> List[int]:
        out = []
        for vid in self.game.vertices.keys():
            if ui_v6.can_upgrade_city(self.game, pid, vid):
                out.append(vid)
        return out

    def legal_road_edges(self, pid: int, must_touch_vid: Optional[int] = None) -> List[Tuple[int, int]]:
        out = []
        for e in self.game.edges:
            if ui_v6.can_place_road(self.game, pid, e, must_touch_vid=must_touch_vid):
                out.append(e)
        return out

    def _hand_size(self, pid: int) -> int:
        return sum(int(v) for v in self.game.players[pid].res.values())

    def _discard_needed(self, pid: int) -> int:
        total = self._hand_size(pid)
        return total // 2 if total > 7 else 0

    def _discard_random(self, pid: int, need: int) -> Dict[str, int]:
        pres = self.game.players[pid].res
        bag = []
        for r, c in pres.items():
            bag += [r] * int(c)
        self.rng.shuffle(bag)
        discard: Dict[str, int] = {r: 0 for r in ui_v6.RESOURCES}
        for _ in range(min(need, len(bag))):
            r = bag.pop()
            discard[r] += 1
        return discard

    def _apply_discard(self, pid: int, discard: Dict[str, int]) -> None:
        pres = self.game.players[pid].res
        for r, n in discard.items():
            q = min(int(n), int(pres.get(r, 0)))
            if q <= 0:
                continue
            pres[r] -= q
            self.game.bank[r] += q

    def _victims_for_tile(self, ti: int, pid: int) -> List[int]:
        g = self.game
        victims = set()
        for vid, (owner, _level) in g.occupied_v.items():
            if owner == pid:
                continue
            if ti in g.vertex_adj_hexes.get(vid, []):
                if self._hand_size(owner) > 0:
                    victims.add(owner)
        return sorted(victims)

    def _steal_random(self, pid: int, target_pid: int) -> Optional[str]:
        pres = self.game.players[target_pid].res
        bag = []
        for r, c in pres.items():
            bag += [r] * int(c)
        if not bag:
            return None
        r = self.rng.choice(bag)
        pres[r] -= 1
        self.game.players[pid].res[r] += 1
        return r

    def _grant_resources(self, pid: int, res: Dict[str, int]) -> None:
        for r, n in res.items():
            if n <= 0:
                continue
            if self.game.bank.get(r, 0) < n:
                raise ValueError(f"Bank lacks {r} for grant: need {n}")
            self.game.bank[r] -= n
            self.game.players[pid].res[r] += n

    def apply_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        g = self.game
        try:
            atype = str(action.get("type", "")).strip().lower()
            pid = int(action.get("pid", g.turn))

            if atype == "grant_resources":
                res = action.get("res", {})
                self._grant_resources(pid, res)
                return {"ok": True}

            if g.game_over and atype not in ("noop",):
                return {"ok": False, "error": "game_over"}

            if atype == "place_settlement":
                vid = int(action["vid"])
                setup = bool(action.get("setup", False)) or g.phase == "setup"
                if setup:
                    if g.setup_need != "settlement":
                        return {"ok": False, "error": "setup_need_not_settlement"}
                    if not ui_v6.can_place_settlement(g, pid, vid, require_road=False):
                        return {"ok": False, "error": "illegal_settlement"}
                    g.occupied_v[vid] = (pid, 1)
                    g.players[pid].vp += 1
                    ui_v6.update_longest_road(g, self._log)
                    ui_v6.check_win(g, self._log)
                    g.setup_need = "road"
                    g.setup_anchor_vid = vid
                    return {"ok": True}

                # main phase
                if g.turn != pid or g.phase != "main":
                    return {"ok": False, "error": "not_your_turn"}
                if not ui_v6.can_place_settlement(g, pid, vid, require_road=True):
                    return {"ok": False, "error": "illegal_settlement"}
                if not ui_v6.can_pay(g.players[pid], ui_v6.COST["settlement"]):
                    return {"ok": False, "error": "insufficient_resources"}
                ui_v6.pay_to_bank(g, pid, ui_v6.COST["settlement"])
                g.occupied_v[vid] = (pid, 1)
                g.players[pid].vp += 1
                ui_v6.update_longest_road(g, self._log)
                ui_v6.check_win(g, self._log)
                return {"ok": True}

            if atype == "place_city":
                vid = int(action["vid"])
                if g.turn != pid or g.phase != "main":
                    return {"ok": False, "error": "not_your_turn"}
                if not ui_v6.can_upgrade_city(g, pid, vid):
                    return {"ok": False, "error": "illegal_city"}
                if not ui_v6.can_pay(g.players[pid], ui_v6.COST["city"]):
                    return {"ok": False, "error": "insufficient_resources"}
                ui_v6.pay_to_bank(g, pid, ui_v6.COST["city"])
                g.occupied_v[vid] = (pid, 2)
                g.players[pid].vp += 1
                ui_v6.update_longest_road(g, self._log)
                ui_v6.check_win(g, self._log)
                return {"ok": True}

            if atype == "place_road":
                raw_e = action["eid"]
                e = tuple(raw_e) if not isinstance(raw_e, tuple) else raw_e
                if len(e) != 2:
                    return {"ok": False, "error": "bad_edge"}
                a, b = e
                e = (a, b) if a < b else (b, a)
                setup = bool(action.get("setup", False)) or g.phase == "setup"
                if setup:
                    if g.setup_need != "road":
                        return {"ok": False, "error": "setup_need_not_road"}
                    if not ui_v6.can_place_road(g, pid, e, must_touch_vid=g.setup_anchor_vid):
                        return {"ok": False, "error": "illegal_road"}
                    g.occupied_e[e] = pid
                    ui_v6.update_longest_road(g, self._log)
                    ui_v6.check_win(g, self._log)
                    g.setup_need = "settlement"
                    g.setup_anchor_vid = None
                    g.setup_idx += 1
                    if g.setup_idx >= len(g.setup_order):
                        g.phase = "main"
                    return {"ok": True}

                if g.turn != pid or g.phase != "main":
                    return {"ok": False, "error": "not_your_turn"}
                if not ui_v6.can_place_road(g, pid, e):
                    return {"ok": False, "error": "illegal_road"}
                if not ui_v6.can_pay(g.players[pid], ui_v6.COST["road"]):
                    return {"ok": False, "error": "insufficient_resources"}
                ui_v6.pay_to_bank(g, pid, ui_v6.COST["road"])
                g.occupied_e[e] = pid
                ui_v6.update_longest_road(g, self._log)
                ui_v6.check_win(g, self._log)
                return {"ok": True}

            if atype == "roll":
                roll = int(action["roll"])
                if g.phase != "main":
                    return {"ok": False, "error": "not_main_phase"}
                if g.turn != pid:
                    return {"ok": False, "error": "not_your_turn"}
                if g.rolled:
                    return {"ok": False, "error": "already_rolled"}
                g.last_roll = roll
                g.rolled = True
                g.roll_history.append(roll)
                if roll == 7:
                    for opid in range(len(g.players)):
                        need = self._discard_needed(opid)
                        if need > 0:
                            discard = self._discard_random(opid, need)
                            self._apply_discard(opid, discard)
                    g.pending_action = "robber_move"
                    g.pending_pid = pid
                    g.pending_victims = []
                    return {"ok": True, "pending": "robber_move"}
                ui_v6.distribute_for_roll(g, roll, self._log)
                return {"ok": True}

            if atype == "move_robber":
                tile = int(action["tile"])
                victim = action.get("victim", None)
                if g.pending_action not in (None, "robber_move"):
                    return {"ok": False, "error": "invalid_pending_state"}
                if tile == g.robber_tile:
                    return {"ok": False, "error": "same_tile"}
                g.robber_tile = tile
                victims = self._victims_for_tile(tile, pid)
                if victim is not None:
                    victim = int(victim)
                    if victim not in victims:
                        return {"ok": False, "error": "invalid_victim"}
                if victims and victim is not None:
                    stolen = self._steal_random(pid, victim)
                    g.pending_action = None
                    g.pending_pid = None
                    g.pending_victims = []
                    return {"ok": True, "stolen": stolen}
                g.pending_action = None
                g.pending_pid = None
                g.pending_victims = []
                return {"ok": True}

            if atype == "trade_bank":
                ensure_game_api(g, override_ports=True, override_trade=True)
                rate = g.trade_with_bank(pid, action["give"], action["get"], int(action.get("get_qty", 1)))
                return {"ok": True, "rate": rate}

            if atype == "buy_dev":
                card = g.buy_dev(pid)
                return {"ok": True, "card": card}

            if atype == "play_dev":
                card = action.get("card")
                out = g.play_dev(pid, card, **{k: v for k, v in action.items() if k not in ("type", "pid", "card")})
                return {"ok": True, "result": out}

            if atype == "end_turn":
                if g.turn != pid:
                    return {"ok": False, "error": "not_your_turn"}
                if g.pending_action is not None:
                    return {"ok": False, "error": "pending_action"}
                g.end_turn_cleanup(pid)
                g.turn = 1 - pid
                g.rolled = False
                g.last_roll = None
                return {"ok": True}

            return {"ok": False, "error": f"unknown_action:{atype}"}
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "exception": traceback.format_exc(),
            }
