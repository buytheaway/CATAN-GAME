from __future__ import annotations

import random
import traceback
from collections import Counter
from copy import deepcopy
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.engine import rules as engine_rules
from app.engine.state import COST, RESOURCES


class ScenarioFailure(Exception):
    def __init__(self, message: str, kind: str = "assertion", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.kind = kind
        self.details = details or {}


class GameDriver:
    def __init__(self, seed: int):
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self.theft_rng = random.Random(self.seed ^ 0xCA7A)
        self.game = engine_rules.build_game(seed=self.seed, max_players=2, size=62.0)
        self.logs: List[str] = []
        self.steps: List[Dict[str, Any]] = []
        self.outcomes: List[Dict[str, Any]] = []
        self.on_step: Optional[Callable[["GameDriver", Dict[str, Any], Dict[str, Any]], None]] = None
        self.expected_totals = self._compute_resource_totals()
        self.initial_game = deepcopy(self.game)

    def _log(self, msg: str) -> None:
        self.logs.append(str(msg))

    def _compute_resource_totals(self) -> Dict[str, int]:
        totals = {r: int(self.game.bank.get(r, 0)) for r in RESOURCES}
        for p in self.game.players:
            for r, q in p.res.items():
                totals[r] += int(q)
        return totals

    def replace_game(self, game) -> None:
        self.game = game
        self.expected_totals = self._compute_resource_totals()
        self.initial_game = deepcopy(game)

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
                "owner": g.largest_army_owner,
                "size": g.largest_army_size,
            },
            "bank": dict(g.bank),
        }

    def fail(self, message: str, kind: str = "assertion", details: Optional[Dict[str, Any]] = None) -> None:
        raise ScenarioFailure(message, kind=kind, details=details)

    def do(self, action: Dict[str, Any]) -> Dict[str, Any]:
        result = self.apply_action(action)
        self.steps.append(deepcopy(action))
        if self.on_step:
            self.on_step(self, action, result)
        return result

    def _accepted(self, action: Dict[str, Any]) -> Dict[str, Any]:
        result = self.do(action)
        if not result.get("ok"):
            self.fail("fixture action rejected", kind="crash" if "exception" in result else "rule",
                      details={"action": action, "result": result})
        return result

    def reject(self, action: Dict[str, Any], *, error: Optional[str] = None,
               message: Optional[str] = None) -> Dict[str, Any]:
        """Record an intentional refusal and check its reason and full atomicity."""
        from tests.harness.invariants import check_invariants
        before = deepcopy(self.game)
        result = self.apply_action(action)
        self.steps.append(deepcopy(action))
        self.outcomes[-1]["expected_rejection"] = True
        if result.get("ok") or "exception" in result or (error is not None and result.get("error") != error) or (
                message is not None and result.get("message") != message):
            self.fail("unexpected rejection result", details={"action": action, "result": result,
                      "expected_error": error, "expected_message": message})
        if self.game != before:
            self.fail("rejected command mutated state", kind="invariant", details={"action": action})
        failures = check_invariants(self.game, self.expected_totals)
        if failures:
            self.fail("invariants failed after rejection", kind="invariant", details={"failures": failures})
        return result

    def resolve_pending(self) -> None:
        """Submit deterministic ordinary choices; never clear pending fields."""
        g = self.game
        for _ in range(100):
            if g.pending_action is None:
                return
            if g.pending_action == "discard":
                pid = next(p for p in sorted(g.discard_required) if p not in g.discard_submitted)
                need, cards = g.discard_required[pid], {}
                for resource in RESOURCES:
                    quantity = min(need, g.players[pid].res[resource])
                    if quantity:
                        cards[resource] = quantity
                        need -= quantity
                self._accepted({"type": "discard", "pid": pid, "discards": cards})
            elif g.pending_action == "choose_gold":
                pid = g.pending_pid
                resource = next((r for r in RESOURCES if g.bank[r] > 0), None)
                if resource is None:
                    self.fail("unresolvable Gold fixture", details={"pending_gold": dict(g.pending_gold)})
                self._accepted({"type": "choose_gold", "pid": pid, "res": resource,
                                "qty": min(g.pending_gold[pid], g.bank[resource])})
            elif g.pending_action == "robber_move":
                tile = next((i for i, t in enumerate(g.tiles)
                             if t.terrain != "sea" and i != g.robber_tile), None)
                if tile is None:
                    self.fail("no legal robber target in fixture")
                self._accepted({"type": "move_robber", "pid": g.pending_pid, "tile": tile})
            else:
                self.fail("unsupported pending fixture", details={"pending": g.pending_action})
        self.fail("pending choices did not terminate")

    def begin_turn(self, pid: Optional[int] = None, *, roll: Optional[int] = None) -> None:
        g = self.game
        pid = g.turn if pid is None else pid
        if g.phase != "main" or g.turn != pid or g.game_over:
            self.fail("fixture requires the current live main turn", details={"pid": pid, "turn": g.turn})
        self.resolve_pending()
        if not g.rolled:
            total = roll if roll is not None else self.rng.randint(1, 6) + self.rng.randint(1, 6)
            self._accepted({"type": "roll", "pid": pid, "roll": total})
            self.resolve_pending()

    def finish_turn(self) -> None:
        self.begin_turn()
        self._accepted({"type": "end_turn", "pid": self.game.turn})

    def advance_to(self, pid: int) -> None:
        if not 0 <= pid < len(self.game.players):
            self.fail("invalid fixture player", details={"pid": pid})
        for _ in self.game.players:
            if self.game.turn == pid:
                return
            self.finish_turn()
        self.fail("fixture turn did not advance", details={"pid": pid})

    def _harvest_roll(self, pid: int, needed: Dict[str, int]) -> int:
        """Choose a reproducible productive total using the executor on copies."""
        before = self.game.players[pid].res
        candidates = []
        for total in range(2, 13):
            if total == 7:
                continue
            probe = deepcopy(self.game)
            engine_rules.apply_cmd(probe, pid, {"type": "roll", "roll": total})
            gains = {r: probe.players[pid].res[r] - before[r] for r in RESOURCES}
            score = sum(q * (4 if before[r] < needed.get(r, 0) else 1) for r, q in gains.items())
            if probe.pending_action == "choose_gold" and probe.pending_gold.get(pid):
                score += probe.pending_gold[pid]
            candidates.append((score, -total))
        score, negative_total = max(candidates)
        # A Seven returns hoarded cards to the bank when ordinary production
        # has no available yield. Its real discards/figure choice are recorded.
        return -negative_total if score > 0 else 7

    def ensure_resources(self, pid: int, needed: Dict[str, int]) -> None:
        """Fund actual costs through production and accepted trades, without grants."""
        for _ in range(240):
            self.advance_to(pid)
            self.resolve_pending()
            if not self.game.rolled:
                self.begin_turn(pid, roll=self._harvest_roll(pid, needed))
            else:
                self.begin_turn(pid)
            g, hand = self.game, self.game.players[pid].res
            if all(hand[r] >= qty for r, qty in needed.items()):
                return
            traded = False
            for resource in RESOURCES:
                if hand[resource] >= needed.get(resource, 0):
                    continue
                for give in RESOURCES:
                    rate = engine_rules.best_trade_rate(g, pid, give)
                    if give != resource and g.bank[resource] and hand[give] - needed.get(give, 0) >= rate:
                        self._accepted({"type": "trade_bank", "pid": pid, "give": give,
                                        "get": resource, "get_qty": 1})
                        traded = True
                        break
                if traded:
                    break
                for other, player in enumerate(g.players):
                    if other == pid or not player.res[resource]:
                        continue
                    give = next((r for r in RESOURCES if r != resource
                                 and hand[r] > needed.get(r, 0)), None)
                    if give is not None:
                        self._accepted({"type": "trade_offer_create", "pid": pid,
                                        "give": {give: 1}, "get": {resource: 1}, "to_pid": other})
                        offer_id = g.trade_offers[-1].offer_id
                        self._accepted({"type": "trade_offer_accept", "pid": other, "offer_id": offer_id})
                        traded = True
                        break
                if traded:
                    break
            if not traded:
                self.finish_turn()
        self.fail("production-funded fixture exceeded its bound", details={"pid": pid, "needed": needed,
                  "hand": dict(self.game.players[pid].res), "bank": dict(self.game.bank)})

    def buy_dev_cards(self, pid: int, required: Dict[str, int]) -> None:
        while any(Counter(c["type"] for c in self.game.players[pid].dev_cards)[card] < qty
                  for card, qty in required.items()):
            if not self.game.dev_deck:
                self.fail("required cards unavailable in actual deck", details={"required": required})
            self.ensure_resources(pid, COST["dev"])
            self._accepted({"type": "buy_dev", "pid": pid})

    def legal_settlement_vertices(self, pid: int, require_road: bool) -> List[int]:
        out = []
        for vid in self.game.vertices.keys():
            if engine_rules.can_place_settlement(self.game, pid, vid, require_road=require_road):
                out.append(vid)
        return out

    def legal_city_vertices(self, pid: int) -> List[int]:
        out = []
        for vid in self.game.vertices.keys():
            if engine_rules.can_upgrade_city(self.game, pid, vid):
                out.append(vid)
        return out

    def legal_road_edges(self, pid: int, must_touch_vid: Optional[int] = None) -> List[Tuple[int, int]]:
        out = []
        for e in self.game.edges:
            if engine_rules.can_place_road(self.game, pid, e, must_touch_vid=must_touch_vid):
                out.append(e)
        return out

    def apply_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        g = self.game
        try:
            pid = int(action.get("pid", g.turn))
            _, events = engine_rules.apply_cmd(g, pid, action, theft_rng=self.theft_rng)
            result: Dict[str, Any] = {"ok": True}
            for ev in events:
                if ev.get("type") == "trade_bank":
                    result["rate"] = ev.get("rate")
                if ev.get("type") == "buy_dev":
                    result["card"] = ev.get("card")
                if ev.get("type") == "play_dev":
                    result["result"] = ev.get("result")
                if ev.get("type") == "roll" and ev.get("pending"):
                    result["pending"] = ev.get("pending")
            self.outcomes.append({"action": deepcopy(action), "result": deepcopy(result)})
            return result
        except engine_rules.RuleError as exc:
            result = {
                "ok": False,
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
            self.outcomes.append({"action": deepcopy(action), "result": deepcopy(result)})
            return result
        except Exception as exc:
            result = {
                "ok": False,
                "error": str(exc),
                "exception": traceback.format_exc(),
            }
            self.outcomes.append({"action": deepcopy(action), "result": deepcopy(result)})
            return result
